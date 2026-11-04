# Handoff: planear la implementación del flujo documental (opción A)

Estado al 2026-11-04. Copiado desde `~/GEB/Extraccion` para planear en otro repo; las rutas relativas son de esta carpeta, y lo que se quedó en el repo original va con ruta completa. Se usa junto con `contexto/flujo-documental-opcion-a.md`, que es la fuente de verdad del diseño. Este archivo no repite el diseño: dice qué existe, qué falta, qué está abierto y cómo trabaja el usuario.

## Tu tarea

Planear la implementación del flujo documental completo que diseñó el usuario el 2026-11-03: normalización, lectura, orquestación, extracción, reglas, tareas de revisión e informe. El diseño está cerrado (31 decisiones); lo que falta es el plan: qué se construye, en qué orden, con qué piezas existentes y cómo se prueba sin los equipos externos.

Todavía no se implementa nada. Primero se acuerda el plan con el usuario.

## Cómo trabaja el usuario

- Escribe en español. Los documentos van en español, en prosa normal.
- Avanza paso a paso, una pieza a la vez. El patrón es: propones con una recomendación, el usuario decide y después escribes ("pásalo al documento"). No escribas, publiques ni cambies archivos de diseño sin su visto bueno.
- Prefiere lo simple. Rechazó una subsanación con rondas y temporizadores por compleja, y la dejó en "documentos que llegan tarde". Si una propuesta crece, ofrece la versión más simple.
- Cuando hay varias decisiones técnicas juntas, pide que se le expliquen despacio, una por una y con ejemplos.
- Commits, pushes y publicaciones solo si los pide.

## Qué leer, en este orden

1. `contexto/flujo-documental-opcion-a.md`: el diseño paso a paso, las decisiones 1 a 31, los cambios a decisiones anteriores y las preguntas abiertas A-1 a A-11.
2. `contexto/constitucion.md`: los siete principios y la estructura que exige para planear (ver "Cómo arrancar").
3. `contracts/modulo3-extraccion/v0/`: el contrato vigente entre orquestador y extracción. Los ocho cambios para la versión 0.2 están en el paso 5 del diseño y todavía no se aplicaron a los archivos.
4. `contexto/refinamiento-grill-me-2.md`: decisiones D1 a D24 sobre la unidad de extracción, que el diseño cita.
5. `contexto/diagramas/flujo_documental_c4.drawio`: C4 niveles 1 a 3 y una secuencia. El nivel 3 es el mapa de componentes a construir.
6. `Documentos/pruebas/HANDOFF.md`: estado del modelo semántico por tipo documental (qué TD están cerrados y con gold).

## Reparto

El usuario es dueño de todo el flujo menos tres piezas de otros equipos: la entrada de documentos (módulo 1), el clasificador y la Power App de revisión. En términos de la constitución, eso es el módulo 3 (sin el clasificador), el módulo 4 (reglas e informe) y el módulo 5 (orquestador).

No propongas construir el clasificador ni la Power App: se tratan como contratos de entrada y salida.

## Qué existe ya

