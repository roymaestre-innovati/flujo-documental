# Handoff: implementación del flujo documental (opción A)

Estado al 2026-11-05, después de la primera medición con la muestra real. Sigue en una sesión local, en la máquina del usuario.

Las rutas relativas son de este repositorio; lo que está en otros repos va con ruta completa. `contexto/flujo-documental-opcion-a.md` sigue siendo la fuente de verdad del diseño. Este archivo no repite el diseño: dice qué existe, qué falta, qué está abierto y cómo trabaja el usuario.

## Dónde quedamos

- **Iniciativa 003, entrega 1 (normalización y lectura): implementada.** Las 13 tareas de `specs/003-validacion-extraccion/tasks.md` están hechas, con 387 pruebas sobre documentos inventados, y fusionadas en `main`. El código está en `servicios/normalizacion/` y el contrato en `contracts/modulo3-normalizacion/v0/`.
- **Primera medición con la muestra real: hecha el 2026-11-05.** Los resultados los escribió el usuario en `specs/003-validacion-extraccion/resultados-muestra.md`, y la revisión está más abajo ("Medición con la muestra real"). La normalización funciona con documentos reales y los umbrales no cambian. Quedan seis decisiones y algunas tareas nuevas antes de cerrar la entrega 1.
- **Checklist de habeas data:** borrador en `specs/003-validacion-extraccion/checklist-habeas-data.md`, todavía sin respuestas de cumplimiento. La medición se hizo antes de tenerlas (ver "Datos personales", más abajo).
- **Archivo de palabras:** el usuario decidió mantenerlo (2026-11-05), aunque hoy no tiene quien lo use. Se revisa cuando se planee la extracción o se sepa si el clasificador lo usa (A-5).

## Cómo trabaja el usuario

- Escribe en español: código con nombres en español, commits y documentos en prosa.
- **Una tarea a la vez.** Por cada tarea: rama nueva desde `main` (`normalizacion-tNN`), pruebas en verde, notas en `tasks.md`, commit, push y un resumen corto. **Después se detiene.** El usuario revisa, fusiona el pull request en GitHub y escribe "ya hice el merge, sigue con TNN".
- **Las dudas no se resuelven solas.** Lo ambiguo se anota en "Notas de implementación" de `tasks.md` y se le pregunta, con una recomendación primero. Suele aceptar la recomendada, pero a veces elige otra o pide explicación ("no entiendo bien…"). Cuando pide explicación, quiere algo simple, con ejemplos.
- Prefiere lo simple: si una propuesta crece, ofrecer la versión más simple.
- Commits y pushes solo dentro de ese flujo, o si los pide. No publicar ni crear pull requests sin pedirlo.

## Qué leer, en este orden

1. Este archivo.
2. `specs/003-validacion-extraccion/resultados-muestra.md`: la primera medición con la muestra real.
3. `specs/003-validacion-extraccion/tasks.md`, sobre todo las "Notas de implementación": cada decisión tomada al implementar y su porqué.
4. `specs/003-validacion-extraccion/spec.md` y `plan.md` (al final del plan, "Lo que cambió al implementar").
5. `contexto/constitucion.md`: los siete principios.
6. `contexto/flujo-documental-opcion-a.md`: el diseño completo (decisiones 1 a 31 y preguntas A-1 a A-11).
7. `servicios/normalizacion/README.md`: cómo instalar, correr y probar.
8. Para lo que viene después (extracción): `contracts/modulo3-extraccion/v0/` y `contexto/refinamiento-grill-me-2.md` (D1 a D24).

## Reparto

El usuario es dueño de todo el flujo menos tres piezas de otros equipos: la entrada de documentos (módulo 1), el clasificador y la Power App de revisión. En términos de la constitución, eso es el módulo 3 (sin el clasificador), el módulo 4 (reglas e informe) y el módulo 5 (orquestador). No se construyen el clasificador ni la Power App: se tratan como contratos de entrada y salida.

