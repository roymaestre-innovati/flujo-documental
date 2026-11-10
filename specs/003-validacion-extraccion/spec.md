# Spec 003 — Validación y extracción documental (módulo 3)

Estado al 2026-11-05. **Entrega 1 (normalización y lectura) cerrada** (`tasks.md`, T01 a T16; normalizador 0.2.0, contrato `modulo3-normalizacion/0.2`). Medida con la muestra real en dos rondas (`resultados-muestra.md`): los criterios A3 a A5 se cumplen y los umbrales no cambian. El checklist de habeas data (`checklist-habeas-data.md`) sigue sin respuesta de cumplimiento.

**Entrega 2 (extracción) en revisión** desde el 2026-11-09: sección "Entrega 2 — Extracción", al final. Su plan y sus tareas están en `plan-extraccion.md` y `tasks-extraccion.md`.

Esta iniciativa cubre el módulo 3 sin el clasificador, que es de otro equipo: preparar los documentos que entrega cada oferente, leerlos y extraer sus datos. Se construye por entregas. Las secciones de aquí hasta "Preguntas abiertas que tocan esta entrega" son la primera entrega, normalización y lectura (pasos 1 y 2 de `contexto/flujo-documental-opcion-a.md`). La segunda, extracción (paso 5), va al final.

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

---

# Entrega 2 — Extracción

Estado al 2026-11-10: **construida** (`tasks-extraccion.md`, T01 a T10; servicio 0.1.0 en `servicios/extraccion/`), con 207 pruebas sobre documentos inventados. Falta A9: la medición con los gold de TD-16 y TD-29, que corre el usuario con `medir-gold` después de autorizar que esos documentos vayan a gpt-5.4. Paso 5 de `contexto/flujo-documental-opcion-a.md` y decisiones D10 a D24 de `contexto/refinamiento-grill-me-2.md`. Contrato: `contracts/modulo3-extraccion/v0.2/` (ya publicado, no cambia en esta entrega).

Decisiones del usuario que la enmarcan (2026-11-09):

- El servicio vive en este repositorio, junto a la normalización y el orquestador.
- El modelo de lenguaje recibe en un solo mensaje el documento y la ficha del tipo documental, sin consultas intermedias. En la versión final, la ficha se pide al servidor del modelo semántico que ya existe, con la versión fijada en el proceso.
- La entrega es local: lee las solicitudes que deja el orquestador y escribe un resultado por segmento. Incluye mostrar los resultados en el visor de corridas.
- Se arranca con la versión actual del modelo semántico, aunque todavía no traiga el identificador de cada regla, su ámbito, el validador ni la marca de tipo documental probado. Lo que depende de eso queda en su valor seguro.

## Para qué

Cada segmento ya clasificado tiene que convertirse en los datos que el proceso necesita para evaluar al oferente: el NIT del certificado, quién firma, si la casilla dice SI o NO. Hoy un evaluador los busca a mano en cada documento. La extracción:

- toma los datos que el modelo semántico define para el tipo documental del segmento;
- deja de cada dato su evidencia (página y cita), para que cualquier veredicto se pueda reconstruir (principio 3);
- decide con reglas fijas, y no con el modelo de lenguaje, qué datos tiene que revisar una persona y por qué (principio 4);
- señala las reglas que necesitan otros documentos o las condiciones del proceso, para que las resuelva el módulo 4.

## Quién lo usa

| Actor | Qué recibe |
|---|---|
| Orquestador (iniciativa 005, entrega 2) | Un resultado por segmento: estado, datos, campos en revisión y error si lo hubo |
| Módulo 4 (reglas e informe) | Por medio del orquestador: los datos con su evidencia y las reglas pendientes |
| Evaluador | Por medio de la tarea de revisión: los campos en revisión con su motivo, su evidencia y una observación |
| Equipo (en local) | Los resultados en el visor de corridas, al lado del documento |

## Historias

