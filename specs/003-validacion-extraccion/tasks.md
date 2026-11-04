# Tareas 003 — Normalización y lectura (primera entrega)

Sale de `plan.md`. Cada tarea termina con sus pruebas en verde y un commit propio.

## Para quien implemente

- Leer antes `spec.md` y `plan.md` de esta carpeta. El contexto de diseño está en `contexto/flujo-documental-opcion-a.md` (pasos 1 y 2) y las reglas del proyecto, en `contexto/constitucion.md`.
- Los documentos de `contexto/` nombran `Documentos/clasificados/manifiesto.csv`, `matriz/` y documentos reales de oferentes. No están en el repo a propósito, porque traen datos personales, y no hacen falta para esta entrega. No buscarlos ni inventarlos.
- Solo documentos sintéticos, fabricados por las pruebas. No subir ningún PDF fuera de `tests/`.
- Nada de LLM ni de servicios de Azure en este código.
- Escribir en español: código con nombres en español, como en el contrato, y documentos en prosa.
- Si algo del plan no se puede hacer como está escrito, anotarlo en "Notas de implementación", al final de este archivo, y seguir con la alternativa más simple.

Dependencias del sistema: `libreoffice` (writer y calc) y Python 3.12 con `uv`. En Debian o Ubuntu: `apt-get install -y libreoffice-writer libreoffice-calc`.

## Tareas

- [x] **T01 — Contrato.** Escribir `contracts/modulo3-normalizacion/v0/`: `README.md`, `manifiesto.schema.json`, `lectura.schema.json` y `palabras.schema.json` (JSON Schema 2020-12), más ejemplos: una entrega con un normalizado, un duplicado, un error y un descartado, y una lectura con una página de cada tipo. Validar los ejemplos contra los esquemas, como en `contracts/modulo3-extraccion/v0/README.md`. **Detenerse aquí para revisión del usuario** antes de seguir (principio 5).
- [x] **T02 — Esqueleto.** `servicios/normalizacion/` con `pyproject.toml` (uv, pytest), `__init__.py` con `VERSION = "0.1.0"`, `parametros.py`, `almacen.py` (interfaz y `AlmacenLocal`) y el comando `normalizar` que por ahora solo lista la entrega. Agregar la prueba que valida los ejemplos del contrato.
- [x] **T03 — Fábrica de pruebas.** `tests/fabrica.py` con todos los casos de la tabla de pruebas del plan. Una prueba por caso que solo confirma que el archivo se fabricó.
- [x] **T04 — Inventario.** Recorrido recursivo, descarte de archivos de sistema (por nombre y por contenido), SHA-256, duplicados por orden de ruta e `id_documento`. Requisitos R1 a R5.
- [x] **T05 — Tipo real.** `tipos.py` con la tabla del plan. Incluye la extensión falsa y los no soportados. Requisito R6.
- [x] **T06 — Revisión del PDF.** Abrir, reparar una vez, detectar contraseña y restricciones, contar páginas. Requisitos R11 a R13 y R16.
- [x] **T07 — Conversión.** LibreOffice con perfil temporal y macros bloqueadas, con tiempo máximo y un reintento; imágenes con img2pdf, incluido el TIFF de varias páginas; Excel convertido y conservado como anexo. Requisitos R7 a R10.
- [x] **T08 — Firma digital.** Firmante, fecha, integridad, formato y `leida`. Casos: íntegro, modificado después de firmar, sin firma. Requisito R15.
- [ ] **T09 — Lectura.** Texto, caracteres, cobertura de imagen (grilla de 200 × 200), rotación, tipo de página, origen del texto y archivo de palabras. Requisitos R14 y R18 a R20, R22 y R23.
- [ ] **T10 — Anclas.** `linea_firma`, `casilla` y `tabla_si_no`, según el plan. Requisito R21.
- [ ] **T11 — Entrega completa.** `entrega.py` une todo y escribe manifiesto, PDF, anexos, lecturas y palabras en el almacén. Aislamiento de errores (R17), errores de clase 4 relanzados al final, idempotencia y `--forzar`, y registros sin datos personales. Prueba de punta a punta con una entrega sintética que trae todos los casos, validada contra el contrato. Prueba de determinismo (R24 y R25, criterio A2).
- [ ] **T12 — Imagen del job.** `Dockerfile` (Python 3.12 slim, LibreOffice writer y calc, uv) que corre `normalizar`. Comprobar que las pruebas pasan dentro de la imagen.
- [ ] **T13 — Script de la muestra.** `scripts/medir_muestra.py <carpeta>`: corre `normalizar` sobre cada oferente de una carpeta e imprime solo conteos (páginas únicas, duplicados, restricciones, firmas, descartados, proporción de tipos de página y tiempo por oferente), para los criterios A3 a A5. No se corre en la nube: lo corre el usuario con la muestra real.

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
