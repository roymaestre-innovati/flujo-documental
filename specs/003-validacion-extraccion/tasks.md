# Tareas 003 — Normalización y lectura (primera entrega)

Sale de `plan.md`. Cada tarea termina con sus pruebas en verde y un commit propio.

**Estado al 2026-11-05: T01 a T13 hechas** y fusionadas en `main` (387 pruebas). Primera medición con la muestra real en `resultados-muestra.md`. De ella salen tres tareas nuevas, **T14 a T16**, con las decisiones del usuario en "Decisiones tras la medición", al final de este archivo.

## Para quien implemente

- Leer antes `spec.md` y `plan.md` de esta carpeta. El contexto de diseño está en `contexto/flujo-documental-opcion-a.md` (pasos 1 y 2) y las reglas del proyecto, en `contexto/constitucion.md`.
- Los documentos de `contexto/` nombran `Documentos/clasificados/manifiesto.csv`, `matriz/` y documentos reales de oferentes. No están en el repo a propósito, porque traen datos personales, y no hacen falta para esta entrega. No buscarlos ni inventarlos.
- Solo documentos sintéticos, fabricados por las pruebas. No subir ningún PDF fuera de `tests/`.
- Nada de LLM ni de servicios de Azure en este código.
- Escribir en español: código con nombres en español, como en el contrato, y documentos en prosa.
- Si algo del plan no se puede hacer como está escrito, anotarlo en "Notas de implementación", al final de este archivo, y seguir con la alternativa más simple.

Dependencias del sistema: `libreoffice` (writer, calc e impress) y Python 3.12 con `uv`. En Debian o Ubuntu: `apt-get install -y libreoffice-writer libreoffice-calc libreoffice-impress`.

## Tareas

- [x] **T01 — Contrato.** Escribir `contracts/modulo3-normalizacion/v0/`: `README.md`, `manifiesto.schema.json`, `lectura.schema.json` y `palabras.schema.json` (JSON Schema 2020-12), más ejemplos: una entrega con un normalizado, un duplicado, un error y un descartado, y una lectura con una página de cada tipo. Validar los ejemplos contra los esquemas, como en `contracts/modulo3-extraccion/v0/README.md`. **Detenerse aquí para revisión del usuario** antes de seguir (principio 5).
- [x] **T02 — Esqueleto.** `servicios/normalizacion/` con `pyproject.toml` (uv, pytest), `__init__.py` con `VERSION = "0.1.0"`, `parametros.py`, `almacen.py` (interfaz y `AlmacenLocal`) y el comando `normalizar` que por ahora solo lista la entrega. Agregar la prueba que valida los ejemplos del contrato.
- [x] **T03 — Fábrica de pruebas.** `tests/fabrica.py` con todos los casos de la tabla de pruebas del plan. Una prueba por caso que solo confirma que el archivo se fabricó.
- [x] **T04 — Inventario.** Recorrido recursivo, descarte de archivos de sistema (por nombre y por contenido), SHA-256, duplicados por orden de ruta e `id_documento`. Requisitos R1 a R5.
- [x] **T05 — Tipo real.** `tipos.py` con la tabla del plan. Incluye la extensión falsa y los no soportados. Requisito R6.
- [x] **T06 — Revisión del PDF.** Abrir, reparar una vez, detectar contraseña y restricciones, contar páginas. Requisitos R11 a R13 y R16.
- [x] **T07 — Conversión.** LibreOffice con perfil temporal y macros bloqueadas, con tiempo máximo y un reintento; imágenes con img2pdf, incluido el TIFF de varias páginas; Excel convertido y conservado como anexo. Requisitos R7 a R10.
- [x] **T08 — Firma digital.** Firmante, fecha, integridad, formato y `leida`. Casos: íntegro, modificado después de firmar, sin firma. Requisito R15.
- [x] **T09 — Lectura.** Texto, caracteres, cobertura de imagen (grilla de 200 × 200), rotación, tipo de página, origen del texto y archivo de palabras. Requisitos R14 y R18 a R20, R22 y R23.
- [x] **T10 — Anclas.** `linea_firma`, `casilla` y `tabla_si_no`, según el plan. Requisito R21.
- [x] **T11 — Entrega completa.** `entrega.py` une todo y escribe manifiesto, PDF, anexos, lecturas y palabras en el almacén. Aislamiento de errores (R17), errores de clase 4 relanzados al final, idempotencia y `--forzar`, y registros sin datos personales. Prueba de punta a punta con una entrega sintética que trae todos los casos, validada contra el contrato. Prueba de determinismo (R24 y R25, criterio A2).
- [x] **T12 — Imagen del job.** `Dockerfile` (Python 3.12 slim, LibreOffice writer y calc, uv) que corre `normalizar`. Comprobar que las pruebas pasan dentro de la imagen.
- [x] **T13 — Script de la muestra.** `scripts/medir_muestra.py <carpeta>`: corre `normalizar` sobre cada oferente de una carpeta e imprime solo conteos (páginas únicas, duplicados, restricciones, firmas, descartados, proporción de tipos de página y tiempo por oferente), para los criterios A3 a A5. No se corre en la nube: lo corre el usuario con la muestra real.

### Después de la medición con la muestra real

Orden acordado: T14, T16 y T15. Mismo flujo que T01 a T13: una rama por tarea, pruebas en verde, notas aquí, y alto para revisión.

