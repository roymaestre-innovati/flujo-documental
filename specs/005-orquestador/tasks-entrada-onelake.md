# Tareas 005 — Entrada desde OneLake: primera versión

Es la primera pieza de la entrega 2 del orquestador: la interfaz `Origen` deja de ser una carpeta local y lee los archivos del módulo 1 en OneLake (plan, tabla de interfaces). El resto de la entrega 2 (Service Bus, Cosmos, Blob Storage, Container Apps) no entra aquí.

**Meta:** correr `orquestar` en la máquina del equipo sobre un evento real de `workspace-evaluacionofertas-dev`, leyendo directo de OneLake, sin copiar los originales, y llegar a los mismos conteos que reporta el módulo 1 en sus tablas.

**Estado al 2026-11-23:** T01 a T05 hechas. `orquestar` ya lee eventos desde OneLake. Sigue T06, la corrida con un evento real que hace el usuario en su máquina. La prueba de acceso está en `servicios/prueba-onelake/`.

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

- [x] **T03 — Reparto con las tablas del módulo 1.** (Ver la nota de T03.) Un módulo nuevo del orquestador (`entrada_modulo1.py`) lee las dos tablas Delta por OneLake (`deltalake`, versión vigente) y arma, para un `event_id`, la lista `archivos` del aviso (`ruta` e `id_oferente`) que ya define el contrato `proceso-listo`. La apertura no cambia: reparte con esa lista, como hoy. Cuando llegue la vista, solo cambia este módulo.
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

- [x] **T03b — Conectar el aviso 0.2.** Hecha el 2026-11-23 (ver la nota de T03b). El orquestador usa los campos que `armar_entrada` llena en el aviso `modulo5-orquestador/0.2` (`contracts/modulo5-orquestador/v0.2/`).
  - La apertura guarda `id_proyecto` en el proceso, y el `tamano` y el `md5` de cada archivo en la entrega, junto a su ruta.
  - `Normalizar` le pasa a `bajar` el `Esperado` de cada archivo, sacado del estado. Así la revisión funciona en Azure sin `OrigenRevisado` y sin volver a leer las tablas. Si no coincide, se reintenta como cualquier descarga fallida (`ArchivoDistinto`).
  - La apertura crea la tarea `documento_con_error` con motivo `COMPRIMIDO_SIN_CONTENIDO` por cada entrada de `comprimidos_sin_contenido`, en la entrega de su `id_oferente`. Esto reemplaza a `crear_tareas_sin_contenido` y deja de hacer falta un paso aparte en el comando. Si el comprimido es de un oferente que no tiene otros archivos, la entrega se crea igual, para que la tarea tenga dónde quedar.
  - Un aviso repetido no duplica nada (R2), y los avisos sin los campos nuevos siguen funcionando.
  - Pruebas: un aviso con tamaño y MD5 que no coinciden con lo bajado, uno con un comprimido sin contenido y uno sin los campos nuevos.
  - Al cerrar: quitar `OrigenRevisado` y `crear_tareas_sin_contenido` si ya no los usa nadie.

- [x] **T04 — Bajar en paralelo.** Hecha el 2026-11-23 (ver la nota de T04). A ~1,5 MB/s por archivo, bajar en serie los 200 MB de un oferente tarda más de 2 minutos.
  - Se baja con varios hilos (`paralelo_bajar`, 8 por defecto) a la misma carpeta temporal. Cada archivo cuesta ~1,8 s de latencia aunque sea chico (nota de T02): la entrega más grande, con 57 archivos, tarda ~100 s en serie y ~15 s con 8 hilos.
  - Tamaños de la muestra sin comprimidos (2026-11-20): la entrega más grande pesa 106 MB (57 archivos), la mediana 7 MB y el archivo más grande 11 MB. El disco efímero de una réplica de 0,5 vCPU basta.
  - Si un archivo falla, falla la entrega, como hoy.
  - Se mide en T06 y se ajusta el valor.

