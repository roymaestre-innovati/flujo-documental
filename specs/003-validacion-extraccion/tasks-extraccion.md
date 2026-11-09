# Tareas 003 — Extracción (segunda entrega)

Sale de `plan-extraccion.md`. Cada tarea termina con sus pruebas en verde y un commit propio.

**Estado al 2026-11-09:** spec, plan y tareas aprobados. T01 a T04 fusionadas. T05 hecha, en revisión.

## Para quien implemente

- Leer antes la sección "Entrega 2 — Extracción" de `spec.md` y `plan-extraccion.md`. El diseño está en `contexto/flujo-documental-opcion-a.md` (paso 5) y en `contexto/refinamiento-grill-me-2.md` (D10 a D24). El estado del trabajo, en `contexto/HANDOFF-extraccion.md`.
- El contrato `contracts/modulo3-extraccion/v0.2/` no se edita. Si hace falta cambiarlo, se le pregunta al usuario, y un cambio incompatible va en una versión nueva.
- Solo documentos inventados y el `LLMFalso` en las pruebas. **Ningún documento real va al LLM** sin la autorización explícita del usuario, y lo corre él.
- No usar gpt-5.4-mini. No meter LLM en la posvalidación. No publicar versiones del modelo semántico. No editar `modelo-semantico/modelos/extraccion_documental/prompt.md`.
- La normalización y el orquestador se usan como están. Si algo hace falta cambiarles, se anota aquí y se le pregunta al usuario antes, salvo lo ya acordado en el plan (mover `en_el_almacen` y el visor).
- Escribir en español: código con nombres en español y documentos en prosa.
- Flujo por tarea: rama nueva desde `main`, pruebas en verde, notas aquí, commit, push y un resumen corto. **Después, alto para revisión del usuario.**
- Lo ambiguo se anota en "Notas de implementación" y se le pregunta al usuario, con una recomendación.

## Tareas

- [x] **T01 — Esqueleto y dobles.** `servicios/extraccion/` con `pyproject.toml` (uv, pytest, `normalizacion` como dependencia de ruta), `VERSION = "0.1.0"`, `datos/parametros.json`, `datos/respuesta.schema.json`, `contratos.py`, las interfaces `FuenteModelo` (con `FuenteModeloArchivo`), `ClienteLLM` (con `LLMFalso`) y `Resultados` (con `ResultadosEnCarpeta`), y el reloj. Fichas de prueba de TD-16, TD-29 y TD-01 con la forma de `obtener_seccion`, y respuestas falsas que dan los ejemplos del contrato. Pruebas: los ejemplos del contrato y las respuestas falsas validan contra sus esquemas.
- [x] **T02 — Entrada.** Mover `en_el_almacen` a `normalizacion.almacen` (el visor la importa de ahí). `entrada.py`: valida la solicitud, resuelve las URI, comprueba las huellas, lee la lectura y revisa el rango, con los errores de la tabla del plan. Requisitos R26 a R30.
- [x] **T03 — Preprocesamiento.** `preproceso.py`: qué va de cada página según su tipo, imagen con pypdfium2, firma ampliada a 300 dpi desde las anclas, valores del anexo con openpyxl y tope con `ANEXO_RECORTADO`, y `lectura` de la salida. Pruebas con PDF y xlsx inventados pasados por `normalizar_entrega`. Requisitos R31 a R34 y R36.
- [x] **T04 — Mensaje y prompt.** `datos/prompt.md` (los cambios del plan sobre el `prompt.md` del modelo semántico) y `mensaje.py` (sistema: prompt + guía; usuario: ficha + contenido). Pruebas: el mensaje solo lleva las páginas del segmento, numeradas sobre el documento completo, y la ficha de la versión pedida. **Alto para que el usuario revise el prompt.** Requisito R35.
- [x] **T05 — Posvalidación.** `posvalidacion.py` y `validadores.py`: forma, `no_corresponde`, alineación con la ficha, citas fuera del segmento, validadores, motivos, `datos_personales` y sobre validado contra el contrato. Con el `LLMFalso`, las solicitudes de ejemplo dan las salidas de ejemplo (criterio A7). Requisitos R37 a R48, R55 y R56.
- [ ] **T06 — Llamada.** `llm_azure.py` (chat completions con `json_object`, traducción de 429, tiempo agotado y 5xx a las excepciones de `llm.py`, y rechazo de un deployment `mini`) y `llamada.py` (reintentos de la tabla del plan y semáforo global). Las pruebas no tocan la red: un cliente HTTP falso para `llm_azure` y el `LLMFalso` con fallas programadas para `llamada`. Requisitos R49 a R52 y R54.
- [ ] **T07 — Servicio, idempotencia y comando.** `servicio.py` (`extraer_segmento`), la clave y el guardado de `resultados.py`, el comando `extraer` con su confirmación antes de mandar documentos, los registros sin datos personales y el README. Prueba de punta a punta (criterio A8): un proceso inventado normalizado, solicitudes armadas con `orquestador.extraer.solicitud` (solo en pruebas), dos corridas. Requisito R53.
- [ ] **T08 — Ficha desde el MCP.** `ficha_mcp.py`: `describir_modelo` y `obtener_seccion` con la versión fijada, guardadas en memoria por (versión, TD), y `--modelo mcp` en el comando. El comando guarda las fichas usadas en `extraccion/fichas/` para el visor. Prueba con un servidor MCP falso. El usuario la prueba contra el MCP real con un comando que solo pide la ficha de TD-16 v21 y cuenta sus elementos (no manda documentos). Requisito R30.
- [ ] **T09 — Visor.** El visor del orquestador muestra los resultados de `extraccion/`: estado por segmento, campos con valor, confianza contra umbral, motivos, reglas pendientes y citas que abren el PDF en su página. Los campos en revisión van resaltados. Pruebas del servidor del visor con una corrida inventada. Requisito R57.
- [ ] **T10 — Medición con los gold (A9), solo con autorización.** Script `scripts/medir_gold.py`: corre el servicio sobre los documentos de un TD con gold y compara campo a campo con `gold_TD-NN.xlsx`. Imprime solo conteos de aciertos por campo, tokens y tiempo, al lado de los de la última corrida de `lote.py`. Antes de escribirlo se le pregunta al usuario cómo está armado el gold (columnas) y cómo se cuenta un acierto en los campos de tipo objeto o lista. **Lo corre el usuario**, con TD-16 y TD-29, después de autorizar que esos documentos vayan a gpt-5.4.

