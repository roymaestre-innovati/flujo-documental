# Tareas 005 — Workers en Container Apps Jobs

Es una pieza de la entrega 2 del orquestador: los manejadores que hoy corren juntos en memoria con `orquestar correr` (`Corrida` de `local.py`) pasan a correr cada uno como un worker que toma mensajes de su cola de Service Bus hasta vaciarla y termina (Container Apps Jobs, decisión del 2026-11-24 en `pendientes-azure.md`). Cada worker arma las versiones de Azure de `Cola`, `Estado`, `Almacen` y `Origen` desde el entorno. `orquestar correr` sigue igual, para las corridas locales.

**Meta:** una corrida de punta a punta con un worker por cola, sobre los clientes falsos de Service Bus, Mongo y Blob, da los mismos estados y solicitudes que `orquestar correr` y los mismos sobres que `extraer_segmento`; y cada worker queda listo para correr como job en Azure, con su imagen y su configuración documentada.

**Estado al 2026-11-25:** T01 a T10 y T12 hechas, en la rama `workers`. T11 está preparada y espera los roles de datos de Service Bus y Blob. Implementó Claude (el usuario andaba bajo en tokens de GPT); Astra revisa al final.

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
- [x] **T02 — Bucle de un worker** (decisiones 5 y 10). Vacía una cola con un manejador hasta que no queda nada visible o se cumple el límite, atiende `SIGTERM`, devuelve conteos por desenlace y el código de salida. Con hilos, cada uno con su cola. Se prueba con `ColaEnMemoria`.
- [x] **T03 — Piezas desde el entorno** (decisiones 9 y 11). Arma `Cola`, `Estado`, `Almacen` y `Origen` con sus `*_desde_entorno`, valida todo antes de recibir, exige las versiones de Azure y cierra todo al terminar.
- [x] **T04 — Reserva por entrega** (decisión 6). Estado `NORMALIZANDO` con dueño y vencimiento, cambio condicional al principio de `Normalizar`, y `Apertura` que anota cada entrega publicada. Pruebas con dos workers sobre la misma entrega, incluida una reserva vencida y la caída de `Apertura` a la mitad.
- [x] **T05 — Workers del orquestador** (decisiones 2 y 8): `orquestar-worker apertura|normalizar|clasificar`, con el clasificador falso desde el almacén.
- [x] **T06 — Worker de extracción** (decisiones 3 y 12): `extraer-worker`, con `Llamador` en modo worker, resultados en el almacén, publicación en `resultados` y `al_fallar` que publica el `error_proceso`.
- [x] **T07 — Pendientes del almacén** (de `tasks-almacen-blob.md`): subtipos públicos de `ErrorAlmacen` (URI inválida y objeto ausente) con su trato en cada consumidor, y `AlmacenBlob.cerrar()` que espera las operaciones activas.
- [x] **T08 — Punta a punta con los workers:** los cuatro workers sobre los clientes falsos dan los mismos estados y solicitudes que `Corrida`, y los mismos sobres que `extraer_segmento`, con dobles y reloj controlado.
- [x] **T09 — Comandos de operación:** `reenviar-errores <cola>` y `escalar-fallas`.
- [x] **T10 — Imágenes y configuración** (decisiones 8 y 13): imagen liviana, etapa de worker en la de LibreOffice, y la tabla de configuración por job en el README.
- [ ] **T11 — Contra Azure (en espera de los roles):** un worker contra las colas, la base y el contenedor de desarrollo, con datos inventados. La corre el usuario.
- [x] **T12 — Cierre.** Notas, `plan.md`, README e `inventario-codigo.md` (incluida su línea de estado, que todavía nombra la rama `almacen-blob`).

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

### T02

`mensajeria/worker.py`, en la mensajería porque lo usan los workers del orquestador y el de la extracción.

