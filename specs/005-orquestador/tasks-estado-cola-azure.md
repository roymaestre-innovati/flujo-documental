# Tareas 005 — Estado en Mongo y cola en Service Bus

Es una pieza de la entrega 2 del orquestador: las interfaces `Estado` y `Cola` dejan de vivir solo en memoria y tienen su versión de Azure. El resto del orquestador (apertura, normalizar, clasificar, el bucle de `errores.py`) no cambia, porque solo habla con las interfaces. Blob va aparte, en `tasks-almacen-blob.md`. Los workers que corren en Container Apps Jobs son la pieza siguiente y no entran aquí.

**Meta:** `EstadoMongo` y `ColaServiceBus` pasan la misma batería de pruebas que `EstadoEnMemoria` y `ColaEnMemoria`, en local sin Azure y, cuando se pida, contra los recursos reales de desarrollo.

**Estado al 2026-11-24:** en curso, rama `estado-cola-azure`.

## Decisiones ya tomadas

Están en `specs/005-orquestador/pendientes-azure.md` de la rama `infra-azure-inicial`, que todavía no está en `main`. Para leerla sin cambiar de rama: `git show infra-azure-inicial:specs/005-orquestador/pendientes-azure.md`. Lo que importa aquí:

- **Estado:** una cuenta de Cosmos DB con la **API de MongoDB** (no la API NoSQL), compartida con otras aplicaciones. Nuestra base es `evaluacion_ofertas`, la colección es `estado` y la clave de partición es `id_proceso` (hash). Ya existen. Se usa `pymongo`. Se entra con una **cadena de conexión**: esta API no acepta identidades de Entra. En Azure la cadena viene de Key Vault.
- **Cola:** un namespace de Service Bus Standard compartido con otras aplicaciones. Nuestras colas llevan el prefijo `evaluacion-ofertas-`: `evaluacion-ofertas-procesos-listos`, `-normalizar`, `-clasificar`, `-extraer` y `-resultados`. Ya existen, con bloqueo de 5 minutos, 10 entregas como máximo antes de ir a errores, 14 días de vida y paso a errores al vencer. Se entra con `DefaultAzureCredential`: en local, el `az login` del usuario; en Azure, la identidad administrada del job.
- **Workers:** Container Apps Jobs que procesan mensajes hasta vaciar la cola y terminan (pieza siguiente).
- **`reenviar_errores` seguro en Azure** (decidido el 2026-11-24): en Service Bus se recibe de la cola de errores con bloqueo, se republica y solo después se completa. Así una caída a la mitad no pierde mensajes.

Decidido al revisar este plan (2026-11-24, con una segunda opinión de Codex):

- **`_id` de Mongo con el proceso adentro.** Cosmos exige `_id` único solo dentro de cada partición, pero `mongomock` y un Mongo normal lo exigen en toda la colección, y los ids de oferente (`PROCESO`, `OF-001`) se repiten entre procesos. Se usa un subdocumento `{"p": id_proceso, "t": tipo, "i": id}`, sin separadores que puedan chocar con un `:` del id. Si Cosmos no lo acepta como `_id`, se pasa a un texto con separador escapado (T03 lo confirma).
- **Bloqueo perdido.** Un `MessageLockLostError` no se traga: `ColaServiceBus` lo convierte en una excepción propia (`BloqueoPerdido`, distinta de `ErrorCola`) y `procesar_uno` la maneja: no republica, no cuenta el mensaje como hecho y no avisa que fue a errores. Service Bus lo vuelve a entregar.
- **El reenvío de errores se define en T04**, no en T06, para que T05 no implemente `sacar_de_errores` solo para retirarlo después.
- **Las colas de desarrollo las usa solo este equipo** (2026-11-24). Las pruebas contra Service Bus revisan con *peek* al empezar que la cola y su cola de errores estén vacías y, si no, se detienen con un mensaje claro. No hacen falta colas exclusivas de prueba.

## Dónde va

En el **orquestador**, al lado de las versiones en memoria: `servicios/orquestador/src/orquestador/estado_mongo.py` y `cola_servicebus.py`. Las dependencias nuevas (`pymongo` y `azure-servicebus`) van en `servicios/orquestador/pyproject.toml`, que ya tiene `azure-identity`.

## Para quien implemente