- [x] **T14 — Sello de tiempo.** Un sello de tiempo del documento (`/Type /DocTimeStamp`, subfiltro `ETSI.RFC3161`) no se cuenta en `firma_digital`: no tiene firmante, así que no es una firma de persona. Hoy aparece como "firma no leída". El esquema no cambia; se anota en el README del contrato. La fábrica suma un PDF firmado con un sello de tiempo encima, y la prueba comprueba que solo queda la firma. En la muestra, el PDF de OF-006 que trae el sello también trae una firma CAdES, así que sigue contando como PDF firmado.
- [x] **T16 — Vínculos externos en Excel.** Antes de convertir un `xlsx`, quitar de la copia que va a LibreOffice los vínculos a otros libros: las partes `xl/externalLinks/`, `<externalReferences>` en `xl/workbook.xml` y sus entradas en `xl/_rels/workbook.xml.rels` y `[Content_Types].xml`. El original queda intacto como anexo (R9). Motivo: un Excel de OF-007 con 201 vínculos (2,9 MB de datos guardados) tardó 64 s en convertirse en la máquina local; sin los vínculos tarda 1,9 s y el PDF sale igual (mismas páginas y mismo texto, sin `#REF`), porque el Excel guarda el último valor de cada fórmula. No era la red ni la actualización de vínculos: sin red tarda lo mismo, y con la opción de no actualizar vínculos de LibreOffice también. La fábrica suma un `xlsx` con muchos vínculos externos; las pruebas comprueban que el texto del PDF no cambia y que el anexo es el original byte a byte. Los `xls` y `ods` no se tocan.
- [x] **T15 — PowerPoint.** Convertir `pptx`, `ppt` y `odp` con LibreOffice, igual que los Word: cada diapositiva queda como una página y las notas del orador no salen. Toca:
    - el contrato: los tres valores nuevos en `tipo_origen`;
    - `tipos.py`: ZIP con `ppt/presentation.xml` es `pptx`, OLE con el flujo `PowerPoint Document` es `ppt`, ZIP con `mimetype` de presentación OpenDocument es `odp`;
    - `conversion.py`: un grupo `PRESENTACIONES`, sin anexo nativo;
    - el `Dockerfile`: `libreoffice-impress-nogui`;
    - la fábrica: un `pptx` mínimo, y el `ppt` y el `odp` convertidos desde él con LibreOffice;
    - las dependencias del sistema de este archivo y del README del servicio.

**Al cerrar las tres,** `VERSION` pasa a `0.2.0`, porque cambia el resultado del normalizador, y se repite la medición solo de OF-006 y OF-007. `version_parametros` sigue en 1: no cambia ningún umbral.

## Notas de implementación

### T01 — Contrato (2026-11-04)

Contrato escrito en `contracts/modulo3-normalizacion/v0/`, con los ejemplos validados. Revisado y fusionado en `main`.

**Dudas resueltas con el usuario (2026-11-04).** Ya están aplicadas en el contrato y en `plan.md`:

1. **Campos del duplicado.** Repite todos los datos del original: `pdf`, `anexo_nativo`, `lectura`, `paginas`, `paginas_sin_texto`, `restricciones`, `firma_digital` y `reparado`.
2. **Rutas con tildes.** `ruta_origen` se normaliza a Unicode NFC. Con esa ruta, en UTF-8, se calcula `id_documento` y se ordena (por punto de código). Le toca a T04.
3. **Documentos que no abren.** `restricciones` y `firma_digital` van en `null` ("no se sabe") en todo `error_entrada`. Basta con avisar claro al evaluador: `detalle` dice qué pasó y qué pedirle al oferente si decide solicitar subsanación. La solicitud va por Ariba, fuera del sistema. `paginas` sigue en `null` en todo error, también en `SIN_PAGINAS`.
4. **Descartados.** Se quedan en su lista aparte, solo con ruta y motivo, sin huella: el original no se borra y los `._*` se reconocen también por contenido.
5. **Archivo de palabras.** Se queda como está, sin `contrato` ni `hash_pdf`. Se identifica por la lectura que lo enlaza.
6. **`ocr_propio`.** Se decide cuando llegue el experimento de OCR. En 0.1 las páginas `imagen` y `vacia` llevan `origen_texto: null`.
7. **PDF reparado.** Campo nuevo `reparado` en el manifiesto (`true` solo en un `pdf` cuya copia reparada es el normalizado). Le toca a T06.

**Decisiones que el plan no fijaba:**

- Todas las claves de cada entrada van siempre, con `null` o `[]` cuando no aplican, como en el contrato de extracción.
- Reglas por estado: `normalizado` exige `pdf`, `lectura` y `paginas`; `error_entrada` exige `error` y deja en `null` `pdf`, `anexo_nativo`, `lectura`, `paginas` y `duplicado_de`; `duplicado` exige `duplicado_de`. `anexo_nativo` solo puede tener valor en `xls`, `xlsx` y `ods`.
- Motivos de descarte: `archivo_sistema_mac` (`.DS_Store`, `__MACOSX/`, `._*`) y `archivo_sistema_windows` (`Thumbs.db`). El plan solo mostraba el primero. Un registro por archivo, ordenado por `ruta_origen`.
- En las anclas, `texto` va en `null` en una casilla. Las páginas `vacia` pueden tener anclas (por ejemplo, un formulario con casillas vacías); el plan solo las prohíbe en `imagen`.
- `rotacion` solo admite 0, 90, 180 o 270. `texto` es una cadena vacía cuando la página no tiene texto.
- El archivo de palabras trae todas las páginas, también las que no tienen palabras.
- Como los esquemas se refieren entre sí, el comando de validación del README los carga en un registro de `referencing`. T02 debe hacer lo mismo en su prueba.

### T02 — Esqueleto (2026-11-04)

`servicios/normalizacion/` con `pyproject.toml` (uv, hatchling, pytest), `uv.lock`, `__init__.py` (`VERSION = "0.1.0"` y la versión del contrato), `parametros.py`, `almacen.py`, `inventario.py` y `cli.py`. 52 pruebas en verde con Python 3.12.

**Decisiones que el plan no fijaba:**

