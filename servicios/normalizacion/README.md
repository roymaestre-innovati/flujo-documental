# Normalización y lectura (módulo 3, entrega 1)

Recibe la carpeta de una entrega (de un oferente o del proceso) y produce, según el contrato `contracts/modulo3-normalizacion/v0`:

1. el **manifiesto** de la entrega, con una entrada por archivo y su estado;
2. un **PDF normalizado** por documento, más la hoja de cálculo original como anexo;
3. la **lectura** por página: tipo, texto, cobertura de imagen, rotación y anclas;
4. las **palabras con su posición**, en un archivo aparte.

Qué se pidió y por qué: `specs/003-validacion-extraccion/` (`spec.md`, `plan.md`, y las decisiones de implementación en las notas de `tasks.md`).

## Requisitos

- Python 3.12 y [uv](https://docs.astral.sh/uv/). uv descarga Python 3.12 si no está.
- LibreOffice, con el comando `soffice` en el PATH. Solo hace falta para convertir Word, hojas de cálculo y presentaciones; sin él, esas pruebas se saltan.
  - Ubuntu o Debian: `sudo apt-get install -y libreoffice-writer libreoffice-calc libreoffice-impress`
  - Mac: `brew install --cask libreoffice`. El instalador no pone `soffice` en el PATH; hay que agregarlo:

    ```bash
    sudo ln -s /Applications/LibreOffice.app/Contents/MacOS/soffice /usr/local/bin/soffice
    ```

## Instalar y probar

```bash
cd servicios/normalizacion
```

```bash
uv sync
```

```bash
uv run pytest -q
```

Son unas 410 pruebas, en un minuto y medio con LibreOffice. Todas usan documentos inventados que fabrica `tests/fabrica.py` en una carpeta temporal: en el repositorio no hay documentos reales.

## Usar

```bash
uv run normalizar <carpeta_entrega> --proceso SR0000000001 --oferente OF-002 --salida <carpeta_salida>
```

- Sin `--oferente`, es una entrega del proceso (condiciones, adendas, anexos).
- `--forzar` vuelve a procesar aunque ya exista el resultado (si no, se reusa lo que no cambió).
- Imprime un resumen con conteos, sin nombres. Los registros salen en JSON por stderr, sin datos personales.
- Sale con 0 aunque haya documentos con error (un error del documento es un resultado) y con 1 ante una falla inesperada.

La salida queda en `<carpeta_salida>/<proceso>/<oferente o PROCESO>/`: `manifiesto.json`, `pdf/`, `anexos/`, `lectura/` y `palabras/`.

Los anexos de hojas de cálculo (XLS, XLSX y ODS) se guardan en su formato original, también en Blob. La conversión a PDF puede perder información. Son los únicos originales que se conservan y quedan sujetos a la retención (S1).

Como función de Python: `normalizacion.entrega.normalizar_entrega(carpeta, id_proceso, id_oferente, AlmacenLocal(salida))`.

**Con documentos reales:** la salida trae datos personales. Va fuera del repositorio y se borra cuando ya no sirve. Antes de usar documentos reales hay que pasar el checklist de habeas data (`specs/003-validacion-extraccion/checklist-habeas-data.md`).

## Almacén en Blob Storage

`AlmacenBlob` guarda la misma salida en Blob Storage. Usa el extra `normalizacion[azure]`, que instala `azure-storage-blob` y `azure-identity`. Desde esta carpeta se instala con `uv sync --extra azure`. La normalización local funciona sin el extra.

`almacen_desde_entorno(raiz_local)`, en `normalizacion.almacen`, elige Blob cuando está definida `ALMACEN_BLOB_CUENTA` y usa `AlmacenLocal` cuando falta. La usan `orquestar` y `extraer`. El comando `normalizar` escribe en disco local.

| Variable | Para qué |
|---|---|
| `ALMACEN_BLOB_CUENTA` | Solo el nombre de la cuenta (`<cuenta>`). Un valor vacío o inválido da error de configuración |
| `ALMACEN_BLOB_CONTENEDOR` | Nombre del contenedor. Por defecto, `evaluacion-ofertas` |
| `AZURE_CLIENT_ID` | ID de cliente de la identidad administrada asignada por el usuario en los jobs. Lo lee `DefaultAzureCredential` |

`AlmacenNoDisponible` indica una falla transitoria, como un corte de red o un 429. Lleva `espera_s` si el servicio indica cuánto esperar. `AlmacenSinPermiso` indica una falla de configuración, como una credencial inválida, un permiso que falta o un contenedor inexistente.

- `normalizar_entrega` relanza ambas excepciones para que las maneje quien la llama.
- El orquestador trata `AlmacenNoDisponible` como `ErrorTransitorio` y aplica los reintentos y la espera pedida. Trata `AlmacenSinPermiso` como `ErrorDeConfiguracion` y manda el mensaje a errores sin reintento.
- Si falla una lectura del almacén, la extracción devuelve `error_proceso`. Usa `ALMACEN_NO_DISPONIBLE` para la falla reintentable y `ALMACEN_SIN_PERMISO` para la falla sin reintento.

Si la configuración falla al crear el almacén, `orquestar` y `extraer` muestran el motivo por stderr y salen con código 2.

### Pruebas contra Azure

La suite normal usa un contenedor falso para las pruebas de Blob. La batería contra el contenedor de desarrollo está preparada (T04) y requiere el rol `Storage Blob Data Contributor` sobre ese contenedor. Desde `servicios/normalizacion`, sustituye `<cuenta>` por el nombre de la cuenta de desarrollo.

```bash
az login
ALMACEN_BLOB_CUENTA="<cuenta>" uv run pytest --azure -m azure -v
```

Reserva entre 10 y 20 segundos. Las pruebas escriben datos inventados bajo `pruebas/<uuid>/` y los borran al terminar. Si aparece `Sin acceso a Azure`, revisa la identidad del inicio de sesión y la asignación del rol.

## Medir la muestra real (criterios A3 a A5)

```bash
uv run python scripts/medir_muestra.py <carpeta_muestra>
```

La carpeta trae una subcarpeta por oferente. Imprime solo conteos frente a lo que espera el diseño, con los oferentes numerados (OF-001…), sin nombres. La salida con datos personales va a una carpeta temporal que se borra al terminar. Opciones: `--json`, `--salida <carpeta>` (conservar para revisar a mano) y `--detalle`.

Solo en la máquina del equipo, nunca en la nube.

## Imagen del job

Se construye desde la raíz del repositorio:

```bash
docker build -f servicios/normalizacion/Dockerfile --target job -t normalizacion .
```

```bash
docker build -f servicios/normalizacion/Dockerfile --target pruebas -t normalizacion-pruebas .
```

```bash
docker run --rm --network none normalizacion-pruebas
```

```bash
docker run --rm --network none -v <entrega>:/entrega:ro -v <salida>:/salida normalizacion /entrega --proceso SR0000000001 --oferente OF-002 --salida /salida
```

La imagen corre con el usuario 10001: la carpeta de salida tiene que admitir escritura para ese usuario. Si Docker Hub limita las descargas, se puede usar un espejo con `--build-arg BASE_IMAGE=mirror.gcr.io/library/ubuntu:24.04`.

## Estructura

| Módulo | Qué hace |
|---|---|
| `entrega.py` | Une todo: inventario, cada archivo y el manifiesto. Idempotencia y manejo de errores |
| `inventario.py` | Recorrido, descarte de archivos de sistema, huella, duplicados e `id_documento` |
| `tipos.py` | Tipo real por contenido; Word, Excel o PowerPoint con contraseña |
| `conversion.py` | Word, hojas de cálculo y presentaciones con LibreOffice; imágenes con img2pdf |
| `revision_pdf.py` | Abre, repara, contraseña, restricciones y páginas |
| `firma.py` | Firma digital (pikepdf para encontrarlas, pyHanko para validarlas) |
| `lectura.py` | Tipo de página, texto, cobertura, rotación y palabras |
| `anclas.py` | Líneas de firma, casillas y tablas SI/NO |
| `almacen.py` | Interfaz `Almacen`, implementación local y selector por entorno |
| `almacen_blob.py` | `AlmacenBlob`, con el extra `azure` |
| `parametros.py` | Umbrales con su versión. Cambiar uno sube `version_parametros` |
| `errores.py` | Códigos de error con el aviso para el evaluador |
| `registros.py` | Registros en JSON sin datos personales |
| `cli.py` | El comando `normalizar` |