- [x] **T05 — Comando.** Hecha el 2026-11-23 (ver la nota de T05). `orquestar` acepta `--onelake-workspace`, `--onelake-lakehouse` y `--evento <event_id>` en lugar de `--origen` y `--proceso`. Publica el aviso que arma T03 con el `event_id` como identificador del proceso. Sin `--clasificacion` los documentos clasificados salen como TD-99. El README incluye cómo correrlo y la prueba de punta a punta usa tablas en memoria y un cliente falso.

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
| `bronce.tbl_evaluacionofertas_adjuntos_metadata` | `event_id` | Filtrar el proceso (`id_proceso` del aviso) |
| | `doc_category` | Proceso u oferente |
| | `invitation_id` | Cruzar con el oferente |
| | `adls_path` | Ruta del archivo |
| | `downloaded_bytes`, `md5_hex` | `tamano` y `md5` de cada archivo del aviso |
| | `is_compressed_archive`, `idempotency_key`, `parent_archive_key` | Excluir comprimidos y detectar los que no tienen contenido |
| `bronce.tbl_evaluacionofertas_oferentes_control` | `event_id`, `invitation_id` | Cruce |
| | `sm_vendor_id` | `id_oferente` del aviso |
| `control.tbl_evaluacionofertas_eventos_control` | `event_id`, `parent_project_id` | `id_proceso` e `id_proyecto` del aviso |
| | `updated_at_epoch_ms` | `fecha` del aviso |
| | `control_status`, `total_files_failed` | Saber que el evento terminó de descargarse (`DESCARGADO`, sin fallidos): es lo que dispararía el aviso |

Lo ideal en la vista, o directamente en el aviso que publique el módulo 1: lo que pide el contrato 0.2. Es decir, una fila por documento descargado de un evento en `DESCARGADO`, con el evento, el proyecto, el SR si existe, el identificador del oferente (vacío en los del proceso), la ruta, el tamaño, el MD5 y la marca de comprimido sin contenido, sin los comprimidos y sin restos de corridas viejas. Así sobraría todo el cruce de T03.

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

### T03 — Reparto con las tablas (2026-11-20)

- **`entrada_modulo1.py`.** `armar_entrada(id_evento, tablas)` devuelve un `EntradaDelEvento` con:
  - el aviso, validado contra `proceso-listo`: `ruta` es `informacion-adjuntos/fase2/<event_id>` y cada archivo es relativo a ella;
  - el proyecto `WS…`;
  - el tamaño y el MD5 esperados de cada archivo;
  - los comprimidos sin contenido, por entrega;
  - los excluidos, por motivo.

  La fecha del aviso es `updated_at_epoch_ms` del evento en `eventos_control`. Así un aviso repetido trae la misma fecha y la apertura lo reconoce.
- **Qué rechaza.** Lo que no cuadra lanza `EventoRechazado`, que es un `AvisoRechazado`:
  - un evento que no está en `DESCARGADO` o que tiene archivos fallidos;
  - una `doc_category` o un `file_status` desconocidos;
  - un oferente que no cruza con un único `sm_vendor_id`;
  - una ruta repetida con datos distintos;
  - una ruta fuera de la carpeta del evento o con `..`.
- **Lectura de Delta (`TablasOneLake`).** `deltalake` solo abre el log y da los parquet vigentes. Los parquet se bajan con el SDK y se leen con `pyarrow`.
  - El cuelgue se reproduce siempre que `deltalake` lee los datos (con `to_pyarrow_table` o `to_pyarrow_dataset`). Abrir la tabla o pedir `file_uris()` termina bien.
  - Sirve porque las tres tablas usan el protocolo 1 de Delta, sin particiones. Si eso cambia, se rechaza con `ErrorDeConfiguracion` en lugar de leer mal.
  - Si a un parquet viejo le falta una columna, llega como None.