- **El comando cuenta, no lista.** La tarea pide que `normalizar` "solo liste la entrega", pero el plan prohíbe sacar nombres de archivo (pueden traer nombres de personas). Imprime solo cuántos archivos trae la entrega. El recorrido, que sí devuelve las rutas, está en `inventario.recorrer()`, y T04 lo amplía.
- **Enlaces simbólicos.** El recorrido no los sigue, para no leer archivos fuera de la entrega.
- **Parámetros como un objeto inmutable** (`PARAMETROS`), con todos los umbrales del plan. "Casi cuadrado" en la casilla no tenía número: se fijó una tolerancia de 20 % entre lados (`tolerancia_cuadrado_casilla`), que T10 puede ajustar subiendo la versión de parámetros.
- **`AlmacenLocal`** escribe con un temporal y un cambio de nombre, para no dejar archivos a medias, y rechaza URI que no sean `file://` locales o que salgan de su carpeta.
- **Python fijado en 3.12** (`>=3.12,<3.13`), el mismo de la imagen del job (T12).
- **Validadores del contrato en `tests/contrato.py`**, para que la prueba de punta a punta (T11) los reuse. Además de validar los ejemplos, las pruebas comprueban que los esquemas rechazan casos mal formados y que los ejemplos usan las versiones del paquete.

**Duda resuelta para T10:** la tabla SI/NO se reconoce sin importar mayúsculas ni tildes ("Sí" cuenta), igual que "firma". Ya está en `plan.md`.

### T03 — Fábrica de pruebas (2026-11-04)

`tests/fabrica.py` fabrica los 18 casos de la tabla de pruebas del plan, repartidos en 24 funciones reunidas en `CASOS`, y `tests/test_fabrica.py` tiene una prueba por función. 88 pruebas en verde. Sin LibreOffice, las de ODT y DOC se saltan.

**Decisiones que el plan no fijaba:**

- **Cada prueba revisa la propiedad del caso**, no solo que el archivo exista: que la contraseña se pida, que el dañado reparable abra solo con recuperación, que la firma esté íntegra o que el TIFF tenga 3 páginas. Usa pikepdf, pyHanko, Pillow y olefile directamente, sin el código del normalizador.
- **Caso extra `appledouble_sin_prefijo`:** un AppleDouble con nombre normal (`anexo_tecnico.pdf`), para probar que R2 descarta también por contenido y no solo por el prefijo `._`.
- **La tabla SI/NO de `pdf_anclas`** trae una fila con "SI"/"NO" y otra con "Sí"/"No", por la decisión de reconocerlas sin mayúsculas ni tildes. El documento tiene dos líneas de firma: una con guiones bajos y otra dibujada.
- **Dañado reparable:** un PDF válido con `startxref` apuntando mal (qpdf reconstruye la tabla). **Irreparable:** la cabecera `%PDF-` seguida de bytes sin estructura.
- **Firma:** certificado autofirmado de curva elíptica (P-256), generado en cada prueba, con un nombre ficticio. pyHanko firma con `adbe.pkcs7.detached`. El caso modificado agrega un dibujo en una actualización incremental: la parte firmada sigue intacta, pero pyHanko reporta un cambio no permitido.
- **Fabricación reproducible:** reportlab con `invariant=1` y pikepdf con identificador fijo, así que el mismo caso da los mismos bytes. Los cifrados son la excepción, porque el cifrado usa una sal aleatoria. La prueba de determinismo (T11) debe fabricar una vez y procesar dos.
- **Dependencias:** reportlab, python-docx, openpyxl, cryptography, pikepdf, pyhanko, Pillow y olefile quedan en el grupo `dev`. pikepdf, pyhanko, Pillow y olefile pasan a dependencias del paquete cuando el código los use (T04 a T08).
- **Nombres de archivo:** varios casos usan nombres parecidos (`carta_presentacion.*`). La entrega completa de T11 debe poner cada caso en su propia subcarpeta.

**Duda para T08, resuelta en T08:** el caso de firma que no se puede leer se fabrica cambiando el `/SubFilter` de un PDF ya firmado a `adbe.pkcs7.sha1`, en el mismo espacio (`pdf_firma_ilegible`).

### T04 — Inventario (2026-11-04)

`inventario.inventariar(carpeta, id_oferente)` devuelve los archivos (con `id_documento`, `ruta_origen` en NFC, ruta en disco, `hash` y `duplicado_de`) y los descartados, los dos ordenados por `ruta_origen`. El comando `normalizar` ya muestra los conteos de archivos, duplicados y descartados. 108 pruebas en verde, con al menos una por requisito de R1 a R5.

**Decisiones que el plan no fijaba:**

- **Archivos `._*`: se descartan por contenido.** R2 dice "por nombre y por contenido". Se descarta todo archivo con cabecera AppleDouble, se llame como se llame. Un archivo que empieza por `._` pero es, por ejemplo, un PDF de verdad, se trata como documento. Así ningún documento se pierde por su nombre. Lo demás va por nombre: `.DS_Store`, `Thumbs.db` (sin importar mayúsculas, como en Windows) y todo lo que esté dentro de una carpeta `__MACOSX`, sea lo que sea.
- **Duplicados:** un archivo descartado nunca cuenta como original de una copia. Un archivo vacío sí entra al inventario, con la huella de cero bytes; T05 le dará su tipo.
- **Enlaces simbólicos:** el recorrido no los sigue (decidido en T02). No quedan en el inventario ni como descartados.

**Duda resuelta con el usuario: sufijo.** Si dos archivos tienen nombres que solo se diferencian en cómo escriben las tildes (uno en NFC y otro en NFD), los dos quedarían con la misma `ruta_origen`. El primero por orden de la ruta en disco conserva el nombre; los siguientes llevan ` (2)`, ` (3)`… en el nombre, antes de la extensión, saltando cualquier ruta que ya exista en la entrega. Es determinista y no cambia el contrato. Solo queda `ErrorInventario` para el caso, prácticamente imposible, de dos rutas distintas cuyo SHA-256 coincida en los primeros 12 hex.

### T05 — Tipo real (2026-11-04)

`tipos.detectar(ruta)` devuelve el `tipo_origen` del contrato y, en las imágenes, el formato (jpeg, png o tiff), siguiendo la tabla del plan. Lo que no reconoce es `no_soportado`, nunca una excepción. La revisión de la cabecera AppleDouble pasó de `inventario.py` a `tipos.py`. `olefile` es ahora dependencia del paquete. La fábrica suma XLS y ODS (R9 los nombra). 149 pruebas en verde.

**Decisiones que el plan no fijaba:**

