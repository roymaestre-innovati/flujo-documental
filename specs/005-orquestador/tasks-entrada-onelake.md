# Tareas 005 — Entrada desde OneLake: primera versión

Es la primera pieza de la entrega 2 del orquestador: la interfaz `Origen` deja de ser una carpeta local y lee los archivos del módulo 1 en OneLake (plan, tabla de interfaces). El resto de la entrega 2 (Service Bus, Cosmos, Blob Storage, Container Apps) no entra aquí.

**Meta:** correr `orquestar` en la máquina del equipo sobre un evento real de `workspace-evaluacionofertas-dev`, leyendo directo de OneLake, sin copiar los originales, y llegar a los mismos conteos que reporta el módulo 1 en sus tablas.

**Estado al 2026-11-18:** por empezar. La prueba de acceso está hecha (`servicios/prueba-onelake/`, paso 0 del diseño).

## Dónde va

En el **orquestador**, no en la normalización ni en un servicio nuevo:

- La normalización recibe una carpeta local y no sabe de dónde vienen los archivos. Así se queda, y se prueba sin Azure.
- El orquestador ya tiene la interfaz `Origen` (`listar` y `bajar`) y el manejador `Normalizar`, que baja los originales a una carpeta temporal que se borra al terminar. Falta la versión de OneLake.
- El reparto entre el proceso y los oferentes ya está en la apertura (`repartir`), y es lo que hay que adaptar a las carpetas del módulo 1.

Un servicio aparte solo agregaría una copia de los originales o un salto de red más, y el diseño los evita (decisión 32).

## Para quien implemente

- Leer antes el paso 0 de `contexto/flujo-documental-opcion-a.md` ("Cómo leemos los archivos de Fabric"), `plan.md` y `tasks.md` de esta carpeta.
- Las pruebas usan un cliente de OneLake falso, en memoria, con carpetas inventadas que imitan la forma del módulo 1. Nada de Azure en las pruebas. Solo T06 toca OneLake, y la corre el usuario en su máquina.
- Con datos reales, por pantalla y en los registros salen solo conteos, extensiones y tamaños. Nunca nombres de oferentes, de carpetas ni de archivos (principio 6).
- `servicios/normalizacion/` no se toca. Si algo hace falta cambiarle, se anota aquí y se le pregunta al usuario antes.
- Mismo flujo que en `tasks.md`: rama, pruebas en verde, notas aquí, commit y **alto para revisión del usuario** después de cada tarea.

## Tareas

- [x] **T01 — Metadatos del módulo 1.** Hecha el 2026-11-20 con `servicios/prueba-onelake/revisar_metadatos.py` (ver la nota de T01). **El reparto sale de las tablas del módulo 1, no de listar carpetas** (decidido por el usuario). Es provisional: el módulo 1 prometió una vista con lo que necesitamos, y la definimos más adelante con lo que se use aquí (sección "Lo que usamos de las tablas"). Queda abierto:
  - **Identificador del proceso (decidido por el usuario, 2026-11-20):** el `event_id` (`Doc…`) es el `id_proceso`, y el proyecto (`WS…`) se guarda en el proceso. El `event_id` no cambia con las versiones del evento en Ariba ni de proyecto (nota de T01).
  - **Para el módulo 1:** ¿un proyecto puede llegar con más de un evento a evaluar (RFI y RFP, o una segunda ronda)? ¿Un evento en `DESCARGADO` puede recibir adjuntos nuevos? ¿Se pueden borrar los archivos huérfanos de `_contenido/` (134 en tres eventos)? ¿Cómo se pasa del evento al SR, si el negocio lo necesita?

- [x] **T02 — `OrigenOneLake`.** En `servicios/orquestador/src/orquestador/origen_onelake.py` (ver la nota de T02), con `azure-identity` y `azure-storage-file-datalake` como dependencias.
  - Se configura con workspace, lakehouse y `DefaultAzureCredential`.
  - Las rutas son relativas a `Files/`.
  - `listar` es recursivo, devuelve solo archivos, en orden y relativos a la carpeta. Con el reparto por tabla ya no lo usa la apertura, pero sirve para la revisión de T06.
  - `bajar` escribe al disco por partes, no carga el archivo entero en memoria (hay RAR de 78 MB). Si recibe el tamaño y el MD5 esperados (de la tabla), los revisa; si no coinciden, es un error de proceso, no del documento.
  - Errores: 404 es `ErrorOrigen`; 429, 5xx y timeouts son `ErrorTransitorio`; 401 y 403 son una falla de configuración que va a operación sin reintentos.
  - Pruebas con el cliente falso, incluidas una ruta con `..` y un MD5 que no coincide.

