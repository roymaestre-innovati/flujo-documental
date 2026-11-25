# Tareas 005 — Almacén en Blob Storage

Es una pieza de la entrega 2 del orquestador: la interfaz `Almacen` deja de ser solo una carpeta local y tiene su versión en Blob Storage, donde quedan los PDF normalizados, las lecturas, las palabras, los anexos y los manifiestos. La decisión 32 deja la entrada en su zona de origen, sin una copia aparte. Un PDF que abre bien se guarda tal cual como normalizado (R11 de la spec 003). Los PDF reparados, las imágenes y los DOC, DOCX y ODT quedan como PDF resultantes. Las hojas de cálculo quedan como PDF y también como anexos en su formato original (decisión 14). `Estado` y `Cola` van aparte, en `tasks-estado-cola-azure.md`.

**Meta:** `AlmacenBlob` pasa la misma batería de pruebas que `AlmacenLocal`, en local sin Azure y, cuando se pida, contra el contenedor real de desarrollo, y una corrida puede escribir ahí sin cambiar el resto del código.

**Estado al 2026-11-25:** T01 a T03 y T05 hechas, en la rama `almacen-blob`. T04 está preparada y espera que el administrador asigne el rol `Storage Blob Data Contributor` sobre el contenedor de desarrollo.

## Decisiones ya tomadas

Detalle en `specs/005-orquestador/pendientes-azure.md` de la rama `infra-azure-inicial` (`git show infra-azure-inicial:specs/005-orquestador/pendientes-azure.md`).

- **Dónde:** un contenedor propio, `evaluacion-ofertas`, en una cuenta de Storage compartida con otras aplicaciones. Ya existe, sin acceso anónimo. Las cuentas compartidas no se reconfiguran desde aquí.
- **Cómo se entra:** con `DefaultAzureCredential` y el rol `Storage Blob Data Contributor` solo sobre el contenedor. No con la clave de la cuenta, que abre todos los contenedores de las otras aplicaciones.
- **Dónde vive el código** (decidido el 2026-11-24): en `servicios/normalizacion/`, junto a `AlmacenLocal`, con `azure-storage-blob` e `azure-identity` como dependencia opcional (`normalizacion[azure]`). Lo usan la normalización, el orquestador y la extracción, y la extracción no depende del orquestador. Es un cambio autorizado a la normalización: solo agrega la clase y la dependencia opcional, sin tocar cómo normaliza.
- **La regla de borrado** del contenedor depende del plazo que defina cumplimiento (S1) y se hace en la infraestructura. No entra aquí.

## Decisiones de esta pieza (2026-11-25)

Revisadas con el usuario y con una segunda opinión de Astra antes de empezar.

