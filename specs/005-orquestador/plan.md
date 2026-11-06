# Plan 005 — Orquestador, entrega 1: del aviso a la cola de extracción

Estado al 2026-11-06. **Acordado y en construcción** (T01 a T04 de `tasks.md`). Los ajustes que salieron al implementar ya están en el texto y explicados en las notas de `tasks.md`. Implementa la entrega 1 de `spec.md`. Decisiones del usuario que lo enmarcan (2026-11-06):

- La entrega 1 llega hasta publicar las solicitudes de extracción. La vuelta de los resultados va en la entrega 2.
- Todo se prueba en la máquina del equipo, con interfaces que tienen una versión en memoria. Service Bus, Cosmos y OneLake reales van en la entrega 2.
- El contrato de extracción 0.2 (decisión 25) se escribe en esta iniciativa, porque el orquestador es quien manda las solicitudes.
- El orquestador vive en este repositorio, en `servicios/orquestador/`.

## Resumen

Un paquete de Python, `orquestador`, con un manejador por cola. Cada manejador recibe un mensaje, hace su trabajo, actualiza el estado y publica en la cola siguiente:

```
aviso del módulo 1 ─► [procesos-listos] ─► apertura: abre el proceso, fija versiones, reparte entregas
   ─► [normalizar] (un mensaje por entrega: PROCESO y cada oferente)
   ─► normalización: baja los originales, llama a normalizar_entrega, registra documentos
   ─► [clasificar] (un mensaje por documento normalizado)
   ─► clasificación: llama al clasificador, valida, aplica umbrales, crea segmentos
   ─► [extraer] (un mensaje por segmento, contrato modulo3-extraccion/0.2)   ◄── fin de la entrega 1
```

Cada cola tiene su cola de errores. Un comando local, `orquestar`, publica un aviso y vacía las colas en memoria hasta que no queda nada, para las pruebas de punta a punta y la corrida con la muestra.

## Tecnología

| Necesidad | Herramienta | Por qué |
|---|---|---|
| Lenguaje y dependencias | Python 3.12, `uv` | Igual que la normalización |
| Normalizar y leer | El paquete `normalizacion`, como dependencia de ruta (`../normalizacion`) | Mismo repo: se importa `normalizar_entrega` directamente, sin publicar un paquete |
| Validar mensajes contra los contratos | `jsonschema` | Ya se usa en las pruebas de la normalización |
| Pruebas | `pytest`; `reportlab` para fabricar PDF | Igual que la normalización |

Nada de Azure en esta entrega. Para la entrega 2 quedan, ya decididos en el diseño: Service Bus (decisión 33), Cosmos (decisión 16), `azure-storage-file-datalake` con identidad administrada para OneLake (decisión 35) y Blob Storage para lo que producimos.

## Interfaces

Cada pieza externa queda detrás de una interfaz pequeña, como `Almacen` en la normalización. En esta entrega solo existen las versiones locales.

| Interfaz | Qué hace | Versión local | Versión de la entrega 2 |
|---|---|---|---|
| `Cola` | `publicar(cola, mensaje, demora=0)`, `recibir(cola)`, `completar`, `a_errores(mensaje, motivo)` | `ColaEnMemoria`: listas por cola, con demora simulada por un reloj inyectable | Service Bus |
| `Estado` | `leer`, `crear_si_no_existe`, `cambiar(id, de_estado, a_estado, motivo)` condicional, `consultar(id_proceso)` | `EstadoEnMemoria`, que puede guardarse en un JSON al terminar | Cosmos, con `id_proceso` como partición |
| `Origen` | `listar(ruta)` y `bajar(ruta, destino)` | `OrigenLocal`: una carpeta | OneLake |
| `Clasificador` | `clasificar(documento) → segmentos` | `ClasificadorFalso`: lee un CSV | El clasificador del otro equipo (C1 a C3) |
| `Almacen` | Lo que producimos | `AlmacenLocal` de la normalización | Blob Storage |

El reloj también es inyectable (`ahora()`), para probar las esperas y las 24 horas del escalamiento sin esperar.

## Contratos (principio 5)

Se escriben y se revisan antes del código (T01).