1. **Datos de un segmento.** Como orquestador, pido la extracción de un segmento (documento, páginas, tipo documental y versión del modelo) y recibo un resultado con un dato por cada campo del tipo documental, incluidos los que no aparecen.
2. **Evidencia.** Como evaluador, veo de cada dato la página y el texto del documento de donde salió, o la descripción de lo que solo se ve en la imagen (una firma, una casilla marcada).
3. **Qué reviso y por qué.** Como evaluador, reviso solo los campos que lo necesitan, y cada uno trae su motivo: confianza baja, no cumple, obligatorio vacío, requiere imagen, plantilla sin llenar, validación fallida, tipo documental no probado o clasificación dudosa.
4. **Reglas de otros documentos.** Como módulo 4, recibo aparte las reglas que el documento no puede resolver solo (cruces con otros documentos, parámetros del proceso), sin que manden el campo a revisión.
5. **Igualdad de trato.** Como evaluador, sé que todos los oferentes del proceso se extrajeron con la misma versión del modelo semántico, y el resultado dice cuál fue.
6. **Pedido repetido.** Como orquestador, si pido dos veces el mismo segmento, recibo el mismo resultado sin volver a pagar la extracción, salvo que pida reprocesarlo.
7. **Fallas.** Como orquestador, distingo un documento que no se puede extraer (páginas fuera de rango, ilegible) de una falla técnica (el modelo de lenguaje no respondió), para mandar el primero al evaluador y la segunda a operación.
8. **Ver los resultados.** Como equipo, abro una corrida en el visor y veo los datos de cada segmento al lado del documento, con los campos en revisión resaltados.

## Requisitos

La numeración sigue la de la entrega 1.

### Entrada

- R26. Se acepta solo una solicitud que cumpla el contrato de entrada 0.2. Una solicitud que no lo cumple es un error de quien la mandó y no se extrae.
- R27. Se trabaja sobre la lectura que ya hizo la normalización: el documento solo se vuelve a abrir para sacar las imágenes de las páginas que las necesitan.
- R28. Si la huella del documento no coincide con la de la solicitud o con la de su lectura, no se extrae: es una falla técnica, porque el documento cambió después de clasificarse.
- R29. Un rango de páginas fuera del documento es un error del documento (`error_entrada`).
- R30. La ficha del tipo documental se toma de la versión del modelo que trae la solicitud, nunca de la vigente (principio 7).

### Qué ve el modelo de lenguaje

- R31. Solo se le muestran las páginas del segmento, numeradas sobre el documento completo.
- R32. Por cada página, según su tipo:
  - `texto`: el texto. La imagen, solo si la página tiene zonas visuales (líneas de firma, casillas, tablas SI/NO).
  - `escaneo_con_ocr` e `imagen`: la imagen completa. El texto del escáner, si lo hay, va como apoyo y marcado como texto de escáner.
  - `vacia`: nada.
- R33. Cada línea de firma se muestra además ampliada, para distinguir una firma de una línea vacía (D20).
- R34. Si el documento era una hoja de cálculo, se le muestran también los valores de la hoja original, porque al paginarla se cortan las tablas anchas.
- R35. Recibe, en un solo mensaje, la guía de interpretación y la ficha del tipo documental de la versión fijada, y el contenido del segmento. No conversa ni consulta nada más.
- R36. El resultado declara qué se le mostró: páginas con texto, páginas solo con imagen y páginas con firma ampliada.

### Qué devuelve

- R37. Un resultado por cada campo del tipo documental que se extrae, en el orden del modelo, incluidos los que no aparecen (sin valor). Los campos calculados no se extraen.
- R38. Cada resultado tiene siempre la misma forma: identificador del campo, valor, confianza, evidencia, cumple, reglas pendientes, revisión, motivos, observación y si trae datos personales (D14).
- R39. La evidencia es una lista de citas con página, texto tal como está en el documento y descripción de lo visual. Una cita de una página fuera del segmento no vale.
- R40. `cumple` evalúa solo las reglas que se resuelven con el propio documento. Las reglas que necesitan otros documentos o parámetros del proceso van en `reglas_pendientes` y no mandan el campo a revisión.
- R41. Si el contenido no es del tipo documental indicado, el resultado es `no_corresponde`, sin datos, y lo decide el modelo de lenguaje. No se reclasifica.
- R42. Lo que el evaluador debe saber del documento y no es de un campo va como alertas con código, nunca como texto libre suelto.