1. **Errores de Blob.** Dos excepciones nuevas en `normalizacion/almacen.py`, que no heredan de `ErrorAlmacen` (que sigue siendo URI inválida, fuera del almacén o inexistente): `AlmacenNoDisponible` (red, cortes sin estado HTTP, 408, 429 y 5xx salvo 501 y 505, con `espera_s` de 0 a 3600 segundos si el servicio la pide con `Retry-After` o `x-ms-retry-after-ms`) y `AlmacenSinPermiso` (401, 403, credencial, contenedor inexistente, configuración que falta o es inválida). `normalizar_entrega` las relanza antes de su `except Exception`, para que no se cuenten como bug del documento. El orquestador las traduce en un solo lugar, el bucle de `errores.py`, a `ErrorTransitorio` y `ErrorDeConfiguracion`; eso cubre normalizar, clasificar y extraer, que leen del almacén. En la extracción, `entrada._leer` las lleva a `error_proceso` con un código propio, reintentable para `AlmacenNoDisponible` y no reintentable para `AlmacenSinPermiso`. Los mensajes llevan solo operación, estado HTTP y, si está en la lista blanca, código del servicio.
2. **Reintentos.** Se dejan los del SDK (los de Blob reintentan 408 y 5xx, no 429) con `connection_timeout=20` y `read_timeout=60`. El 429 lo reintenta el bucle con la espera pedida.
3. **`existe`** usa `get_blob_properties()`: solo `BlobNotFound` es `False`. `exists()` del SDK también da `False` si el contenedor no existe, y eso es configuración.
4. **Prefijo de pruebas.** `AlmacenBlob` recibe `prefijo=""`, que se aplica en `uri()` y se valida por segmento en todas las operaciones (`pruebas/abc` nunca abarca `pruebas/abcd`). Solo `listar` acepta la raíz del prefijo.
5. **`listar`** en una sola llamada a `list_blobs(name_starts_with=…)`, filtrando los nombres iguales al prefijo o que empiezan por `prefijo + "/"`; si existe el blob exacto, solo ese. El iterador se consume dentro de la traducción de errores. La raíz (del contenedor o del prefijo) se puede listar, como en local.
6. **URI.** Solo `https://<cuenta>.blob.core.windows.net/<contenedor>/…`, host sin distinguir mayúsculas, sin usuario, puerto, query (tampoco SAS) ni fragmento. Cada `%` debe ir seguido de dos dígitos hexadecimales. La ruta se decodifica una sola vez y se revisan contenedor, prefijo y `..`.
7. **`content_type`** con `mimetypes.guess_type`, `application/octet-stream` si no sabe.
8. **Entorno.** `DefaultAzureCredential(exclude_interactive_browser_credential=True)`, cerrada con el cliente, también si falla la construcción. `ALMACEN_BLOB_CUENTA` es solo el nombre, `[a-z0-9]{3,24}`; `ALMACEN_BLOB_CONTENEDOR` también se valida. El selector de T03 usa local si la variable no está y falla si está vacía o mal. `AZURE_CLIENT_ID` para la identidad del job va en el README.
9. **Un cliente de Blob por hilo**, como `OrigenOneLake`: la normalización corre entregas en paralelo y el transporte del SDK no garantiza uso concurrente.
10. **`ubicar`** solo reubica URI `file://` cuando el almacén activo es local. Con Blob, una URI `file://` es `ErrorAlmacen`.
11. **Pruebas normales** borran `ALMACEN_BLOB_CUENTA` del entorno, para no escribir en Azure aunque haya `az login`. Las de Azure llevan la marca `azure` en la normalización también (hoy su `conftest.py` no la tiene), y el corte por falta de permisos reconoce `AlmacenSinPermiso`.
12. **Registros.** Los comandos dejan el logger `azure` en `ERROR` (Azure Identity registra detalles de credenciales en `WARNING`). Al construirse, `AlmacenBlob` fija el logger de `HttpLoggingPolicy` en `WARNING` como mínimo, porque el SDK registra la URL completa en `INFO`.
13. **CLI.** `orquestar correr` avisa por stderr si escribe en Blob. `extraer` también usa el selector. El visor sigue local, y `orquestar correr` con Blob real no respeta las esperas de un 429 (reloj simulado): quedan como limitaciones.
14. **Originales en la salida.** El usuario aceptó el 2026-11-25 que, si el archivo sirve tal cual, se guarde tal cual. El normalizado de un PDF que abre bien coincide byte a byte con la entrada y conserva sus firmas (R11 de la spec 003). Los PDF reparados, las imágenes y los DOC, DOCX y ODT quedan convertidos. Las hojas de cálculo se convierten a PDF y se guardan también como anexos en su formato original (XLS, XLSX, ODS), porque la conversión puede perder información. Todo forma parte de la salida sujeta a retención (S1). La decisión 32 deja la entrada en el origen, sin una copia en una zona aparte.
15. `servicios/extraccion/uv.lock` se conserva y se actualiza en T03.

## Dónde va

