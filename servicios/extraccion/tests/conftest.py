import json
from pathlib import Path

import pytest

from extraccion.ficha import FuenteModeloArchivo

AQUI = Path(__file__).parent
FICHA_V21 = AQUI / "fichas" / "extraccion_documental.v21.json"
EJEMPLOS = AQUI.parents[2] / "contracts" / "modulo3-extraccion" / "v0.2" / "ejemplos"


@pytest.fixture(autouse=True)
def _sin_almacen_blob(monkeypatch):
    monkeypatch.delenv("ALMACEN_BLOB_CUENTA", raising=False)
    monkeypatch.delenv("ALMACEN_BLOB_CONTENEDOR", raising=False)


@pytest.fixture
def contenedor_blob_falso(monkeypatch):
    pruebas_normalizacion = AQUI.parents[1] / "normalizacion" / "tests"
    with monkeypatch.context() as parche:
        parche.syspath_prepend(str(pruebas_normalizacion))
        from blob_falso import ContenedorFalso

    return ContenedorFalso()


def cargar(ruta: Path):
    return json.loads(ruta.read_text(encoding="utf-8"))


def respuesta_falsa(td: str) -> str:
    """El texto que responde el LLM falso para un TD, tal como lo mandaría el LLM."""
    return (AQUI / "respuestas" / f"{td}.json").read_text(encoding="utf-8")


@pytest.fixture
def fuente_modelo() -> FuenteModeloArchivo:
    return FuenteModeloArchivo(FICHA_V21)