- **DOCX y XLSX se reconocen por su pieza principal** (`[Content_Types].xml` más `word/document.xml` o `xl/workbook.xml`), no solo por la carpeta `word/` o `xl/`. Así un ZIP que el oferente armó con una carpeta llamada `word/` no pasa por Word. Los DOCM y XLSM (con macros) tienen las mismas piezas y se tratan como DOCX y XLSX; LibreOffice los convierte sin ejecutar macros (T07).
- **El `%PDF-` tiene que estar al comienzo del archivo**, como dice la tabla.

**Dudas abiertas:**

1. **Word o Excel con contraseña: resuelta con el usuario.** `detectar` marca `cifrado = True` en el DOCX o XLSX con `EncryptedPackage` (queda `no_soportado`, porque no se sabe si era Word o Excel), en el DOC con la bandera `fEncrypted`, en el XLS con el registro `FILEPASS` y en el ODT u ODS con datos de cifrado en el manifiesto (estos conservan su tipo). La entrega (T11) deja esos documentos con `CONTRASENA`, sin convertirlos. La fábrica suma un DOCX y un XLSX cifrados con `msoffcrypto-tool` (MIT, solo en desarrollo).
2. **PDF con bytes antes de `%PDF-`.** Acrobat abre PDF con hasta 1024 bytes de basura antes de la cabecera; aquí quedarían `no_soportado`. No se sabe si pasa en la muestra real: se verá en A3. Si pasa, la regla se amplía a "`%PDF-` en los primeros 1024 bytes".
3. **Formatos fuera de la tabla:** RTF, PPTX, HEIC (fotos de iPhone), GIF, BMP y WEBP quedan `no_soportado`, con el aviso de entregarlos en PDF. HEIC y RTF podrían ser comunes entre oferentes; convendría confirmarlo con la muestra antes de agregarlos.

### T06 — Revisión del PDF (2026-11-04)

`revision_pdf.revisar(datos)` devuelve el PDF normalizado (el original tal cual, o la copia reparada), las páginas, las restricciones, si se reparó y el error, si lo hay. Nunca lanza excepción por un problema del documento. `errores.py` reúne los cinco códigos con su aviso para el evaluador, según la tabla del README del contrato. `pikepdf` es ahora dependencia del paquete. La fábrica suma un PDF sin páginas. 192 pruebas en verde.

**Decisiones que el plan no fijaba:**

- **"Abre"** quiere decir que pikepdf lo abre sin recuperación y puede contar sus páginas. Si no, se intenta la reparación una sola vez: se abre con recuperación, se guarda una copia y la copia tiene que abrir sin recuperación. Si algo de eso falla, `DANADO`.
- **La copia reparada se guarda sin cifrado** y con un identificador derivado del contenido, así reparar dos veces da los mismos bytes (R25). Las restricciones se leen del original, así que `restricciones` sigue siendo `true` aunque la copia ya no las traiga.
- **`restricciones`** solo cuenta las de copia e impresión (`extract`, `print_lowres` y `print_highres`), que son las que nombra R13. Un PDF cifrado que solo prohíbe, por ejemplo, modificarlo queda con `restricciones: false`.
- **Avisos:** `error_documento(codigo, documento)` arma el `detalle` con el sujeto que corresponde ("El PDF pide contraseña…", "El archivo pide contraseña…").
- **Registro de la reparación:** un mensaje con `logging`, sin nombre ni texto del documento. El formato JSON con los identificadores llega en T11.

**Duda resuelta con el usuario, para T09.** Si un PDF abre y cuenta sus páginas pero falla al leer una página (un objeto roto adentro), se lee lo que se pueda: la página que falla queda `vacia`, con texto vacío y sin anclas, y el registro anota el número de página sin datos del documento. El documento no queda `DANADO`.

### T07 — Conversión (2026-11-04)

`conversion.convertir(ruta, tipo)` devuelve el PDF convertido, el anexo (el original, solo en hojas de cálculo) y el error, si lo hay. Word y hojas de cálculo van por LibreOffice; imágenes, por img2pdf. Los Word y Excel con contraseña quedan `CONTRASENA` y los no soportados, `NO_SOPORTADO`, sin intentar la conversión. `img2pdf` y `Pillow` son ahora dependencias del paquete. 231 pruebas en verde (sin LibreOffice: 202 y 29 saltadas).

**Decisiones que el plan no fijaba:**

- **PDF reproducible.** LibreOffice pone en cada PDF la fecha, una suma de control (`/DocChecksum`) y un identificador al azar, así que convertir dos veces daba bytes distintos y la lectura cambiaría de `hash_pdf` entre corridas (R25). Después de convertir se quitan esas tres cosas y los metadatos XMP, y el identificador se recalcula a partir del contenido. Lo mismo con img2pdf. Comprobado: dos conversiones del mismo DOCX, XLSX, TIFF o PNG dan los mismos bytes.
- **LibreOffice en su propio grupo de procesos.** Si se pasa del tiempo, se mata el grupo entero, porque `soffice` lanza otros procesos que, si no, quedarían vivos. Cada conversión usa una carpeta temporal y un perfil propios, que se borran al terminar.
- **El archivo se copia como `entrada.<ext>`** antes de convertir, para que el nombre del oferente (que puede traer nombres de personas) no aparezca en la lista de procesos ni en los registros.
- **Imágenes con transparencia** (PNG de capturas de pantalla): img2pdf no las acepta. Se aplanan sobre fondo blanco y se guardan como PNG, sin pérdida. Las demás imágenes pasan tal cual: el JPEG queda adentro del PDF sin recomprimir.
- **Una imagen que Pillow no abre queda `DANADO`** (el plan no decía qué código). Cualquier excepción de Pillow en esa validación cuenta como imagen dañada, porque Pillow lanza muchos tipos distintos con archivos corruptos. Si img2pdf falla después, queda `CONVERSION_FALLIDA`.
- **Rotación EXIF:** img2pdf respeta la orientación que trae la foto (`Rotation.ifvalid`).
- **Sin LibreOffice instalado** se lanza `RuntimeError`: es un bug de despliegue (clase 4), no un error del documento.
- **Casos nuevos en la fábrica:** PNG con transparencia y ODT con macro.