- `servicios/normalizacion/src/normalizacion/almacen_blob.py` (o dentro de `almacen.py`, si queda corto), con la librería importada solo ahí, para que la normalización siga funcionando sin el extra.
- El extra `azure` en `servicios/normalizacion/pyproject.toml`. El orquestador y la extracción lo piden en sus dependencias cuando lo usen.

## Para quien implemente

- Leer antes `normalizacion/almacen.py` (la interfaz y `AlmacenLocal`), `normalizacion/entrega.py` (cómo se arman las rutas: `<id_proceso>/<entrega>/{pdf,lectura,palabras,anexos}/…` y `manifiesto.json`) y `extraccion/entrada.py` (`ubicar`: las URI que no son `file://` ya se usan tal como vienen).
- **Las pruebas normales no tocan Azure.** Se prueba con un cliente de Blob falso en memoria que imite lo que se usa del SDK. Las pruebas contra Azure llevan la marca `azure` y solo corren si están sus variables de entorno.
- **El contenedor es nuestro, pero la cuenta es compartida.** Las pruebas contra Azure escriben bajo un prefijo inventado y único (`pruebas/<uuid>/`), con datos inventados, y lo borran al terminar.
- **Datos personales:** en Azure van a quedar PDF de cédulas y RUT. Nunca se imprimen nombres de archivo ni contenido en registros o errores: solo la ruta relativa con identificadores, como hoy (principio 6).
- **El repositorio de GitHub es público.** El nombre de la cuenta va en una variable de entorno, no en el código ni en los documentos.
- Las pruebas contra Azure las corre el usuario, con comandos listos y cuánto tardan.
- Flujo de siempre: una tarea a la vez, rama desde `main`, pruebas en verde, notas aquí, commit y **alto para revisión del usuario**.

## Tareas

- [x] **T01 — Batería de contrato de `Almacen`.** Pasar `servicios/normalizacion/tests/test_almacen.py` a una batería que reciba la implementación por fixture. Hoy corre solo sobre `AlmacenLocal`. Las pruebas propias de la versión local (archivos temporales `.escribiendo-`, URI `file://`) quedan aparte. Agregar:
  - **listar con prefijo de carpeta:** el prefijo `p/OF-1` no trae `p/OF-10/…`;
  - listar el prefijo de un archivo devuelve ese archivo;
  - escribir bytes vacíos funciona;
  - una URI de otro almacén (otro esquema, otra cuenta, otro contenedor) da `ErrorAlmacen`.

- [x] **T02 — `AlmacenBlob`.** Implementa `Almacen` con `azure-storage-blob`. Recibe un cliente del contenedor ya armado, para poder pasarle uno falso, y trae una función que lo arma desde el entorno (`ALMACEN_BLOB_CUENTA`, la URL `https://<cuenta>.blob.core.windows.net`, y `ALMACEN_BLOB_CONTENEDOR`, por defecto `evaluacion-ofertas`) con `DefaultAzureCredential`. Pasa la batería de T01 con el cliente falso.
  - `uri(ruta)`: `https://<cuenta>.blob.core.windows.net/<contenedor>/<ruta>`, con la ruta codificada (espacios, tildes) y las mismas validaciones que la versión local: relativa, sin `..` y no vacía.
  - `escribir`: `upload_blob(overwrite=True)`. Blob ya escribe completo o no escribe, así que no hace falta el temporal de la versión local. Con `content_type` según la extensión (`application/pdf`, `application/json`).
  - `leer`: `download_blob().readall()`. Un blob que no existe da `ErrorAlmacen`.
  - `existe`: `exists()` del blob.
  - `listar(prefijo)`: `list_blobs(name_starts_with=…)`. Si el prefijo es un blob, ese blob; si no, se cierra con `/` antes de buscar. Devuelve las URI ordenadas.
  - Errores del SDK: los de red y de servicio ocupado o limitado (429, 503) son `ErrorTransitorio` del orquestador, o la excepción que el bucle ya trata como transitoria; los de permiso (401, 403) se distinguen con un mensaje claro, porque son de configuración y no se reintentan. Revisar cómo los clasifica hoy `errores.py` y seguir lo mismo. Si para eso hay que importar algo del orquestador en la normalización, preguntar antes.