- Leer antes `plan.md` (secciones "Mensajes internos" y "Estado") y "Manejo de errores" del paso 4 de `contexto/flujo-documental-opcion-a.md`. También las interfaces: `estado.py`, `cola.py` y el bucle `procesar_uno` de `errores.py`, que es quien usa la cola.
- **Las pruebas normales no tocan Azure.** La versión de Mongo se prueba con un Mongo falso en memoria (recomendado: `mongomock`, como dependencia de pruebas). La de Service Bus, con un cliente falso mínimo que imite lo que se usa del SDK. Las pruebas contra Azure llevan la marca `azure` y solo corren si están sus variables de entorno. Si no están, se saltan.
- **Los recursos de Azure son compartidos.** Cada prueba contra Azure usa un `id_proceso` inventado y único (`PRUEBA-<uuid>`) y borra lo suyo al terminar. Contra Service Bus, solo se corren cuando no hay workers consumiendo las colas de desarrollo, porque la prueba recibiría sus mensajes. Se vacía lo que la prueba publicó.
- **Nada de secretos** en el código, las pruebas, los registros ni el repositorio. La cadena de conexión se lee de una variable de entorno y nunca se imprime.
- **El repositorio de GitHub es público.** No se escriben en él nombres de cuentas, namespaces ni grupos de Azure: van en variables de entorno.
- En los registros, solo identificadores (principio 6).
- Las pruebas contra Azure las corre el usuario en su máquina, con los comandos listos para copiar y cuánto tardan.
- Flujo de siempre: una tarea a la vez, rama nueva desde `main`, pruebas en verde, notas en "Notas de implementación" de este archivo, commit y **alto para revisión del usuario**. Lo ambiguo se anota y se le pregunta, con una recomendación primero.

## Tareas

- [x] **T01 — Batería de contrato de `Estado`.** Pasar las pruebas de `Estado` de `test_interfaces.py` a una batería que reciba la implementación por fixture, para correr las mismas pruebas sobre cualquier versión. Hoy corre solo sobre `EstadoEnMemoria`. No cambia ninguna regla. Agregar las que falten para lo que promete la interfaz:
  - `crear_si_no_existe` devuelve lo que quedó y `False` si ya existía, sin cambiarlo;
  - `reemplazar` sube `version` y da `Conflicto` si el registro cambió, o `ErrorEstado` si no existe;
  - `listar` ordena por tipo (en el orden de `TIPOS`) y por id, y no mezcla procesos;
  - `procesos` devuelve los `id_proceso` ordenados;
  - se rechazan los tipos desconocidos y lo que no es JSON;
  - lo devuelto es una copia: cambiarlo no cambia lo guardado;
  - el mismo tipo e id en dos procesos son registros independientes (crear y reemplazar uno no toca al otro);
  - ida y vuelta exacta de `datos` con claves que llevan `.`, `/`, `$` inicial y tildes, como las rutas de `esperados` (crear, leer, reemplazar y volver a leer).

  `guardar()` no es parte de `Estado`: su prueba queda solo para `EstadoEnMemoria`.

- [x] **T02 — `EstadoMongo`.** Implementa `Estado` sobre una colección de `pymongo`. Recibe la colección ya armada, para poder pasarle una falsa en las pruebas, y trae una función que la arma desde el entorno (`ESTADO_MONGO_URL`, y la base y la colección con valores por defecto `evaluacion_ofertas` y `estado`). Pasa la batería de T01 con `mongomock`.
  - Forma de cada documento: `{"_id": {"p": <id_proceso>, "t": <tipo>, "i": <id>}, "id_proceso", "tipo", "id", "version", "datos": {...}}`. `datos` va anidado, para que un campo del flujo nunca choque con `version` ni con `_id`.
  - Se valida con `_revisar` antes de tocar Mongo (lo que no es JSON da `TypeError`, como en memoria) y se revisa el tamaño del documento BSON completo contra el límite de Cosmos (2 MB): si se pasa, `ErrorEstado` con el tamaño, sin el contenido.
  - **Todo filtro lleva `id_proceso`**, porque es la clave de partición. La única excepción es `procesos()` (`distinct`), que la usan solo los trabajos periódicos.
  - `crear_si_no_existe`: `insert_one`. Ante `DuplicateKeyError`, lee lo que quedó y lo devuelve con `False`.
  - `reemplazar`: `replace_one` con filtro `{_id, id_proceso, version}` que escribe `version + 1`. Si no coincide nada, se lee para distinguir `ErrorEstado` (no existe) de `Conflicto` (cambió).
  - `listar`: `find` por `id_proceso` y, si viene, `tipo`. El orden se hace en Python, porque no es alfabético.
  - **Límite de RU:** Cosmos responde el error 16500 (`TooManyRequests`), a veces con el tiempo de espera en el mensaje (`RetryAfterMs`). Se convierte en `ErrorTransitorio` con ese `espera_s` en segundos, para que el bucle lo reprograme sin contar intento (R19). Si no viene el tiempo, se usa una espera por defecto (parámetro, 1 s), para que el límite de RU nunca gaste intentos. Puede llegar también al recorrer un cursor de `find`. Los errores de red de `pymongo` son `ErrorTransitorio` sin espera.
  - La cadena de conexión de Cosmos trae `retrywrites=false`: no cambiarlo.

