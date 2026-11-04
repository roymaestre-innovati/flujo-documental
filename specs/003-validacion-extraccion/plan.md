# Plan 003 — Normalización y lectura (primera entrega)

Estado al 2026-11-04. Borrador para revisión. Implementa la parte de normalización y lectura de `spec.md`. La extracción tendrá su propio plan más adelante, en esta misma carpeta.

## Resumen

Un paquete de Python, `normalizacion`, que recibe la carpeta de una entrega (de un oferente o del proceso) y produce:

1. el **manifiesto** de la entrega, con una entrada por archivo;
2. un **PDF normalizado** por documento, más el Excel original como anexo cuando aplica;
3. la **lectura** por página de cada PDF normalizado;
4. las **palabras con su posición**, en un archivo aparte.

Se usa por línea de comandos (`normalizar`) y como función de Python, para que después el worker del orquestador (iniciativa 005) la llame desde la cola. En producción corre como un Container Apps Job (decisión 16). En esta entrega no se conecta a ninguna cola ni a Azure: el almacenamiento queda detrás de una interfaz, con una implementación en disco local.

## Tecnología

Todas con licencia permisiva. Nada AGPL, mientras arquitectura no responda A-6.

| Necesidad | Herramienta | Licencia | Por qué |
|---|---|---|---|
| Abrir, reparar, detectar contraseña y restricciones, contar páginas | `pikepdf` (trae qpdf adentro) | MPL-2.0 | Cubre lo que el diseño pedía a qpdf sin instalar el comando aparte |
| Texto, palabras con posición, imágenes, rectángulos y rotación por página | `pdfplumber` (sobre `pdfminer.six`) | MIT | Una sola librería para toda la lectura. Reemplaza a PyMuPDF (AGPL) |
| Firma digital | `pyHanko` | MIT | Ya probada en el diseño con los 7 PDF firmados |
| Imágenes a PDF | `img2pdf` | LGPL-3.0 | Sin pérdida (no recomprime el JPEG). Se usa como librería sin modificarla, lo que la LGPL permite; se anota para A-6. Alternativa si arquitectura la rechaza: Pillow (recomprime) |
| TIFF de varias páginas, validar imágenes | `Pillow` | MIT-CMU | Dependencia de img2pdf |
| Distinguir DOC de XLS (los dos son OLE) | `olefile` | BSD-2 | Pequeña; mira qué flujos trae el archivo |
| Word y Excel a PDF | LibreOffice headless, como comando | MPL-2.0 | Lo pide el diseño. Si A-1 resulta en SharePoint, se cambia por la conversión de Graph API |
| Pruebas | `pytest`; para fabricar documentos: `reportlab`, `python-docx`, `openpyxl`, `cryptography` | BSD, MIT, MIT, Apache-2.0 | Solo en desarrollo |

Python 3.12 y `uv` para dependencias y entorno.

El tipo real de cada archivo se detecta con código propio, mirando los primeros bytes y, en los ZIP y OLE, su contenido. Son unas pocas reglas y así no se agrega otra dependencia:

| Contenido | Tipo |
|---|---|
| `%PDF-` | `pdf` |
| `FF D8 FF` | `imagen` (jpeg) |
| `89 50 4E 47` | `imagen` (png) |
| `II*\0` o `MM\0*` | `imagen` (tiff) |
| `00 05 16 07` | descartar: archivo `._*` de Mac (AppleDouble) |
| ZIP con `word/` | `docx` |
| ZIP con `xl/` | `xlsx` |
| ZIP con `mimetype` = `application/vnd.oasis.opendocument.text` | `odt` |
| ZIP con `mimetype` = `application/vnd.oasis.opendocument.spreadsheet` | `ods` |
| OLE con el flujo `WordDocument` | `doc` |
| OLE con el flujo `Workbook` o `Book` | `xls` |
| Cualquier otro | `no_soportado`: va al manifiesto con error |

## Estructura del repositorio

Cada pieza que se despliega por separado tiene su carpeta en `servicios/`. Esta es la primera.

