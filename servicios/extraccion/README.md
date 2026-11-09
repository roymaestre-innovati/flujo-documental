# Extracción

Saca los datos de cada segmento de documento ya clasificado (iniciativa 003, entrega 2). Recibe una solicitud del contrato `modulo3-extraccion/0.2` y devuelve un resultado del mismo contrato. La spec está en `specs/003-validacion-extraccion/spec.md` (sección "Entrega 2 — Extracción"), el plan en `plan-extraccion.md` y las tareas en `tasks-extraccion.md`.

**Estado:** en construcción. T01 hecha: esqueleto y dobles de prueba.

## Instalar y probar

Python 3.12 y `uv`. Desde esta carpeta:

```bash
uv sync
uv run pytest
```

La normalización (`../normalizacion`) se instala como dependencia de ruta, editable.

## Dobles de prueba

- `tests/fichas/extraccion_documental.v21.json`: las secciones TD-01, TD-16 y TD-29 del modelo semántico v21, con la forma que devuelve el MCP. Solo metadatos del modelo.
- `tests/respuestas/TD-16.json` y `TD-29.json`: lo que respondería el LLM para dar las salidas de ejemplo del contrato.

Se regeneran con `uv run python tests/generar_dobles.py ~/GEB/modelo-semantico` (ver el docstring del script).

Las pruebas usan solo documentos inventados y el `LLMFalso`. Ningún documento real va al LLM desde las pruebas.
