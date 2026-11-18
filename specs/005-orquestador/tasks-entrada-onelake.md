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

- [ ] **T01 — Metadatos del módulo 1.** Casi resuelta en la revisión del 2026-11-18 (ver la nota de T01): **el reparto sale de las tablas del módulo 1, no de listar carpetas** (decidido por el usuario). Es provisional: el módulo 1 prometió una vista con lo que necesitamos, y la definimos más adelante con lo que se use aquí (sección "Lo que usamos de las tablas"). Falta:
  - Cómo se pasa de `event_id` al identificador del proceso (SR…). Ver `tbl_evaluacionofertas_eventos_listados`.
  - Qué traen los JSON del módulo 1. Ya no entran, porque no están en la tabla, pero pueden servir para la vista.
  - Preguntarle al módulo 1 por los 134 archivos huérfanos y por los oferentes con `has_bid = False`.

- [ ] **T02 — `OrigenOneLake`.** En `servicios/orquestador/src/orquestador/origen.py`, con `azure-identity` y `azure-storage-file-datalake` como dependencias.
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
  - Pruebas con tablas inventadas (filas en memoria, sin Delta): proceso y dos oferentes, un RAR con hijos, un ZIP dentro de otro, un RAR sin hijos, una ruta repetida, un oferente que no cruza y una categoría desconocida.

- [ ] **T04 — Bajar en paralelo.** `Normalizar` baja hoy los archivos de uno en uno. A ~1,5 MB/s por archivo, un oferente de 200 MB tarda más de 2 minutos solo en bajar.
  - Se baja con varios hilos (`paralelo_bajar`, 4 por defecto) a la misma carpeta temporal.
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
| `bronce.tbl_evaluacionofertas_eventos_listados` | por definir en T01 | Identificador del proceso (SR…) |

Lo ideal en la vista: una fila por documento descargado, con el proceso, el identificador del oferente (vacío en los del proceso), la ruta, el tamaño, el MD5 y la marca de comprimido sin contenido, sin los comprimidos y sin restos de corridas viejas. Así sobraría todo el cruce de T03.

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