**Al cerrar la entrega:** actualizar el estado en `spec.md` y en `plan-extraccion.md` (agregar "Lo que cambió al implementar"), el README del repo y `contexto/HANDOFF-extraccion.md`.

## Notas de implementación

### Spec, plan y tareas (2026-11-09)

Decisiones del usuario antes de escribir: el código va en `servicios/extraccion/`; chat completions directo, en una vuelta y con la ficha inyectada, "teniendo en cuenta que la versión final será con el MCP que construimos" (se interpretó como: el servicio pide la ficha al MCP con código, en T08, y el LLM no llama tools); versión local simple más el visor; se arranca con el modelo v21 tal como está.

Para revisar con el usuario:

1. **El MCP como fuente de la ficha, no como tools del LLM.** Si la intención era que el LLM siga llamando las tools en producción, cambian T04, T06 y T08, y el costo vuelve a unos 22.000 tokens por documento.
2. **`TD_NO_PROBADO` en todos los TD** mientras la ficha no traiga la marca. Todo irá a revisión. La alternativa es una lista provisional con los 11 TD con gold, que se descartó en la pregunta inicial.
3. **Prompt propio del servicio**, a partir del `prompt.md` del modelo semántico, que no se toca.
4. **Las páginas escaneadas siempre llevan imagen**, también en documentos de más de 20 páginas: si no, no queda nada que leer. Aceptado por el usuario el 2026-11-09 por ahora; queda para estudio posterior (tope de imágenes por documento u OCR, decisión 9) si el costo de los escaneos largos pesa.
5. **Falla técnica sin guardar:** un `error_proceso` no queda en el almacén de resultados, para que el reintento del orquestador vuelva a extraer.
6. **La cifra del criterio de adopción** (70 % de campos aceptados sin cambios) es una propuesta. Hay que confirmarla con negocio.

### T01 — Esqueleto y dobles (2026-11-09)