## Qué existe ya

| Pieza | Dónde | Estado |
|---|---|---|
| **Normalización y lectura** | `servicios/normalizacion/` | Hecha (iniciativa 003, entrega 1). Comando `normalizar`, imagen Docker, script de la muestra |
| **Contrato de normalización** | `contracts/modulo3-normalizacion/v0/` | Versión `modulo3-normalizacion/0.1`, revisada con el usuario |
| Contrato de extracción | `contracts/modulo3-extraccion/v0/` | Versión 0.1. Los ocho cambios para la 0.2 (paso 5 del diseño) no se han aplicado |
| Checklist de habeas data | `specs/003-validacion-extraccion/checklist-habeas-data.md` | Borrador para cumplimiento |
| Resultados de la muestra real | `specs/003-validacion-extraccion/resultados-muestra.md` | Primera medición (2026-11-05), escrita por el usuario. Solo conteos |
| Matriz de campos por TD (TD-01 a TD-35) | Fuente: `~/GEB/Extraccion/matriz/campos.py`, que genera el Excel con `generar_matriz.py` | En uso. El Excel es generado: no se edita a mano |
| Modelo semántico y servidor MCP | `~/GEB/modelo-semantico` (repo aparte): modelo en Cosmos DB, servidor en Container Apps | Desplegado; modelo `extraccion_documental` en v21 |
| Agente de extracción de prueba | `~/GEB/modelo-semantico/agente_local/chat.py` y `lote.py` | Arnés de pruebas con gpt-5.4. No es el servicio de producción |
| Gold por tipo documental | `~/GEB/Extraccion/Documentos/pruebas/TD-NN/gold_TD-NN.xlsx` (no van a git: datos reales) | TD-03, 05, 15, 16, 17, 18, 26, 27, 29, 30 y 35. Estado en `Documentos/pruebas/HANDOFF.md` |
| Clasificación manual de la muestra | `Documentos/clasificados/manifiesto.csv` (no está en este repo: datos reales) | Sirve como clasificador falso |
| Documentos reales de SR5658940621 | `~/GEB/Extraccion/Documentos/98. PCA SR5658940621- …/` | 6 oferentes, CPC y 3 adendas. No van a git |
| Plantilla de evaluación | `insumos/Matriz_Extraccion_Evaluacion_Ofertas_PCA-SR5587392192.xlsx` | Formato del informe |

No existe código de orquestación, extracción como servicio, reglas, tareas ni informe.

## Medición con la muestra real (2026-11-05)

Los resultados completos están en `specs/003-validacion-extraccion/resultados-muestra.md`. En corto: la muestra 1 son los 6 oferentes del proceso de referencia, y la muestra 2 es un oferente más (OF-007), con 553 páginas y muchos Word y Excel. En total fueron 1.004 páginas, sin fallas del programa. La máquina local es la mitad de rápida que la de referencia (las pruebas tardan 2 min 56 s frente a 1 min 30 s).

| Criterio | Resultado | Lectura |
|---|---|---|
| A3, conteos | Muestra 1: 451 páginas, 8 copias, 15 PDF con restricciones y 6 con firma digital (diseño: 415, 9, 15 y 7) | Se parece al diseño |
| A4, tipos de página | Muestra 1: 78 % texto, 11 % escaneo con OCR, 6 % imagen y 6 % vacía (diseño: 76, 11, 8 y 5) | A 2 puntos o menos: **los umbrales no cambian** y `version_parametros` sigue en 1 |
| A5, tiempo | De 5 a 61 s en la muestra 1, a unos 0,3 s por página de PDF. OF-007 tardó 310 s, 134 de ellos en Excel | Se cumple para un oferente típico. OF-007 es atípico por tamaño |

**Revisión hecha en la nube** (2026-11-05). Las cuentas cuadran: los tipos de página suman las páginas únicas en cada muestra y en el total, las firmas suman 20 y los comprimidos coinciden en las dos tablas. Faltan cinco cosas:

