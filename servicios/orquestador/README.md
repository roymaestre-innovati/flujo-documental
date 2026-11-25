# Orquestador

Lleva cada proceso de selección desde el aviso del módulo 1 hasta las solicitudes de extracción (iniciativa 005, entrega 1). La spec, el plan y las tareas están en `specs/005-orquestador/`; los contratos, en `contracts/modulo5-orquestador/v0.2/` y `contracts/modulo3-extraccion/v0.2/`.

**Estado**. Entrega 1 cerrada (T01 a T11), en local. El resultado con la muestra real está en la nota de T11 de `tasks.md`. De la entrega 2 está cerrada la entrada desde OneLake (`tasks-entrada-onelake.md`, 2026-11-23): `orquestar` arma el aviso con las tablas del módulo 1, lee los originales de OneLake y ya corrió un evento real. También están las versiones de Azure de `Estado` (Cosmos con la API de MongoDB, ya probada contra la base de desarrollo) y de `Cola` (Service Bus, lista para probar cuando estén los roles), en `tasks-estado-cola-azure.md`. `AlmacenBlob` ya está implementado y falta probarlo contra el contenedor de desarrollo (T04 de `tasks-almacen-blob.md`). Los workers (`orquestar-worker`, `extraer-worker` y `orquestar-operar`) están hechos y probados con clientes falsos, y esperan los roles para correr contra Azure (`tasks-workers.md`). Su configuración está en `servicios/workers/README.md`.

## Cómo funciona

```
aviso del módulo 1 ──► procesos-listos ──► Apertura ──► normalizar (una por entrega, 2 a la vez)
                                                            │
                                     Normalizar ◄───────────┘
                                         │  un mensaje por documento normalizado
                                         ▼
                                     clasificar ──► Clasificar ──► extraer (contrato 0.2)
                                                        │
                                                        └──► tareas para una persona
```

1. **Apertura** valida el aviso, reparte los archivos entre la entrega del proceso (`PROCESO/`) y la de cada oferente, fija las versiones del proceso y publica un `normalizar` por entrega.
2. **Normalizar** baja los originales a una carpeta temporal, llama a la normalización (iniciativa 003), registra cada documento y publica un `clasificar` por cada uno normalizado. Las copias exactas no se clasifican; los documentos con error generan una tarea `documento_con_error`.
3. **Clasificar** llama al clasificador, revisa la respuesta, aplica los umbrales y crea los segmentos. Cada segmento que se extrae sale a `extraer`; TD-98 y TD-99 no se extraen; los de confianza baja esperan a una persona con una tarea `clasificacion`.
4. **Resolver** una tarea de clasificación (`resolucion.py`) aplica el tipo que asignó la persona y pide la extracción. En la entrega 2 lo dispara la Power App.
5. **Escalar** (`tareas.escalar_fallas`) convierte en tarea `falla_tecnica` lo que lleva más de 24 horas en error de proceso.

Cada manejador es idempotente: un mensaje repetido no duplica nada. Las fallas siguen las clases de error del diseño: reintentos, cola de errores y alerta a operación (`errores.py`).

## Instalar y probar

Python 3.12 y `uv`. Desde esta carpeta:

```bash
uv sync
uv run pytest
```

La normalización (`../normalizacion`) se instala como dependencia de ruta, editable: un cambio allá se ve aquí sin reinstalar. Las pruebas del orquestador no necesitan LibreOffice, salvo una marcada `libreoffice` (un Excel de punta a punta), que se salta si `soffice` no está instalado.

### Pruebas contra Azure

Las pruebas marcadas `azure` usan los recursos de desarrollo y nunca corren en la suite normal: piden `--azure` y su variable de entorno, y si falta alguna se saltan. Usan solo datos inventados (`PRUEBA-<uuid>` en el estado) y borran lo suyo al terminar. Si falta un permiso, la corrida se detiene en la primera prueba con una sola línea.

