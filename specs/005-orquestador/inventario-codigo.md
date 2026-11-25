# Inventario del código: lo que hay y lo que falta

Estado al 2026-11-25, revisando `main` y la rama `almacen-blob`. Tareas: `tasks-estado-cola-azure.md` (`Estado` y `Cola`) y `tasks-almacen-blob.md` (`Almacen`). Las decisiones de Azure (colas con prefijo `evaluacion-ofertas-`, estado en Mongo con `pymongo`, workers como Container Apps Jobs) están en la rama `infra-azure-inicial` (`pendientes-azure.md`), que todavía no está en `main`.

## Lo que hay

| Pieza | Dónde | Estado |
|---|---|---|
| Normalización y lectura | `servicios/normalizacion/` (0.2.0) | Cerrada. Tiene `Dockerfile` |
| Orquestador, entrega 1: aviso, apertura, normalizar, clasificar y pedir extracción | `servicios/orquestador/` (0.1.0) | Cerrada, en local |
| Entrada desde OneLake: `OrigenOneLake`, aviso 0.2 armado con las tablas del módulo 1 y descarga en paralelo | `origen_onelake.py`, `entrada_modulo1.py` | Primera versión cerrada; corrió con un evento real |
| Bucle de mensajes: reintentos, 429, clases de error y cola de errores | `errores.py` (`procesar_uno`) | Hecho, sobre la interfaz `Cola` |
| Interfaces `Cola`, `Estado` y `Almacen` | `cola.py`, `estado.py`, `normalizacion/almacen.py` | Tienen versiones en memoria o en disco local y sus versiones de Azure: `ColaServiceBus`, `EstadoMongo` y `AlmacenBlob` (abajo) |
| `Estado` en Cosmos (API de MongoDB) | `estado_mongo.py` | Hecho y probado contra la base de desarrollo (`tasks-estado-cola-azure.md`, T01 a T03) |
| `Cola` en Service Bus | `cola_servicebus.py` | Hecha con un cliente falso, con renovación del bloqueo y reenvío seguro. Falta correrla contra las colas reales (T07), que espera los roles de datos |
| Clasificador | `clasificador.py` | Solo el falso. El real es de otro equipo |
| Extracción | `servicios/extraccion/` (0.1.0) | Construida: corre en local, con LLM falso o gpt-5.4 y ficha de archivo o del MCP. Lee las solicitudes de un archivo, no de una cola |
| Tareas humanas y escalamiento | `tareas.py` (`crear_tarea`, `escalar_fallas`) | Se crean en el estado. `escalar_fallas` y `reenviar_errores` (ahora de la cola) existen, pero nada los llama |

## Lo que falta

### 1. Versiones de Azure de las interfaces

Cada una con las mismas pruebas que su versión en memoria o en disco local.