- [ ] **T03 — Reparto con las tablas del módulo 1.** Un módulo nuevo del orquestador (`entrada_modulo1.py`) lee las dos tablas Delta por OneLake (`deltalake`, versión vigente) y arma, para un `event_id`, la lista `archivos` del aviso (`ruta` e `id_oferente`) que ya define el contrato `proceso-listo`. La apertura no cambia: reparte con esa lista, como hoy. Cuando llegue la vista, solo cambia este módulo.
  - `doc_category = DOCUMENTOS_PROCESO`: documento del proceso (`id_oferente` vacío).
  - `doc_category = OFERENTE`: el `id_oferente` es el `sm_vendor_id` de `oferentes_control`, cruzando por `event_id` e `invitation_id`. Una fila de oferente que no cruza rechaza el aviso: no se reparte a ciegas.
  - Cualquier otro valor de `doc_category` rechaza el aviso.
  - Las rutas (`adls_path`) son relativas a la carpeta del shortcut (`informacion-adjuntos/`). Las repetidas cuentan una vez.
  - **Comprimidos (decidido por el usuario, 2026-11-18):** solo se baja lo descomprimido. Las filas con `is_compressed_archive = True` no entran en ninguna entrega, tampoco las que vienen dentro de `_contenido/`.
  - Un comprimido sin filas hijas (ninguna con su `idempotency_key` como `parent_archive_key`) no se baja, pero no se calla: genera una tarea `documento_con_error` con motivo `comprimido_sin_contenido`, en la entrega a la que pertenece, para que no se evalúe a nadie con documentos de menos. En la muestra hay 6.
  - Lo que no está en la tabla (los JSON del módulo 1 y los archivos huérfanos) no entra. El MD5 y el tamaño de cada fila se pasan a `bajar` (T02).
  - Lo excluido se cuenta en el registro de la apertura, por motivo.
  - Ojo: con `deltalake` la lectura termina en segundos, pero el proceso se quedó colgado al salir en dos de tres corridas (2026-11-20). Reproducirlo y, si sigue, leer el log de Delta con `pyarrow` o cerrar sus hilos. Un job que no termina no se puede usar.
  - Pruebas con tablas inventadas (filas en memoria, sin Delta): proceso y dos oferentes, un RAR con hijos, un ZIP dentro de otro, un RAR sin hijos, una ruta repetida, un oferente que no cruza y una categoría desconocida.

- [ ] **T04 — Bajar en paralelo.** `Normalizar` baja hoy los archivos de uno en uno. A ~1,5 MB/s por archivo, un oferente de 200 MB tarda más de 2 minutos solo en bajar.
  - Se baja con varios hilos (`paralelo_bajar`, 8 por defecto) a la misma carpeta temporal. Cada archivo cuesta ~1,8 s de latencia aunque sea chico (nota de T02): la entrega más grande, con 57 archivos, tarda ~100 s en serie y ~15 s con 8 hilos.
  - Tamaños de la muestra sin comprimidos (2026-11-20): la entrega más grande pesa 106 MB (57 archivos), la mediana 7 MB y el archivo más grande 11 MB. El disco efímero de una réplica de 0,5 vCPU basta.
  - Si un archivo falla, falla la entrega, como hoy.
  - Se mide en T06 y se ajusta el valor.

- [ ] **T05 — Comando.** `orquestar` acepta `--onelake-workspace`, `--onelake-lakehouse` y `--evento <event_id>` en lugar de `--origen`, y arma el aviso con la lista de T03 y el identificador del proceso que salga de T01. Sin `--clasificacion` sigue saliendo todo TD-99. Prueba de punta a punta con el cliente falso. README del orquestador actualizado.

- [ ] **T06 — Corrida con un evento real.** La corre el usuario en su máquina, con `az login`, sobre el evento más chico de `fase2/` (39 archivos del proceso y 6 oferentes, o 21 y 9).
  - Debe imprimir solo conteos: filas de la tabla, archivos excluidos por motivo, bajados, MB y tiempo de descarga. También, para revisar la tabla: cuántos archivos hay en la carpeta del evento que no están en la tabla (sin contar los JSON).
  - Debe imprimir también los documentos normalizados, copias exactas y errores por tipo, y compararlos con los `file_status` de `adjuntos_metadata` de ese evento.
  - La salida va fuera del repositorio y se borra al terminar.
  - Criterio: cada fila de documento de la tabla queda en una entrega, no se baja ningún ZIP ni RAR y cada comprimido sin contenido tiene su tarea.