**`contracts/modulo5-orquestador/v0/`**, versión `modulo5-orquestador/0.1`, con las dos fronteras externas que toca esta entrega:

| Archivo | Frontera | Contenido |
|---|---|---|
| `proceso-listo.schema.json` | Módulo 1 | `contrato`, `id_proceso`, `ruta`, `archivos` opcional (lista de `{ruta, id_oferente o null}`), `fecha` |
| `clasificacion-solicitud.schema.json` | Clasificador | `id_proceso`, `id_oferente` (o `null`), `id_documento`, `pdf` (URI y huella), `paginas`, `ruta_origen` (incluye el nombre), `lectura` (URI) y `version_ontologia` fijada del proceso |
| `clasificacion-respuesta.schema.json` | Clasificador | `id_documento`, `segmentos`: lista de `{pagina_inicio, pagina_fin, tipo_documental, subtipo opcional, confianza}`, y `version_ontologia` |
| `ejemplos/` | | Avisos con y sin lista de archivos, una solicitud y respuestas: normal, compuesta, dudosa, de desempate e inválida |

Son una propuesta para llevar al módulo 1 (A-1) y a clasificación (C1 a C3). Mientras sean 0.x se pueden cambiar avisando.

**`contracts/modulo3-extraccion/v0.2/`**, versión `modulo3-extraccion/0.2`: los ocho cambios del paso 5 del diseño, en una carpeta nueva. La `v0/` (0.1) no se toca (principio 5, decisión 25).

| # | Cambio | En el esquema |
|---|---|---|
| 1 | Transporte por cola | Se anota en el README: cola `extraer` de entrada, cola `resultados` de salida |
| 2 | Referencia a la lectura | `lectura`: URI de la lectura del paso 2 |
| 3 | Excel nativo | `anexos`: lista de URI, vacía si no hay |
| 4 | Clasificación dudosa | `clasificacion_dudosa`: booleano; en la salida, el motivo `CLASIFICACION_DUDOSA` |
| 5 | Versión del proceso | `version_modelo` se describe como "la registrada del proceso"; sin ella, la extracción consulta el registro, no la vigente |
| 6 | Sin oferente | `id_oferente` admite `null` (documentos del proceso); sigue siendo obligatorio, para que la forma sea estable |
| 7 | TD-98 no se envía | Se excluyen TD-98 y TD-99 del patrón de `tipo_documental` |
| 8 | `forzar_reproceso` | Igual, con la descripción de que solo lo activa `reprocesar` |

Además, `id_documento` de la extracción pasa a llamarse por lo que es: el identificador del **segmento** (`id_segmento`), y se agrega `id_documento` con el del archivo normalizado. Es un cambio que conviene aprovechar ahora que la versión es nueva; se confirma en la revisión de T01.

## Mensajes internos

No son frontera entre módulos, así que no van a `contracts/`. Se validan con `dataclass` en el código.

| Cola | Mensaje | Clave de idempotencia |
|---|---|---|
| `normalizar` | `id_proceso`, `entrega` (`PROCESO` o `id_oferente`), `ruta` | `id_proceso` + `entrega` + versión del normalizador |
| `clasificar` | `id_proceso`, `entrega`, `id_documento` | `id_documento` + `hash` + versión de la ontología |
| `extraer` | Solicitud del contrato 0.2 | `id_segmento` + TD + versión del modelo (D22) |

Los reintentos se cuentan con `intento` (empieza en 1) y `esperas` en las **propiedades** del mensaje, no en el cuerpo, como las application properties de Service Bus. Así no dependen de la cola y el cuerpo sigue cumpliendo su contrato: el aviso del módulo 1 no admite campos extra.

**Una cola más que el diseño.** El diagrama del paso 4 va de `procesos-listos` directo al worker que normaliza. Aquí la apertura reparte el proceso en un mensaje `normalizar` por entrega. Así cada oferente se normaliza en paralelo y por separado (R6), cada mensaje dura lo de un oferente (de 3 a 43 s el típico, 149 s el más grande de la muestra) y no lo de todo el proceso, y una falla solo repite su entrega. El bloqueo de un mensaje de Service Bus dura como máximo 5 minutos y hay que renovarlo si el trabajo tarda más; con mensajes por entrega casi nunca hace falta, pero el bucle de la entrega 2 lo renueva igual (en memoria no hay bloqueo que venza).