- [x] **`Estado` en Mongo** (`pymongo`), en `estado_mongo.py`. `reemplazar` hace el cambio condicional con un filtro por `version`. Va con `id_proceso` en cada filtro, porque es la clave de partición. Se entra con la cadena de conexión, desde una variable de entorno o desde Key Vault. **Se puede ya:** no espera roles.
- [x] **`Cola` en Service Bus** (`azure-servicebus`, `DefaultAzureCredential`), en `cola_servicebus.py`, con la renovación del bloqueo. Falta solo correrla contra Azure (T07). Los nombres de `cola.py` no cambian: la versión de Service Bus les antepone el prefijo `evaluacion-ofertas-`, que es configuración. Hay que agregar `resultados`. Las propiedades `intento` y `esperas` van como application properties, y la demora como `scheduled_enqueue_time`. Falta la renovación del bloqueo, que hoy no existe porque en memoria no hay bloqueo que venza. Se escribe ya; probarlo contra Azure espera los roles.
- [x] **`Almacen` en Blob** (`AlmacenBlob`, extra `azure` de la normalización). Pasó las pruebas con un contenedor falso, incluida una corrida con lectura desde la extracción. Falta correr la batería contra el contenedor de desarrollo (T04), a la espera del rol. Ver el [README de la normalización](../../servicios/normalizacion/README.md#almacén-en-blob-storage).
- [x] Repetir contra Mongo las pruebas de mensajes repetidos y de cambio condicional (T03).
- [ ] Decidir si dos trabajadores pueden normalizar la misma entrega a la vez con Blob, o si hace falta un lease por entrega.

### 2. Workers que corren en Azure

- [ ] **Un comando por worker**: toma mensajes de su cola hasta vaciarla y termina (Container Apps Jobs). Arma las versiones de Azure con la configuración del entorno. Hoy solo existe `orquestar`, que corre todo junto en memoria.
- [ ] **La extracción como worker:** que lea de la cola `extraer` en vez de un archivo y publique en `resultados`. Hoy guarda sus resultados en un almacén propio (`resultados.py`).
- [ ] **Imagen liviana** para los manejadores que no necesitan LibreOffice (la de normalización ya existe).
- [ ] **Tareas programadas:** `escalar_fallas` (24 horas) necesita algo que la corra cada cierto tiempo, por ejemplo un job con horario. `reenviar_errores` necesita un comando para operación.
- [ ] **gpt-5.4 con identidad** (`Cognitive Services OpenAI User`) en vez de la clave, si se decide así. Cambia `llm_azure.py`.

### 3. Entrega 2 del orquestador: funcionalidad nueva

Todavía sin spec ni tareas: `spec.md` cubre solo la entrega 1.

- [ ] **Manejador de `resultados`:** el segmento pasa a `extraido` o `en_revision` según la salida 0.2.
- [ ] **Tarea de revisión de campos** para los campos que quedan en revisión.
- [ ] **Ficha del proceso:** los segmentos del proceso (CPC, adendas) arman la ficha. Va al estado `ficha_por_confirmar` y crea la tarea de confirmarla.
- [ ] **¿Terminó el oferente?** Sin contadores, preguntando si le queda algo pendiente. Si terminó, publica en la cola `reglas`.
- [ ] **Menor precio:** el estado `en_espera` para los oferentes que todavía no les toca.
- [ ] **Power App:** escribir las tareas donde la Power App las lea (Dataverse) y recibir las correcciones por Service Bus. La Power App es de otro equipo: solo se hace el contrato y nuestro lado.
- [ ] **`reprocesar`:** el comando que activa `forzar_reproceso` y guarda quién lo pidió y por qué.
- [ ] **Clasificador real:** el cliente del servicio del otro equipo, cuando exista su contrato (A-5).

### 4. Extracción: lo que quedó abierto (`contexto/HANDOFF-extraccion.md`)

- [ ] **A9:** la medición con los gold, que corre el usuario.
- [ ] **`describir_modelo` con versión**, en el modelo semántico: sin eso, la extracción con `--modelo mcp` se detiene cuando se publique la v22.
- [ ] **Datos del modelo semántico:** `id_regla`, ámbito, validadores y `td_probado`. Mientras tanto todo va a revisión por `TD_NO_PROBADO`.
- [ ] **Trazas de 30 días** (D23) y **gate de regresión** con los gold (D24).

### 5. Módulo 4: reglas e informe

- [ ] Por planear. Consume la cola `reglas`, con la hoja Reglas de la matriz (decisión 28).

### 6. Documentos

- [ ] El README del contrato 0.2 nombra la cola `procesos-listos`: pasarla a `evaluacion-ofertas-procesos-listos` antes de que el módulo 1 acepte el contrato.
- [ ] Los diagramas de `contexto/diagramas/` todavía muestran el aviso por oferente y Blob con los originales.

## Orden sugerido

1. ~~`Estado` en Mongo~~ (hecho).
2. ~~`Cola` en Service Bus y `Almacen` en Blob~~ (hechos y probados con clientes falsos).
3. Probar `Cola` (T07) y `Almacen` (T04) contra Azure cuando estén los roles.
4. El comando de worker que vacía su cola, con las tres versiones de Azure.
5. La spec de la entrega 2 del orquestador (sección 3), antes de escribir su código.
