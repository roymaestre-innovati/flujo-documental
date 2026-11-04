# Spec 003 — Validación y extracción documental (módulo 3)

Estado al 2026-11-04. Borrador para revisión.

Esta iniciativa cubre el módulo 3 sin el clasificador, que es de otro equipo: preparar los documentos que entrega cada oferente, leerlos y extraer sus datos. Se construye por entregas. **Esta versión de la spec cubre solo la primera: normalización y lectura** (pasos 1 y 2 de `contexto/flujo-documental-opcion-a.md`). La extracción (paso 5) se agrega a esta misma spec más adelante.

Siguiendo el principio 1 de la constitución, esta spec habla en términos del proceso de selección. Las herramientas concretas están en `plan.md`.

## Para qué

Cuando un oferente entrega su oferta, los documentos llegan como él los armó: PDF escaneados, Word, Excel, fotos, carpetas anidadas, copias repetidas y archivos basura del computador. Antes de clasificar o extraer nada hay que:

- dejar cada documento en un formato único, con una paginación fija, para que el clasificador y la extracción hablen de las mismas páginas;
- descartar lo que no es documento y marcar las copias repetidas;
- avisar qué documentos no se pueden abrir, para que el evaluador decida si pide subsanación;
- saber qué trae cada página (texto, escaneo, nada) y dejar el texto listo, una sola vez por documento.

## Quién lo usa

| Actor | Qué recibe |
|---|---|
| Clasificador (otro equipo) | El documento normalizado y, si lo quiere, la lectura por página |
| Unidad de extracción (esta iniciativa, entrega siguiente) | El documento normalizado, la lectura por página y el Excel original como anexo |
| Orquestador (iniciativa 005) | El inventario de la entrega, con el estado de cada documento |
| Evaluador | Por medio del orquestador: la lista de documentos con error, cada uno con su motivo |

## Historias

1. **Inventario de la entrega.** Como orquestador, recibo de cada entrega de un oferente (o del proceso: condiciones, adendas, anexos) un inventario con todos sus documentos, la ruta con que los entregó, su huella digital y su estado, para seguir cada uno hasta el informe.
2. **Un solo formato.** Como clasificador y como extracción, recibo cada documento en el mismo formato y con la misma paginación, sin importar si el oferente lo mandó en Word, Excel o foto.
3. **Copias repetidas.** Como evaluador, no reviso dos veces el mismo documento: una copia exacta queda marcada como copia del original y no se procesa otra vez, pero no desaparece.
4. **Documentos que no abren.** Como evaluador, me entero de qué documentos de un oferente no se pudieron abrir y por qué (dañado, protegido con contraseña, formato no soportado), para decidir si pido subsanación.
5. **Hojas de cálculo.** Como extracción, recibo la hoja de cálculo original además de su versión paginada, porque al paginarla se cortan las tablas anchas.
6. **Firma digital.** Como evaluador, sé qué documentos traen firma digital, quién firma, cuándo, y si el documento se modificó después de firmarse.
7. **Lectura por página.** Como extracción y como clasificador, sé de cada página si trae texto del computador, si es un escaneo (con o sin la capa de texto del escáner) o si está en blanco, y tengo su texto y las zonas visuales que importan (líneas de firma, casillas, tablas SI/NO).

## Requisitos

### Inventario y huella

- R1. Se recorre la entrega completa, incluidas las carpetas anidadas, y se guarda la ruta de origen de cada archivo.
- R2. Se descartan los archivos de sistema: `.DS_Store`, `Thumbs.db`, la carpeta `__MACOSX` y los archivos `._*` de Mac. Estos últimos llevan la extensión del original, así que se reconocen por nombre y por contenido, no por extensión. Los descartados quedan anotados en el inventario como descartados, con el motivo.
- R3. Cada archivo lleva su huella (SHA-256 del original).
- R4. Una copia exacta dentro de la misma entrega se marca como copia del primero (por orden de ruta) y no se procesa otra vez. No se borra.
- R5. Cada documento tiene un identificador estable: procesar la misma entrega dos veces da los mismos identificadores.

### Formato único

- R6. El tipo real del archivo se reconoce por su contenido, no por la extensión.
- R7. Word (DOC, DOCX, ODT) se convierte al formato único sin ejecutar macros.
- R8. Las imágenes (JPG, PNG, TIFF) se convierten con una página por imagen. Un TIFF de varias páginas da varias páginas.
- R9. Las hojas de cálculo (XLS, XLSX, ODS) se convierten al formato único, para clasificar y citar páginas, y además se conserva el original como anexo.
- R10. El original nunca se modifica. El documento normalizado es una copia aparte, lo que también deja intactas las firmas digitales.
- R11. Un PDF que ya viene bien se usa tal cual, sin reescribirlo, para no cambiar su paginación ni romper firmas.

### Revisión del documento

- R12. Se revisa si el documento abre. Si está dañado, se intenta repararlo una sola vez; si no se puede, queda con error.
- R13. Un documento que pide contraseña para abrirse queda con error. Uno que solo trae restricciones de copia o impresión se procesa normal y se anota la restricción.
- R14. Se anotan el número de páginas y las páginas sin capa de texto.
- R15. Si el documento trae firma digital, se anota por cada firma quién firma, cuándo y si el documento está íntegro, es decir, si no se modificó después de firmar. Si la firma está en un formato que no se puede leer, se anota que hay una firma sin poder leerla. No se valida si el certificado es confiable (decisión 4 del diseño).
- R16. Un documento sin páginas, un formato no soportado o una conversión fallida quedan con error y su motivo.
- R17. Un documento con error no frena a los demás de la entrega.