| Pieza | Dónde | Estado |
|---|---|---|
| Matriz de campos por TD (TD-01 a TD-35) | Fuente: `~/GEB/Extraccion/matriz/campos.py`, que genera el Excel con `generar_matriz.py`. Aquí hay una copia de consulta del Excel en `matriz/` | En uso. El Excel es generado: no se edita a mano, y la copia de aquí no es la fuente |
| Modelo semántico y servidor MCP | `~/GEB/modelo-semantico` (repo aparte): modelo en Cosmos DB, servidor en Container Apps | Desplegado; modelo `extraccion_documental` publicado en v21 |
| Agente de extracción de prueba | `~/GEB/modelo-semantico/agente_local/chat.py` y `lote.py` | Arnés de pruebas: agente de Foundry con gpt-5.4, manda texto e imagen de cada página a 100 dpi, consulta el MCP con 3 tools. No es el servicio de producción |
| Gold por tipo documental | `~/GEB/Extraccion/Documentos/pruebas/TD-NN/gold_TD-NN.xlsx` (no se copiaron: traen datos de documentos reales) | TD-03, 05, 15, 16, 17, 18, 26, 27, 29, 30 y 35 |
| Clasificación manual de la muestra | `Documentos/clasificados/manifiesto.csv` | Sirve como clasificador falso (decisión del paso 3) |
| Documentos reales del proceso SR5658940621 | `~/GEB/Extraccion/Documentos/98. PCA SR5658940621- …/` | 6 oferentes, CPC y 3 adendas. No se copiaron y no van a git: traen datos personales |
| Plantilla de evaluación de GEB | `insumos/Matriz_Extraccion_Evaluacion_Ofertas_PCA-SR5587392192.xlsx` | Formato del informe (hojas Jurídica, Financiera, Técnica, Económica, Datos_Subsanaciones) |

No existe código de normalización, lectura, orquestación, reglas, tareas ni informe. Los scripts de exploración que se usaron para el diseño (firmas con pyHanko, tipos de página con PyMuPDF) eran temporales y no quedaron en el repo.

## Qué hay que construir

Sale del nivel 3 del C4. Todo corre en Azure; el LLM aparece solo en la extracción.

| Componente | Paso | Tecnología prevista |
|---|---|---|
| Normalizador | 1 | Container Apps Job, Python, LibreOffice headless, qpdf, img2pdf, pyHanko |
| Lector de páginas | 2 | Mismo job, Python. Librería de PDF según A-6 (abajo) |
| OCR, como experimento | 2 | Document Intelligence Read |
| Colas por paso, con dead-letter | 4 | Azure Service Bus |
| Worker de clasificación (llama al clasificador, valida, aplica umbrales) | 3-4 | Container Apps, Python |
| Worker de resultados y estado | 4 | Container Apps, Python, Cosmos DB |
| Apertura del proceso y ficha (CPC + adendas) | 4 | Workers existentes más la extracción de TD-01 y TD-02 |
| Comando `reprocesar` | 4 | Python |
| Unidad de extracción como servicio (preprocesamiento, agente, posvalidación) | 5 | Container Apps, agente de Foundry con gpt-5.4, contrato 0.2 |
| Motor de reglas (módulo 4) y hoja Reglas | 6 | Python; reglas como datos en la matriz |
| Tareas de revisión e informe Excel | 6 | Python, openpyxl; integración con Dataverse |
| Estado, versiones fijadas, fichas, reglas | 4-6 | Cosmos DB |
| Archivos, PDF normalizados, lectura, informes | 1-6 | Blob Storage (supuesto: depende de A-1) |

## Cómo avanzar sin los equipos externos (principio 5)

| Frontera | Doble de prueba |
|---|---|
| Módulo 1, entrada | Carpeta con los documentos de la muestra y un mensaje "entrega lista" publicado a mano |
| Clasificador | `Documentos/clasificados/manifiesto.csv` |
| Power App | Tareas escritas en una tabla o archivo; correcciones inyectadas con un script como mensajes de Service Bus |

## Pendientes que el plan debe incluir

- **Contrato 0.2** (decisión 25): actualizar esquemas JSON y ejemplos de `contracts/modulo3-extraccion/` y validarlos. Es un cambio incompatible, así que va como versión nueva, sin editar la vigente (principio 5).
- **Medir la ficha inyectada** (decisión 26) con `lote.py` sobre TD-16 y TD-29: tokens, tiempo y exactitud contra el gold. Decide si producción hace una vuelta del LLM o sigue con las 3 tools del MCP.
- **Hoja Reglas** (decisión 28): reescribir las reglas de texto libre de la matriz en los tipos `comparar`, `existe`, `calculo` y `juicio`, con `id_regla` estable. Es el trabajo más grande del paso 6. Un LLM puede redactar el borrador y una persona revisa cada fila.
- **Imágenes solo donde hacen falta** (decisión 8): medir con los gold antes de cambiar el preprocesamiento.
- **OCR** (decisión 9): experimento con TD-27 y TD-26.
- **TD-98** en la matriz y en la ontología del clasificador (decisión 14).