`servicios/extraccion/` con `pyproject.toml`, `VERSION = "0.1.0"`, `parametros.json` (versión 1), `respuesta.schema.json`, `contratos.py`, `ficha.py` (`FuenteModelo`, `FuenteModeloArchivo`, `Ficha`), `llm.py` (`ClienteLLM`, `LLMFalso`, `LimiteDeUso`, `FallaPasajera`), `resultados.py` (`Clave`, `ResultadosEnCarpeta`) y `reloj.py`. 24 pruebas.

Lo que se decidió al escribir y conviene revisar:

1. **La ficha de prueba es una copia de v21**, de las secciones TD-01, TD-16 y TD-29, tomada de `tipos_documentales.json` del modelo semántico y pasada por `elemento_para_agente`, la misma función del MCP. Son metadatos del modelo, sin datos de documentos. La genera `tests/generar_dobles.py`, que se corre a mano. No se comprobó que el archivo local sea idéntico a la v21 de Cosmos; eso se verá en T08, contra el MCP.
2. **Lo que la ficha de prueba agrega a v21**, solo para reproducir los ejemplos del contrato: `td_probado: true` en las secciones TD-16 y TD-29 (en `secciones`, como la daría `describir_modelo`) y `atributos.validador` en `td16.sociedad` (`nit_dv`), `td29.contratos` (`fecha_orden`) y `td29.totales_declarados` (dos `suma_igual`). Esa es la forma propuesta para declarar validadores en la matriz (D16): una lista de `{tipo, …parámetros}`. Se puede ajustar en T05.
3. **Respuesta del LLM:** las alertas exigen `id_tecnico` (puede ser `null`) y un código en mayúsculas, para que el LLM no las omita a medias.
4. **El LLM falso reconoce el TD** por la línea `Tipo documental: TD-NN` del mensaje del usuario. T04 tiene que armar el mensaje con esa línea.
5. **Reproceso:** el resultado reemplazado queda como `<nombre>.anterior-<id de ejecución>.json`, al lado del vigente.
6. **El reloj** de la extracción tiene `dormir` y `monotono`, además de `ahora`, para probar las esperas y medir la duración. Es una copia pequeña del del orquestador, porque la extracción no depende del orquestador.

### T02 — Entrada (2026-11-09)

`entrada.py` con `preparar(solicitud, almacen) → Entrada` (lectura, PDF, anexos y las páginas del segmento) y los errores de la tabla del plan. `tests/fabrica.py` normaliza PDF inventados con `normalizar_entrega` y arma las solicitudes como el orquestador. 38 pruebas en la extracción; la normalización (416) y el orquestador (182) siguen en verde.

`en_el_almacen` pasó del visor a `normalizacion.almacen`, partida en dos: `ruta_en_el_almacen(uri)` da la ruta relativa al almacén (la usa la extracción para reubicar las URI en su `AlmacenLocal`) y `en_el_almacen(carpeta, uri)` da el archivo dentro de la corrida (la usa el visor, que ahora la importa). Diferencia con la anterior: solo acepta URI `file://`; las demás devuelven None.

Lo que se decidió al escribir y conviene revisar:

1. **Sin `version_modelo`:** el contrato la deja opcional, con la versión registrada del proceso como respaldo. La extracción no guarda las versiones de los procesos (las fija el orquestador, que la manda siempre), así que una solicitud sin versión da `error_proceso` `VERSION_NO_INDICADA`, no reintentable. Nunca se usa la vigente.
2. **La lectura no se valida contra su esquema completo** (tiene una referencia al esquema del manifiesto). Solo se revisa que sea JSON, que su `id_documento` sea el de la solicitud y que traiga `paginas`. Si no, `error_proceso` `LECTURA_INVALIDA`, no reintentable.
3. **Huella:** se compara el SHA-256 del PDF con `archivo.sha256` (si viene) y siempre con `hash_pdf` de la lectura. Si no coincide, `ARCHIVO_DISTINTO`.
4. **Orden de las revisiones:** primero el contrato y la versión, después la lectura, el PDF y su huella, y al final el rango. Un documento que cambió se informa como falla técnica antes que como rango fuera.
5. **El mensaje del rango** dice "de la N a la M", algo distinto del ejemplo `salida_error.json` ("hasta la 9"). El ejemplo es solo una muestra; el contrato no fija el texto.