- [x] **T03 — `EstadoMongo` contra la base de desarrollo.** Correr la batería de T01 con la marca `azure` contra la base real (`ESTADO_MONGO_URL` del entorno). Repetir contra Mongo las pruebas de mensajes repetidos y de cambio condicional, con dos hilos que intentan crear o reemplazar lo mismo a la vez: gana uno y el otro recibe `False` o `Conflicto`. La corrió el usuario el 2026-11-24.
  - Si una consulta por `tipo` falla o cuesta mucho por falta de índice, anotarlo: el índice se agrega en la infraestructura (`infra/recursos.bicep`, rama `infra-azure-inicial`), no en el código.
  - Anotar el costo en RU de cada operación (`db.command("getLastRequestStatistics")`), para tener una idea del consumo, fuera de la prueba con hilos.
  - Confirmar que Cosmos acepta el `_id` en subdocumento, las claves con `.` y `$` en `datos`, y que `distinct` devuelve procesos de varias particiones.

- [ ] **T04 — Batería de contrato de `Cola`.** Igual que T01, para las pruebas de `Cola`. Las que usan `RelojManual` para la demora quedan solo para la versión en memoria. La batería general prueba la demora con el reloj real y una espera corta: que no se vea antes y que se vea después, con margen. Agregar:
  - las propiedades (`intento`, `esperas`) viajan aparte del cuerpo y vuelven igual;
  - `entregas` sube con cada entrega. Service Bus cuenta desde 1 en la primera: confirmar que coincida con la versión en memoria;
  - completar, abandonar o mandar a errores un mensaje que no está bloqueado da `ErrorCola`;
  - el cuerpo debe ser JSON;
  - el motivo llega a la cola de errores;
  - `reenviar_errores(cola)` reemplaza a `sacar_de_errores`: republica en la cola original el mismo cuerpo y las propiedades sin `intento` ni `esperas`, deja vacía la cola de errores y devuelve cuántos reenvió. `errores.reenviar_errores(cola, nombre)` conserva su firma y la usa;
  - completar con una entrega vieja (el mismo mensaje se abandonó y se volvió a recibir) da error.