- `vaciar(colas, manejador, parametros=, limites=, detener=)` corre un hilo por cada `Cola` de `colas` (cada hilo con la suya, como pide la decisión 4) y comparte el manejador. Termina cuando una recepción vuelve vacía, al cumplirse `Limites.tomar_mensajes_s` (25 minutos por defecto) o `max_mensajes`, o cuando se pide terminar. No lanza: una falla de la cola corta todos los hilos y queda en `Resumen.falla`.
- El turno se reserva antes de recibir y se devuelve si la recepción no trae nada, así `max_mensajes` es exacto entre hilos.
- `atender_senales(detener)` convierte `SIGTERM` y `SIGINT` en el pedido de terminar: el mensaje en curso se termina y no se toma otro.
- `Resumen.codigo_salida`: 0 normal (aunque haya mensajes en errores), 2 si la cola dio `ErrorDeConfiguracion`, 1 con cualquier otra falla. La configuración inválida antes de recibir la valida T03 con el mismo código 2.
- `informar(resumen)` registra una línea con la cola, los conteos por desenlace, el motivo de fin y la duración; de una falla, solo el tipo y el lugar.

Pruebas: mensajería 18.

### T03

`orquestador/entorno.py`: `piezas_desde_entorno(con_origen=)` revisa primero todas las variables obligatorias (`SERVICEBUS_NAMESPACE`, `ESTADO_MONGO_URL`, `ALMACEN_BLOB_CUENTA` y, con origen, `ONELAKE_WORKSPACE` y `ONELAKE_LAKEHOUSE`) y, si falta alguna, lanza un solo `ErrorDeConfiguracion` que las nombra sin sus valores. No cae a lo local.

- Arma `EstadoMongo`, `AlmacenBlob` y, si se pide, `OrigenOneLake`. Un `AlmacenSinPermiso` al armar se vuelve `ErrorDeConfiguracion`, como en la cola y el estado, para que el worker salga con 2.
- Las colas se crean aparte, una por hilo, con `Piezas.colas(n)`.
- `Piezas.cerrar()` cierra en orden inverso: colas, almacén y cliente de Mongo, también si algo falla a la mitad.
- `Fabricas` permite pasar versiones falsas en las pruebas. Sin red, las fábricas reales arman Mongo (pymongo no se conecta hasta la primera operación) y Blob.

Pruebas: orquestador 498 (58 saltadas).

### T04

- **Estado nuevo `normalizando`** en la máquina del oferente: `recibido → normalizando → procesando`, y `normalizando → error_proceso` o de vuelta a `recibido`. `error_proceso → normalizando` para reintentar. Ya no se pasa directo de `recibido` a `procesando`.
- **`estados.reservar`** hace el cambio condicional y guarda `reserva: {dueno, vence, desde}`. Si hay una reserva vigente de otro, lanza `Reservado` con su vencimiento; si venció, la toma (paso `normalizando → normalizando`, motivo `reserva vencida`); si ya es del mismo dueño, no cambia nada.
- **`Normalizar`** reserva después de revisar las versiones y antes de bajar nada, con un dueño nuevo por intento (`uuid4`). La duración es `Parametros.reserva_normalizar_s` (2400 s, más que los 30 minutos de un job). Si la entrega está reservada, lanza `ErrorTransitorio` con la espera que le queda a la reserva más 1 s, que el bucle trata como espera y no como intento.
- **Un intento que falla en la misma ejecución** suelta la reserva con `estados.liberar`, que devuelve la entrega al estado del que se reservó. Así el reintento no espera a que venza. Solo una ejecución que muere deja la reserva puesta hasta que vence.
- **Antes de registrar documentos y publicar** se comprueba que la reserva sigue siendo propia. Si no, se registra un aviso y no se publica nada. Con la duración elegida no debería pasar.
- **`al_fallar`** no marca `error_proceso` si otra ejecución tiene la reserva vigente. El dueño de cada intento se guarda por hilo.
- **`Apertura`** marca `publicada: True` en cada oferente al publicar su `normalizar`. Si se cae a la mitad, la repetición no vuelve a publicar los ya marcados. `test_caida_a_la_mitad_se_completa_al_reenviar` cambia: la primera entrega ya no sale dos veces.
- Pruebas nuevas en `test_reserva.py`: dos ejecuciones a la vez (la segunda espera sin escribir en el almacén), la espera que queda, la reserva vencida que se toma y se termina, el intento fallido que suelta la reserva, `al_fallar` que respeta la reserva ajena, el bug que deja `error_proceso` y se puede reintentar, y la reserva perdida a la mitad que no publica nada.