**Limitación de la prueba de macros.** El ODT de la fábrica trae una macro que, al abrirse el documento, escribe un archivo marca. Con el perfil seguro la macro no se ejecuta, y la prueba lo comprueba. Pero tampoco se ejecutó con la seguridad de macros en mínimo: LibreOffice parece no disparar los eventos de apertura al convertir sin interfaz. Así que la prueba no demuestra que sea el perfil el que la bloquea; sirve como regresión. Aparte, otra prueba comprueba que cada conversión recibe un perfil propio con `MacroSecurityLevel = 3` y `DisableMacrosExecution = true`.

### T08 — Firma digital (2026-11-04)

`firma.leer_firmas(datos)` devuelve una `FirmaDigital` por firma (`firmante`, `fecha`, `integro`, `formato`, `leida`), en el orden del formulario, o una lista vacía si el PDF no tiene firmas. `pyhanko` es ahora dependencia del paquete. La fábrica suma `pdf_firma_ilegible`. 250 pruebas en verde.

**Hallazgo.** pyHanko no lista las firmas `adbe.pkcs7.sha1`: si solo se le preguntara a pyHanko, el manifiesto diría "sin firma" justo en los certificados de la Cámara de Comercio. Por eso las firmas se buscan en dos pasos: pikepdf recorre los campos de firma del formulario (también los anidados) y anota su formato; pyHanko valida los que puede. Un campo que pyHanko no lee, o cuya validación falla, queda con `leida: false` y su formato.

**Decisiones que el plan no fijaba:**

- **`integro`** es `true` si la parte firmada está intacta, la firma es matemáticamente válida y los cambios posteriores, si los hay, están permitidos (por ejemplo, una segunda firma). Una actualización que cambia el contenido de la página la deja en `false`. No se mira la confianza del certificado: sin autoridades raíz y sin consultas a la red.
- **`firmante`** es el CN del certificado; si no tiene CN, el nombre completo del titular. **`fecha`** es la hora de firma que declara la firma; si no la trae, la `/M` del diccionario de firma.
- **Una firma leída sin firmante o sin fecha queda como `leida: false`**, porque el contrato exige los dos en una firma leída. Es raro, pero si pasa en la muestra habría que revisar el contrato.
- **Campos de firma vacíos** (el formulario tiene el campo, pero nadie firmó) no cuentan como firma.
- **PDF con solo restricciones y firmado:** pyHanko lo abre con la contraseña vacía y la firma se valida normal.
- **Registros:** pyHanko escribe en el registro los datos del certificado (el nombre de quien firma) cuando algo le parece raro, por ejemplo un certificado autofirmado. Se silencian los registros de `pyhanko` y `pyhanko_certvalidator` para que esos nombres no lleguen a los registros del servicio (principio 6).

**Para T11:** las firmas se leen del PDF original del oferente, no de la copia reparada, porque reescribir el archivo invalida la firma. En un PDF dañado que se reparó, lo más probable es que la firma quede `leida: false`.

### T09 — Lectura (2026-11-04)

`lectura.leer(datos, id_documento, firmas, uri_palabras)` devuelve la lectura y el archivo de palabras, los dos según el contrato, y `paginas_sin_texto` para el manifiesto. Las anclas quedan vacías hasta T10. `pdfplumber` es ahora dependencia del paquete. 289 pruebas en verde. Un PDF sintético de 40 páginas se lee en unos 0,2 s; los reales pesan más y lo medirá A5.

**Hallazgo: rotación.** pdfplumber devuelve las coordenadas de una página con `/Rotate` ya giradas, y su texto sale con una palabra por línea. El contrato pide las cajas sobre la página sin rotar. Se lee una copia interna del PDF con `/Rotate` en 0, así que texto y cajas quedan como si la página no estuviera girada. La `rotacion` de la lectura es la del PDF normalizado, también cuando la página la hereda de su padre.

**Decisiones que el plan no fijaba:**

- **Cobertura:** una celda de la grilla de 200 × 200 cuenta como cubierta si su centro cae dentro de alguna imagen (recortada al borde de la página). El valor es la fracción exacta de celdas cubiertas, sin redondear.
- **Texto:** `extract_text()` de pdfplumber con sus valores por defecto; incluye el texto invisible (modo de render 3) de los escáneres. **Palabras:** `extract_words()`, en el orden de lectura de pdfplumber, con las cajas redondeadas a 2 decimales para que el archivo pese menos.
- **Rotaciones raras:** se normalizan a 0, 90, 180 o 270 (`-90` es 270). Un valor que no es múltiplo de 90 se toma como 0.
- **Página que no se puede leer** (decisión del usuario): queda `vacia`, sin texto ni palabras, y el registro anota el número de página. Si pdfplumber no puede abrir el documento entero, todas las páginas quedan `vacia`.

**Para revisar con la muestra (A4):** la página que cae en la regla 2 por ser "una foto chica en una página blanca" (el plan ya lo acepta en v0) y si `extract_text()` con sus valores por defecto junta bien las columnas de tablas anchas.

### T10 — Anclas (2026-11-04)

`anclas.buscar()` encuentra las líneas de firma, las casillas y las tablas SI/NO de una página, y la lectura las incluye en cada página que no es `imagen`. Trabaja sobre la página sin rotar, así que una página girada da las mismas anclas. 332 pruebas en verde.

**Decisiones que el plan no fijaba:**