Detalles de la cola `normalizar` (acordados el 2026-11-06):

- **Unidad: la entrega.** Por proceso se pierde el paralelo y el aislamiento; por archivo se rompe el manifiesto y la detección de copias de la normalización, que trabajan por entrega.
- **Máximo 2 entregas en paralelo**, como parámetro (`paralelo_normalizar`). Cada conversión con LibreOffice usa cerca de un CPU. Se ajusta después de medir; si llegan varios procesos juntos, la cola guarda el resto. En la versión local el comando `orquestar` respeta el mismo límite.
- **Quién mira OneLake.** Si el aviso trae `archivos`, la apertura reparte con esa lista sin leer nada. Si no, lista las carpetas de `ruta`, con la misma identidad que usa la normalización. Se anota en A-1.
- **Mensaje repetido o trabajador caído:** la normalización reusa lo que ya quedó escrito y los `clasificar` repetidos se ignoran por su clave. No hace falta lógica nueva.
- **Imagen aparte.** Solo este manejador necesita LibreOffice (1,2 GB). En la entrega 2 va en su propia imagen y los demás manejadores en una liviana. El código no cambia.

## Estado

Un documento por entidad, todos con `id_proceso` (será la partición en Cosmos), `estado`, `historial` (lista de `{de, a, cuando, motivo}`) y `version` (para el cambio condicional).

| Entidad | Identificador | Estados en esta entrega | Además guarda |
|---|---|---|---|
| Proceso | `id_proceso` | `abierto` | Versiones fijadas, ruta de origen, fecha del aviso |
| Oferente (su entrega) | `id_oferente` o `PROCESO` | `recibido` → `procesando`; `error_proceso` si la normalización de la entrega falla entera | Conteos se calculan; no se guardan (decisión 15) |
| Documento | `id_documento` (el de la normalización) | Nace `normalizado`, `duplicado` o `error_entrada`; `normalizado` → `clasificado`, `esperando_clasificacion_humana` (respuesta inválida) o `error_proceso` | Hash, URI del PDF y la lectura, `duplicado_de` |
| Segmento | `id_segmento` = `<id_documento>-p<inicio>-<fin>` | `pendiente` (publicado a `extraer`); `sin_extraccion` (TD-98, TD-99); `esperando_clasificacion_humana` (confianza baja) → `pendiente` o `sin_extraccion` | TD, subtipo, confianza, `clasificacion_dudosa`, quién asignó el TD si fue humano |
| Tarea humana | `<clase>-<id del documento o segmento>` | `abierta` → `resuelta` | Clase (`clasificacion`, `documento_con_error`, `falla_tecnica`), motivo, resolución |

Los estados `extrayendo` en adelante, `en_revision`, `listo_para_reglas` y los de la ficha del proceso se usan en la entrega 2. El identificador de la tarea es determinista, así que crearla dos veces no la duplica (R27).

`orquestador.consultar(id_proceso)` devuelve, por oferente, cuántos documentos y segmentos hay en cada estado y las tareas abiertas (R25).

## Cómo se decide cada cosa

### Entregas del proceso (supuesto de A-1)

Si el aviso trae `archivos`, manda esa lista. Si no, la carpeta `ruta` trae una subcarpeta por entrega: `PROCESO/` para los documentos del proceso y una por oferente, con su identificador como nombre. Cualquier otra cosa en la raíz se registra como error del aviso, a operación. Es lo único que cambia cuando el módulo 1 responda A-1, y queda en una sola función.

### Versiones fijadas (R5)

Un archivo de datos, `versiones.json`, con las vigentes: `modelo_extraccion`, `ontologia`, `reglas` y `umbrales`. La apertura copia las vigentes al proceso con `crear_si_no_existe`: si dos avisos llegan a la vez, gana el primero (decisión 5 y paso 4). La versión del normalizador y de sus parámetros se toma del paquete `normalizacion` y también queda en el proceso. Si al normalizar la versión del paquete no coincide con la fijada, es un error de proceso: el proceso no se normaliza con otra versión sin un `reprocesar` (entrega 2).