```
servicios/normalizacion/
  pyproject.toml
  Dockerfile                 # imagen del job: Python + LibreOffice
  src/normalizacion/
    __init__.py              # VERSION del normalizador
    cli.py                   # comando `normalizar`
    entrega.py               # orquesta una entrega: inventario → por archivo → manifiesto
    inventario.py            # recorrido, descarte de archivos de sistema, hash, duplicados, id_documento
    tipos.py                 # detección del tipo real por contenido
    conversion.py            # LibreOffice e img2pdf
    revision_pdf.py          # abre, repara, contraseña, restricciones, páginas
    firma.py                 # firma digital con pyHanko
    lectura.py               # tipo de página, texto, cobertura, rotación
    anclas.py                # zonas visuales
    almacen.py               # interfaz de almacenamiento + implementación en disco
    parametros.py            # umbrales con su versión
  tests/
    conftest.py
    fabrica.py               # genera los documentos sintéticos de prueba
    test_*.py
contracts/modulo3-normalizacion/v0/
  README.md
  manifiesto.schema.json
  lectura.schema.json
  palabras.schema.json
  ejemplos/
```

## Contrato (principio 5)

Va en `contracts/modulo3-normalizacion/v0/`, versión `modulo3-normalizacion/0.1`. Se escribe **antes** que el código (tarea T01) y lo revisa el usuario. Lo usan el clasificador (A-5), la extracción (cambio 2 del contrato 0.2) y el orquestador.

### Manifiesto de la entrega

```json
{
  "contrato": "modulo3-normalizacion/0.1",
  "id_proceso": "SR0000000001",
  "id_oferente": "OF-002",
  "version_normalizador": "0.1.0",
  "version_parametros": "1",
  "ejecucion": {"inicio": "2026-11-04T10:00:00Z", "duracion_ms": 41200},
  "archivos": [ { "...": "una entrada por archivo, ver abajo" } ],
  "descartados": [ {"ruta_origen": "__MACOSX/._carta.pdf", "motivo": "archivo_sistema_mac"} ]
}
```

- `id_oferente` es `null` en una entrega del proceso (condiciones, adendas, anexos).
- `archivos` va ordenado por `ruta_origen`, para que dos corridas den el mismo manifiesto.
- `ejecucion` es lo único que cambia entre dos corridas de la misma entrega.

Entrada por archivo. Son los campos del paso 1 del diseño, más `estado` y `lectura`:

| Campo | Tipo | Contenido |
|---|---|---|
| `id_documento` | texto | `<id_oferente o PROCESO>-<primeros 12 hex del SHA-256 de ruta_origen>`. Es estable entre corridas. Provisional hasta A-1: si el módulo 1 da identificadores, se usan los suyos |
| `ruta_origen` | texto | Ruta relativa dentro de la entrega, con `/` |
| `hash` | texto | SHA-256 del original |
| `tipo_origen` | enum | `pdf`, `doc`, `docx`, `odt`, `xls`, `xlsx`, `ods`, `imagen`, `no_soportado` |
| `estado` | enum | `normalizado`, `duplicado` o `error_entrada` |
| `pdf` | URI o null | PDF normalizado |
| `anexo_nativo` | URI o null | Excel original, si aplica |
| `lectura` | URI o null | Lectura por página |
| `paginas` | entero o null | |
| `paginas_sin_texto` | lista de enteros | Contadas desde 1 |
| `duplicado_de` | texto o null | `id_documento` del original |
| `restricciones` | booleano | Trae restricciones de copia o impresión |
| `firma_digital` | lista | `{firmante, fecha, integro, formato, leida}`. `leida: false` cuando no se pudo leer (p. ej. `adbe.pkcs7.sha1`); en ese caso `firmante`, `fecha` e `integro` van en `null` |
| `error` | objeto o null | `{codigo, detalle}`. Códigos: `CONTRASENA`, `DANADO`, `SIN_PAGINAS`, `NO_SOPORTADO`, `CONVERSION_FALLIDA`. `detalle` no lleva texto del documento |

`formato` y `leida` amplían lo que pide el diseño (`{firmante, fecha, integro}`), para no confundir "no tiene firma" con "tiene una firma que no se pudo leer".

Un duplicado lleva `hash`, `tipo_origen` y `duplicado_de`. `pdf`, `lectura` y `paginas` apuntan a los del original, para que nadie tenga que seguir el enlace.