1. **`.gitignore` y `salida1/`.** El documento menciona las carpetas de salida `salida` y `salida1`, y el patrón `salida-*/` no cubría `salida1/`. Ya se cambió a `salida*/` y `muestra*/`, pero hay que **borrar esas carpetas** (tienen datos personales) y revisar que no se hayan subido.
2. **Firmas `adbe.pkcs7.sha1`.** Para que las cuentas cierren, son 3 en la muestra 1 (las mismas del diseño: Cámara de Comercio y RUP) y 1 en OF-007. Conviene escribirlo en el documento.
3. **Las 36 páginas de más** (451 frente a 415). Se puede comprobar si vienen de los 5 Excel sumando sus páginas en los manifiestos. La copia exacta que falta (8 frente a 9) podría estar dentro del ZIP de OF-001 que trae 3 PDF que no se midieron.
4. **El sello de tiempo de OF-006** cuenta hoy dentro de los "6 PDF con firma digital". Si es lo único que tiene ese PDF, el número real es 5.
5. **Tiempos:** en la máquina de referencia, OF-007 rondaría los 150 s.

### Hallazgos

- **Llegan archivos comprimidos.** Son 8 ZIP y 5 RAR, aunque el diseño daba por confirmado que no llegaban. Quedan `NO_SOPORTADO`. En 7 de los 8 ZIP el contenido ya está suelto en la carpeta. Un ZIP de OF-001 trae 3 PDF que no se midieron, y los 4 RAR de OF-002 no se pudieron abrir: **son lo más urgente de revisar**, porque pueden esconder documentos.
- **PowerPoint:** OF-007 entregó 2 PPTX, que quedan `NO_SOPORTADO`.
- **Firmas:** de 20, se leyeron 13 (11 íntegras y 2 no íntegras). Causas de las 7 no leídas: 4 `adbe.pkcs7.sha1` (riesgo conocido), 2 `adbe.pkcs7.detached` con el algoritmo mal declarado por el programa que firmó, y 1 sello de tiempo `ETSI.RFC3161`, que no es una firma de persona. De las 2 no íntegras, la de OF-005 es correcta (el archivo se reescribió) y la de OF-006 puede ser una falsa alarma.
- **Un Excel de una página, de menos de 1 MB, tardó 85 s en convertirse** (el límite es 120 s). Arrancar LibreOffice cuesta unos segundos, no 85. Causas típicas: una hoja con formato aplicado hasta el final de la planilla, muchas fórmulas que se recalculan al abrir, o vínculos externos.

### Decisiones pendientes del usuario

Vienen del documento de resultados, con la opción recomendada primero. El usuario todavía no las ha tomado.

| Tema | Recomendación | Alternativa | Nota de la revisión |
|---|---|---|---|
| ZIP y RAR | Pedir al módulo 1 (A-1) que confirme que en producción todo llega descomprimido. Para la medición, descomprimir a mano y repetir solo esos oferentes | Que el normalizador descomprima | De acuerdo. Empezar por los RAR de OF-002 |
| PPTX | Convertirlos con LibreOffice | Dejarlos `NO_SOPORTADO` y pedir subsanación en PDF | No es un cambio pequeño: hace falta Impress en la imagen (hoy solo hay Writer y Calc) y agregar `pptx` a los tipos de origen del contrato (está en 0.x, así que se puede avisando). Toca el contrato, `tipos.py`, `conversion.py`, el Dockerfile y la fábrica |
| Excel de 85 s | Convertir solo ese archivo, midiendo, para ver qué lo frena | Subir el límite de 120 s | De acuerdo |
| Sello de tiempo `ETSI.RFC3161` | No contarlo como firma digital | Dejarlo como firma no leída | El esquema no cambia: basta con no contarlo y anotarlo en el README del contrato. Se reconoce por `/Type /DocTimeStamp` o por el subfiltro |
| Firmas con el algoritmo mal declarado | Dejarlas no leídas y anotarlo; tolerarlas si se repiten | Tolerarlas desde ya | De acuerdo |
| CAdES posiblemente falsa alarma (OF-006) | Dejarla no íntegra | Aceptar cambios de estructura posteriores a la firma | De acuerdo |