Pruebas: orquestador 507 (58 saltadas).

### T05

`orquestar-worker apertura|normalizar|clasificar [--hilos 1] [--tomar-mensajes-s 1500] [--soffice <ruta>]` (`orquestador/workers.py`).

- Configura los registros en JSON por stderr (también los de `mensajeria`), arma las piezas con `piezas_desde_entorno` (OneLake solo para `apertura` y `normalizar`), crea una cola para publicar y una por hilo para recibir, y vacía la cola con `mensajeria.worker.vaciar` bajo `atender_senales`. Devuelve el código de salida de `informar`.
- `clasificar` exige `CLASIFICADOR=falso` y `CLASIFICADOR_CSV` (ruta dentro del almacén), y revisa antes de recibir que el CSV exista, sea válido y tenga filas. `ClasificadorFalso` acepta ahora el contenido del CSV (`texto=`) además de una ruta.
- Una configuración inválida o una variable que falta salen con 2 sin tocar la cola; un mensaje que va a errores no cambia el 0.

Pruebas: orquestador 518 (58 saltadas).

### T06

`extraer-worker [--hilos 3] [--tomar-mensajes-s 1500]` (`extraccion/worker.py`). Depende de la mensajería y de la normalización, no del orquestador (hay una prueba que lo comprueba).

- **`Llamador` en modo worker** (`ajustes_del_worker`): `reintentos_falla_pasajera=0` y `espera_limite_uso_total_s=0`, así una falla pasajera o un 429 salen enseguida como `LlamadaFallida`, que ahora lleva `espera_s` del 429. Las respuestas mal formadas se siguen repitiendo por dentro. La CLI `extraer` no cambia.
- **`Servicio.relanzar_reintentables`**: con él, `extraer_segmento` lanza el `ErrorDeSolicitud` reintentable en vez de devolver su sobre. El worker lo traduce a `ErrorTransitorio` con la espera, y el bucle reintenta (3 veces con 2, 4 y 8 minutos, o espera lo pedido sin contar el intento).
- **`al_fallar`** publica en `resultados` el sobre `error_proceso` del último error de ese hilo (`resultado_de_error`), o `FALLA_INTERNA` si fue un bug. Una solicitud inválida no publica nada: no se puede armar un sobre válido.
- **`ResultadosEnAlmacen`** guarda los resultados en `extraccion/<id_proceso>/<entrega>/` del almacén, con el mismo formato y los anteriores al lado. Un mensaje repetido publica lo guardado sin llamar al LLM.
- **`SolicitudInvalida`** es `MensajeRechazado`, con solo la cantidad de problemas en el motivo.
- Los registros de la mensajería salen por el mismo manejador JSON de la extracción.
- **Tamaño (decisión 12):** los sobres de ejemplo del contrato miden menos de la décima parte del límite de 248 000 bytes. Medir un sobre real grande queda para la corrida contra Azure (T11), porque los resultados de la muestra no están en el repositorio.

Pruebas: extracción 238.

### T07