### Lectura de un documento

```json
{
  "contrato": "modulo3-normalizacion/0.1",
  "id_documento": "OF-002-3fa9c1d2e4b7",
  "hash_pdf": "…",
  "version_normalizador": "0.1.0",
  "version_parametros": "1",
  "firma_digital": [],
  "palabras": "<URI del archivo de palabras>",
  "paginas": [
    {
      "pagina": 1,
      "tipo": "texto",
      "texto": "…",
      "origen_texto": "nativo",
      "caracteres": 2140,
      "cobertura_imagen": 0.04,
      "rotacion": 0,
      "anclas": [
        {"tipo": "linea_firma", "caja": [72.0, 640.5, 300.0, 660.0], "texto": "Firma del representante legal"}
      ]
    }
  ]
}
```

- `hash_pdf` es el SHA-256 del PDF normalizado: permite saber que la lectura corresponde a ese PDF.
- `caja` va en puntos PDF, `[x0, y0, x1, y1]`, con el origen arriba a la izquierda (la convención de pdfplumber), y sobre la página sin rotar.
- `origen_texto` vale `null` en las páginas `imagen` y `vacia`.

### Palabras

Un archivo por documento: `{id_documento, paginas: [{pagina, palabras: [{t, caja}]}]}`. Las claves son cortas porque es el archivo pesado.

## Cómo se decide cada cosa

### Tipo de página

Con los parámetros de `parametros.py` (versión `"1"`):

- `caracteres` = caracteres sin contar espacios en blanco.
- `cobertura_imagen` = fracción del área de la página cubierta por la unión de las cajas de imagen, recortadas al borde de la página. La unión se calcula sobre una grilla fija de 200 × 200 celdas: es determinista y suficiente.
- Reglas, en orden:
  1. `caracteres < MIN_CARACTERES_TEXTO` (20) y `cobertura_imagen ≥ COBERTURA_ESCANEO` (0,80): `imagen`.
  2. `caracteres < MIN_CARACTERES_TEXTO` y `cobertura_imagen < COBERTURA_ESCANEO`: `vacia`.
  3. `caracteres ≥ MIN_CARACTERES_TEXTO` y `cobertura_imagen ≥ COBERTURA_ESCANEO`: `escaneo_con_ocr`.
  4. El resto: `texto`.
- Una página que casi no tiene texto y cuya imagen cubre entre 0 y 80 % (una foto chica en una página blanca) queda `vacia` por la regla 2. Se acepta en v0 y se revisa con la muestra (A4).
- `paginas_sin_texto` del manifiesto = páginas con `caracteres = 0`. No es lo mismo que el tipo `imagen`.

Los umbrales son datos con versión (principio 2). Si se cambian después de calibrar con la muestra, sube `version_parametros`.

### Anclas (zonas visuales)

Reglas simples y deterministas, sin LLM:

- `linea_firma`: una palabra que empieza por "firma" (sin importar mayúsculas ni tildes), o una línea dibujada horizontal, o una secuencia de 8 o más `_`, con texto que menciona firma, representante, revisor o contador a menos de 60 puntos. La caja cubre la línea y su rótulo.
- `casilla`: un rectángulo casi cuadrado, de 6 a 20 puntos de lado.
- `tabla_si_no`: una línea de texto donde aparecen las palabras "SI" y "NO" como palabras sueltas, junto con al menos una casilla o una celda de tabla a menos de 20 puntos.

En las páginas `imagen` no hay anclas, porque no hay texto: el recorte de firma de la extracción toma el tercio inferior (D20). Las palabras clave quedan en `parametros.py`.

### Firma digital

`pyHanko` lista los campos de firma. Por cada firma:

- `firmante`: el CN del certificado del firmante;
- `fecha`: la hora de firma declarada, en ISO 8601;
- `integro`: `true` si la firma cubre el documento y no hay cambios posteriores que la invaliden; `false` en el caso Acueducto (modificado después de firmar);
- `formato`: el subfiltro (`adbe.pkcs7.detached`, `ETSI.CAdES.detached`, `adbe.pkcs7.sha1`…).