- [ ] **T07 — Cierre.** Notas de lo encontrado aquí. Actualizar el paso 0 y A-1 del diseño, la tabla de interfaces de `plan.md` ("Lo que cambió al implementar") y el README del repo.

## Fuera de esta versión

- La identidad administrada del job y el acceso en producción. Se pide al módulo 1 (A-1) y se prueba al desplegar en Container Apps.
- El aviso real por Service Bus. Aquí el aviso lo arma el comando.
- La vista del módulo 1. Se define después con la sección siguiente; mientras tanto se leen sus tablas internas, que pueden cambiar sin aviso.

## Lo que usamos de las tablas

Es el borrador de lo que le pediremos al módulo 1 en la vista. Se actualiza en cada tarea si se usa algo más.

| Tabla | Columna | Para qué |
|---|---|---|
| `bronce.tbl_evaluacionofertas_adjuntos_metadata` | `event_id` | Filtrar el proceso |
| | `doc_category` | Proceso u oferente |
| | `invitation_id` | Cruzar con el oferente |
| | `adls_path` | Ruta del archivo |
| | `downloaded_bytes`, `md5_hex` | Revisar lo bajado |
| | `is_compressed_archive`, `idempotency_key`, `parent_archive_key` | Excluir comprimidos y detectar los que no tienen contenido |
| `bronce.tbl_evaluacionofertas_oferentes_control` | `event_id`, `invitation_id` | Cruce |
| | `sm_vendor_id` | Identificador del oferente |
| `control.tbl_evaluacionofertas_eventos_control` | `event_id`, `parent_project_id` | Identificador del proceso y del proyecto de Ariba |
| | `control_status`, `total_files_failed` | Saber que el evento terminó de descargarse (`DESCARGADO`, sin fallidos): es lo que dispararía el aviso |

Lo ideal en la vista: una fila por documento descargado de un evento en `DESCARGADO`, con el evento, el proyecto, el SR si existe, el identificador del oferente (vacío en los del proceso), la ruta, el tamaño, el MD5 y la marca de comprimido sin contenido, sin los comprimidos y sin restos de corridas viejas. Así sobraría todo el cruce de T03.

## Notas de implementación

### T01 — Revisión de las tablas (2026-11-18)

Versión vigente de las tablas, leída con `deltalake` (5 s cada una). Solo conteos.

- `adjuntos_metadata`: versión 8, 310 filas, 4 eventos. `doc_category`: 172 `DOCUMENTOS_PROCESO` y 138 `OFERENTE`. `file_status`: 108 `EXITOSO` y 202 `YA_EXISTIA_IDENTICO`.
- Las 310 filas existen en la carpeta y el tamaño coincide con `downloaded_bytes` en todas. Hay 10 rutas repetidas.
- Comprimidos: 18 filas con `is_compressed_archive`. Las 136 filas que salen de un comprimido encuentran su padre por `parent_archive_key`. Hay 6 comprimidos sin ninguna fila hija.
- `oferentes_control`: versión 7, 20 oferentes, todos con `sm_vendor_id`. 10 con `has_bid = False`: falta saber si se evalúan.
- El cruce por `event_id` e `invitation_id` funciona para las 138 filas de oferente. Las filas del proceso también traen `invitation_id`, pero no cruzan, como se espera.
- En la carpeta hay 168 archivos que no están en la tabla:
  - 34 son los JSON del módulo 1.
  - 134 están dentro de `_contenido/`, en carpetas sin ninguna fila en la tabla. Todos se escribieron entre las 21:04 y las 21:05 del 2026-10-21, con la misma profundidad que los registrados. Parecen una descompresión de una corrida vieja que quedó huérfana. Listando carpetas habrían entrado dos veces: es la razón principal para repartir con la tabla.

### T01 — Cierre (2026-11-20)

Corrida de `revisar_metadatos.py` (versiones: `adjuntos_metadata` 8, `oferentes_control` 7, `eventos_control` 15).

- **Eventos:** `eventos_control` tiene 118 eventos de Ariba (102 RFP, 15 RFI y 1 subasta). Solo 4 están en `DESCARGADO`, y son los 4 que tienen adjuntos, todos sin archivos fallidos. Los demás: 51 `NO_ELEGIBLE_TIPO`, 37 `ELEGIBLE` y 26 `EN_SEGUIMIENTO`.
- **Identificadores:** el `event_id` tiene la forma `Doc` y 10 dígitos, y es el nombre de la carpeta bajo `fase2/`. Cada evento tiene un solo proyecto, `parent_project_id`, con la forma `WS` y 10 dígitos. Ninguna tabla trae el SR (`eventos_listados` solo trae evento, proyecto y fechas).
- **Tabla contra carpeta, por evento:**
  - Todas las filas existen y coinciden en tamaño.
  - El evento 4 trae 10 rutas repetidas.
  - Los archivos huérfanos están en los eventos 1, 2 y 3 (53, 53 y 28). El evento 4, que no tiene comprimidos, no tiene huérfanos.