### Tareas que saldrían de esas decisiones

Si el usuario acepta las recomendaciones, son tareas nuevas en `tasks.md`, con el mismo flujo: una rama por tarea, resumen y alto.

- **T14 — Sello de tiempo.** No contar un `/DocTimeStamp` (`ETSI.RFC3161`) en `firma_digital`. Agregar un caso a la fábrica y una nota en el README del contrato.
- **T15 — PowerPoint.** Agregar `pptx` (y quizá `ppt` y `odp`) al contrato, a `tipos.py` y a `conversion.py`, `libreoffice-impress-nogui` a la imagen y un caso a la fábrica.
- **Diagnóstico del Excel lento.** No es tarea de código: medir ese archivo solo, en la máquina local.
- **ZIP y RAR.** Solo si el módulo 1 dice que en producción pueden llegar comprimidos: la descompresión sería otra tarea, con sus riesgos (bombas de compresión, rutas maliciosas, contraseñas).

### Datos personales

- La medición se hizo antes de tener las respuestas de cumplimiento, y el checklist marcaba HD-14 como bloqueante. El documento de resultados lo dice. **Al pasarle el checklist a cumplimiento, contarlo**, junto con que una herramienta auxiliar mostró en consola el nombre de un firmante durante el diagnóstico de firmas (el normalizador no lo hace).
- Borrar las carpetas de salida (`salida` y `salida1`) cuando ya no hagan falta.
- El documento de resultados está en el repositorio y solo trae conteos y códigos de oferente: no tiene nombres ni contenido.

## Pendiente

### Decisiones tomadas al implementar que el usuario no confirmó de forma explícita

Fusionó las tareas, pero no respondió estas preguntas. Conviene confirmarlas:

- **T10, anclas:** "una palabra que empieza por firma" se tomó como una frase cuya *primera* palabra empieza por "firma" (así "la firma del contrato", en medio de un párrafo, no cuenta).
- **T11, entrega:** ante un bug, los demás documentos se escriben pero el manifiesto no. La idempotencia se decide con el manifiesto anterior, no con la lectura. Consecuencia: después de una corrida con bug, el reintento procesa todo.
- **T08, firma:** una firma que se lee pero no trae firmante o fecha queda `leida: false`, porque el contrato exige los dos.

### Para calibrar todavía

La medición confirmó los umbrales de tipo de página y el tiempo. Lo que sigue sin revisar con documentos reales:

- Páginas con una foto chica en una hoja blanca, que hoy quedan `vacia`.
- Si `extract_text()` junta bien las columnas de las tablas anchas.
- Falsos positivos de anclas: bordes de tabla como líneas de firma, y "si"/"no" en renglones de tablas.
- Casillas que no se detectan: las escritas como símbolo (☐), las dibujadas con curvas y las de formularios PDF.
- HEIC, RTF y PDF con bytes antes de `%PDF-`: no aparecieron en la muestra.

Si se cambia un parámetro, sube `version_parametros`: ya hubo una corrida real.

### Preguntas de otros equipos que afectan lo construido

- **Cumplimiento:** HD-1 a HD-14 del checklist; incluye S1 (conservación) y S2 (enviar datos a eastus).
- **A-1, módulo 1:** dónde dejan los archivos y qué identificadores usan. Cambia el almacén (hoy solo hay `AlmacenLocal`) y quizá `id_documento`. **Agregar a la pregunta:** si en producción pueden llegar ZIP o RAR (la muestra trajo 13).
- **A-5, clasificación:** si clasifican sobre nuestro PDF normalizado y usan nuestra lectura.
- **A-6, arquitectura:** licencias. Se evitó AGPL (PyMuPDF); img2pdf es LGPL-3.0 y queda anotado.