No se valida la cadena de confianza: no se cargan autoridades raíz ni se consulta revocación. Si pyHanko falla con una firma, queda `leida: false` con su `formato`, y el documento sigue su curso. Una firma que no se lee no es error del documento.

### Conversión

- **LibreOffice:** `soffice --headless --norestore --convert-to pdf`, con un perfil temporal propio por conversión (`-env:UserInstallation=file:///tmp/...`), configurado con la seguridad de macros en "muy alta", para que ninguna macro se ejecute. Tiempo máximo de 120 s por archivo. Si falla o se pasa del tiempo, se reintenta una vez; si vuelve a fallar, `CONVERSION_FALLIDA`.
- **Imágenes:** `img2pdf`, una página por imagen o por cuadro del TIFF. Antes se valida con Pillow que la imagen abre.
- **PDF:** se abre con `pikepdf`. Si abre sin contraseña, se usa el original tal cual (R11). Si está dañado, se intenta guardar una copia reparada una vez: si pikepdf la guarda y la copia abre, esa copia es el normalizado (se anota en el log); si no, `DANADO`.
- Si el PDF pide contraseña para abrirse: `CONTRASENA`. Si abre con contraseña vacía y solo trae permisos restringidos: `restricciones = true`, y se procesa.

### Duplicados e identificadores

- Se ordena todo por `ruta_origen` antes de procesar. Para cada hash, el primero es el original; los siguientes quedan `duplicado` con `duplicado_de`.
- `id_documento` depende de la ruta y no del hash, así dos copias del mismo archivo tienen identificadores distintos.

### Almacén

Interfaz `Almacen`, con `leer(uri)`, `escribir(uri, bytes)`, `existe(uri)` y `listar(prefijo)`. Implementación `AlmacenLocal` sobre una carpeta, con URIs `file://`. La de Blob Storage llega cuando se responda A-1. Distribución de la salida:

```
<salida>/<id_proceso>/<id_oferente o PROCESO>/
  manifiesto.json
  pdf/<id_documento>.pdf
  anexos/<id_documento>.<ext>
  lectura/<id_documento>.json
  palabras/<id_documento>.json
```

### Idempotencia

Si para un `id_documento` ya existe la lectura con el mismo `hash` y la misma `version_normalizador`, no se vuelve a convertir ni a leer: se reusa. Es la clave del paso 4 del diseño (hash del archivo). La opción `--forzar` lo ignora.

### Comando

```
normalizar <carpeta_entrega> --proceso SR0000000001 [--oferente OF-002] --salida <carpeta> [--forzar]
```

Imprime un resumen sin datos personales (conteos por estado y tipo de página) y sale con código 0, aunque haya documentos con error, porque un error del documento es un resultado. Solo sale distinto de 0 ante un bug (clase 4 del diseño).

### Errores (paso 4 del diseño)

- **Clase 1 (del documento):** quedan en el manifiesto con `estado = error_entrada` y su código. No se lanza excepción.
- **Clase 4 (bug):** una excepción inesperada en un archivo no se traga en silencio. Se registra con `id_documento` y se relanza al final, después de escribir lo que sí se pudo, para que el worker la mande a la cola de errores.
- Las clases 2 y 3 (transitorios y LLM) no aplican aquí: no hay red ni LLM.

### Registros

`logging` estándar, en JSON, con `id_proceso`, `id_oferente`, `id_documento` y `hash[:12]`. Nunca texto de páginas ni la ruta de origen completa (puede traer nombres de personas).

## Pruebas

Todo con documentos sintéticos que fabrica `tests/fabrica.py` en una carpeta temporal. No hay documentos reales en el repo.

