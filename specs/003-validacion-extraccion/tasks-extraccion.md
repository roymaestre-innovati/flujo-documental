# Tareas 003 — Extracción (segunda entrega)

Sale de `plan-extraccion.md`. Cada tarea termina con sus pruebas en verde y un commit propio.

**Estado al 2026-11-09:** spec, plan y tareas aprobados. T01 fusionada. T02 hecha, en revisión.

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
- [ ] **T03 — Preprocesamiento.** `preproceso.py`: qué va de cada página según su tipo, imagen con pypdfium2, firma ampliada a 300 dpi desde las anclas, valores del anexo con openpyxl y tope con `ANEXO_RECORTADO`, y `lectura` de la salida. Pruebas con PDF y xlsx inventados pasados por `normalizar_entrega`. Requisitos R31 a R34 y R36.
- [ ] **T04 — Mensaje y prompt.** `datos/prompt.md` (los cambios del plan sobre el `prompt.md` del modelo semántico) y `mensaje.py` (sistema: prompt + guía; usuario: ficha + contenido). Pruebas: el mensaje solo lleva las páginas del segmento, numeradas sobre el documento completo, y la ficha de la versión pedida. **Alto para que el usuario revise el prompt.** Requisito R35.
- [ ] **T05 — Posvalidación.** `posvalidacion.py` y `validadores.py`: forma, `no_corresponde`, alineación con la ficha, citas fuera del segmento, validadores, motivos, `datos_personales` y sobre validado contra el contrato. Con el `LLMFalso`, las solicitudes de ejemplo dan las salidas de ejemplo (criterio A7). Requisitos R37 a R48, R55 y R56.
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
