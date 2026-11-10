# Extracción

Saca los datos de cada segmento de documento ya clasificado (iniciativa 003, entrega 2). Recibe una solicitud del contrato `modulo3-extraccion/0.2` y devuelve un resultado del mismo contrato. La spec está en `specs/003-validacion-extraccion/spec.md` (sección "Entrega 2 — Extracción"), el plan en `plan-extraccion.md` y las tareas en `tasks-extraccion.md`.

**Estado:** en construcción. T01 a T10 hechas: el servicio corre de punta a punta en local, con el LLM falso o con gpt-5.4, y la ficha de un archivo o del MCP. Los resultados se ven en el visor del orquestador (`uv run visor --corridas <carpeta>`). Falta correr la medición con los gold (criterio A9), que corre el usuario.

## Instalar y probar

Python 3.12 y `uv`. Desde esta carpeta:

```bash
uv sync
uv run pytest
```

La normalización (`../normalizacion`) se instala como dependencia de ruta, editable. El orquestador (`../orquestador`) solo entra en las pruebas, para armar las solicitudes como él.

## Uso

Como función: `extraer_segmento(solicitud, servicio)` en `servicio.py` devuelve el resultado del contrato. Por línea de comandos, sobre una corrida local del orquestador (`orquestar --salida <carpeta>`):

```bash
# Sin red: el LLM falso responde con un JSON por TD.
uv run extraer <carpeta>/solicitudes-extraccion.jsonl --corrida <carpeta> \
    --modelo archivo:tests/fichas/extraccion_documental.v21.json \
    --llm falso --respuestas tests/respuestas
```

- Los resultados quedan en `<carpeta>/extraccion/<id_proceso>/<entrega>/<id_segmento>.<TD>.v<versión>.json`. La corrida tiene que estar fuera de cualquier repositorio git, porque los resultados traen datos personales.
- Una segunda corrida devuelve lo guardado sin llamar al LLM. `--forzar` extrae otra vez y deja el resultado anterior al lado, con el sufijo `.anterior-<id de ejecución>`. Una falla técnica (`error_proceso`) no se guarda.
- `--solo <id_segmento>` (se puede repetir) extrae solo esos segmentos. `--concurrencia` cambia el tope de llamadas al LLM a la vez (3).
- Por pantalla salen solo conteos: por estado, campos en revisión por motivo, errores, tokens, reintentos, repetidos y tiempo. `--registros <archivo>` guarda una línea JSON por segmento, con identificadores y conteos, nunca valores ni citas.
- Sale con 0 si todo terminó, 1 si hubo líneas ilegibles, solicitudes que no cumplen el contrato, fallas internas o `error_proceso`, y 2 si los argumentos no sirven.

**Ficha desde el MCP (`--modelo mcp`):** pide la ficha al servidor del modelo semántico con `MCP_URL` y `MCP_API_KEY` (del entorno o del `.env`). Al MCP solo van el modelo, la versión y el TD. Las fichas usadas quedan en `<carpeta>/extraccion/fichas/v<versión>/<TD>.json`, para el visor. Para probar la conexión sin mandar documentos:

```bash
cd ~/GEB/modelo-semantico   # su .env ya trae MCP_URL y MCP_API_KEY
uv run --project ~/GEB/flujo-documental-repo/servicios/extraccion probar-ficha-mcp --td TD-16 --version 21
```

**Con gpt-5.4 (`--llm azure`):** manda el contenido de los documentos a Azure OpenAI. Solo con documentos autorizados. Lee `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` y `AZURE_OPENAI_DEPLOYMENT` del entorno o del `.env` de la carpeta actual, sin imprimirlos, y rechaza un deployment `mini`. Antes de mandar nada pregunta si seguir, salvo con `--si-mando-documentos`.

## Medir contra el gold (`medir-gold`)

Extrae los documentos de un TD con gold y compara campo a campo con `gold_TD-NN.xlsx`, al lado de la última corrida de `lote.py` de la misma carpeta. **Manda los documentos a gpt-5.4:** solo con autorización. Imprime solo conteos por campo, tokens y tiempo: nunca valores ni nombres de documentos. Sale con 1 si algún campo baja frente a `lote.py`.

```bash
cd ~/GEB/modelo-semantico   # su .env trae las variables de Azure OpenAI y del MCP
uv run --project ~/GEB/flujo-documental-repo/servicios/extraccion medir-gold \
    ~/GEB/Extraccion/Documentos/pruebas/TD-16 --trabajo ~/GEB/medicion-gold/TD-16
```

- Los PDF se toman de `../../clasificados/TD-16 …` (o `--documentos`). La normalización y los resultados quedan en `--trabajo`, fuera de cualquier repositorio.
- Una segunda corrida usa lo guardado en `--trabajo` y no llama al LLM. `--solo-comparar` no extrae nada: solo compara.
- `--modelo mcp` (por defecto) o `archivo:<ficha.json>`; `--version` (21 por defecto); `--lote <carpeta>` para comparar con otra corrida de `lote.py`.
- Cómo se lee el gold y cuándo cuenta un acierto: docstring de `src/extraccion/medicion.py`.

## Dobles de prueba

- `tests/fichas/extraccion_documental.v21.json`: las secciones TD-01, TD-16 y TD-29 del modelo semántico v21, con la forma que devuelve el MCP. Solo metadatos del modelo.
- `tests/respuestas/TD-16.json` y `TD-29.json`: lo que respondería el LLM para dar las salidas de ejemplo del contrato.

Se regeneran con `uv run python tests/generar_dobles.py ~/GEB/modelo-semantico` (ver el docstring del script).

Las pruebas usan solo documentos inventados y el `LLMFalso`. Ningún documento real va al LLM desde las pruebas.
