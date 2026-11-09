"""Validadores genéricos de D16 (R47)."""

import pytest

from extraccion.validadores import (
    ValidadorDesconocido, claves_objeto, en_catalogo, fecha, fecha_orden, nit_dv, suma_100, suma_igual, validar,
)

SUBTIPO = {"id_tecnico": "td16.subtipo", "valores_permitidos": ["PJ", "PN"], "atributos": {}}
FIRMANTE = {
    "id_tecnico": "td16.firmante",
    "atributos": {"propiedades": [
        {"nombre": "rol", "valores": "RL / RF / CONTADOR"},
        {"nombre": "nombre"},
        {"nombre": "firma", "valores": "SI / NO / null"},
        {"nombre": "vigencia", "valores": "fecha / Indefinida"},
    ]},
}


def test_en_catalogo_con_valores_permitidos():
    assert en_catalogo(SUBTIPO, "PJ") == []
    assert en_catalogo(SUBTIPO, "Persona jurídica") == ["'Persona jurídica' no está entre los valores permitidos (PJ, PN)."]
    assert en_catalogo({"valores_permitidos": [{"valor": "PJ_NAL", "etiqueta": "x"}, "EP"]}, ["EP", "PN"]) == ["'PN' no están entre los valores permitidos."]


def test_en_catalogo_en_propiedades_solo_con_codigos():
    bien = [{"rol": "RF", "nombre": "Ana", "firma": None, "vigencia": "2027-01-01"}]
    assert en_catalogo(FIRMANTE, bien) == []
    mal = [{"rol": "RF", "firma": "SI"}, {"rol": "Revisor", "firma": "Sí", "vigencia": "cualquier cosa"}]
    assert en_catalogo(FIRMANTE, mal) == [
        "fila 2: rol = 'Revisor' no está entre RL / RF / CONTADOR.",
        "fila 2: firma = 'Sí' no está entre SI / NO / null.",
    ]


@pytest.mark.parametrize("nit,fallas", [
    ("900123456-8", 0), ("890.903.938-8", 0), ("900123456-1", 1), ("900123456", 0), ("no es un nit", 0),
])
def test_nit_dv(nit, fallas):
    assert len(nit_dv(nit)) == fallas


def test_nit_dv_en_una_propiedad():
    assert nit_dv({"razon_social": "X", "nit": "900123456-2"}, propiedad="nit") == [
        "El dígito de verificación del NIT 900123456-2 no es correcto (debería ser 8)."
    ]


def test_fecha():
    assert fecha("2026-02-28") == []
    assert fecha("2026-02-30") == ["'2026-02-30' no es una fecha AAAA-MM-DD válida."]
    assert fecha([{"f": "2026-01-01"}, {"f": "01/02/2026"}], propiedad="f") == ["fila 2: '01/02/2026' no es una fecha AAAA-MM-DD válida."]


def test_fecha_orden():
    filas = [{"inicio": "2021-01-05", "fin": "2026-06-30"}, {"inicio": "2027-07-10", "fin": "2020-12-31"}, {"inicio": None, "fin": "2020-01-01"}]
    assert fecha_orden(filas, "inicio", "fin") == ["fila 2: inicio 2027-07-10 es posterior a fin 2020-12-31."]
    assert fecha_orden({"inicio": "2020-01-02", "fin": "2020-01-01"}, "inicio", "fin") == ["inicio 2020-01-02 es posterior a fin 2020-01-01."]


def test_suma_igual():
    valores = {"td29.contratos": [{"v": "100.50"}, {"v": "200"}]}
    assert suma_igual({"total": "300.5"}, "total", "td29.contratos", "v", valores=valores) == []
    assert len(suma_igual({"total": "301"}, "total", "td29.contratos", "v", valores=valores)) == 1
    assert suma_igual({"total": "301"}, "total", "td29.contratos", "v", tolerancia=1, valores=valores) == []
    # Sin datos para comparar, no falla: no es un validador de formato.
    assert suma_igual({"total": "301"}, "total", "td29.contratos", "v", valores={"td29.contratos": [{"v": "N/A"}]}) == []
    assert suma_igual({"total": None}, "total", "td29.contratos", "v", valores=valores) == []


def test_suma_100():
    assert suma_100([{"p": "60"}, {"p": 40}], "p") == []
    assert suma_100([{"p": "60"}, {"p": 30}], "p") == ["p suma 90, no 100 (tolerancia 0)."]


def test_claves_objeto():
    assert claves_objeto({"a": 1, "b": 2}, ["a", "b"]) == []
    assert claves_objeto([{"a": 1}, {"a": 1, "c": 3}], ["a", "b"]) == ["fila 1: faltan b.", "fila 2: sobran c; faltan b."]
    assert claves_objeto("texto", ["a"]) == ["Se esperaba un objeto o una lista de objetos."]


def test_validar_aplica_catalogo_y_los_declarados():
    elemento = dict(SUBTIPO, atributos={"validador": [{"tipo": "fecha"}]})
    assert validar(elemento, None, {}) == []
    assert validar(elemento, "PX", {}) == [
        "Validador en_catalogo: 'PX' no está entre los valores permitidos (PJ, PN).",
        "Validador fecha: 'PX' no es una fecha AAAA-MM-DD válida.",
    ]


def test_validador_desconocido_es_un_error_de_la_ficha():
    with pytest.raises(ValidadorDesconocido):
        validar({"id_tecnico": "x", "atributos": {"validador": [{"tipo": "magia"}]}}, "1", {})