- [x] **T03 — Elegir el almacén por configuración.** Una función que devuelve `AlmacenBlob` si está `ALMACEN_BLOB_CUENTA` y `AlmacenLocal` si no, para que los comandos y, después, los workers no tengan que saberlo. Revisar que la extracción (`entrada.ubicar`) y el orquestador funcionen con URI `https://` de punta a punta: una prueba con `orquestar` en memoria y el cliente de Blob falso, donde el manifiesto, la lectura y el PDF quedan en el almacén falso y la extracción los lee de ahí. El visor sigue siendo local y no cambia.

- [ ] **T04 — `AlmacenBlob` contra el contenedor de desarrollo.** Correr la batería de T01 con la marca `azure` contra el contenedor real, con `az login`. **Necesita que el administrador haya asignado al usuario** `Storage Blob Data Contributor` sobre el contenedor (`infra/roles.bicep`, rama `infra-azure-inicial`). Mientras tanto, la tarea queda en espera. La prueba anónima (sin credenciales) debe seguir dando 404. La corre el usuario.

- [x] **T05 — Cierre.** Notas de lo encontrado. Actualizar la tabla de interfaces de `plan.md`, los README de la normalización y el orquestador, y `inventario-codigo.md`.

## Fuera de esta versión

- La regla de borrado del contenedor (S1, HD-7), en la infraestructura.
- Decidir si dos trabajadores pueden normalizar la misma entrega a la vez sobre Blob o si hace falta un lease por entrega. Se mira con los workers, cuando el mensaje `normalizar` pueda llegar repetido de verdad.
- Leer en Azure lo que ya existe en una corrida local, o migrar corridas viejas.

## Notas de implementación

### T01

`test_almacen_contrato.py` comprueba la interfaz, la lectura y escritura (incluidos bytes vacíos), los prefijos al listar y el rechazo de rutas y URI ajenas. `test_almacen.py` conserva las pruebas de URI `file://`, temporales y ubicación de archivos en corridas movidas.

Para T02, se agrega `pytest.param("almacen_blob", id="blob")`. El fixture `almacen_blob` devuelve el almacén con cliente falso y las URI de `uris_ajenas_blob` (otro esquema, otra cuenta, otro contenedor y query).

### T02

El SDK 12.31.1 puede entregar `error_code` como texto o enum. `get_blob_properties()` permite distinguir `BlobNotFound` de un contenedor inaccesible. La traducción abarca todo el iterador paginado de `list_blobs()` y `readall()`, pues el SDK puede envolver un corte de descarga en un `HttpResponseError` sin estado. Los errores conservan datos estructurados y la espera del servicio dentro del límite de una hora.

Se reutiliza un cliente de contenedor por hilo con la misma credencial. El cliente inyectado se usa bajo un candado. La fábrica valida el entorno antes de crear recursos y transfiere su cierre al almacén mediante `ExitStack`. La batería de contrato comparte los casos de Local y Blob con un contenedor en memoria.

### T03

Los comandos eligen y cierran el almacén mediante la interfaz común. El bucle del orquestador y la entrada de extracción clasifican las fallas del almacén. Una prueba con el contenedor falso exporta las solicitudes del orquestador y comprueba que la extracción lee el PDF y la lectura desde Blob.

El visor solo lee `file://`. `orquestar correr` con Blob real adelanta su reloj simulado y por eso no respeta en tiempo real las esperas de un 429.

### T04 (preparada)

Desde `servicios/normalizacion`, sustituye `<cuenta>` por el nombre de la cuenta de desarrollo y ejecuta estos comandos cuando tengas el rol `Storage Blob Data Contributor` sobre el contenedor.