- **Oferentes:** todas las filas de oferente cruzan con `oferentes_control`. Los 10 oferentes con `has_bid = False` no tienen ningún archivo, así que no llegan al reparto. Ya no hace falta preguntarlo.
- **Comprimidos:** 18 en total. Sin filas hijas: 3 en el evento 1, 2 en el 2, 1 en el 3 y ninguno en el 4. Son los que generan la tarea `comprimido_sin_contenido`.
- **Fuera de `fase2/`:** hay 55 archivos en otras dos carpetas del shortcut (una con nombre de evento y `mvp`), de corridas anteriores. No están en la tabla y no entran.
- **JSON del módulo 1:** cuatro formas, ninguna es un documento del oferente.
  - Ficha del oferente (20): `event_id`, `invitation_id`, `sm_vendor_id`, `participation_status`, `has_bid` y el nombre. Es lo mismo que `oferentes_control`.
  - Ofertas por ítem (10): `payload` con `eventId`, `itemId`, `invitationId`, `bidStatus`, `submissionDate` y el ítem.
  - Contenido del evento (14, en dos formas): `payload` con los ítems del evento, su `title` y sus `terms`, que son las preguntas y condiciones del evento en Ariba.

  Los `terms` pueden servir más adelante para la ficha del proceso (módulo 4); por ahora no entran.

### T01 — ¿El `event_id` es estable? (2026-11-20)

Revisión de la historia de las tablas Delta, todas sus versiones (desde octubre de 2026):

- El `event_id` se mantiene con las versiones del evento en Ariba. `document_version` llega hasta 17, y 14 eventos cambiaron de versión durante el seguimiento con el mismo `event_id`.
- Ningún evento cambió de proyecto, y ningún proyecto tiene más de un evento en estos datos.
- En toda la historia de `adjuntos_metadata` hay 444 claves de archivo, y ninguna cambió de ruta ni de MD5: un archivo que cambia entra como uno nuevo. La versión vigente tiene 310 claves. Las 134 que faltan son justo los archivos huérfanos: el módulo 1 borró esas filas en una corrida y dejó los archivos.
- Sin ver todavía: un proyecto con varios eventos, y adjuntos nuevos en un evento ya `DESCARGADO`. Con el versionado por MD5, esos adjuntos llegarían como filas nuevas del mismo evento, es decir, como documentos tardíos (A-10, sin diseñar).

### T02 — `OrigenOneLake` (2026-11-20)

- **Módulo aparte:** `origen_onelake.py`, no `origen.py`. Así `OrigenLocal` y las pruebas que no tocan OneLake no importan el SDK de Azure.
- **`bajar` recibe un `esperado` opcional** (`Esperado(tamano, md5)`) en la interfaz `Origen`, y lo revisan las dos versiones. Si no coincide, borra lo bajado y lanza `ArchivoDistinto`, que es un `ErrorOrigen`: en `Normalizar` se reintenta como una descarga fallida. Por ahora nadie le pasa `esperado`; lo conecta T03.
- **Un 401, un 403 o una identidad que falta** (por ejemplo, `az login` vencido) lanzan `ErrorDeAcceso`. No es un `ErrorOrigen`, para que `Normalizar` no lo reintente: va a errores como clase 4, y el motivo dice "Bug" con el lugar de la excepción. Lo anoto por si el usuario prefiere una clase propia de "configuración" en `errores.py`.
- **408, 429 y 5xx, y las fallas de red,** son `ErrorTransitorio`, con `Retry-After` como espera cuando viene. Otro código sale tal cual, como bug.
- **Pruebas:** 21 nuevas con un cliente falso (`tests/test_origen_onelake.py`). La suite completa pasa: 212 pruebas.
- **Humo contra OneLake real** (usuario del equipo, `az login`; solo conteos):
  - `listar` de `fase2/` y de un evento de 81 archivos: 6,2 s.
  - Bajar 5 PDF (3,9 MB): 9,2 s con 1 parte por archivo y 8,5 s con 4, unos 1,8 s por archivo.
  - El SDK solo parte los archivos de más de 32 MB, así que la concurrencia por archivo casi no cambia nada. La latencia por archivo es lo que pesa, y se ataca en T04 bajando varios archivos a la vez.
  - Una carpeta que no existe da `ErrorOrigen`.
