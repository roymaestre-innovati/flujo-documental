"""El orquestador usa la normalización del mismo repositorio, importada directo."""

import normalizacion
from normalizacion.entrega import normalizar_entrega

import orquestador


def test_normalizacion_se_importa_desde_el_repositorio():
    assert callable(normalizar_entrega)
    assert normalizacion.VERSION
    assert "servicios/normalizacion" in normalizacion.__file__.replace("\\", "/")


def test_version():
    assert orquestador.VERSION == "0.1.0"