### Lectura por página

- R18. Por cada página del documento normalizado se guardan: número de página (sobre el documento completo), tipo de página, texto, origen del texto, fracción de la página cubierta por imágenes, rotación y zonas visuales.
- R19. Tipos de página:
  - `texto`: generada en computador. Tiene texto y la imagen cubre poco de la página.
  - `escaneo_con_ocr`: escaneada, con la capa de texto que le puso el escáner. Tiene texto, pero una imagen cubre más del 80 % de la página.
  - `imagen`: escaneada, sin texto. Casi sin texto y una imagen cubre la página.
  - `vacia`: en blanco o casi. Casi sin texto y sin imagen.
- R20. El origen del texto es `nativo` en las páginas `texto` y `ocr_escaner` en las `escaneo_con_ocr`. El valor `ocr_propio` queda reservado para el experimento de OCR, que no entra en esta entrega.
- R21. Las zonas visuales se ubican por palabras clave y por posición, sin inteligencia artificial: líneas de firma, casillas y tablas SI/NO.
- R22. Las posiciones de cada palabra se guardan aparte, porque pesan.
- R23. La lectura es determinista: el mismo documento da siempre la misma lectura.

### Trazabilidad

- R24. El inventario y la lectura llevan la versión del normalizador y de sus parámetros (por ejemplo, el umbral de cobertura de imagen), para poder reconstruir de dónde salió cada resultado (principio 3).
- R25. Procesar dos veces la misma entrega da el mismo inventario y la misma lectura, salvo la fecha de ejecución.

## Fuera de esta entrega

- OCR propio de las páginas escaneadas (experimento de la decisión 9).
- Validar la confianza de los certificados de firma digital.
- La clasificación y la extracción.
- El disparo automático desde la cola y el estado del proceso: son del orquestador (005). Aquí se entrega la pieza que normaliza y lee una entrega, invocable por línea de comandos y como función.
- Detectar copias entre entregas distintas o entre oferentes distintos. Cada entrega se trata sola, y ningún oferente se compara con otro (principio 6).
- Decidir qué documento cuenta cuando llega una subsanación: lo decide el evaluador (decisión 19).

## Datos personales (principio 6)

| Pregunta | Respuesta |
|---|---|
| ¿Qué dato se captura? | El documento completo y el texto de cada página. Puede traer cédulas, RUT, estados financieros, firmas y datos de contacto de personas. No se extrae ningún campo en esta entrega |
| ¿Para qué requisito? | Para todos los requisitos que se acreditan con documentos: sin normalizar y leer no hay extracción ni evaluación |
| ¿Quién puede verlo? | La unidad de extracción y el clasificador, como servicios. Operación, solo para resolver fallas. El evaluador ve el documento por medio de su tarea de revisión. Ningún oferente ve documentos de otro |
| ¿Cuánto se conserva? | Lo mismo que la evidencia del proceso, porque el documento normalizado y su lectura sostienen cada veredicto (principio 3). El plazo lo define cumplimiento (pregunta S1) |
| Registros (logs) | Nunca llevan texto de las páginas ni nombres de archivo completos: solo identificadores, huellas, conteos y motivos de error |
| Pruebas | Solo con documentos sintéticos generados por las pruebas. Los documentos reales de la muestra no se suben al repositorio |

Antes de procesar documentos reales en un ambiente compartido se corre el checklist de habeas data (constitución, principio 6). El borrador para cumplimiento está en `checklist-habeas-data.md`, en esta carpeta.

## Criterios de aceptación

Con documentos sintéticos, en las pruebas automáticas:

- A1. Cada caso de los requisitos R1 a R25 tiene al menos una prueba.
- A2. Procesar dos veces la misma entrega da resultados idénticos, salvo la fecha de ejecución.

Con la muestra real SR5658940621 (6 oferentes), corrida localmente por el equipo, nunca en la nube:

- A3. Se reproducen los conteos del diseño: unas 415 páginas únicas; 9 copias exactas; 15 PDF con solo restricciones de copia, que se leen; 7 PDF con firma digital; los archivos `._*` descartados.
- A4. La proporción de tipos de página queda cerca de la del diseño (76 % `texto`, 11 % `escaneo_con_ocr`, 8 % `imagen`, 5 % `vacia`), y las diferencias se explican.
- A5. Un oferente se procesa en el orden de un minuto.

## Criterio de adopción (gestión del cambio)

Hoy el evaluador abre, convierte y ordena a mano los archivos de cada oferente. La pieza se considera adoptada cuando, sobre los procesos de un trimestre, al menos el 98 % de los documentos quedan normalizados o con un error explicado, sin que nadie tenga que abrirlos o convertirlos a mano antes de clasificarlos.

## Preguntas abiertas que tocan esta entrega

| # | Pregunta | Qué se supone mientras tanto |
|---|---|---|
| A-1 | ¿Dónde deja el módulo 1 los archivos, cómo avisa y qué identificadores usa? | Carpeta local y un identificador propio, derivado de la ruta; el almacenamiento queda detrás de una interfaz para cambiarlo después |
| A-5 | ¿El clasificador trabaja sobre nuestro documento normalizado y usa nuestra lectura? | Sí |
| A-6 | ¿Se acepta una librería con licencia AGPL? | No: solo licencias permisivas (ver `plan.md`) |
| S1 | Plazo de conservación | Igual al de la evidencia del proceso |
