# Handoff: implementación del flujo documental (opción A)

Estado al 2026-11-10. Cerradas la entrega 1 de la iniciativa 003 (normalización y lectura) y la entrega 1 de la 005 (orquestador, del aviso a la cola de extracción), las dos en local. **La extracción (entrega 2 de la 003) está construida** en `servicios/extraccion/`; le falta la medición con los gold (A9), que corre el usuario. Estado y pendientes al principio de `contexto/HANDOFF-extraccion.md`.

Las rutas relativas son de este repositorio (`~/GEB/flujo-documental-repo`, en GitHub `roymaestre-innovati/flujo-documental`); lo que está en otros repos va con ruta completa. `contexto/flujo-documental-opcion-a.md` sigue siendo la fuente de verdad del diseño. Este archivo no repite el diseño: dice qué existe, qué falta, qué está abierto y cómo trabaja el usuario.

## Dónde quedamos

- **Iniciativa 003, entrega 1 (normalización y lectura): cerrada.** Las tareas T01 a T16 de `specs/003-validacion-extraccion/tasks.md` están hechas y fusionadas en `main`, con 413 pruebas sobre documentos inventados. Normalizador `0.2.0`, contrato `modulo3-normalizacion/0.2`, parámetros versión 1.
- **Medida con la muestra real** (7 oferentes, 1.034 páginas, dos mediciones): `specs/003-validacion-extraccion/resultados-muestra.md`. Los criterios A3 a A5 se cumplen y los umbrales no cambian. De la primera medición salieron T14 (el sello de tiempo no cuenta como firma), T15 (PowerPoint) y T16 (vínculos a otros libros en Excel); la segunda medición los confirma.
- **Checklist de habeas data:** `specs/003-validacion-extraccion/checklist-habeas-data.md`. El 2026-11-10 el equipo respondió que la autorización se obtiene cuando los oferentes cargan sus documentos: las pruebas con documentos reales están autorizadas. Para producción quedan preguntas abiertas (sección "Respuestas").
- **Iniciativa 005, entrega 1 (orquestador): cerrada** el 2026-11-09. T01 a T11 de `specs/005-orquestador/tasks.md`, con 166 pruebas sobre documentos inventados (182 con las del visor). Va del aviso del proceso a las solicitudes de extracción, todo local, con interfaces que tienen versión en memoria (Service Bus, Cosmos y OneLake reales en la entrega 2). Comando `orquestar` y `scripts/correr_muestra.py`. Lo que cambió respecto del plan está al final de `plan.md`, en "Lo que cambió al implementar".
- **Corrida con la muestra real (A4, 2026-11-09):** las 7 entregas llegan a las solicitudes o a una tarea; nada atascado ni en errores; 75 solicitudes de extracción, 13 tareas `NO_SOPORTADO` (los ZIP y RAR ya conocidos), 270 s. OF-007 no tiene clasificación manual que coincida con sus archivos y sale todo TD-99. Detalle en la nota de T11.

## Cómo trabaja el usuario

- Escribe en español: código con nombres en español, commits y documentos en prosa.
- **Una tarea a la vez.** Por cada tarea: rama nueva desde `main`, pruebas en verde, notas en `tasks.md`, commit, push y un resumen corto. **Después se detiene.** El usuario revisa, fusiona el pull request en GitHub y escribe "merge listo" o "sigue con TNN".
- **Las dudas no se resuelven solas.** Lo ambiguo se anota en "Notas de implementación" de `tasks.md` y se le pregunta, con una recomendación primero. Suele aceptar la recomendada, pero a veces elige otra o pide revisar cada opción. Cuando pide explicación, quiere algo simple, con ejemplos ("es como escribir…").
- Prefiere lo simple: si una propuesta crece, ofrecer la versión más simple.
- Commits y pushes solo dentro de ese flujo, o si los pide. No publicar ni crear pull requests sin pedirlo.
- Corre él mismo lo que toca documentos reales y pega la salida (solo conteos). Se le dan los comandos listos para copiar y se le dice cuánto tardan.

## Para seguir con el orquestador

### Qué leer, en este orden

