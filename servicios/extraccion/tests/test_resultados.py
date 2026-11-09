"""Almacén de resultados por clave de idempotencia."""

import pytest

from extraccion.resultados import Clave, ResultadosEnCarpeta

from conftest import EJEMPLOS, cargar


@pytest.fixture
def solicitud():
    return cargar(EJEMPLOS / "entrada_td16.json")


def test_clave_de_una_solicitud(solicitud):
    clave = Clave.de(solicitud)
    assert clave.entrega == "OF-002"
    assert clave.nombre == "OF-002-4b7e21c90d3a-p1-2.TD-16.v21"


def test_clave_de_un_documento_del_proceso():
    clave = Clave.de(cargar(EJEMPLOS / "entrada_td01_proceso.json"))
    assert clave.entrega == "PROCESO"


def test_misma_clave_aunque_cambie_lo_demas(solicitud):
    otra = dict(solicitud, clasificacion_dudosa=True, confianza_clasificacion=0.8, forzar_reproceso=True)
    assert Clave.de(otra) == Clave.de(solicitud)
    assert Clave.de(dict(solicitud, version_modelo=22)) != Clave.de(solicitud)
    assert Clave.de(dict(solicitud, tipo_documental="TD-17")) != Clave.de(solicitud)


def test_guardar_y_buscar(tmp_path, solicitud):
    resultados = ResultadosEnCarpeta(tmp_path)
    clave = Clave.de(solicitud)
    assert resultados.buscar(clave) is None
    salida = cargar(EJEMPLOS / "salida_td16.json")
    resultados.guardar(clave, salida)
    assert resultados.buscar(clave) == salida
    assert resultados.ruta(clave) == tmp_path / "SR0000000001" / "OF-002" / "OF-002-4b7e21c90d3a-p1-2.TD-16.v21.json"
    assert [p.name for p in resultados.ruta(clave).parent.iterdir()] == ["OF-002-4b7e21c90d3a-p1-2.TD-16.v21.json"]


def test_reemplazar_conserva_el_anterior(tmp_path, solicitud):
    resultados = ResultadosEnCarpeta(tmp_path)
    clave = Clave.de(solicitud)
    primero = cargar(EJEMPLOS / "salida_td16.json")
    segundo = dict(primero, ejecucion=dict(primero["ejecucion"], id="ej-nuevo"))
    resultados.guardar(clave, primero)
    resultados.guardar(clave, segundo)
    assert resultados.buscar(clave)["ejecucion"]["id"] == "ej-nuevo"
    nombres = sorted(p.name for p in resultados.ruta(clave).parent.iterdir())
    assert nombres == [
        "OF-002-4b7e21c90d3a-p1-2.TD-16.v21.anterior-ej-000000000002.json",
        "OF-002-4b7e21c90d3a-p1-2.TD-16.v21.json",
    ]