| Caso | Cómo se fabrica |
|---|---|
| PDF de texto | reportlab |
| Escaneo sin texto | reportlab, con una imagen a página completa |
| Escaneo con capa de texto del escáner | imagen a página completa más texto invisible (modo de render 3) |
| Página vacía | reportlab, página sin nada |
| Página rotada | `/Rotate 90` con pikepdf |
| Con contraseña para abrir | pikepdf, con contraseña de usuario |
| Solo restricciones | pikepdf, con contraseña de dueño y permisos limitados |
| Dañado reparable y dañado irreparable | bytes truncados o alterados |
| Firmado íntegro | pyHanko, con un certificado autofirmado generado en la prueba |
| Modificado después de firmar | el firmado, más una actualización incremental que cambia el contenido |
| DOCX, ODT, DOC | python-docx; ODT y DOC convertidos con LibreOffice en la fixture, si está instalado |
| XLSX con una hoja ancha | openpyxl |
| JPG, PNG, TIFF de 3 páginas | Pillow |
| Archivos de sistema | `.DS_Store`, `Thumbs.db`, `__MACOSX/`, `._carta.pdf` con cabecera AppleDouble |
| Extensión falsa | un DOCX renombrado a `.pdf` |
| No soportado | un `.txt` y un `.zip` |
| Duplicados | el mismo PDF en dos carpetas |
| Anclas | PDF con línea de firma con rótulo, casillas y tabla SI/NO |

- Las pruebas que necesitan LibreOffice se marcan `@pytest.mark.libreoffice` y se saltan si `soffice` no está.
- Una prueba de determinismo corre la entrega dos veces y compara manifiesto y lecturas, salvo `ejecucion`.
- Los ejemplos del contrato se validan contra sus esquemas, y también el manifiesto y la lectura que produce una entrega sintética.

**Fuera de la nube:** la prueba con la muestra real SR5658940621 (criterios A3 a A5) la corre el usuario en su máquina, con un script `scripts/medir_muestra.py` que solo imprime conteos.

## Chequeo de Constitución

| Principio | ¿Cumple? | Cómo |
|---|---|---|
| 1. El proceso manda sobre la tecnología | Sí | La spec no nombra tecnología; este plan la elige |
| 2. Condiciones como datos | Sí | No hay condiciones del proceso aquí. Los umbrales de lectura son parámetros con versión |
| 3. Veredicto trazable | Sí | Huella del original y del PDF, versión del normalizador y de los parámetros, páginas sobre el documento completo, nada se borra ni se reemplaza |
| 4. La IA extrae y el evaluador decide | Sí | No hay IA. Los documentos con error llegan al evaluador por medio del orquestador |
| 5. Contrato primero | Sí | `contracts/modulo3-normalizacion/v0` se escribe y revisa antes del código (T01). Se prueba sin el módulo 1, con carpetas locales |
| 6. Datos personales | Sí, con condición | Pruebas solo sintéticas, registros sin texto ni rutas completas. El checklist de habeas data se corre antes de procesar documentos reales fuera de la máquina del equipo |
| 7. Igualdad de trato | Sí | La lectura es determinista y sus parámetros llevan versión. El orquestador fija esa versión por proceso, igual que el modelo |

**Mínimo necesario (restricción de stack):** un job que escala a cero, librerías de Python y LibreOffice. Se descartaron Power Automate (no maneja bien el hash ni el análisis por página) y Document Intelligence para la lectura (cuesta y no hace falta para las páginas con texto; queda solo como experimento de OCR).

## Complejidad y excepciones

- **img2pdf es LGPL-3.0.** No es AGPL y se usa como librería sin modificar, pero se anota para la respuesta de A-6. Si se rechaza, se cambia por Pillow; solo toca `conversion.py`.
- **LibreOffice pesa** (unos 500 MB en la imagen). Es la forma más simple de convertir DOC, DOCX y XLS sin depender de Microsoft 365. Si A-1 resulta en SharePoint, se evalúa cambiarla por Graph API.
- **Firmas `adbe.pkcs7.sha1` sin leer en v0** (Cámara de Comercio y RUP). Quedan como `leida: false`. Buscar otra herramienta queda para después, si negocio responde A-3 o A-4.

## Riesgos

- Los umbrales (20 caracteres, 80 % de cobertura) salen de la exploración del diseño, no de una calibración. A4 los confirma con la muestra.
- Puede que pdfplumber sea lento en PDF grandes (de 40 páginas o más). Si A5 no se cumple, la alternativa es pypdfium2 (Apache-2.0 o BSD) para el texto y las imágenes.
- Las anclas se calibran con documentos sintéticos. Su efecto real se ve cuando la extracción las use (decisión 8).
