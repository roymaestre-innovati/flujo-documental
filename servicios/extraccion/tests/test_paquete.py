"""Esqueleto del servicio: versión, contratos, parámetros y dobles de prueba."""

import re

import pytest

from extraccion import CONTRATO, VERSION, contratos
from extraccion.parametros import parametros, version_parametros

from conftest import EJEMPLOS, cargar


def test_version_y_contrato():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)
    assert CONTRATO == "modulo3-extraccion/0.2"
    assert contratos.validador(contratos.ENTRADA).schema["properties"]["contrato"]["const"] == CONTRATO


@pytest.mark.parametrize("tipo", ["entrada", "salida"])
def test_ejemplos_del_contrato_cumplen_su_esquema(tipo):
    rutas = sorted(EJEMPLOS.glob(f"{tipo}_*.json"))
    assert rutas
    esquema = contratos.ENTRADA if tipo == "entrada" else contratos.SALIDA
    for ruta in rutas:
        assert contratos.errores(esquema, cargar(ruta)) == [], ruta.name


def test_errores_no_muestran_valores():
    solicitud = cargar(EJEMPLOS / "entrada_td16.json")
    solicitud["tipo_documental"] = "TD-99"
    solicitud["id_oferente"] = ""
    problemas = contratos.errores(contratos.ENTRADA, solicitud)
    assert problemas == ["id_oferente: no cumple 'minLength'", "tipo_documental: no cumple 'not'"]
    assert not any("TD-99" in p for p in problemas)


def test_parametros_tienen_version():
    assert version_parametros() == "1"
    llamada = parametros()["llamada"]
    assert llamada["concurrencia"] == 3
    assert llamada["reintentos_falla_pasajera"] == len(llamada["esperas_falla_pasajera_s"]) == 3
    assert llamada["reintentos_respuesta_invalida"] == 2
    assert parametros()["firma"]["dpi"] == 300