- [ ] **T05 — `ColaServiceBus`.** Implementa `Cola` con `azure-servicebus` y `DefaultAzureCredential`. Recibe el namespace (`SERVICEBUS_NAMESPACE`, el nombre completo `<namespace>.servicebus.windows.net`) y el prefijo (`COLAS_PREFIJO`, por defecto `evaluacion-ofertas-`). Pasa la batería de T04 con un cliente falso.
  - **Los nombres del código no cambian.** `cola.py` sigue con `normalizar`, `clasificar`, etc., y `ColaServiceBus` les antepone el prefijo. Así la versión en memoria, las pruebas y el comando local quedan igual. Se agrega `resultados` a `COLAS`, porque la cola ya existe en Azure y la usará la entrega 2.
  - `publicar`: el cuerpo va como JSON y las propiedades como *application properties*. Con demora, se usa `scheduled_enqueue_time_utc`. El id del mensaje lo genera la clase, como hoy.
  - `recibir`: modo PeekLock, de a un mensaje. Se guarda el mensaje original del SDK por id, porque `completar`, `abandonar` y `a_errores` lo necesitan y deben pasar por el mismo receptor que lo recibió. Hay que mantener un receptor abierto por cola mientras haya mensajes bloqueados.
  - `a_errores`: `dead_letter_message`, con el motivo en `reason` y su detalle en `error_description`.
  - `errores(cola)` y `pendientes(cola)`: con *peek*, que solo pide el rol de recibir. Solo los usa el resumen de la corrida local (`local.py`), pero la interfaz los pide.
  - Mensajes de más de 256 KB: Service Bus Standard los rechaza. Que el error sea claro (`ErrorCola`) y diga el tamaño, no el contenido.
  - Errores del SDK: los de red y los de servicio ocupado son `ErrorTransitorio`; un bloqueo perdido (`MessageLockLostError`) es `BloqueoPerdido` (ver "Decisiones"); los de permiso son `ErrorDeConfiguracion`.
  - `entregas`: confirmar en el código del SDK si `delivery_count` empieza en 0 o en 1 y ajustarlo para que la primera entrega sea 1, como en memoria. Las claves y valores de texto de las propiedades pueden volver como `bytes`: se pasan a `str` antes de entregarlas, o el bucle no encontraría `intento`.
  - `recibir` usa `max_wait_time` configurable (5 s por defecto). `None` quiere decir que no llegó nada en ese tiempo, aunque queden mensajes programados o bloqueados.
  - Una instancia por hilo: los receptores del SDK no son seguros entre hilos. El comando local sigue con `ColaEnMemoria`.

- [ ] **T06 — Renovar el bloqueo y reenviar de errores.**
  - **Renovación:** el bloqueo dura 5 minutos y una normalización puede tardar más. `ColaServiceBus` registra cada mensaje recibido en un `AutoLockRenewer` (uno por instancia, con un máximo configurable, por defecto 30 minutos). El renovador no tiene cómo soltar un mensaje: deja de renovarlo cuando se completa, abandona o manda a errores, y se cierra al cerrar la cola. La interfaz no cambia. Probarlo con el cliente falso: un mensaje recibido queda registrado una sola vez.
  - **Reenviar en Service Bus:** recibir de la cola de errores con bloqueo, publicar el mismo cuerpo sin `intento` ni `esperas` en la cola original y solo después completar. Se cuenta solo lo que se completó. Probar con el falso que si falla el envío el original sigue en errores.

- [ ] **T07 — `ColaServiceBus` contra las colas de desarrollo.** Correr la batería de T04 con la marca `azure` contra las colas reales, con `az login`. **Necesita que el administrador haya asignado los roles** de Service Bus al usuario (`infra/roles.bicep`, rama `infra-azure-inicial`). Mientras tanto, la tarea queda en espera. Probar además la renovación con un mensaje que se tiene bloqueado más de 5 minutos. La corre el usuario.

- [ ] **T08 — Cierre.** Notas de lo encontrado. Actualizar la tabla de interfaces de `plan.md` ("Lo que cambió al implementar"), el README del orquestador (variables de entorno y cómo correr las pruebas contra Azure) y `inventario-codigo.md`.

## Fuera de esta versión

- `Almacen` en Blob: `tasks-almacen-blob.md`.
- El comando de worker que vacía su cola y termina, las imágenes y los Container Apps Jobs.
- Leer la cadena de conexión de Key Vault desde el código: en Azure, el job la recibe como variable de entorno con referencia a Key Vault.
- El freno automático cuando el LLM falla muchas veces seguidas (opcional en v0).

## Notas de implementación

### T01 — Batería de contrato de Estado

`test_estado_contrato.py` parametriza el fixture `estado` por fábrica, con `memoria` como primer caso.
Cada prueba usa IDs de proceso propios y `procesos()` se comprueba sobre esos IDs para que la batería pueda correr en una base compartida.
`guardar()` se sigue probando con `EstadoEnMemoria` en `test_interfaces.py`. La implementación en memoria cumple los casos agregados sin cambios.

### T02 — EstadoMongo

`EstadoMongo` valida el BSON completo, usa `id_proceso` en las operaciones por partición y reemplaza por versión. El límite de RU se traduce a una espera con un valor configurable cuando Cosmos no indica el tiempo.
La batería de T01 también corre con `mongomock`, que acepta el `_id` en subdocumento y conserva las claves con `.` y `$` en `datos`. Como `mongomock` funciona en memoria, la clave de partición y las fallas de red y de RU se prueban con envoltorios y colecciones falsas.
T03 confirmará estos formatos y el `distinct` entre particiones en Cosmos, probará la concurrencia real y medirá el consumo de RU.