- **Tareas.** `crear_tareas_sin_contenido` crea una tarea `documento_con_error` con motivo `COMPRIMIDO_SIN_CONTENIDO` por cada comprimido sin hijos. Va después de la apertura. El identificador sale de un hash de la ruta, así que repetirla no duplica.
- **Revisión de lo bajado.** `OrigenRevisado` envuelve el origen y le pasa a `bajar` el tamaño y el MD5 de cada archivo. En Azure no sirve, porque el trabajador que normaliza no tiene la entrada en memoria. **Resuelto con el contrato 0.2** (decisión del usuario, 2026-11-20): `tamano` y `md5` opcionales en cada archivo del aviso, más `id_proyecto` y `comprimidos_sin_contenido`. `armar_entrada` ya los llena; conectarlos es T03b.
- **Pruebas.** 24 nuevas (`tests/test_entrada_modulo1.py`), con tablas inventadas y, para Delta, un log y unos parquet falsos. Incluye una prueba con la apertura de verdad: las entregas quedan `PROCESO`, `S100` y `S200`, sin ningún ZIP ni RAR. La suite completa pasa: 237 pruebas.
- **Humo con las tablas reales** (solo conteos):

  | Evento | Archivos | Proceso | Oferentes | Entregas | Comprimidos excluidos | Sin contenido |
  |---|---|---|---|---|---|---|
  | 1 | 81 | 57 | 24 | 4 | 7 | 3 |
  | 2 | 74 | 57 | 17 | 3 | 7 | 2 |
  | 3 | 59 | 24 | 35 | 2 | 4 | 1 |
  | 4 | 67 | 20 | 47 | 5 | 0 | 0 |

  Los conteos cuadran con T01 (por ejemplo, el evento 4 tiene 78 filas, 10 de ellas repetidas). La entrega más chica (8 archivos, 3,6 MB) bajó completa con tamaño y MD5 revisados en 10 s.
- **Tiempo.** Armar un aviso toma ~23 s, porque lee las tres tablas enteras y baja sus ~60 parquet de uno en uno. Para la primera versión alcanza. Si molesta, se bajan en paralelo (como en T04) o se leen las tablas una vez para varios eventos.

### T03b — Conectar el aviso 0.2 (2026-11-23)

- `apertura.py` guarda `id_proyecto` en el proceso y `esperados` por ruta relativa en cada entrega. `normalizar.py` reconstruye `Esperado` desde ese estado y reintenta si la descarga difiere. `contratos.py` valida los avisos 0.1 con su esquema.
- La apertura registra una tarea `documento_con_error` con motivo `COMPRIMIDO_SIN_CONTENIDO` en la entrega correspondiente, incluso si la entrega solo trae comprimidos. La referencia usa un hash del proceso, la entrega y la ruta para que el reenvío conserve la misma tarea.
- Se retiraron `OrigenRevisado` y `crear_tareas_sin_contenido` de `entrada_modulo1.py` y de sus pruebas.
- Una entrega que solo trae comprimidos sin contenido queda con cero archivos y pasa a `procesando` con cero documentos. Su tarea es lo único que la persona revisa.
- Pruebas nuevas: un tamaño o MD5 que no coincide se reintenta y luego va a errores; un aviso 0.1 o 0.2 sin los campos nuevos; una entrega con solo un comprimido; un aviso repetido no duplica las tareas. La suite completa pasa: 248 pruebas.

### T04 — Bajar en paralelo (2026-11-23)

- `Corrida` pasa `Parametros` a `Normalizar`. `paralelo_bajar` limita las descargas por entrega a 8 por defecto. Todos los archivos van a la misma carpeta temporal, cada uno con su `Esperado` leído del estado. Con un hilo, o si dos rutas apuntan al mismo destino, se conserva el orden de descarga.
- `OrigenOneLake` reutiliza un cliente del SDK y su sesión HTTP por hilo, todos con una sola credencial creada al construirlo, para no pedir el token en cada hilo. Un cliente inyectado se protege con un candado.
- La primera falla corta la asignación de archivos. Las descargas en curso terminan antes de borrar la carpeta temporal. Un `ErrorOrigen`, incluido `ArchivoDistinto`, reintenta la entrega completa sin normalizar documentos.

### T05 — Comando (2026-11-23)

- `cli.py` publica el aviso 0.2 de `armar_entrada` y usa el mismo workspace y lakehouse para las tablas y los originales. La apertura crea las tareas de los comprimidos sin contenido. Las pruebas inyectan `TablasEnMemoria` y un `OrigenOneLake` con un cliente falso.
- Después de `az login`, desde `servicios/orquestador`, se corre `uv run orquestar --onelake-workspace <workspace> --onelake-lakehouse <lakehouse> --evento <event_id> --salida <carpeta-fuera-del-repo>`. En ambos modos se puede omitir `--clasificacion` para usar TD-99 y ajustar `--paralelo-bajar` (8 por defecto).
- El resumen agrega archivos del aviso, excluidos por motivo, comprimidos sin contenido, archivos bajados, MB y segundos con descargas en curso. `OrigenOneLake` mide las descargas simultáneas sin sumar dos veces el mismo intervalo. Un evento rechazado sale con código 2 e imprime solo el motivo.