1. Este archivo.
2. `specs/005-orquestador/`: `spec.md`, `plan.md` y `tasks.md`, con sus notas de implementación.
3. `contexto/constitucion.md`: los siete principios.
4. `contexto/flujo-documental-opcion-a.md`, **paso 0 (Entrada)**: cómo llegan los procesos (OneLake de Fabric, cola `procesos-listos`, un aviso por proceso completo) y las decisiones 32 a 35. Después el **paso 4 (Orquestación)**: estado que guarda (cinco entidades: proceso, oferente, archivo, segmento y tarea humana), tecnología (Service Bus + workers en Container Apps + estado en Cosmos), manejo de errores por clases, versión del modelo por proceso, subsanación y reprocesamiento, apertura del proceso, cola y volumen. También las decisiones 15 y 16 y las preguntas abiertas A-1 a A-11.
5. `contexto/refinamiento-grill-me-2.md` (D1 a D24): de ahí salen D7 (versión del modelo), D22 (reintentos) y otras que usa el paso 4.
6. Los contratos: `contracts/modulo5-orquestador/v0/` (aviso del módulo 1 y clasificador), `contracts/modulo3-extraccion/v0.2/` (solicitudes de extracción) y `contracts/modulo3-normalizacion/v0/` (lo que produce la normalización).
7. `servicios/orquestador/README.md` y `servicios/normalizacion/README.md`: cómo se instala, corre y prueba cada uno.

### Por qué en este mismo repositorio

Se decidió el 2026-11-06. El repo ya está armado para varias piezas (`servicios/` una carpeta por pieza desplegable, `specs/` una por iniciativa, `contracts/` las fronteras). La constitución, el diseño y los contratos quedan en un solo lugar, sin copias que se desalineen. El orquestador importa `normalizacion` directamente, sin publicar un paquete. Cada servicio sigue con su propia imagen y se despliega por separado. Se reconsidera solo si otro equipo toma el orquestador o necesita permisos o ciclos de versión propios.

### Lo que el orquestador necesita saber de la normalización

- **Cómo llega el trabajo (paso 0, decisiones 32 a 35):** el módulo 1 deja el proceso completo (CPC, adendas y todos los oferentes) en su datalake de Fabric (OneLake) y publica **un mensaje por proceso** en la cola de Service Bus `procesos-listos`, con `id_proceso`, `ruta` y, opcional, la lista de archivos (forma por confirmar, A-1). Por ahora no llegan documentos tardíos. Si no pueden publicar en Service Bus, el plan B es un endpoint mínimo que deja el mensaje en esa misma cola.
- **Los originales no se copian:** el normalizador los lee de OneLake con `azure-storage-file-datalake` y la identidad administrada del job, los baja a disco temporal, normaliza y lee, y escribe solo lo que produce en nuestro almacenamiento. Ningún otro paso vuelve a tocar Fabric. Hoy `normalizar_entrega` recibe una carpeta local: falta la pieza que lista y baja los archivos de la `ruta` del mensaje y los reparte entre el proceso y cada oferente.
- **Entrada:** la carpeta de una entrega (un oferente, o el proceso: condiciones, adendas, anexos), `id_proceso` y `id_oferente` (sin oferente es una entrega del proceso).
- **Como función:** `normalizacion.entrega.normalizar_entrega(carpeta, id_proceso, id_oferente, almacen, forzar=False)` devuelve un `Resultado` con el `manifiesto` (un dict según el contrato). **Por línea de comandos:** `normalizar <carpeta> --proceso SR… --oferente OF-… --salida <carpeta>`.
- **Salida:** en el almacén, bajo `<proceso>/<oferente o PROCESO>/`: `manifiesto.json`, `pdf/`, `anexos/`, `lectura/` y `palabras/`.
- **Almacén:** interfaz `Almacen` (`uri`, `leer`, `escribir`, `existe`, `listar`) en `almacen.py`. Solo existe `AlmacenLocal`. **Falta una implementación en Blob Storage** para lo que producimos. Ya no depende de A-1: los originales se quedan en OneLake y el almacén es nuestro.
- **Errores:** un documento que no se puede procesar es un resultado, no una falla: queda `error_entrada` con su código en el manifiesto, y el comando sale con 0. Un bug (clase 4) en algún documento lanza `ErrorEntrega` al final, con los `id_documento` afectados; los demás documentos ya quedaron escritos, pero el manifiesto no. Por línea de comandos sale con 1.
- **Idempotencia:** volver a correr la misma entrega reusa lo que no cambió, comparando con el manifiesto anterior. `forzar=True` procesa todo de nuevo. Después de una corrida con bug, como no hay manifiesto, el reintento procesa todo.
- **Determinismo:** misma entrada, misma versión del normalizador y de parámetros, mismos bytes de salida.
- **Tiempos medidos** (portátil de trabajo): de 3 a 43 s por oferente típico, unos 0,3 s por página de PDF; un oferente grande (583 páginas, muchos Office) tardó 149 s. Sirve para dimensionar los workers y los tiempos de espera de la cola.