### No hecho en la entrega 1

- Almacén en Blob Storage (espera A-1) y conexión a la cola (iniciativa 005, orquestador).
- Análisis de vulnerabilidades de la imagen y publicación en un registro de Azure.
- Experimento de OCR propio (decisión 9).

## Lo que viene después

La entrega 1 se cierra cuando se tomen las seis decisiones de arriba, se hagan las tareas que salgan de ellas y se repita la medición de OF-001, OF-002 y OF-007 con los comprimidos abiertos. Después el usuario elige con qué seguir. Opciones que salen del diseño:

- **Entrega 2 de la iniciativa 003: extracción.** Agregarla a `spec.md` y escribir su plan en la misma carpeta. Empieza por el contrato 0.2 de extracción (decisión 25), como versión nueva, sin editar la vigente (principio 5). Depende de S2 (enviar datos a eastus).
- **Iniciativa 005: orquestador** (Service Bus, workers, estado en Cosmos), que llama a la normalización como función.
- **Módulo 4: reglas e informe**, con la hoja Reglas de la matriz (decisión 28).

Pendientes del diseño que siguen abiertos: medir la ficha inyectada (decisión 26), imágenes solo donde hacen falta (decisión 8), TD-98 (decisión 14).

Pendiente de una sesión anterior: el usuario preguntó por qué, en el diagrama de secuencia, el mensaje "archivo listo" pasa por Orquestación antes del clasificador. Se propuso partir el participante "Orquestación" en "Worker de clasificación" y "Worker de resultados y reglas", y no respondió. Si el usuario retocó el `.drawio` a mano, se edita ese archivo directamente: no se regenera con el script.

## Riesgos y datos técnicos conocidos

- **gpt-5.4 es obligatorio en la extracción:** gpt-5.4-mini no respeta las reglas de evidencia (prueba con TD-17).
- **429:** la concurrencia de extracción hoy es 3. Un proceso de 10 oferentes son unos 160 segmentos, unos 20 minutos.
- **Service Bus entrega mensajes dos veces a veces:** la normalización ya es idempotente; los demás workers también deben serlo.
- **Firma digital:** las firmas `adbe.pkcs7.sha1` (Cámara de Comercio, RUP) quedan como "firma que no se pudo leer" (`leida: false`). Leerlas necesita otra herramienta.
- **LibreOffice:** la imagen pesa 1,2 GB. Si A-1 resulta en SharePoint, se puede evaluar la conversión de Graph API. Hay Excel que tardan mucho en convertirse (85 s en la muestra, con un límite de 120 s).
- **Firmas que pyHanko no lee:** además de `adbe.pkcs7.sha1`, las que declaran mal el algoritmo (2 en la muestra).
- **Fuentes:** sin fuentes con las medidas de Office (Carlito, Caladea, Liberation), los Word y Excel cambian de paginación al convertirse. La imagen las trae; una máquina local quizá no.

## Datos de la sesión en la nube

- Docker Hub limitaba las descargas: se usó el espejo `mirror.gcr.io`. Localmente no debería hacer falta.
- La red de la nube no permitía paquetes de Debian, y por eso la imagen es Ubuntu 24.04. El usuario lo confirmó.

## Qué no hacer

- No construir el clasificador ni la Power App.
- No procesar documentos reales sin las respuestas de cumplimiento, ni subir al repositorio documentos reales o salidas con datos personales.
- No editar el Excel de la matriz: se regenera desde `~/GEB/Extraccion/matriz/campos.py`.
- No publicar versiones del modelo semántico sin que el usuario lo pida.
- No regenerar `flujo_documental_c4.drawio` si el usuario lo retocó.
- No meter LLM en normalización, lectura, orquestación ni reglas: el diseño los dejó deterministas a propósito.
- No editar un contrato vigente de forma incompatible: va versión nueva (principio 5). El de normalización sigue en 0.x, así que se puede cambiar avisando, pero conviene dejarlo estable.
