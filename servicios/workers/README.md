# Workers

Cada manejador del flujo corre como un Container Apps Job que vacía su cola de Service Bus y termina (`specs/005-orquestador/tasks-workers.md`). Aquí está lo que necesita cada job. La definición de los jobs (Bicep), sus roles y sus secretos van en el repositorio de infraestructura de Azure DevOps, no en este, que es público.

## Imágenes

| Imagen | Dockerfile | Comandos |
|---|---|---|
| Liviana | `servicios/workers/Dockerfile` | `orquestar-worker apertura`, `orquestar-worker clasificar`, `extraer-worker`, `orquestar-operar …` |
| Con LibreOffice | `servicios/normalizacion/Dockerfile`, etapa `worker` | `orquestar-worker normalizar` (su `ENTRYPOINT`) |

```bash
# Desde la raíz del repositorio
docker build -f servicios/workers/Dockerfile -t workers .
docker build -f servicios/normalizacion/Dockerfile --target worker -t worker-normalizar .
```

Sin `--target`, `servicios/normalizacion/Dockerfile` sigue dando el job `normalizar` de antes.

En Azure, las imágenes se fijan por digest (`…@sha256:…`), no por etiqueta: un proceso abierto fija las versiones del normalizador y del modelo, y una imagen que cambia debajo de él da `VersionNoCoincide` o una ficha de otra versión.

## Configuración de cada job