### Revisión (la decide el código)

- R43. Lo que diga el modelo de lenguaje sobre la revisión no cuenta. El código calcula la revisión de cada campo y sus motivos con reglas fijas:
  - `CONFIANZA_BAJA`: la confianza es menor que el umbral del campo en la ficha.
  - `NO_CUMPLE`: `cumple` es NO.
  - `OBLIGATORIO_VACIO`: el campo es obligatorio y quedó sin valor.
  - `VALIDACION_FALLIDA`: falla un validador del campo (por ejemplo, un valor fuera de los permitidos o una cita fuera del segmento).
  - `TD_NO_PROBADO`: el tipo documental no se ha probado con documentos reales.
  - `CLASIFICACION_DUDOSA`: la solicitud llegó con la clasificación dudosa.
- R44. Hay motivos que solo se reconocen leyendo el documento: `REQUIERE_IMAGEN`, `PLANTILLA_SIN_LLENAR`, `NOTA_ELEMENTO` y `CONTRADICCION`. Esos los propone el modelo de lenguaje, y el código los acepta solo si están en el catálogo.
- R45. Un campo va a revisión si tiene al menos un motivo, y nunca va a revisión sin motivo.
- R46. Mientras la ficha no diga qué tipos documentales están probados, todos se tratan como no probados: todos sus campos van a revisión con `TD_NO_PROBADO` (lado seguro del principio 4).
- R47. Los validadores deterministas son genéricos y se aplican según lo que declare la ficha, sin código por tipo documental (D16, principio 2). Con la versión actual del modelo solo se aplican los valores permitidos.
- R48. La confianza es la que da el modelo de lenguaje y no se mezcla con los validadores (D17).

### Fallas, repeticiones y costo

- R49. Las fallas pasajeras (el servicio no responde, se agota el tiempo) se reintentan hasta 3 veces con espera creciente. Un aviso de límite de uso se espera y no cuenta como intento.
- R50. Una respuesta que no tiene la forma pedida se pide otra vez hasta 2 veces.
- R51. Agotados los reintentos, el resultado es `error_proceso`, con el código del error y si se puede reintentar. Un bug no se reintenta.
- R52. Como máximo 3 segmentos se extraen a la vez (límite de uso del modelo).
- R53. La misma solicitud (mismo documento, páginas, tipo documental y versión del modelo) devuelve el resultado guardado, marcado como repetido, salvo que pida reprocesar. Una falla técnica no se guarda: la siguiente vez se intenta de nuevo.
- R54. Cada resultado lleva su ejecución: identificador, inicio, duración, tokens, modelo de lenguaje, versión del prompt, versión del servicio y reintentos.

### Trazabilidad

- R55. El resultado lleva la versión del modelo semántico, del prompt y del servicio, para reconstruir de dónde salió cada dato (principio 3).
- R56. Todo resultado se valida contra el contrato de salida antes de escribirse. Si no lo cumple, es un bug.

### Visor

- R57. El visor de corridas muestra, por segmento, el estado de la extracción y sus campos: valor, confianza, evidencia con enlace a su página, motivos y reglas pendientes, con los campos en revisión resaltados.

## Fuera de esta entrega

- Azure: la cola real, el almacenamiento en la nube y el despliegue como servicio.
- Las trazas completas de 30 días (D23) y el gate de regresión con los gold (D24).
- Partir las reglas de la matriz con identificador y ámbito, declarar validadores, rol revisor y tipo documental probado, y publicar una versión nueva del modelo semántico. Lo pide el usuario cuando quiera.
- El texto de escáner propio (experimento de la decisión 9).
- Recibir los resultados en el orquestador (su entrega 2): pasar segmentos a extraído o en revisión y crear las tareas de revisión.
- Las cajas por cita (P1) y el tipo documental sugerido en `no_corresponde` (C4).