- **Subtipos de `ErrorAlmacen`** en `normalizacion/almacen.py`: `UriInvalida` (la URI o la ruta no son de este almacén, o no sirven) y `NoEncontrado` (la URI es del almacén pero no hay archivo). `AlmacenLocal` y `AlmacenBlob` lanzan siempre uno de los dos; quien atrapa `ErrorAlmacen` sigue funcionando.
- **Extracción:** `UriInvalida` es `error_proceso` con `URI_INVALIDA`, no reintentable (por ejemplo, una URI `file://` con Blob activo); `NoEncontrado` sigue siendo `ARCHIVO_NO_ENCONTRADO`, reintentable. Fila nueva en la tabla de errores de `plan-extraccion.md`.
- **Bucle:** un `ErrorAlmacen` en un manejador (por ejemplo, falta la lectura al clasificar) va a errores con motivo `Almacén: ...` en vez de `Bug: ...`. No se reintenta: el archivo no aparece solo.
- **`AlmacenBlob.cerrar()`** no acepta operaciones nuevas (lanzan `RuntimeError`), espera las que están en curso en otros hilos hasta `espera_cierre_s` (120 s) y después cierra. Si no terminan a tiempo, registra un aviso con cuántas seguían.

Pruebas: normalización 643 (23 saltadas), orquestador 519 (58 saltadas), extracción 238.

### T08

`servicios/extraccion/tests/test_workers_punta_a_punta.py`, en la extracción porque es el único servicio que puede importar los dos (el orquestador solo en `dev`). Un proceso con dos oferentes y un documento del proceso pasa por `apertura`, `normalizar`, `clasificar` y `extraer-worker` (con 2 hilos), con cola y estado en memoria, el almacén Blob sobre el contenedor falso (cada worker arma y cierra el suyo) y el LLM falso.

- Los estados de todos los registros y las solicitudes (sin las URI, que cambian de `file://` a `https://`) son los mismos que da `orquestador.local.Corrida` con la misma entrada.
- Los sobres que publica el worker en `resultados` son los mismos que da `extraer_segmento` llamado directo, salvo `ejecucion`.
- El estado va en memoria y no en `mongomock`, que es dependencia de pruebas del orquestador y no de la extracción: `EstadoMongo` ya pasa la misma batería que `EstadoEnMemoria`. Lo mismo con la cola: `ColaServiceBus` pasa la batería de `Cola`.

Pruebas: extracción 239.

### T09

`orquestar-operar` (`orquestador/operacion.py`), con dos subcomandos:

- `reenviar-errores <cola>` vuelve a publicar la cola de errores de una de las cinco colas, desde el primer intento, con `reenviar_errores`. Solo pide `SERVICEBUS_NAMESPACE`.
- `escalar-fallas` corre `escalar_fallas` sobre el estado y crea la tarea "falla técnica" de cada entrega o documento con más de 24 horas en `error_proceso`. Repetirlo no duplica tareas. Solo pide `ESTADO_MONGO_URL`. En Azure va como job con horario (cada hora), en el repositorio de infraestructura.
- Por pantalla, solo conteos. 2 si falta configuración, 1 si otra falla corta el comando (solo el tipo y el lugar).
- `entorno.estado_desde_entorno` queda pública para que la usen los dos comandos.

Pruebas: orquestador 524 (58 saltadas).

### T10

- **Imagen liviana** (`servicios/workers/Dockerfile`, sobre `python:3.12-slim-bookworm`): el orquestador y la extracción en entornos separados (`/opt/orquestador` y `/opt/extraccion`), cada uno con su lock y sin dependencias de desarrollo, y los esquemas en `/app/contracts` (`ORQUESTADOR_CONTRATOS` y `EXTRACCION_CONTRATOS`). Trae `orquestar-worker`, `orquestar-operar` y `extraer-worker`; cada job elige su comando. Corre con el usuario 10001. Construida y probada con podman el 2026-11-25: cada comando sin variables sale con 2 y las nombra, encuentra los 38 esquemas, y la extracción no carga el orquestador. Pesa 1,31 GB, sobre todo por deltalake y pyarrow del orquestador (los usa la entrada desde OneLake).
- **Imagen con LibreOffice**: etapa nueva `worker` en `servicios/normalizacion/Dockerfile`, con el orquestador y la mensajería instalados sobre la base. `ENTRYPOINT ["orquestar-worker"]` y `CMD ["normalizar"]`. Las etapas `job` y `pruebas` no cambian. Construida y probada el mismo día: pide sus variables, y `normalizar` y LibreOffice 24.2 siguen disponibles.
- Los `.dockerignore` dejan entrar solo lo que se copia; nunca documentos, la matriz ni `.env`.
- **Configuración por job** en `servicios/workers/README.md`: comando, disparo, ejecuciones a la vez (`extraer` con una sola), variables, secretos, `replicaTimeout` 1800 s, `replicaRetryLimit` 0, escalador con `activationMessageCount: 0`, roles por cola y contenedor, alertas, y qué pasa con `resultados` mientras no tenga consumidor. Es la entrada para el repositorio de infraestructura.