```bash
az login
ALMACEN_BLOB_CUENTA="<cuenta>" uv run pytest --azure -m azure -v
```

La corrida debería tardar entre 10 y 20 segundos. Son unas 105 peticiones, incluyendo la limpieza, que a unos 70 ms cada una suman 7 segundos. A eso se añade la obtención de la credencial y la transferencia de 5 MiB en cada dirección.

Si la corrida se corta con `Sin acceso a Azure`, verifica que el inicio de sesión corresponde a la identidad con el rol sobre el contenedor. Si falta la asignación, pídesela al administrador y repite el comando cuando esté activa. El nombre de la cuenta va solo en la variable de entorno, nunca en el repositorio.

### T05

- El SDK de Blob deja pasar el 429. El bucle del orquestador lo reintenta y usa la espera pedida por el servicio cuando viene indicada.
- `exists()` del SDK da `False` si falta el contenedor. `get_blob_properties()` permite reservar `False` para `BlobNotFound` y tratar el contenedor inexistente como un error de configuración.
- `normalizar_entrega` atrapaba las fallas del almacén como si fueran bugs del documento. Ahora las relanza para que el orquestador pueda reintentar las transitorias o mandar a errores las de configuración.

Queda por correr T04 cuando esté el rol. La retención (S1), la decisión sobre el lease por entrega y el acceso desde Azure a corridas locales ya hechas quedan fuera de esta pieza, igual que migrar esas corridas.

### Revisión de Astra

1. El logger de `HttpLoggingPolicy` queda en `WARNING` como mínimo al construir el almacén, con una prueba del SDK sobre un transporte en memoria.
2. Los mensajes solo incluyen códigos conocidos de Storage de la lista blanca. La clasificación usa el código recibido.
3. T04 usa `pruebas/<uuid>/interno` como prefijo del almacén y prueba los prefijos ajenos `otra` e `internod` dentro del mismo UUID que limpia.
4. Los errores `OSError` y `ValueError` al crear la credencial se traducen a `AlmacenSinPermiso` con un mensaje fijo.
5. Los cortes sin estado HTTP y los estados 5xx, salvo 501 y 505, se traducen como fallas transitorias en las cuatro operaciones.
6. `Retry-After` acepta segundos y fechas HTTP con el analizador del SDK. Las fechas pasadas dan cero. Si cualquiera de las dos cabeceras pide más de una hora, el bucle usa el reintento normal.
7. Solo `listar` admite la raíz del prefijo. Las operaciones de archivo exigen un nombre debajo de ella.
8. El cierre intenta liberar cada recurso y registra una advertencia con la operación y la clase de error por cada fallo. El comando guarda el estado y las solicitudes aunque falle un cierre.
9. T04 comprueba listado, escritura, lectura y borrado antes de correr. Las fallas del SDK se muestran con mensajes limpios y la limpieza informa cuántos blobs quedaron tras intentar todos los borrados.
10. Las URI con escapes mal formados se rechazan antes de decodificar. Los nombres que contienen `%` conservan su ida y vuelta.
11. El README de extracción indica que el ejemplo local se corre sin `ALMACEN_BLOB_CUENTA`.
12. La documentación de normalización, del orquestador y de cumplimiento precisa qué archivos quedan guardados, según la decisión del 2026-11-25.

**Pendientes para los workers**

- Con Blob activo, una URI `file://` da `ARCHIVO_NO_ENCONTRADO` reintentable aunque repetir no ayude. Si falta la lectura en `Clasificar` o `Extraer.pedir`, el bucle manda el mensaje a errores como bug, igual que con `AlmacenLocal`. Distinguir «URI inválida» de «objeto ausente» con subtipos públicos de `ErrorAlmacen`.
- `AlmacenBlob.cerrar()` puede cerrar un cliente que otro hilo todavía esté usando. Las CLI esperan a sus hilos antes de cerrar. Los workers deberán impedir operaciones nuevas y esperar las activas.