## Datos personales (principio 6)

| Pregunta | Respuesta |
|---|---|
| ¿Qué dato se captura? | Los campos de cada tipo documental. Muchos son personales: nombres, cédulas, tarjetas profesionales y firmas. La ficha marca cuáles |
| ¿Para qué requisito? | El que cita cada campo en la matriz (habilitantes jurídicos, financieros, técnicos y factores de puntaje) |
| ¿Quién puede verlo? | El orquestador y el módulo 4, como servicios. El evaluador ve los campos de su tarea de revisión. Ningún oferente ve datos de otro |
| ¿Dónde se procesa? | El contenido del segmento se manda a un modelo de lenguaje en la nube. Hoy está fuera de Colombia (S2 / HD-10, sin respuesta) |
| ¿Cuánto se conserva? | El resultado se conserva como la evidencia del proceso (S1). No se guardan las imágenes que se le mandaron al modelo ni su conversación |
| Registros (logs) | Solo identificadores, conteos, tiempos, tokens y códigos de error. Nunca valores, citas ni texto del documento |
| Pruebas | Solo con documentos inventados y con un modelo de lenguaje falso que responde con los ejemplos del contrato |

**Antes de mandar un documento real al modelo de lenguaje** hacen falta las respuestas de HD-10 (procesar en Estados Unidos) y, para el uso en la nube, HD-5 (Microsoft como encargado), del checklist `checklist-habeas-data.md`. Mientras tanto, solo lo corre el usuario, en su máquina y con autorización explícita.

## Criterios de aceptación

Con documentos inventados y el modelo de lenguaje falso, en las pruebas automáticas:

- A6. Cada caso de los requisitos R26 a R57 tiene al menos una prueba.
- A7. Las solicitudes de los ejemplos del contrato dan resultados que cumplen el contrato de salida, con los mismos campos en revisión y los mismos motivos que los ejemplos de salida (teniendo en cuenta R46).
- A8. Una corrida de punta a punta (normalización de documentos inventados, solicitudes como las del orquestador, extracción) escribe un resultado válido por solicitud, y correrla dos veces no vuelve a llamar al modelo.

Con documentos reales, solo si el usuario lo autoriza y lo corre en su máquina:

- A9. Con los gold de TD-16 y TD-29, la exactitud por campo no baja frente a las corridas actuales del agente de prueba (decisión 26). Si baja, no se usa la versión de un solo mensaje con documentos reales hasta corregirlo.

## Criterio de adopción (gestión del cambio)

Hoy el evaluador copia a mano los datos de cada documento a la hoja de evaluación. La extracción se considera adoptada cuando, en los procesos de un trimestre, el evaluador confirma o corrige los campos desde su tarea de revisión, sin hoja paralela, y al menos el 70 % de los campos de los tipos documentales probados se aceptan sin cambios (cifra propuesta, por confirmar con negocio). Se mide con las correcciones de los revisores (P2).

## Preguntas abiertas que tocan esta entrega

| # | Pregunta | Qué se supone mientras tanto |
|---|---|---|
| S2 / HD-10 | ¿Se acepta procesar documentos en Estados Unidos? | Nada real sale de la máquina del usuario sin su autorización |
| S1 / HD-8 | ¿Bastan 30 días de traza? | No se guarda traza: solo el resultado y los registros sin datos |
| R1 | Identificador estable de regla | Provisional: `<id_tecnico>.r<n>`, en el orden en que el modelo de lenguaje las reporta |
| O2 | Forma final de las referencias a archivos | URI `file://` del almacén local, resueltas por lo que va después de `almacen/` |
| N-B | Umbral de confianza de cada campo | El de la ficha, sin validar con negocio |
| C4 | ¿`no_corresponde` lleva un tipo documental sugerido? | No |