### T03 — Preprocesamiento (2026-11-09)

`preproceso.py` con `preparar_contenido(entrada) → Contenido`: por página, el texto (marcado si es del escáner), la imagen y las firmas ampliadas, más los anexos y las alertas, y `Contenido.lectura()` para el campo `lectura` de la salida. Dependencias nuevas: `pypdfium2` (Apache-2.0 / BSD-3), `pillow` y `openpyxl`. La fábrica suma un PDF de seis páginas, una de cada caso (texto, texto con firma, escaneo, escaneo con capa de texto y firma, en blanco y girada), y una hoja de cálculo. 49 pruebas.

Lo que se decidió al escribir y conviene revisar:

1. **Zona de la firma:** la caja del ancla (que ya trae la línea y su rótulo) más 3 renglones de 14 puntos hacia arriba, 1 hacia abajo y media pulgada a cada lado, a 300 dpi. El plan decía "a todo el ancho de la columna"; se dejó un margen fijo porque la lectura no dice dónde están las columnas. Una línea de firma típica da una imagen de unos 1.100 × 340 píxeles.
2. **Páginas giradas:** la imagen de la página sale como se ve en un visor (pdfium aplica la rotación). El recorte se dibuja sobre la página sin girar, porque las cajas de la lectura son de la página sin girar, y después se gira la imagen.
3. **Firmas en páginas `escaneo_con_ocr`:** también se amplían cuando la capa del escáner trajo el rótulo y la normalización encontró el ancla.
4. **Anexos:** se leen con openpyxl solo los xlsx y xlsm, con los valores que guardó Excel (no calcula fórmulas). Un xls, un ods o un archivo dañado no frena la extracción: queda la alerta `ANEXO_NO_LEIDO` y se usa solo el PDF. El tope es de 60.000 caracteres por anexo, con la alerta `ANEXO_RECORTADO`.
5. **Las alertas del preprocesamiento** no traen datos del documento, solo el número del anexo. Van a la salida junto con las del LLM (T05).

### T04 — Mensaje y prompt (2026-11-09)

`datos/prompt.md` (versión `extraccion/prompt@1`) y `mensaje.py` con `mensajes(entrada, ficha, contenido)`. 60 pruebas. Una prueba guarda la huella del prompt por versión: si alguien cambia el texto sin subir `VERSION_PROMPT`, falla.

Cómo queda el mensaje:

- **Sistema:** el prompt del servicio y, a continuación, la guía de interpretación de la versión fijada. Es el mismo para todos los segmentos de una versión, así que sirve de prefijo para la caché de prompt.
- **Usuario:** el encabezado (tipo documental con su nombre, versión del modelo, tipo de oferente o "no informado" y rango de páginas), la ficha del TD en JSON (solo los elementos que se extraen) y el contenido: por página, el rótulo `--- Página N ---` con su texto (o "(sin texto: ver la imagen)" o "(página en blanco)"), la imagen y cada ampliación de firma con su rótulo. Los anexos legibles van al final.

Tamaño medido con la ficha de prueba: prompt unos 7.200 caracteres, guía v21 unos 10.300, ficha de TD-16 o TD-29 unos 5.900 y la de TD-01 unos 22.000. En tokens, del orden de 4.500 fijos más 1.500 de la ficha, antes del documento.

Cambios frente al `prompt.md` del modelo semántico, que no se tocó:

1. **Sin herramientas:** la ficha ya viene en el mensaje. Si la guía dice que se consulte una sección, se toma como hecho. Si la guía y el prompt chocan en la forma de la respuesta, la evidencia, `cumple` o la revisión, manda el prompt (choque conocido con la guía v21, ver riesgos del plan).
2. **Sin parámetros ni datos de otros documentos** (D8): se quitó "Si te entregan parámetros del proceso…".
3. **Respuesta:** un único objeto JSON con `corresponde`, `motivo_no_corresponde`, `resultados` y `alertas`, sin líneas después (D10). Las "tres líneas para el evaluador" pasan a `alertas` con código.
4. **Evidencia estructurada** `{pagina, cita, visual}` (D12), con la página tal como dice el rótulo.
5. **`cumple`** solo con las reglas que resuelve el documento, `null` si el elemento no tiene ninguna; las demás en `reglas_pendientes` con su texto y lo que requieren (D14).
6. **Sin `revision`:** el LLM solo propone los cuatro motivos que se reconocen leyendo (`REQUIERE_IMAGEN`, `PLANTILLA_SIN_LLENAR`, `NOTA_ELEMENTO`, `CONTRADICCION`). La revisión la calcula el código.
7. **Confianza de un valor `null`:** `null` si el dato no aparece; 0,50 o menos si está pero no se lee (casilla sin marca legible). Así la casilla ilegible va a revisión por `CONFIANZA_BAJA` y el dato ausente de un campo no obligatorio no.
8. **Texto de escáner, ampliaciones de firma y anexos de hoja de cálculo** se explican en la entrada, que el prompt original no tenía.