### Umbrales (R12, R13)

`datos/umbrales/<versión>.json`: un umbral por TD que se extrae (0,85 a 0,95, según la matriz) y el piso de 0,75. Sin valor por defecto: un TD sin umbral es un error de datos. Lo carga la versión fijada en el proceso, no la vigente.

### Validación de la respuesta del clasificador (R11)

Las páginas de todos los segmentos cubren de 1 a `paginas` sin huecos ni solapes, cada TD está en la lista de TD de la matriz (más TD-98 y TD-99) y la confianza está entre 0 y 1. Si falla: se publica de nuevo con `intento + 1` una sola vez; la segunda falla crea la tarea de clasificación y deja el documento en `esperando_clasificacion_humana`.

### Clasificador falso

Lee un CSV con columnas `id_oferente, ruta_origen, pagina_inicio, pagina_fin, tipo_documental, confianza`. Un documento sin filas devuelve TD-99 con confianza 1; páginas vacías en el CSV significan "todo el documento". Para la muestra, un script convierte `Documentos/clasificados/manifiesto.csv` (columnas `tipo_documental, oferente, archivo, origen, nota`) a esta forma, fuera del repositorio.

### Errores y reintentos (R18 a R23)

Un bucle común envuelve a todos los manejadores y traduce cada excepción a su clase del paso 4:

| Excepción | Clase | Qué hace el bucle |
|---|---|---|
| `ErrorDelDocumento` | 1 | Lo registra el manejador como `error_entrada` y crea la tarea; el mensaje se completa |
| `ErrorTransitorio(espera=None)` | 2 | Publica de nuevo con demora 2, 4 y 8 minutos e `intento + 1`; al cuarto, `error_proceso`, a errores y alerta. Si trae `espera` (límite de uso), publica con esa demora sin subir `intento` |
| `RespuestaInvalida` | 3 | Lo maneja el clasificador (R11) |
| Cualquier otra | 4 | A errores sin reintento, `error_proceso` y alerta |

La "alerta" en esta entrega es un registro con nivel `ERROR` y los identificadores; en la entrega 2 se conecta a Application Insights. Reenviar desde errores es una función, `reenviar_errores(cola)`, que publica de nuevo con `intento = 1`.

**Escalamiento a 24 horas (R22):** `escalar_fallas(ahora)` busca documentos en `error_proceso` con más de 24 horas (configurable) y sin tarea, y crea la tarea `falla_tecnica`. En producción será un job programado; aquí se prueba con el reloj inyectable.

### Errores de la normalización

`normalizar_entrega` ya separa los dos casos: los documentos que no se pueden procesar quedan en el manifiesto con `error_entrada` (clase 1, R8), y un bug en algún documento lanza `ErrorEntrega` al final, sin manifiesto (clase 4). En ese caso los documentos de esa entrega quedan en `error_proceso` y el mensaje va a errores; al reenviarlo, la normalización reusa lo que ya estaba bien.

### Solicitudes de extracción (R16, R17)

Por cada segmento que se extrae: `contrato`, `id_proceso`, `id_oferente` (sin él si es del proceso), `id_segmento`, `id_documento`, `archivo` (URI y hash del PDF normalizado), `paginas`, `tipo_documental`, `lectura`, `anexos`, `version_modelo` del proceso, `confianza_clasificacion` y `clasificacion_dudosa`. Se valida contra el esquema 0.2 antes de publicar: si no cumple, es un bug (clase 4).

### Comando local

```
orquestar --origen <carpeta del proceso> --proceso SR… --clasificacion <csv> --salida <carpeta>
```

Publica el aviso, corre los manejadores hasta vaciar las colas (con el reloj adelantado para las demoras), guarda el estado y las solicitudes de extracción en `<salida>` e imprime **solo conteos**: documentos y segmentos por estado, solicitudes por TD, tareas por clase, mensajes en errores y tiempo. `<salida>` trae datos personales y no va al repositorio.

## Estructura