- **Frases.** Las palabras se agrupan en renglones (bordes superiores a 3 puntos o menos) y, dentro del renglón, en frases (huecos de 10 puntos o menos). Hace falta porque dos rótulos en el mismo renglón ("Firma del representante legal" y "Firma del revisor fiscal") son de líneas distintas.
- **Línea de firma.** Las candidatas son las líneas dibujadas horizontales (también los rectángulos de 1,5 puntos de alto o menos) y las palabras con 8 o más `_`. Cada una toma como rótulo la frase más cercana, a menos de 60 puntos, que tiene una palabra que empieza por firma, representante, revisor o contador. La caja une la línea y el rótulo, y `texto` es el rótulo.
- **"Una palabra que empieza por firma"** (el plan la pone como tercera candidata): se tomó como una frase cuya **primera** palabra empieza por "firma" y que no es ya el rótulo de una línea. Así "Firma del oferente:" cuenta, pero "la firma del contrato", en medio de un párrafo, no.
- **Casilla:** "casi cuadrado" es que los lados difieren a lo más 20 % (fijado en T02). Un rectángulo repetido (borde y relleno) cuenta una vez.
- **Tabla SI/NO:** "SI" y "NO" tienen que estar como palabras sueltas en el mismo renglón, sin mayúsculas ni tildes (decisión del usuario). "Celda de tabla" es cualquier rectángulo que no sea una línea. La caja une el renglón y las casillas de ese mismo renglón, no las del renglón de al lado aunque estén a menos de 20 puntos.
- **Orden:** de arriba abajo y de izquierda a derecha.
- **Parámetros nuevos:** `tolerancia_renglon` (3), `separacion_max_frase` (10) y `grosor_max_linea` (1,5). `version_parametros` sigue en `"1"`, porque todavía no se ha procesado nada real con ella; desde la primera corrida con la muestra, cualquier cambio la sube.

**Para calibrar con la muestra:**

1. **Falsos positivos.** Los bordes horizontales de una tabla cuentan como línea si hay un rótulo con "representante" o "contador" cerca, y "si" y "no" son palabras comunes: un renglón como "si el oferente no presenta…" dentro de una tabla cuenta como tabla SI/NO. Un falso positivo cuesta poco (la extracción manda la imagen de la página), pero conviene medirlo.
2. **Casillas que no son rectángulos:** las casillas escritas como carácter (☐, ☑ o Wingdings), las dibujadas con curvas y los campos de formulario (casillas de AcroForm) no se detectan.
3. **Escaneos con OCR:** en las páginas `escaneo_con_ocr` las anclas salen de las palabras del escáner, que pueden venir mal ubicadas.

### T11 — Entrega completa (2026-11-04)

`entrega.normalizar_entrega(carpeta, id_proceso, id_oferente, almacen)` une todas las piezas, escribe en el almacén el PDF, el anexo, la lectura y las palabras de cada documento y, al final, el manifiesto. Devuelve el manifiesto y los conteos por tipo de página. El comando `normalizar` la usa e imprime el resumen. `registros.py` escribe los registros en JSON. 378 pruebas en verde (sin LibreOffice: 316 y 62 saltadas).

La prueba de punta a punta arma una entrega con todos los casos de la fábrica, cada uno en su subcarpeta, y comprueba:

- que el manifiesto, cada lectura y cada archivo de palabras cumplen el contrato y son coherentes entre sí (huella del PDF, páginas, páginas sin texto, firmas);
- el estado, el tipo y el error de cada caso;
- el determinismo: dos corridas dan exactamente los mismos archivos, salvo `ejecucion` en el manifiesto (A2).

A mano, con el comando: 32 archivos (8 conversiones con LibreOffice) en unos 10 s, y la segunda corrida reusa los 24 normalizados.

**Decisiones que el plan no fijaba:**

- **Ante un bug (clase 4) el manifiesto no se escribe.** El plan dice que la excepción "se relanza al final, después de escribir lo que sí se pudo". Se escriben los PDF, lecturas y palabras de los demás documentos, pero no el manifiesto: si se escribiera sin el documento que falló, el orquestador podría dar la entrega por terminada. `ErrorEntrega` lleva solo los `id_documento` que fallaron. Si falla el original de una copia, la copia también cuenta como fallida.
- **Idempotencia por el manifiesto anterior, no por la lectura.** El plan dice reusar si "ya existe la lectura con el mismo hash", pero la lectura guarda la huella del PDF normalizado, que en un Word o una imagen no es la del original. Se reusa un documento si el manifiesto anterior lo tiene `normalizado`, con la misma huella del original, la misma versión del normalizador y de los parámetros, y si su PDF, lectura, palabras y anexo siguen en el almacén. Los documentos con error se vuelven a intentar siempre, porque una conversión puede haber fallado por algo pasajero. Consecuencia: después de una corrida con bug (sin manifiesto), el reintento procesa todo de nuevo.
- **La firma se lee del PDF original** del oferente, también cuando el normalizado es la copia reparada (decidido en T08).
- **PDF convertido que no pasa la revisión:** si sale sin páginas, `SIN_PAGINAS`; si no abre, `CONVERSION_FALLIDA`. Los convertidos llevan `restricciones: false` y `firma_digital: []`: las firmas digitales dentro de un Word no se leen.
- **Copia de un documento con error:** repite los `null` del original, pero con `error: null`, porque el contrato lo exige en un `duplicado`.
- **Formato de los archivos:** el manifiesto y la lectura van en JSON con sangría; las palabras van compactas, porque es el archivo pesado. `ejecucion.inicio` va en UTC, con segundos.
- **Registros:** una línea JSON por evento en stderr, con `id_proceso`, `id_oferente`, `id_documento` y `hash` (12 caracteres) tomados del contexto. De una excepción se anota solo el tipo y el lugar del código (`ValueError en lectura.py:120`), nunca su mensaje, que puede traer rutas o texto del documento.
- **Sin LibreOffice instalado,** cada Word o Excel falla como bug y la entrega termina con `ErrorEntrega`. Es un problema de la imagen (T12), no del documento.

### T12 — Imagen del job (2026-11-04)

`servicios/normalizacion/Dockerfile`, con tres etapas: `base` (sistema, LibreOffice, fuentes y uv), `pruebas` (dependencias de desarrollo, pruebas y contrato; corre pytest) y `job` (solo las dependencias del paquete; usuario sin privilegios, uid 10001; `ENTRYPOINT ["normalizar"]`). Se construye desde la raíz del repositorio, porque las pruebas necesitan el contrato, y `Dockerfile.dockerignore` deja entrar solo lo que se copia: los documentos y la matriz nunca entran a la imagen.

**Comprobado en este entorno:**

