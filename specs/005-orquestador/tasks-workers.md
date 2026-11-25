# Tareas 005 — Workers en Container Apps Jobs

Es una pieza de la entrega 2 del orquestador: los manejadores que hoy corren juntos en memoria con `orquestar correr` (`Corrida` de `local.py`) pasan a correr cada uno como un worker que toma mensajes de su cola de Service Bus hasta vaciarla y termina (Container Apps Jobs, decisión del 2026-11-24 en `pendientes-azure.md`). Cada worker arma las versiones de Azure de `Cola`, `Estado`, `Almacen` y `Origen` desde el entorno. `orquestar correr` sigue igual, para las corridas locales.

**Meta:** una corrida de punta a punta con un worker por cola, sobre los clientes falsos de Service Bus, Mongo y Blob, da los mismos estados y solicitudes que `orquestar correr` y los mismos sobres que `extraer_segmento`; y cada worker queda listo para correr como job en Azure, con su imagen y su configuración documentada.

**Estado al 2026-11-25:** en curso, rama `workers`. Implementa Claude (el usuario anda bajo en tokens de GPT); Astra revisa al final.

## Decisiones ya tomadas

- **Workers como Container Apps Jobs** que procesan mensajes hasta vaciar la cola y terminan; ninguna ejecución se corta a la mitad, cada entrega arranca con disco limpio y queda historial por ejecución (`pendientes-azure.md`, sección 3).
- **Concurrencia:** como máximo 2 entregas normalizando a la vez y 3 llamadas a la vez al LLM en `extraer`, por los 429 (paso 4 del diseño).
- **Imágenes:** la de normalización, con LibreOffice, ya existe (`servicios/normalizacion/Dockerfile`); falta una liviana para los demás.
- **Reintentos y errores:** los del bucle `procesar_uno` (`errores.py`): 3 reintentos con 2, 4 y 8 minutos, el 429 no cuenta como intento, y los bugs y la configuración van a errores.
- **La infraestructura no va en este repositorio** (es público): la definición de los jobs, sus disparadores, roles y secretos se hacen en el repositorio de Azure DevOps. Aquí solo se documenta qué necesita cada worker.

## Decisiones de esta pieza (2026-11-25)

Revisadas con el usuario y con una segunda opinión de Astra antes de empezar.

1. **Paquete compartido de mensajería.** `Cola`, `ColaEnMemoria`, `ColaServiceBus`, el bucle `procesar_uno`, sus excepciones (`ErrorTransitorio`, `ErrorDeConfiguracion`, `MensajeRechazado`, etc.), los parámetros que usa y el contexto de registro pasan a un paquete nuevo, `servicios/mensajeria`. El orquestador y la extracción dependen de él, pero no uno del otro: se mantiene que la extracción no depende del orquestador. El orquestador conserva sus imports actuales reexportando desde `mensajeria`, para no tocar su código ni sus pruebas.
2. **`clasificar` en desarrollo con el clasificador falso.** `CLASIFICADOR=falso` con el CSV leído del almacén, validado antes de recibir mensajes (sin CSV, todo saldría TD-99 y no se extraería nada). Sin configurar, error de configuración. El clasificador real espera A-5.
3. **Errores de la extracción en modo worker.**
   - `Llamador` conserva solo los reintentos de respuesta inválida. Las fallas pasajeras y los 429 los reintenta el bucle, con la espera pedida (si no, una solicitud podría llegar a 16 llamadas). La CLI local conserva su política actual.
   - `ok`, `no_corresponde`, `error_entrada` y un `error_proceso` no reintentable se publican en `resultados` y se completa el mensaje.
   - Al agotarse los reintentos, `al_fallar` arma el sobre `error_proceso` con la solicitud y el motivo, y lo publica en `resultados`.
   - `SolicitudInvalida` es `MensajeRechazado`.
   - Los resultados se guardan en el almacén (Blob), no en disco local, que en un job se pierde. Si un mensaje se vuelve a entregar, se republica lo guardado sin llamar al LLM. Quien consuma `resultados` (entrega 2) deduplica por la clave de la solicitud.