| Variable | Para qué | Por defecto |
|---|---|---|
| `ESTADO_MONGO_URL` | Cadena de conexión de la cuenta de Cosmos (API de MongoDB). Es un secreto: nunca se imprime ni se guarda | — |
| `ESTADO_MONGO_BASE`, `ESTADO_MONGO_COLECCION` | Base y colección del estado | `evaluacion_ofertas`, `estado` |
| `SERVICEBUS_NAMESPACE` | Nombre completo del namespace (`<namespace>.servicebus.windows.net`). Se entra con `DefaultAzureCredential` (`az login` en local) | — |
| `COLAS_PREFIJO` | Prefijo de las colas en Service Bus | `evaluacion-ofertas-` |

```bash
# Estado en Cosmos (unos 40 s) y medición de RU (unos 5 s)
read -rs ESTADO_MONGO_URL; printf '\n'; export ESTADO_MONGO_URL
uv run pytest --azure -m azure -v -k estado
uv run python scripts/medir_ru_estado.py
unset ESTADO_MONGO_URL

# Cola en Service Bus (1 a 3 minutos). Necesita los roles Data Sender y Data Receiver
# y que nadie más esté usando las colas de desarrollo.
export SERVICEBUS_NAMESPACE='<namespace>.servicebus.windows.net'
uv run pytest --azure -m azure -v -k cola
# Renovación del bloqueo: mantiene un mensaje 6 minutos
SERVICEBUS_PRUEBA_LARGA=1 uv run pytest --azure -m azure -v -s tests/test_cola_servicebus_azure.py
```