- Las 379 pruebas pasan **dentro de la imagen de pruebas, sin red** (`--network none`), en unos 90 s.
- La imagen `job` procesa la entrega sintética completa (32 archivos) en unos 12 s, con el usuario sin privilegios, sin red, con la entrega montada de solo lectura. El manifiesto y las 24 lecturas cumplen el contrato.
- Tamaños: `job` 1,22 GB y `pruebas` 1,28 GB. Casi todo es LibreOffice; el plan estimaba unos 500 MB solo para LibreOffice.

**Hallazgo y corrección en la lectura.** Dentro de la imagen falló la prueba de punta a punta: una palabra de la hoja ancha de Excel convertida quedó con una coordenada negativa, y el contrato pide cajas desde 0. La imagen tenía menos fuentes que el entorno de desarrollo; sin la equivalente de Calibri, el texto salía más ancho y se salía de la página. Dos arreglos:

1. `lectura.py` recorta las cajas de palabras y anclas al borde de la página y las mide desde su esquina superior izquierda. Una palabra que queda entera fuera de la página se descarta del archivo de palabras (su texto sigue en `texto`). Vale para cualquier PDF, no solo los convertidos. Hay una prueba nueva.
2. La imagen trae las fuentes Carlito (medidas de Calibri) y Caladea (de Cambria), además de Liberation, para que los Word y Excel hechos en Office conserven su paginación.

**Desviación del plan: Ubuntu 24.04 en vez de `python:3.12-slim`.** La red de este entorno no deja descargar paquetes de Debian (`deb.debian.org`), así que una imagen sobre `python:3.12-slim` no se podía construir ni probar aquí. Ubuntu 24.04 trae Python 3.12.3 y LibreOffice 24.2, las mismas versiones del entorno donde corrieron todas las pruebas; Debian bookworm trae LibreOffice 7.4, más antiguo. **Confirmado por el usuario: se queda Ubuntu 24.04.**

**Otras decisiones:**

- **uv se instala desde PyPI** (`pip install uv==0.11.32`, la versión de desarrollo), en vez de copiarlo de `ghcr.io/astral-sh/uv`. Así la construcción depende de un registro menos; en la etapa `job` se desinstala al terminar.
- **`BASE_IMAGE` es un argumento**, para usar un espejo de Docker Hub si hace falta (`--build-arg BASE_IMAGE=mirror.gcr.io/library/ubuntu:24.04`). Aquí Docker Hub respondió 429 (demasiadas solicitudes).
- **Cómo se construyó aquí:** con una copia temporal del Dockerfile, fuera del repositorio, que solo agrega el certificado del proxy de este entorno y pasa los repositorios de Ubuntu a HTTPS. El Dockerfile del repositorio no lleva nada de eso.

**No se hizo:** análisis de vulnerabilidades de la imagen ni publicación en un registro de Azure (no hay acceso a Azure en esta entrega).

### T13 — Script de la muestra (2026-11-04)

`servicios/normalizacion/scripts/medir_muestra.py` corre la normalización sobre cada oferente de una carpeta e imprime solo conteos, junto a lo que espera el diseño, para los criterios A3 a A5. 387 pruebas en verde.

**Cómo correrlo** (en la máquina del equipo, con la muestra real SR5658940621; nunca en la nube):

```bash
cd servicios/normalizacion
uv sync
uv run python scripts/medir_muestra.py /ruta/a/la/muestra
```

La carpeta trae una subcarpeta por oferente, con sus archivos tal como los entregó. Opciones: `--json` (los mismos conteos en JSON), `--salida <carpeta>` (conserva PDF y lecturas para revisarlos a mano) y `--detalle` (registros de cada documento en stderr, sin nombres). Hace falta LibreOffice instalado, o correrlo dentro de la imagen de T12.

**Decisiones que el plan no fijaba:**

- **Ubicación:** en `servicios/normalizacion/scripts/` y no en `scripts/` en la raíz, para correrlo con el entorno del servicio (`uv run`).
- **Oferentes anónimos:** se numeran OF-001, OF-002… en el orden alfabético de sus carpetas. Nunca se imprimen nombres de carpetas ni de archivos, ni texto, ni quién firma. Las carpetas ocultas y los archivos sueltos en la raíz se ignoran.
- **La salida se borra:** los PDF, lecturas y palabras traen datos personales, así que por defecto van a una carpeta temporal que se borra al terminar. Con `--salida` se conservan; esa carpeta no se sube al repositorio.
- **Qué se cuenta:** "páginas únicas" son las páginas de los documentos normalizados, sin los duplicados. "PDF con restricciones" y "PDF con firma digital" cuentan documentos normalizados; de las firmas se cuentan además las leídas, las no leídas y las no íntegras. También van los descartados por motivo, los errores por código, los reparados y los convertidos.
- **Falla inesperada en un oferente:** se marca en la tabla, se siguen los demás y el script sale con código 1.

### Decisiones tras la medición (2026-11-05)

Revisadas una por una con el usuario a partir de `resultados-muestra.md`:

| Tema | Decisión | Por qué |
|---|---|---|
| ZIP y RAR (13 en la muestra) | No se toca el código | Fueron un error al armar la carpeta de prueba: en la versión final no llegan comprimidos |
| Firmas `adbe.pkcs7.detached` con el algoritmo mal declarado (2, OF-007) | Quedan `leida: false` y se anota. Si se repiten en más oferentes, se agrega la tolerancia | El programa que firmó puso el algoritmo de firma (sha256 con RSA) donde va el de resumen, y pyHanko no lo reconoce. El revisor la abre en Adobe |
| Firma CAdES de OF-006 marcada no íntegra | Queda no íntegra | La parte firmada está intacta, pero cambios posteriores tocan la estructura interna del PDF. Es preferible una falsa alarma que se revisa en Adobe a dejar pasar un cambio real |
| Sello de tiempo `ETSI.RFC3161` | No se cuenta como firma (T14) | No tiene firmante |
| PowerPoint (2 PPTX en OF-007) | Se soporta con LibreOffice (T15) | Se convierte sin problema, igual que los Word |
| Excel que tardó 85 s | Se diagnosticó: eran 201 vínculos externos. Se quitan antes de convertir (T16) | Ver T16 |