## Reparto

El usuario es dueño de todo el flujo menos tres piezas de otros equipos: la entrada de documentos (módulo 1), el clasificador y la Power App de revisión. En términos de la constitución, eso es el módulo 3 (sin el clasificador), el módulo 4 (reglas e informe) y el módulo 5 (orquestador). No se construyen el clasificador ni la Power App: se tratan como contratos de entrada y salida.

## Qué existe ya

| Pieza | Dónde | Estado |
|---|---|---|
| **Normalización y lectura** | `servicios/normalizacion/` | Cerrada (entrega 1, T01 a T16). Versión 0.2.0. Comando `normalizar`, imagen Docker, script de la muestra |
| **Contrato de normalización** | `contracts/modulo3-normalizacion/v0/` | Versión `modulo3-normalizacion/0.2` (0.2 sumó `ppt`, `pptx` y `odp`) |
| **Orquestador** | `servicios/orquestador/` | Entrega 1 cerrada (T01 a T11). Versión 0.1.0. Manejadores de `procesos-listos`, `normalizar` y `clasificar`, solicitudes de extracción 0.2, tareas, escalamiento, comando `orquestar` y script de la muestra |
| **Extracción** | `servicios/extraccion/` | Entrega 2 de la 003 construida (T01 a T10). Versión 0.1.0. `extraer_segmento`, comandos `extraer`, `probar-ficha-mcp` y `medir-gold` |
| Visor de corridas | `servicios/orquestador/src/orquestador/visor/` (comando `visor`) | Página local (127.0.0.1) para revisar una corrida guardada con `--salida`: resumen, documentos con su PDF, tareas, errores y los resultados de la extracción. Hecho a imagen de `~/GEB/Extraccion/visor` |
| **Contrato del orquestador** | `contracts/modulo5-orquestador/v0/` | Versión 0.1: aviso de proceso listo (módulo 1) y solicitud y respuesta del clasificador. Propuesta para A-1 y C1 a C3 |
| Contrato de extracción | `contracts/modulo3-extraccion/v0.2/` | Versión 0.2, con los ocho cambios del paso 5 del diseño más `id_segmento`. La 0.1 queda en `v0/`, sin cambios |
| Resultados de la muestra real | `specs/003-validacion-extraccion/resultados-muestra.md` | Dos mediciones (2026-11-05). Solo conteos |
| Checklist de habeas data | `specs/003-validacion-extraccion/checklist-habeas-data.md` | Borrador para cumplimiento |
| Matriz de campos por TD (TD-01 a TD-35) | Fuente: `~/GEB/Extraccion/matriz/campos.py`, que genera el Excel con `generar_matriz.py` | En uso. El Excel es generado: no se edita a mano |
| Modelo semántico y servidor MCP | `~/GEB/modelo-semantico` (repo aparte): modelo en Cosmos DB, servidor en Container Apps | Desplegado; modelo `extraccion_documental` en v21 |
| Agente de extracción de prueba | `~/GEB/modelo-semantico/agente_local/chat.py` y `lote.py` | Arnés de pruebas con gpt-5.4. No es el servicio de producción |
| Gold por tipo documental | `~/GEB/Extraccion/Documentos/pruebas/TD-NN/gold_TD-NN.xlsx` (no van a git: datos reales) | TD-03, 05, 15, 16, 17, 18, 26, 27, 29, 30 y 35 |
| Clasificación manual de la muestra | `~/GEB/Extraccion/Documentos/clasificados/manifiesto.csv` (datos reales, fuera de git) | Clasificador falso de `correr_muestra.py`. Las 17 filas del oferente de OF-007 no coinciden con sus archivos |
| Muestra real para medir | `~/GEB/pruebas-normalizacion/muestra1` (6 oferentes) y `muestra` (OF-007) | Fuera del repo. Datos reales |
| Plantilla de evaluación | `insumos/Matriz_Extraccion_Evaluacion_Ofertas_PCA-SR5587392192.xlsx` | Formato del informe |