Las pruebas de Blob se corren desde `servicios/normalizacion`. Los comandos y el rol están en el [README de la normalización](../normalizacion/README.md#pruebas-contra-azure).

## Correr un proceso en local

```bash
uv run orquestar --origen <carpeta del proceso> --proceso SR0000000001 \
                 --clasificacion <csv> --salida <carpeta fuera del repo>
```

- `--origen`: la carpeta del proceso, con `PROCESO/` y una subcarpeta por oferente, nombrada con su identificador. Un archivo suelto en la raíz rechaza el aviso.
- `--clasificacion` recibe el CSV opcional del clasificador falso, con las columnas `id_oferente` (vacío para los documentos del proceso), `ruta_origen` (relativa a la carpeta de la entrega), `pagina_inicio` y `pagina_fin` (vacíos para todo el documento), `tipo_documental`, `confianza` y, opcional, `subtipo`. Un documento que no está en el CSV sale como TD-99. Al omitir el CSV, todos los documentos clasificados salen como TD-99.
- `--paralelo`: entregas que se normalizan a la vez (2 por defecto). Cada conversión con LibreOffice usa cerca de un CPU.
- `--paralelo-bajar` controla cuántos archivos se bajan a la vez por entrega (8 por defecto). Ambos valores de paralelo deben ser de 1 o más.
- `--registros <archivo>`: registros en JSON, solo con identificadores. Sin él, por pantalla salen solo las advertencias.
- `--soffice`: la ruta de LibreOffice, si no está en el `PATH`.

Por stdout salen **solo conteos**: entregas, documentos y segmentos por estado, solicitudes por tipo documental, tareas abiertas por clase y motivo, registros atascados (en un estado intermedio sin tarea; debe ser 0), mensajes en errores y tiempo. En `<salida>` quedan `estado.json`, `solicitudes-extraccion.jsonl`, `errores.json` y `conteos.json`. **Todo eso trae datos personales**: el comando se niega a escribir dentro de un repositorio git. Termina con 0 si nada quedó en errores, 1 si algo quedó y 2 si los argumentos están mal.

El almacén queda por defecto en `<salida>/almacen/`. Si está configurada `ALMACEN_BLOB_CUENTA`, `orquestar` escribe el almacén en Blob y avisa por stderr. Esto aplica con entrada local o desde OneLake. Ver el [README de la normalización](../normalizacion/README.md#almacén-en-blob-storage).

El comando adelanta el reloj simulado para los reintentos. Con Blob real, reintenta un 429 sin hacer en tiempo real la espera que pide el servicio. Si algo queda en errores, se ve en `errores.json` con su motivo.

## Correr un evento desde OneLake

Desde esta carpeta, inicia sesión con una cuenta con permiso de lectura sobre el lakehouse. Ingresa el `event_id` de un evento en estado `DESCARGADO` y sin archivos fallidos.

```bash
az login
read -r -p 'event_id: ' EVENTO
SALIDA=$(mktemp -d /tmp/orquestador-onelake.XXXXXX)
uv run orquestar --onelake-workspace workspace-evaluacionofertas-dev \
                 --onelake-lakehouse lkh_evaluacionofertas_bronce \
                 --evento "$EVENTO" --salida "$SALIDA"
```

Las tres opciones de OneLake reemplazan a `--origen` y `--proceso`. El comando arma el aviso 0.2 con las tablas del módulo 1, usa el `event_id` como identificador del proceso y baja los archivos de ese mismo lakehouse. La apertura registra una tarea por cada comprimido sin contenido. Los ZIP y RAR quedan excluidos del aviso. Las opciones de clasificación y paralelo son las mismas del modo local.

El resumen agrega los archivos del aviso, los excluidos por motivo, los comprimidos sin contenido, los archivos bajados y aceptados, sus MB decimales y los segundos con descargas en curso. El tiempo incluye los intentos fallidos y cuenta una sola vez las descargas simultáneas. Los archivos y bytes aceptados se cuentan por descarga, incluidos los que se vuelvan a bajar en un reintento de la entrega.

La salida queda fuera del repositorio git y tiene los mismos archivos y opciones de almacén que una corrida desde una carpeta local. Los originales se bajan a carpetas temporales que se borran al terminar cada entrega. Si se rechaza el evento, el comando imprime el motivo y termina con código 2.

## Correr la muestra real

Solo en la máquina del equipo (principio 6). Imprime solo conteos:

```bash
uv run python scripts/correr_muestra.py \
    --manifiesto ~/GEB/Extraccion/Documentos/clasificados/manifiesto.csv \
    --muestra ~/GEB/pruebas-normalizacion/muestra1 --muestra ~/GEB/pruebas-normalizacion/muestra
```

Convierte la clasificación manual al CSV del clasificador falso (`SIN CLASIFICAR` como TD-99, los huecos de una clasificación por páginas como TD-99), nombra los oferentes OF-001, OF-002… en el orden de las carpetas y corre todo. Con `--salida <carpeta vacía fuera del repo>` conserva el estado y las solicitudes para revisarlos a mano.

## Ver las corridas en el navegador

```bash
uv run visor --corridas <carpeta>
```

Abre `http://127.0.0.1:8766` con lo que dejó una corrida guardada con `--salida` (de `orquestar` o de `correr_muestra.py`). `<carpeta>` puede ser la salida de una corrida o una carpeta con varias, una por subcarpeta; se elige en la lista de arriba. Hay cuatro vistas:

- **Resumen:** conteos, una fila por entrega (clic para ver sus documentos), solicitudes por tipo documental, tareas por motivo y versiones fijadas.
- **Documentos:** la lista por entrega, con filtros (texto, entrega, estado, con tarea, dudosa). El detalle muestra los segmentos con su confianza frente al umbral y el piso, las tareas, la lectura página por página, el historial y la solicitud de extracción de cada segmento. "Ver PDF" abre el PDF normalizado al lado; un clic en una página lo lleva a esa página.
- **Extracción** (si la corrida tiene `extraccion/`, que deja el comando `extraer` del servicio de extracción): en el resumen, segmentos con resultado, campos en revisión por motivo y tokens. En el detalle de un documento, la columna "Extracción" de cada segmento y, debajo, una tabla por segmento con cada campo: valor, confianza frente al umbral de la ficha, `cumple`, motivos, evidencia (un clic en la página abre el PDF ahí) y reglas pendientes. Los campos en revisión van resaltados. El filtro "Con campos en revisión" deja solo esos documentos. El visor lee los archivos del contrato `modulo3-extraccion/0.2`; no importa el servicio de extracción.
- **Tareas:** todas, abiertas primero; un clic abre el documento.
- **Errores:** mensajes en las colas de errores y entregas con error.

Las corridas traen datos personales: el servidor solo escucha en 127.0.0.1 y solo sirve archivos del almacén local de la corrida (`file://`). Se puede mover la carpeta de una corrida local: los PDF se buscan en su `almacen/`. La página se recarga para ver una corrida nueva.

## Qué hay

| Archivo | Qué hace |
|---|---|
| `cola.py`, `cola_servicebus.py`, `errores.py`, `reloj.py` | Alias de los módulos de `servicios/mensajeria` (las colas, `ColaServiceBus`, el bucle y sus clases de error, y el reloj), que comparte con la extracción |
| `estado.py` | Almacén del estado y `EstadoEnMemoria`, con creación idempotente y escritura condicional, como Cosmos |
| `estado_mongo.py` | `EstadoMongo`: el `Estado` en Cosmos con la API de MongoDB (`pymongo`), con `id_proceso` como partición. Traduce el límite de RU a una espera |
| `estados.py` | Las cinco entidades (proceso, oferente, documento, segmento y tarea), sus transiciones, el historial, `consultar` y la reserva con dueño y vencimiento (`reservar`, `liberar`) |
| `origen.py` | Dónde están los originales: la interfaz `Origen` y `OrigenLocal`, una carpeta. `bajar` revisa el tamaño y el MD5 si se los dan |
| `origen_onelake.py` | `OrigenOneLake`: los originales en `Files/` de un lakehouse, con `DefaultAzureCredential`. Traduce las fallas de OneLake a las clases de error |
| `entrada_modulo1.py` | Arma el aviso de un evento con las tablas Delta del módulo 1 hasta que exista su vista |
| `clasificador.py` | `ClasificadorFalso`, con un CSV opcional |
| `contratos.py` | Valida mensajes contra los esquemas de `contracts/` |
| `datos.py` y `datos/` | Versiones vigentes, umbrales y tipos documentales, con un archivo por versión |
| `parametros.py` | Los de la mensajería (reintentos, demoras, bloqueo) más escalamiento, paralelo de normalización y descargas, y la duración de la reserva |
| `registros.py` | Registros en JSON, solo con identificadores |
| `apertura.py` | Manejador de `procesos-listos`: valida el aviso, reparte las entregas y fija las versiones |
| `normalizar.py` | Manejador de `normalizar`: baja los originales, llama a la normalización y registra los documentos |
| `clasificar.py` | Manejador de `clasificar`: revisa la respuesta, aplica los umbrales y crea segmentos y tareas |
| `extraer.py` | Arma y valida las solicitudes de extracción 0.2 y las publica en `extraer` |
| `tareas.py` | Tareas para una persona y el escalamiento a 24 horas |
| `resolucion.py` | Resolver una tarea de clasificación |
| `local.py` | Una corrida completa sobre las versiones en memoria, con la normalización en paralelo |
| `cli.py` | El comando `orquestar` |
| `entorno.py` | Las piezas de Azure de un worker, armadas desde el entorno, sin caer a lo local |
| `workers.py` | El comando `orquestar-worker apertura\|normalizar\|clasificar` |
| `operacion.py` | El comando `orquestar-operar reenviar-errores\|escalar-fallas` |
| `visor/` | El comando `visor`: servidor local y página para revisar corridas |

## Datos personales

Las pruebas usan solo datos inventados. Los registros y los motivos de error llevan identificadores, nunca texto de los documentos ni rutas de origen (principio 6).