### T05 — Posvalidación (2026-11-09)

`posvalidacion.py` (`interpretar`, `sobre`, `sobre_de_error`, `RespuestaInvalida`, `SalidaInvalida`) y `validadores.py` (los siete de D16). 97 pruebas.

**Criterio A7:** con la ficha de prueba y las respuestas falsas, las solicitudes de ejemplo de TD-16 y TD-29 dan las salidas de ejemplo: los mismos valores, evidencia, `cumple`, motivos, campos en revisión, alertas y `lectura`. Difieren solo en dos cosas, que la prueba tiene en cuenta:

- `id_regla`: aquí se numeran solo las reglas pendientes (`td16.firmante.r1`, `r2`); el ejemplo numeraba todas las reglas del elemento (`r2`, `r3`, porque `r1` era la del documento). Los dos son provisionales hasta la hoja Reglas (R1).
- `observacion`: al texto del LLM se le suma la explicación de cada validador que falla, por ejemplo "Validador fecha_orden: fila 2: fecha_inicio 2027-07-10 es posterior a fecha_fin 2020-12-31."

**Cambio en T02:** una solicitud sin `version_modelo` ya no da `error_proceso`, sino `SolicitudInvalida` (bug de quien la manda). La salida exige `version_modelo`, así que no había forma de contestar con un error válido.

Lo que se decidió al escribir y conviene revisar:

1. **`en_catalogo` sin declararlo:** se aplica siempre con `valores_permitidos` y, en las propiedades de los objetos, solo cuando todas sus opciones son códigos en mayúsculas (`SI / NO / null`, `RL / RF / CONTADOR`, `COP / USD / EUR / OTRA`). En v21 hay opciones que describen el dato más que listarlo (`fecha / Indefinida`, `manuscrita / digital / escaneada`, `unidades / miles / millones`): esas no se validan. `null` siempre vale.
2. **`nit_dv`** solo falla si el NIT trae dígito de verificación y no es el correcto (algoritmo de la DIAN). Un NIT sin DV no se verifica.
3. **Los validadores que no son de formato** (`suma_igual`, `suma_100`, `fecha_orden`) no fallan si no pueden leer los datos (un `N/A`, una fecha mal escrita): para eso está `fecha`.
4. **`suma_igual` con tolerancia 0** en la ficha de prueba de TD-29, como en el ejemplo (NEG-13 sin respuesta).
5. **Un validador desconocido** en la ficha (`ValidadorDesconocido`) es un error de la ficha y se trata como bug, sin reintento.
6. **`CONFIANZA_BAJA`** también cuando el campo tiene valor y el LLM no dio confianza.
7. **`OBLIGATORIO_VACIO`** solo con `obligatoriedad: Si`. Los `Condicional` no, porque la condición puede no aplicar (O3).
8. **`datos_personales`:** `true` salvo que la ficha diga "No". "Posible: correo" (td07.domicilio_contacto, td13.ubicacion_contacto, td34.autoevaluacion) cuenta como sí.
9. **Alineación:** un campo que el LLM no devolvió queda vacío con la alerta `CAMPO_SIN_RESPUESTA`; uno que no está en la ficha se descarta con `CAMPO_DESCONOCIDO`; uno repetido se toma la primera vez con `CAMPO_REPETIDO`. Las alertas van en este orden: preprocesamiento, LLM y alineación.
10. **`no_corresponde`:** sin resultados, sin revisión, y con la alerta `NO_CORRESPONDE`, que lleva el motivo que dio el LLM.