4. **Concurrencia por ejecución.** `normalizar`: una entrega por ejecución, como máximo 2 ejecuciones, con las 8 descargas internas. `extraer`: una sola ejecución a la vez, con 3 hilos que comparten un solo `Llamador`. `apertura` y `clasificar`: un hilo. Cada hilo consumidor tiene su propia `ColaServiceBus`; `AlmacenBlob` se comparte (cliente por hilo).
5. **Cuándo termina una ejecución.** Cuando no queda nada visible en la cola, o al cumplirse un límite para tomar mensajes nuevos (25 minutos por defecto, ajustable por worker, para un tiempo máximo del job de 30). Los mensajes con demora no hacen esperar: el disparador lanza otra ejecución cuando se vuelven visibles. Con `SIGTERM`, deja de tomar mensajes y lo que no terminó queda sin completar, para que Service Bus lo vuelva a entregar.
6. **Reserva por entrega.** Antes de bajar nada, `Normalizar` pasa la entrega de `RECIBIDO` o `ERROR_PROCESO` a un estado nuevo, `NORMALIZANDO`, con un cambio condicional que anota el dueño (id de ejecución) y el vencimiento. Solo el dueño normaliza y al final pasa a `PROCESANDO`. Otra ejecución que la encuentre reservada y vigente lanza `ErrorTransitorio` con espera; si la reserva venció, la toma. El vencimiento es mayor que el tiempo máximo del job, para que la primera ejecución ya no exista cuando otra la tome. Además, `Apertura` anota cada entrega publicada, para no republicarlas si se cae a la mitad. Motivo: dos conversiones de LibreOffice del mismo archivo no dan los mismos bytes (fecha de creación), y dos ejecuciones a la vez pueden dejar un PDF y una lectura con huellas distintas.
7. **Alcance.** Entran los cuatro workers (`apertura`, `normalizar`, `clasificar`, `extraer`), la reserva, los resultados en el almacén, los dos pendientes del almacén (subtipos públicos de `ErrorAlmacen` y `AlmacenBlob.cerrar()` que espera las operaciones activas), los comandos `reenviar-errores` y `escalar-fallas`, la imagen liviana y una tabla de configuración por job. Quedan fuera: el manejador de `resultados` (necesita la spec de la entrega 2), el Bicep de los jobs y gpt-5.4 con identidad.
8. **Comandos e imágenes.** `orquestar-worker <apertura|normalizar|clasificar>` en el orquestador y `extraer-worker` en la extracción. La imagen liviana lleva `apertura`, `clasificar` y `extraer-worker`; la de LibreOffice suma una etapa con el orquestador para `normalizar`, sin quitar el comando `normalizar` actual. Los esquemas de los contratos van a rutas explícitas en las imágenes.
9. **OneLake por entorno.** `ONELAKE_WORKSPACE` y `ONELAKE_LAKEHOUSE` desde el entorno, para `normalizar` y también para `apertura`, que lista el origen cuando el aviso no trae los archivos.
10. **Códigos de salida.** 0 si la cola se vació, aunque algún mensaje haya ido a errores (ya alertado); 2 si la configuración es inválida antes de recibir; 1 si una falla de infraestructura corta la ejecución.
11. **En Azure no se cae a lo local.** Los workers exigen las versiones de Azure: si falta `ALMACEN_BLOB_CUENTA` (o las variables de Service Bus, Mongo u OneLake que necesite), salen con código 2.
12. **Tamaño de los mensajes.** Una prueba con el sobre de resultado más grande de la muestra contra el límite de 248 000 bytes de `ColaServiceBus`.
13. **Para el repositorio de infraestructura** (se documenta aquí, no se hace): identidad y roles por worker, secretos de Key Vault solo en los jobs que los usan (`ESTADO_MONGO_URL`, `AZURE_OPENAI_API_KEY`, `MCP_API_KEY`), imágenes fijadas por digest, alertas (cola de errores, antigüedad, 429, bloqueo perdido) y qué pasa con `resultados` mientras no tenga consumidor (14 días de vida).

## Para quien implemente

- Leer antes `local.py` (`Corrida`), `errores.py` (`procesar_uno`), los manejadores (`apertura.py`, `normalizar.py`, `clasificar.py`, `extraer.py`), `cola.py`, `cola_servicebus.py` (`cola_desde_entorno`), `estado_mongo.py` (`coleccion_desde_entorno`), `estados.py`, `normalizacion/almacen.py` (`almacen_desde_entorno`), `origen_onelake.py`, y en la extracción `servicio.py` (`extraer_segmento`), `llamada.py`, `cli.py` y `resultados.py`.
- **Las pruebas normales no tocan Azure:** usan el cliente falso de Service Bus, `mongomock` y el contenedor falso de Blob. Las de Azure llevan la marca `azure(variable=...)`.
- **Nada de secretos ni nombres de recursos de Azure** en el código, las pruebas, los registros ni el repositorio: van en variables de entorno.
- En los registros, solo identificadores (principio 6).
- Flujo de siempre: una tarea a la vez, rama `workers` desde `main`, pruebas en verde, notas aquí, commit por tarea y revisión al final.

## Tareas