No existe código de extracción como servicio, reglas, tareas en la Power App ni informe. El orquestador no recibe resultados de extracción todavía (entrega 2).

## Pendiente

### Preguntas de otros equipos que afectan al orquestador

- **A-1, módulo 1 (respondida en parte, ver paso 0):** falta saber si pueden publicar en Service Bus, la forma del mensaje, cómo organizan las carpetas y distinguen los documentos del proceso de los de cada oferente, si los identificadores son los de Ariba, si los archivos quedan quietos después del aviso, y que den permiso de lectura en el workspace, habiliten en el tenant las APIs de Fabric para service principals y digan el workspace y el lakehouse. Confirmar también que los archivos llegan descomprimidos (en la muestra hubo ZIP y RAR, pero fueron un error al armar la carpeta de prueba).
- **A-10, módulo 1:** en pausa. Por ahora no llegan documentos tardíos; si hay errores en la evaluación, un oferente podría volver a subir todo. No se diseña hasta confirmarlo.
- **A-5, clasificación:** si clasifican sobre nuestro PDF normalizado y usan nuestra lectura.
- **A-6, arquitectura:** licencias. Se evitó AGPL (PyMuPDF); img2pdf es LGPL-3.0 y queda anotado.
- **Cumplimiento:** HD-1 a HD-14 del checklist; incluye S1 (conservación) y S2 (enviar datos a eastus).

### Decisiones de la entrega 1 que el usuario no confirmó de forma explícita

- **T10, anclas:** "una palabra que empieza por firma" se tomó como una frase cuya *primera* palabra empieza por "firma".
- **T11, entrega:** ante un bug, los demás documentos se escriben pero el manifiesto no (ver "Errores", arriba).
- **T08, firma:** una firma que se lee pero no trae firmante o fecha queda `leida: false`, porque el contrato exige los dos.

### Decisiones del orquestador para confirmar con el uso

- La tarea `falla_tecnica` no se cierra sola si lo escalado se recupera (T09).
- Una tarea de clasificación ya resuelta no se vuelve a resolver; cambiar un tipo será `reprocesar` (T09).
- "SIN CLASIFICAR" de la clasificación manual se trata como TD-99 (T11).
- Revisar la clasificación manual de OF-007 y volver a correr `correr_muestra.py` (T11).

### Para calibrar la normalización más adelante

- Diapositivas con imagen de fondo y texto encima quedan `escaneo_con_ocr` en vez de `texto` (4 de 30 en la muestra).
- Páginas con una foto chica en una hoja blanca, que hoy quedan `vacia`.
- Si `extract_text()` junta bien las columnas de las tablas anchas.
- Falsos positivos de anclas: bordes de tabla como líneas de firma, y "si"/"no" en renglones de tablas.
- Casillas que no se detectan: las escritas como símbolo (☐), las dibujadas con curvas y las de formularios PDF.
- Firmas `adbe.pkcs7.detached` con el algoritmo mal declarado (2 en la muestra): quedan no leídas; agregar la tolerancia si se repiten.
- Un PPT (formato 97) con contraseña queda `CONVERSION_FALLIDA` y no `CONTRASENA`.

Si se cambia un parámetro, sube `version_parametros`: ya hubo corridas reales.

### No hecho en la entrega 1

- Almacén en Blob Storage para lo que producimos.
- Lectura de los originales desde OneLake. Antes de construirla, **prueba de acceso** (decisión 35): que el job lea una carpeta de prueba de OneLake con su identidad administrada. La configuración del tenant y los roles del paso 0 se escribieron sin verificar en la documentación de Microsoft; la prueba los confirma.
- Análisis de vulnerabilidades de la imagen y publicación en un registro de Azure.
- Experimento de OCR propio (decisión 9).

