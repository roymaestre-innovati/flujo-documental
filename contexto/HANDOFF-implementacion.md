# Handoff: implementación del flujo documental (opción A)

Estado al 2026-11-04, al cerrar la sesión en la nube. Sigue en una sesión local, en la máquina del usuario.

Las rutas relativas son de este repositorio; lo que está en otros repos va con ruta completa. `contexto/flujo-documental-opcion-a.md` sigue siendo la fuente de verdad del diseño. Este archivo no repite el diseño: dice qué existe, qué falta, qué está abierto y cómo trabaja el usuario.

## Dónde quedamos

- **Iniciativa 003, entrega 1 (normalización y lectura): hecha.** Las 13 tareas de `specs/003-validacion-extraccion/tasks.md` están implementadas, probadas (387 pruebas, solo con documentos inventados) y fusionadas en `main`. El código está en `servicios/normalizacion/` y el contrato en `contracts/modulo3-normalizacion/v0/`.
- **Checklist de habeas data: borrador listo** en `specs/003-validacion-extraccion/checklist-habeas-data.md`, con 14 preguntas para cumplimiento (HD-1 a HD-14). El usuario lo va a pasar a cumplimiento.
- **Siguiente paso natural:** medir la muestra real con `scripts/medir_muestra.py` (criterios A3 a A5) y calibrar. Para eso hacen falta antes las respuestas HD-1 a HD-4 y HD-14 del checklist.

## Cómo trabaja el usuario

- Escribe en español: código con nombres en español, commits y documentos en prosa.
- **Una tarea a la vez.** Por cada tarea: rama nueva desde `main` (`normalizacion-tNN`), pruebas en verde, notas en `tasks.md`, commit, push y un resumen corto. **Después se detiene.** El usuario revisa, fusiona el pull request en GitHub y escribe "ya hice el merge, sigue con TNN".
- **Las dudas no se resuelven solas.** Lo ambiguo se anota en "Notas de implementación" de `tasks.md` y se le pregunta, con una recomendación primero. Suele aceptar la recomendada, pero a veces elige otra o pide explicación ("no entiendo bien…"). Cuando pide explicación, quiere algo simple, con ejemplos.
- Prefiere lo simple: si una propuesta crece, ofrecer la versión más simple.
- Commits y pushes solo dentro de ese flujo, o si los pide. No publicar ni crear pull requests sin pedirlo.

## Qué leer, en este orden

1. Este archivo.
2. `specs/003-validacion-extraccion/tasks.md`, sobre todo las "Notas de implementación": cada decisión tomada al implementar y su porqué.
3. `specs/003-validacion-extraccion/spec.md` y `plan.md` (al final del plan, "Lo que cambió al implementar").
4. `contexto/constitucion.md`: los siete principios.
5. `contexto/flujo-documental-opcion-a.md`: el diseño completo (decisiones 1 a 31 y preguntas A-1 a A-11).
6. `servicios/normalizacion/README.md`: cómo instalar, correr y probar.
7. Para lo que viene después (extracción): `contracts/modulo3-extraccion/v0/` y `contexto/refinamiento-grill-me-2.md` (D1 a D24).

## Reparto

El usuario es dueño de todo el flujo menos tres piezas de otros equipos: la entrada de documentos (módulo 1), el clasificador y la Power App de revisión. En términos de la constitución, eso es el módulo 3 (sin el clasificador), el módulo 4 (reglas e informe) y el módulo 5 (orquestador). No se construyen el clasificador ni la Power App: se tratan como contratos de entrada y salida.

## Qué existe ya

| Pieza | Dónde | Estado |
|---|---|---|
| **Normalización y lectura** | `servicios/normalizacion/` | Hecha (iniciativa 003, entrega 1). Comando `normalizar`, imagen Docker, script de la muestra |
| **Contrato de normalización** | `contracts/modulo3-normalizacion/v0/` | Versión `modulo3-normalizacion/0.1`, revisada con el usuario |
| Contrato de extracción | `contracts/modulo3-extraccion/v0/` | Versión 0.1. Los ocho cambios para la 0.2 (paso 5 del diseño) no se han aplicado |
| Checklist de habeas data | `specs/003-validacion-extraccion/checklist-habeas-data.md` | Borrador para cumplimiento |
| Matriz de campos por TD (TD-01 a TD-35) | Fuente: `~/GEB/Extraccion/matriz/campos.py`, que genera el Excel con `generar_matriz.py` | En uso. El Excel es generado: no se edita a mano |
| Modelo semántico y servidor MCP | `~/GEB/modelo-semantico` (repo aparte): modelo en Cosmos DB, servidor en Container Apps | Desplegado; modelo `extraccion_documental` en v21 |
| Agente de extracción de prueba | `~/GEB/modelo-semantico/agente_local/chat.py` y `lote.py` | Arnés de pruebas con gpt-5.4. No es el servicio de producción |
| Gold por tipo documental | `~/GEB/Extraccion/Documentos/pruebas/TD-NN/gold_TD-NN.xlsx` (no van a git: datos reales) | TD-03, 05, 15, 16, 17, 18, 26, 27, 29, 30 y 35. Estado en `Documentos/pruebas/HANDOFF.md` |
| Clasificación manual de la muestra | `Documentos/clasificados/manifiesto.csv` (no está en este repo: datos reales) | Sirve como clasificador falso |
| Documentos reales de SR5658940621 | `~/GEB/Extraccion/Documentos/98. PCA SR5658940621- …/` | 6 oferentes, CPC y 3 adendas. No van a git |
| Plantilla de evaluación | `insumos/Matriz_Extraccion_Evaluacion_Ofertas_PCA-SR5587392192.xlsx` | Formato del informe |