```
servicios/orquestador/
  README.md
  pyproject.toml                # depende de normalizacion por ruta
  src/orquestador/
    __init__.py                 # VERSION
    datos/versiones.json            # las vigentes
    datos/umbrales/<versión>.json   # un archivo por versión; los publicados no se editan
    datos/tipos_documentales/<versión>.json   # TD-01 a TD-35, TD-98 y TD-99
    datos.py  contratos.py
    cola.py  estado.py  origen.py  clasificador.py  reloj.py   # interfaces y versiones locales
    errores.py                  # clases de error y bucle común
    apertura.py                 # procesos-listos
    normalizar.py               # normalizar
    clasificar.py               # clasificar, umbrales, segmentos
    extraer.py                  # solicitudes 0.2
    tareas.py                   # crear, resolver, escalar
    consulta.py
    cli.py                      # comando orquestar
  tests/
  scripts/correr_muestra.py
```

## Pruebas

Todo con documentos inventados: unos pocos PDF hechos con `reportlab` (no hace falta LibreOffice), un PDF con contraseña con `pikepdf` y una copia exacta. El clasificador falso usa un CSV escrito en la prueba.

| Caso | Qué se comprueba |
|---|---|
| Aviso válido, inválido y repetido | R1, R2 |
| Carpeta con `PROCESO/` y dos oferentes, más algo suelto en la raíz | R4 |
| Dos aperturas a la vez | Gana la primera; las versiones no cambian al cambiar `versiones.json` (R5) |
| Entrega con una copia y un documento con contraseña | R7, R8, R10 |
| Clasificación normal, dudosa, baja, TD-98, TD-99, compuesta e inválida dos veces | R11 a R14 |
| Resolver una tarea de clasificación | R15 |
| Solicitudes contra el esquema 0.2, con y sin oferente | R16, R17 |
| Clasificador que falla 2 veces y luego responde; que falla siempre; que pide esperar | R19 |
| Manejador que lanza una excepción cualquiera | R20, R21 |
| Reloj adelantado 24 horas | R22 |
| Cada mensaje entregado dos veces | R26, R27 (A3) |
| Punta a punta | A2 |

## Chequeo de Constitución

| Principio | ¿Cumple? | Cómo |
|---|---|---|
| 1. El proceso manda sobre la tecnología | Sí | La spec no nombra tecnología; este plan la elige |
| 2. Condiciones como datos | Sí | Umbrales, versiones y lista de TD son datos con versión. No hay condiciones del proceso en esta entrega |
| 3. Veredicto trazable | Sí | Cada cambio de estado guarda cuándo y por qué; el segmento guarda su clasificación y quién la asignó si fue humano; las versiones quedan fijadas en el proceso |
| 4. La IA extrae y el evaluador decide | Sí | Baja confianza no se extrae sin una persona; confianza media se marca para revisión |
| 5. Contrato primero | Sí | T01 escribe el contrato del orquestador y el 0.2 de extracción antes del código. Módulo 1, clasificador y extracción se reemplazan por dobles |
| 6. Datos personales | Sí, con condición | El orquestador no extrae datos; registros solo con identificadores; pruebas inventadas; la muestra se corre local e imprime conteos |
| 7. Igualdad de trato | Sí | Versiones fijadas en la apertura y leídas del proceso, nunca de las vigentes |

**Mínimo necesario:** colas y estado ya están decididos en el diseño (decisión 16). Aquí no se agrega ningún servicio: solo interfaces y su versión en memoria.

## Complejidad y excepciones

- **Cola `normalizar`, que el diseño no tenía.** Ver "Mensajes internos". La alternativa más simple, normalizar todo el proceso en un solo mensaje, se descarta por el tiempo y por el aislamiento entre oferentes.
- **El estado en memoria no es el de producción.** Las pruebas de cambio condicional y de mensajes repetidos pasan contra la versión en memoria; con Cosmos hay que repetirlas en la entrega 2.

## Riesgos

- **El clasificador real puede no parecerse al falso** (C1 a C3). Solo cambia `clasificador.py`; la validación y los umbrales siguen.
- **Las carpetas del módulo 1 pueden no seguir el supuesto** (A-1). Solo cambia la función que reparte entregas.
- **Dos entregas en paralelo puede quedarse corto** con varios cierres el mismo día: 10 oferentes de 40 s son unos 3 a 4 minutos por proceso. Es un parámetro; se sube después de medir.