## Riesgos y datos técnicos conocidos

- **gpt-5.4 es obligatorio en la extracción:** gpt-5.4-mini no respeta las reglas de evidencia (prueba con TD-17).
- **429:** la concurrencia de extracción hoy es 3. Un proceso de 10 oferentes son unos 160 segmentos, unos 20 minutos.
- **Service Bus entrega mensajes dos veces a veces:** todo worker es idempotente, con las claves del paso 4.
- **Firma digital:** pyHanko no lee el formato `adbe.pkcs7.sha1` de las firmas de Cámara de Comercio y RUP. Hace falta otra herramienta o aceptar que esas firmas no se detectan en v0.
- **Licencia (A-6):** PyMuPDF es AGPL. Mientras arquitectura no responda, conviene planear con alternativas permisivas (pypdfium2, pdfplumber, poppler).
- **Datos personales (principio 6):** los documentos traen cédulas, RUT y estados financieros. La constitución exige correr `/checklist` de habeas data antes de `/implementar` y acceso por rol.
- **Stack:** Power Platform para las tareas humanas, Azure para lo demás. Cada elección concreta se justifica con el principio de mínimo necesario.

## Preguntas abiertas que afectan el plan

Las 11 están en el diseño (A-1 a A-11). Las que cambian lo que se construye:

- **A-1, módulo 1:** dónde dejan los archivos (Blob o SharePoint) y cómo avisan. Cambia el disparador del normalizador y la conversión (Graph API si es SharePoint).
- **A-2, Power App:** forma de las tareas y de las correcciones. Cambia la integración con Dataverse.
- **A-5 y A-7, clasificación:** si clasifican sobre nuestro PDF normalizado y si aceptan TD-98.
- **A-6, arquitectura:** licencia AGPL.
- **A-11, negocio:** si el informe va en Excel con las plantillas actuales.

## Pendiente de la sesión anterior

El usuario preguntó por qué en el diagrama de secuencia el mensaje "archivo listo" pasa por Orquestación antes del clasificador. Se le explicó que Service Bus solo guarda mensajes y que el worker de clasificación es quien llama al clasificador, valida y aplica umbrales. Se propuso partir el participante "Orquestación" en "Worker de clasificación" y "Worker de resultados y reglas", y no respondió. Si el usuario ya retocó el `.drawio` a mano, se edita ese archivo directamente: no se regenera con el script.

## Cómo arrancar

1. Confirma con el usuario la forma del plan. La constitución pide una iniciativa numerada por módulo bajo `specs/NNN-nombre/`, cada una con `spec.md`, `plan.md` y `tasks.md`, un "Chequeo de Constitución" en el plan y el contrato en `contracts/`. Propón cómo repartir lo suyo en iniciativas (por ejemplo, orquestador, extracción y reglas e informe) y espera su decisión.
2. Propón un orden. Una opción a considerar: una primera tajada vertical con un solo oferente de SR5658940621, de punta a punta con los dobles de prueba (normaliza, lee, clasificador falso, extracción con el agente actual, reglas de uno o dos TD cerrados, tareas en archivo). Prueba las uniones entre piezas antes de completar cada una.
3. Ve pieza por pieza, como en el diseño: propuesta, decisión del usuario, escritura.

## Qué no hacer

- No construir el clasificador ni la Power App.
- No editar el Excel de la matriz: se regenera desde `~/GEB/Extraccion/matriz/campos.py`, y la copia de aquí es solo de consulta.
- No publicar versiones del modelo semántico sin que el usuario lo pida.
- No regenerar `flujo_documental_c4.drawio` si el usuario lo retocó.
- No meter LLM en normalización, lectura, orquestación ni reglas: el diseño los dejó deterministas a propósito.