### T11 (preparada)

Contra los recursos de desarrollo, con `az login` y las variables en el entorno (nunca en el repositorio). Necesita los roles de datos de Service Bus y Blob (T07 de `tasks-estado-cola-azure.md` y T04 de `tasks-almacen-blob.md`). Las colas de desarrollo deben estar vacías.

Primero, cada worker sobre su cola vacía: tiene que salir con 0 en unos segundos, lo que prueba la identidad, las variables y el permiso de recibir de cada pieza, sin datos.

```bash
export SERVICEBUS_NAMESPACE=<namespace>.servicebus.windows.net ALMACEN_BLOB_CUENTA=<cuenta>
export ESTADO_MONGO_URL='<cadena de conexión>' ONELAKE_WORKSPACE=<workspace> ONELAKE_LAKEHOUSE=<lakehouse>
cd servicios/orquestador
uv run orquestar-worker apertura; echo $?
uv run orquestar-worker normalizar; echo $?
CLASIFICADOR=falso CLASIFICADOR_CSV=config/clasificacion.csv uv run orquestar-worker clasificar; echo $?
uv run orquestar-operar escalar-fallas; echo $?
```

`clasificar` sale con 2 si no está el CSV en el almacén: subir antes uno inventado (`id_oferente,ruta_origen,pagina_inicio,pagina_fin,tipo_documental,confianza,subtipo` y una fila). Con los cuatro en 0 queda probado el acceso. Una corrida con documentos va después, con un evento de prueba del módulo 1 y datos inventados, cuando cumplimiento lo permita (S2).

### T12

Cierre: `plan.md` (estados del oferente con `normalizando` e imágenes), `inventario-codigo.md` (mensajería, workers, sección 2 y orden sugerido), el README del orquestador (estado y tabla de módulos), el de la extracción (`extraer-worker`) y los nuevos de `servicios/mensajeria` y `servicios/workers`.

Lo encontrado en la pieza:

- `Apertura` publicaba los `normalizar` antes de marcar el proceso: una caída a la mitad republicaba todas las entregas. Ahora marca cada una al publicarla.
- Dos conversiones de LibreOffice del mismo archivo no dan los mismos bytes (fecha de creación), así que la idempotencia de la normalización no alcanzaba para dos ejecuciones a la vez: de ahí la reserva.
- En modo worker, los reintentos internos de `Llamador` se sumaban a los del bucle (hasta 16 llamadas por solicitud). Ahora el bucle lleva las fallas pasajeras y los 429.
- La extracción guardaba sus resultados en disco local, que en un job se pierde al terminar. Ahora los guarda en el almacén.
- El tope de 3 llamadas al LLM vale para todo el proceso solo con una ejecución de `extraer` a la vez: queda en la configuración del job.

Queda fuera, como estaba previsto: el manejador de `resultados` (spec de la entrega 2), el clasificador real (A-5), gpt-5.4 con identidad y la definición de los jobs en la infraestructura.

Pruebas al cerrar: mensajería 18, normalización 643 (23 saltadas), orquestador 524 (58 saltadas), extracción 239.