No existe código de orquestación, extracción como servicio, reglas, tareas ni informe.

## Antes de medir la muestra real (en la máquina local)

1. **Cumplimiento** responde HD-1 a HD-4 y HD-14 del checklist. Sin eso, no se procesan documentos reales.
2. **Instalar:** Python 3.12, uv y LibreOffice. En Mac, `soffice` no queda en el PATH: ver `servicios/normalizacion/README.md`. Correr `uv run pytest -q` y confirmar que no se salta ninguna prueba de LibreOffice.
3. **Armar la carpeta de la muestra:** una subcarpeta por oferente, y nada más. El script trata cada subcarpeta como un oferente, así que las CPC y las adendas (que son del proceso) no van ahí. Revisar cómo está organizada `~/GEB/Extraccion/Documentos/98. PCA SR5658940621- …/` antes de apuntar el script.
4. **Correr** `uv run python scripts/medir_muestra.py <carpeta>` desde `servicios/normalizacion`. Imprime solo conteos, sin nombres: el usuario los puede compartir.
5. **Comparar** con el diseño (A3: unas 415 páginas únicas, 9 copias, 15 PDF con restricciones, 7 PDF con firma digital; A4: 76 % texto, 11 % escaneo con OCR, 8 % imagen, 5 % vacía; A5: del orden de un minuto por oferente) y explicar las diferencias.

La salida con datos personales (`--salida`) va fuera del repositorio y se borra al terminar.

## Pendiente

### Decisiones tomadas al implementar que el usuario no confirmó de forma explícita

Fusionó las tareas, pero no respondió estas preguntas. Conviene confirmarlas:

- **T10, anclas:** "una palabra que empieza por firma" se tomó como una frase cuya *primera* palabra empieza por "firma" (así "la firma del contrato", en medio de un párrafo, no cuenta).
- **T11, entrega:** ante un bug, los demás documentos se escriben pero el manifiesto no. La idempotencia se decide con el manifiesto anterior, no con la lectura. Consecuencia: después de una corrida con bug, el reintento procesa todo.
- **T08, firma:** una firma que se lee pero no trae firmante o fecha queda `leida: false`, porque el contrato exige los dos.

### Para calibrar con la muestra real

- Umbrales de tipo de página (20 caracteres, 80 % de cobertura) frente a la proporción del diseño (A4). Si se cambia un parámetro, sube `version_parametros`: desde la primera corrida real, cualquier cambio la sube.
- Páginas con una foto chica en una hoja blanca, que hoy quedan `vacia`.
- Si `extract_text()` junta bien las columnas de las tablas anchas.
- Falsos positivos de anclas: bordes de tabla como líneas de firma, y "si"/"no" en renglones de tablas.
- Casillas que no se detectan: las escritas como símbolo (☐), las dibujadas con curvas y las de formularios PDF.
- PDF con bytes antes de `%PDF-` (hoy quedan `no_soportado`) y formatos sin soporte (HEIC, RTF, PPTX): ver si aparecen.
- Tiempo por oferente (A5). Si no se cumple, la alternativa del plan es pypdfium2.

### Preguntas de otros equipos que afectan lo construido

- **Cumplimiento:** HD-1 a HD-14 del checklist; incluye S1 (conservación) y S2 (enviar datos a eastus).
- **A-1, módulo 1:** dónde dejan los archivos y qué identificadores usan. Cambia el almacén (hoy solo hay `AlmacenLocal`) y quizá `id_documento`.
- **A-5, clasificación:** si clasifican sobre nuestro PDF normalizado y usan nuestra lectura.
- **A-6, arquitectura:** licencias. Se evitó AGPL (PyMuPDF); img2pdf es LGPL-3.0 y queda anotado.

### No hecho en la entrega 1

- Almacén en Blob Storage (espera A-1) y conexión a la cola (iniciativa 005, orquestador).
- Análisis de vulnerabilidades de la imagen y publicación en un registro de Azure.
- Experimento de OCR propio (decisión 9).

## Lo que viene después

Cuando la medición cierre la entrega 1, el usuario elige con qué seguir. Opciones que salen del diseño:

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
- **LibreOffice:** la imagen pesa 1,2 GB. Si A-1 resulta en SharePoint, se puede evaluar la conversión de Graph API.
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
