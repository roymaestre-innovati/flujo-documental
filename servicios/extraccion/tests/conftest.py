import json
from pathlib import Path

import pytest

from extraccion.ficha import FuenteModeloArchivo

AQUI = Path(__file__).parent
FICHA_V21 = AQUI / "fichas" / "extraccion_documental.v21.json"
EJEMPLOS = AQUI.parents[2] / "contracts" / "modulo3-extraccion" / "v0.2" / "ejemplos"


def cargar(ruta: Path):
    return json.loads(ruta.read_text(encoding="utf-8"))


def respuesta_falsa(td: str) -> str:
    """El texto que responde el LLM falso para un TD, tal como lo mandaría el LLM."""
    return (AQUI / "respuestas" / f"{td}.json").read_text(encoding="utf-8")


@pytest.fixture
def fuente_modelo() -> FuenteModeloArchivo:
    return FuenteModeloArchivo(FICHA_V21)