### T14 — Sello de tiempo (2026-11-05)

`firma._campos_firmados` salta los campos cuyo valor es un sello de tiempo del documento: `/Type /DocTimeStamp` o subfiltro `ETSI.RFC3161` (basta con uno de los dos). Nota en el README del contrato; el esquema no cambia. 391 pruebas en verde.

- **Fábrica:** `pdf_firmado_con_sello_de_tiempo` es el firmado de siempre con un sello encima, y `sellar(datos)` agrega el sello a cualquier PDF. El sellador de prueba de pyHanko solo acepta claves RSA, así que `_firmante(rsa=True)` genera una; el firmante de siempre sigue con curva elíptica.
- **Pruebas:** el firmado con sello deja una sola firma, leída e íntegra (el sello no rompe la integridad de la firma anterior); un PDF que solo tiene un sello queda sin firmas (`[]`); la entrega completa incluye el caso nuevo.
- **Con el PDF real de OF-006:** antes daba `ETSI.CAdES.detached` y `ETSI.RFC3161`; ahora solo la CAdES, que sigue no íntegra (decisión de arriba).
- **Sin cambio en `VERSION`** todavía: sube a `0.2.0` al cerrar T14 a T16, como dice la lista de tareas.

### T16 — Vínculos externos en Excel (2026-11-05)

`conversion.sin_vinculos_externos(datos)` quita de la copia de un `xlsx` las partes `xl/externalLinks/`, el bloque `<externalReferences>` de `xl/workbook.xml` y sus entradas en `xl/_rels/workbook.xml.rels` y `[Content_Types].xml`. `convertir` la usa solo con `xlsx`; el anexo sigue siendo el original. Si el archivo no tiene vínculos, o no es un ZIP que se pueda leer, devuelve los mismos bytes y LibreOffice recibe el archivo tal cual. 399 pruebas en verde.

**Con los Excel reales** (11 en las dos muestras; 5 tienen vínculos):

| Excel | Antes | Después | PDF |
|---|---|---|---|
| OF-007, 1 página, 201 vínculos | 64 a 68 s | 1,9 s | Igual |
| OF-007, 47 páginas | 22 s | 3,3 s | Igual; ver abajo |
| Los otros 3 con vínculos | 1,7 a 2 s | Igual | Igual |

**Hallazgo: con vínculos, LibreOffice no siempre da el mismo PDF.** El Excel de 47 páginas, convertido 4 veces tal cual, dio un texto distinto en una de ellas; sin vínculos, las 4 dieron el mismo. Así que T16 también ayuda al determinismo (R25), no solo al tiempo.

**Decisiones que la tarea no fijaba:**

- **Solo `xlsx`** (incluye los `xlsm`, que se detectan como `xlsx`). Los `xls` y `ods` guardan los vínculos de otra forma y no aparecieron en la muestra.
- **Los nombres definidos que apuntan a otros libros se dejan.** En el Excel real de 201 vínculos había 2.185; quitarlos no cambió el tiempo, y sin los vínculos LibreOffice los ignora sin errores en el PDF.
- **El caso de la fábrica (`xlsx_con_vinculos`, 50 vínculos) comprueba que el resultado es correcto, no la velocidad.** Con vínculos inventados LibreOffice no se pone lento (1,7 s con 200, con muchas hojas o con nombres definidos); no se encontró qué rasgo exacto de los reales lo frena, y no hizo falta: el arreglo se midió con los archivos reales. Las pruebas comprueban que se quitan las partes, que el Excel limpio abre, que el PDF muestra el último valor de una fórmula que apuntaba a otro libro, sin `#REF` ni `#NAME`, que el anexo es el original byte a byte y que el original no cambia.

### T15 — PowerPoint (2026-11-05)

`pptx`, `ppt` y `odp` se convierten con LibreOffice, como los Word: una página por diapositiva, sin anexo, y sin las notas del orador. El contrato sube a `modulo3-normalizacion/0.2` (decisión del usuario: un consumidor que valide contra 0.1 rechazaría los tipos nuevos) y `VERSION` a `0.2.0`, como estaba previsto al cerrar T14 a T16. 413 pruebas en verde, también dentro de la imagen.

- **`tipos.py`:** ZIP con `[Content_Types].xml` y `ppt/presentation.xml` es `pptx`; OLE con el flujo `PowerPoint Document` es `ppt`; ZIP con `mimetype` de presentación OpenDocument es `odp`, y el ODP con contraseña se marca como los ODT y ODS. Grupo nuevo `PRESENTACIONES`.
- **Un PPT con contraseña no se reconoce como cifrado:** queda `ppt` y LibreOffice no lo abre, así que termina en `CONVERSION_FALLIDA`, no en `CONTRASENA`. Un PPTX con contraseña sí queda en `CONTRASENA`, porque es el mismo `EncryptedPackage` de los DOCX y XLSX. Detectar el cifrado de PPT pide leer los registros del formato binario; no vale la pena mientras no aparezca.
- **Contrato:** `tipo_origen` suma los tres valores; versión 0.2 en los esquemas, los ejemplos y el README, con la nota del cambio.
- **Imagen:** `libreoffice-impress-nogui`. La imagen de pruebas queda en 936 MB.
- **Arreglo de paso en la imagen:** la etapa de pruebas no copiaba `scripts/`, así que desde T13 la prueba de `medir_muestra.py` fallaba dentro de la imagen. Ahora se copia.
- **Fábrica:** `pptx` (dos diapositivas, con notas del orador en la primera), hecho con `python-pptx`, que entra solo como dependencia de desarrollo; `ppt` y `odp` salen de él con LibreOffice. La prueba de conversión comprueba 2 páginas, el texto de las diapositivas y que la nota no aparece. La prueba de "no soportados" usaba un ODP; ahora usa un dibujo ODG, que sigue sin soporte.
- **Con los PPTX reales de OF-007:** los dos se convierten (20 y 10 páginas, 4,4 s y 2,8 s).