- [x] **T01 — Paquete `mensajeria`** (decisión 1). Mover `Cola`, `ColaEnMemoria`, `ColaServiceBus`, `procesar_uno`, sus excepciones, parámetros y contexto de registro, con sus pruebas. El orquestador reexporta; su suite pasa sin cambios.
- [ ] **T02 — Bucle de un worker** (decisiones 5 y 10). Vacía una cola con un manejador hasta que no queda nada visible o se cumple el límite, atiende `SIGTERM`, devuelve conteos por desenlace y el código de salida. Con hilos, cada uno con su cola. Se prueba con `ColaEnMemoria`.
- [ ] **T03 — Piezas desde el entorno** (decisiones 9 y 11). Arma `Cola`, `Estado`, `Almacen` y `Origen` con sus `*_desde_entorno`, valida todo antes de recibir, exige las versiones de Azure y cierra todo al terminar.
- [ ] **T04 — Reserva por entrega** (decisión 6). Estado `NORMALIZANDO` con dueño y vencimiento, cambio condicional al principio de `Normalizar`, y `Apertura` que anota cada entrega publicada. Pruebas con dos workers sobre la misma entrega, incluida una reserva vencida y la caída de `Apertura` a la mitad.
- [ ] **T05 — Workers del orquestador** (decisiones 2 y 8): `orquestar-worker apertura|normalizar|clasificar`, con el clasificador falso desde el almacén.
- [ ] **T06 — Worker de extracción** (decisiones 3 y 12): `extraer-worker`, con `Llamador` en modo worker, resultados en el almacén, publicación en `resultados` y `al_fallar` que publica el `error_proceso`.
- [ ] **T07 — Pendientes del almacén** (de `tasks-almacen-blob.md`): subtipos públicos de `ErrorAlmacen` (URI inválida y objeto ausente) con su trato en cada consumidor, y `AlmacenBlob.cerrar()` que espera las operaciones activas.
- [ ] **T08 — Punta a punta con los workers:** los cuatro workers sobre los clientes falsos dan los mismos estados y solicitudes que `Corrida`, y los mismos sobres que `extraer_segmento`, con dobles y reloj controlado.
- [ ] **T09 — Comandos de operación:** `reenviar-errores <cola>` y `escalar-fallas`.
- [ ] **T10 — Imágenes y configuración** (decisiones 8 y 13): imagen liviana, etapa de worker en la de LibreOffice, y la tabla de configuración por job en el README.
- [ ] **T11 — Contra Azure (en espera de los roles):** un worker contra las colas, la base y el contenedor de desarrollo, con datos inventados. La corre el usuario.
- [ ] **T12 — Cierre.** Notas, `plan.md`, README e `inventario-codigo.md` (incluida su línea de estado, que todavía nombra la rama `almacen-blob`).

## Fuera de esta versión

- El manejador de `resultados` y todo lo demás de la sección 3 del inventario: necesita la spec de la entrega 2.
- El clasificador real (A-5).
- gpt-5.4 con identidad en vez de la clave.
- La definición de los jobs en Bicep, en el repositorio de Azure DevOps.

## Notas de implementación

### T01

`servicios/mensajeria` tiene `cola.py`, `cola_servicebus.py`, `errores.py` y `reloj.py`, movidos sin cambios de comportamiento desde el orquestador, más `parametros.py` (los del bucle y la cola) y `registros.py` (`contexto_de` y `alertas`). Depende de la normalización, que ya es la base de todos los servicios, por sus registros y por las excepciones del almacén que traduce el bucle.

- En el orquestador, `cola.py`, `cola_servicebus.py`, `errores.py` y `reloj.py` quedan como alias de módulo (`sys.modules[__name__] = mensajeria.<módulo>`). Con un reexporte simple, los `monkeypatch` de las pruebas sobre `orquestador.cola_servicebus` dejarían de afectar al código real.
- `orquestador.parametros.Parametros` hereda de `mensajeria.parametros.Parametros` y agrega los suyos, así un mismo objeto sirve para el bucle y para el orquestador.
- Los registros del bucle pasan de `orquestador.bucle` y `orquestador.alertas` a `mensajeria.bucle` y `mensajeria.alertas`. `orquestador.registros.configurar` conecta también el registro `mensajeria`. Es el único cambio en las pruebas del orquestador (`test_errores.py`).
- Las pruebas de la cola y del bucle siguen en el orquestador, que las corre sobre los mismos módulos. La mensajería tiene dos propias: que se importa sin el orquestador ni la extracción, y que el bucle completa un mensaje en memoria.
- `azure-servicebus` pasa del orquestador a la mensajería. La extracción todavía no la usa (T06).

Pruebas: mensajería 2, orquestador 491 (58 saltadas), extracción 224.