| Job | Comando | Disparo | Ejecuciones a la vez | Variables | Secretos (Key Vault) |
|---|---|---|---|---|---|
| apertura | `orquestar-worker apertura` | cola `procesos-listos` | 1 | comunes + OneLake | `ESTADO_MONGO_URL` |
| normalizar | `orquestar-worker normalizar` | cola `normalizar` | 2 (`paralelo_normalizar`) | comunes + OneLake | `ESTADO_MONGO_URL` |
| clasificar | `orquestar-worker clasificar` | cola `clasificar` | 1 | comunes + `CLASIFICADOR=falso`, `CLASIFICADOR_CSV` | `ESTADO_MONGO_URL` |
| extraer | `extraer-worker --hilos 3` | cola `extraer` | **1**: el tope de 3 llamadas al LLM vale para todo el proceso solo si no hay otra ejecución, tampoco una manual ni la de un despliegue | `SERVICEBUS_NAMESPACE`, `ALMACEN_BLOB_CUENTA`, `EXTRACCION_MODELO` (`mcp`), `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `MCP_URL` | `AZURE_OPENAI_API_KEY`, `MCP_API_KEY` |
| escalar-fallas | `orquestar-operar escalar-fallas` | horario, cada hora | 1 | `ESTADO_MONGO_URL` | `ESTADO_MONGO_URL` |
| reenviar-errores | `orquestar-operar reenviar-errores <cola>` | manual, lo corre operación | 1 | `SERVICEBUS_NAMESPACE` | — |

**Variables comunes:** `SERVICEBUS_NAMESPACE` (el nombre completo del namespace), `ESTADO_MONGO_URL`, `ALMACEN_BLOB_CUENTA` (solo el nombre de la cuenta), `AZURE_CLIENT_ID` (la identidad administrada asignada por el usuario). Opcionales: `COLAS_PREFIJO` (por defecto `evaluacion-ofertas-`), `ESTADO_MONGO_BASE`, `ESTADO_MONGO_COLECCION`, `ALMACEN_BLOB_CONTENEDOR` (por defecto `evaluacion-ofertas`). **OneLake:** `ONELAKE_WORKSPACE` y `ONELAKE_LAKEHOUSE`. `apertura` los usa cuando el aviso no trae la lista de archivos.

Si falta una variable obligatoria, el worker sale con código 2 sin tocar la cola, y nombra las variables, nunca sus valores. No cae a las versiones locales ni lee un `.env`. `normalizar` también sale con 2 si no encuentra LibreOffice, y `clasificar` si el CSV no es válido.

Los workers del orquestador corren un mensaje a la vez; la concurrencia de `normalizar` la dan las ejecuciones del job.

**Para todos los jobs:**

- **Tiempo máximo de la réplica (`replicaTimeout`): 1800 s.** El worker deja de tomar mensajes a los 1500 s (`--tomar-mensajes-s`) para terminar el último a tiempo. La reserva de una entrega en `normalizar` dura 2400 s, más que el job, a propósito.
- **Reintentos de la réplica (`replicaRetryLimit`): 0.** Los reintentos de cada mensaje los lleva Service Bus con el bucle del worker; repetir la réplica entera no agrega nada.
- **Disparo por cola:** escalador de Service Bus con la misma identidad, `messageCount: 1` y `activationMessageCount: 0`, para que un reintento programado que se vuelve visible lance una ejecución nueva. Sondeo cada 30 s (el valor por defecto).
- **Códigos de salida:** 0 si la cola se vació, aunque algún mensaje haya ido a errores (ya se alertó); 2 si la configuración es inválida; 1 si una falla de la cola o del entorno cortó la ejecución. Una ejecución que sale con 1 o 2 se alerta.
- **Apagado:** con `SIGTERM`, el worker deja de tomar mensajes y termina el actual. Si Azure corta antes, ese mensaje no se completó y Service Bus lo vuelve a entregar.

## Roles de la identidad del job

Los asigna quien tenga Owner o User Access Administrator (`pendientes-azure.md`, sección 4).

| Job | Service Bus | Blob (`Storage Blob Data Contributor`, solo el contenedor) | OneLake | Key Vault (`Key Vault Secrets User`, por secreto) |
|---|---|---|---|---|
| apertura | Receiver y Sender en `procesos-listos` (reintentos), Sender en `normalizar` | sí | lectura | `ESTADO_MONGO_URL` |
| normalizar | Receiver en `normalizar`, Sender en `normalizar` (reintentos) y `clasificar` | sí | lectura | `ESTADO_MONGO_URL` |
| clasificar | Receiver en `clasificar`, Sender en `clasificar` y `extraer` | sí (lee el CSV y las lecturas) | — | `ESTADO_MONGO_URL` |
| extraer | Receiver en `extraer`, Sender en `extraer` y `resultados` | sí | — | `AZURE_OPENAI_API_KEY`, `MCP_API_KEY` |
| escalar-fallas | — | — | — | `ESTADO_MONGO_URL` |
| reenviar-errores | Receiver y Sender en la cola que se reenvía | — | — | — |

Cada worker publica sus reintentos en su propia cola, por eso necesita también Sender en ella. El escalador del job necesita leer la cuenta de mensajes de la cola que lo dispara. El registro de imágenes necesita `AcrPull`.

## Alertas

Con los registros en Log Analytics (solo identificadores, principio 6):

- un mensaje en cualquier cola de errores (registro `mensajeria.alertas`, nivel ERROR);
- el mensaje más viejo de una cola por encima de un umbral;
- muchos 429 seguidos en `extraer` (`Falla transitoria` o `El servicio pidió esperar` en `mensajeria.bucle`);
- un bloqueo perdido (`Bloqueo perdido` en `mensajeria.bucle`);
- una ejecución que sale con 1 o 2 (`mensajeria.worker`, nivel ERROR).

## `resultados`, mientras no tenga consumidor

El manejador de `resultados` es de la entrega 2 del orquestador y todavía no existe. Mientras tanto los sobres se acumulan en la cola `resultados` y, a los 14 días, pasan a su cola de errores. Para probar en desarrollo se leen con *peek* desde el portal o con el SDK. Los `ok`, `no_corresponde` y `error_entrada` también quedan guardados en el almacén, en `extraccion/<id_proceso>/<entrega>/`, así que no se pierden. Los `error_proceso` no se guardan: van solo en el sobre. Antes de procesar documentos reales hace falta ese consumidor.