### Otros pendientes

- **Datos personales:** borrar `~/GEB/pruebas-normalizacion/salida` y `salida1` (salidas de la primera medición).
- **Diagramas:** `contexto/diagramas/` todavía muestra "Avisa entrega lista" por oferente y Blob Storage con los originales. Con el paso 0 el aviso es por proceso (cola `procesos-listos`) y los originales se leen de OneLake. Falta actualizarlos.
- **Iniciativa 003:** `spec.md` y `plan.md` todavía dicen que A-1 está abierta y que, si fuera SharePoint, se usaría Graph API. Ya no aplica; se actualiza cuando se toque esa iniciativa.
- Pendientes del diseño que siguen abiertos: medir la ficha inyectada (decisión 26), imágenes solo donde hacen falta (decisión 8), TD-98 (decisión 14).
- El usuario preguntó por qué, en el diagrama de secuencia, el mensaje "archivo listo" pasa por Orquestación antes del clasificador. Se propuso partir el participante "Orquestación" en "Worker de clasificación" y "Worker de resultados y reglas", y no respondió. Es relevante para el orquestador. Si el usuario retocó el `.drawio` a mano, se edita ese archivo directamente: no se regenera con el script.

## Lo que viene después

- **Entrega 2 del orquestador:** resultados de la extracción, ficha del proceso, menor precio, tareas en la Power App, `reprocesar` y las piezas en Azure (Service Bus, Cosmos, OneLake, Blob, alertas). Antes de OneLake, la prueba de acceso (decisión 35).
- **Entrega 2 de la iniciativa 003: extracción.** Es lo siguiente, elegido el 2026-11-09. El contrato 0.2 ya está (T01 de la 005), así que empieza por el servicio. Depende de S2 (enviar datos a eastus). Todo lo que hace falta para empezar está en `contexto/HANDOFF-extraccion.md`.
- **Módulo 4: reglas e informe**, con la hoja Reglas de la matriz (decisión 28).

## Riesgos y datos técnicos conocidos

- **Service Bus entrega mensajes dos veces a veces:** la normalización y los manejadores del orquestador son idempotentes (probado en local, A3). Con Cosmos hay que repetir esas pruebas. Si el `normalizar` llega repetido, dos trabajadores pueden normalizar la misma entrega a la vez: confirmar con Blob o tomar un lease por entrega.
- **Paralelo en local:** la corrida local normaliza en hilos y casi no acelera (Python no reparte el trabajo entre hilos). En producción cada entrega va en su contenedor.
- **gpt-5.4 es obligatorio en la extracción:** gpt-5.4-mini no respeta las reglas de evidencia (prueba con TD-17).
- **429:** la concurrencia de extracción hoy es 3. Un proceso de 10 oferentes son unos 160 segmentos, unos 20 minutos.
- **LibreOffice:** la imagen de pruebas pesa unos 940 MB. Cada conversión arranca LibreOffice desde cero; el tiempo máximo es 120 s con un reintento.
- **Firma digital:** las `adbe.pkcs7.sha1` (Cámara de Comercio, RUP) quedan como "firma que no se pudo leer". Leerlas necesita otra herramienta.
- **Fuentes:** sin fuentes con las medidas de Office (Carlito, Caladea, Liberation), los Word, Excel y PowerPoint cambian de paginación al convertirse. La imagen las trae.
- **Docker local:** en la máquina del usuario `docker` es podman. Para construir: ruta absoluta en `-f` y `--build-arg BASE_IMAGE=docker.io/library/ubuntu:24.04`.

## Qué no hacer

- No construir el clasificador ni la Power App.
- No procesar documentos reales sin las respuestas de cumplimiento, ni subir al repositorio documentos reales o salidas con datos personales.
- No editar el Excel de la matriz: se regenera desde `~/GEB/Extraccion/matriz/campos.py`.
- No publicar versiones del modelo semántico sin que el usuario lo pida.
- No regenerar `flujo_documental_c4.drawio` si el usuario lo retocó.
- No meter LLM en normalización, lectura, orquestación ni reglas: el diseño los dejó deterministas a propósito.
- No editar un contrato vigente de forma incompatible: va versión nueva (principio 5).