### T03 — EstadoMongo contra la base de desarrollo

Desde `servicios/orquestador`, en Bash, pega la cadena de desarrollo cuando `read` esté esperando. La entrada queda oculta y fuera del historial.

```bash
read -rs ESTADO_MONGO_URL
printf '\n'
export ESTADO_MONGO_URL
uv run pytest -m azure -v
uv run python scripts/medir_ru_estado.py
unset ESTADO_MONGO_URL
```

Las 36 pruebas hacen unas 230 solicitudes, incluidos los borrados. Con 60–70 ms por solicitud, son unos 14–16 s de ida y vuelta en serie. Reserva unos 20–35 s para las pruebas, contando la conexión inicial y la carga de la base. El script hace unas 22 solicitudes, incluidas las de estadísticas y limpieza. Reserva unos 2–5 s.

Revisa que Cosmos guarde y encuentre el `_id` en subdocumento y que las claves de `datos.esperados` con `.` y `$` inicial se conserven al crear, leer y reemplazar. `distinct` debe devolver los procesos de prueba de varias particiones en el orden que aplica `procesos()`. En cada una de las diez carreras de creación debe haber un `True` y una copia del registro ganador para cada hilo. En las diez carreras de reemplazo, un hilo debe guardar la versión 2 y el otro recibir `Conflicto`.

Si Cosmos rechaza el `_id` en subdocumento, aplica el plan acordado de usar un texto con separador escapado y repite las pruebas. Si falla la ida y vuelta de las claves o `distinct`, anota la operación y el código de error sin copiar datos de conexión. Si la consulta por `tipo` falla o resulta costosa por falta de índice, anótalo y agrega el índice en `infra/recursos.bicep` de `infra-azure-inicial`.

El script mide los milisegundos de la operación completa. La RU corresponde a la última solicitud de esa operación. `crear repetido` y `reemplazar con conflicto` hacen también una lectura interna, así que en esas filas la RU corresponde a esa lectura.

**Resultado (2026-11-24, corrida del usuario).** Las 36 pruebas `azure` pasaron en 36 s: Cosmos acepta el `_id` en subdocumento, conserva las claves con `.` y `$` en `datos`, `distinct` devuelve los procesos de varias particiones, y en las 20 carreras con dos hilos ganó siempre uno solo. No hace falta el plan B. La limpieza dejó 0 documentos `PRUEBA-`. `pymongo` avisa con un `UserWarning` que está conectado a Cosmos; es solo informativo.

RU y tiempo de cada operación, con un oferente de 80 archivos en `esperados`:

| Operación | RU | ms |
|---|---|---|
| Leer inexistente | 14,63 | 2970 (incluye abrir la conexión) |
| Crear | 9,71 | 190 |
| Crear repetido | 3,15 (la lectura posterior) | 310 |
| Leer | 3,15 | 171 |
| Reemplazar | 20,33 | 206 |
| Reemplazar con conflicto | 3,15 (la lectura posterior) | 320 |
| Listar | 3,05 | 195 |
| Listar por tipo | 5,74 | 145 |
| Procesos | 2,29 | 155 |

Lo que sale de aquí:

- **Latencia:** cada solicitud tarda de 150 a 200 ms desde la máquina del usuario, más que los 60 a 70 ms estimados entre regiones de Azure. Las operaciones que hacen dos solicitudes (crear repetido, conflicto) tardan el doble. Desde los jobs en Azure debería bajar; se mide cuando corran allá.
- **Consumo:** escribir un documento de este tamaño cuesta de 10 a 20 RU y leerlo unos 3. Un proceso con unos cientos de operaciones de estado queda muy por debajo de las 100 RU/s mínimas de la base.
- **Índice por `tipo`:** no hace falta por ahora; `listar` por tipo cuesta menos de 6 RU.

La última línea del script cuenta los documentos cuyo `id_proceso` empieza por `PRUEBA-`, con una consulta entre particiones. El conteo esperado es `0` cuando no hay otras corridas de prueba activas. Si quedan documentos, revisa el resultado del borrado y verifica con el equipo si hay otra corrida en curso antes de intervenir en la base compartida.
