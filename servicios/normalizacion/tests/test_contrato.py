import copy
import json

import pytest
from jsonschema import Draft202012Validator

from normalizacion import CONTRATO as VERSION_CONTRATO
from normalizacion import VERSION
from normalizacion.parametros import VERSION_PARAMETROS

from contrato import CONTRATO, NOMBRES, esquemas, validador


def _ejemplos(nombre):
    return sorted((CONTRATO / "ejemplos").glob(f"{nombre}_*.json"))


def _cargar(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


@pytest.mark.parametrize("nombre", NOMBRES)
def test_el_esquema_es_valido(nombre):
    Draft202012Validator.check_schema(esquemas()[nombre])


@pytest.mark.parametrize("nombre", NOMBRES)
def test_hay_ejemplos(nombre):
    assert _ejemplos(nombre)


@pytest.mark.parametrize(
    "ruta",
    [ruta for nombre in NOMBRES for ruta in _ejemplos(nombre)],
    ids=lambda ruta: ruta.name,
)
def test_el_ejemplo_cumple_su_esquema(ruta):
    nombre = ruta.name.split("_", 1)[0]
    validador(nombre).validate(_cargar(ruta))


def test_el_paquete_produce_la_version_del_contrato():
    assert esquemas()["manifiesto"]["properties"]["contrato"]["const"] == VERSION_CONTRATO
    assert esquemas()["lectura"]["properties"]["contrato"]["const"] == VERSION_CONTRATO


def test_los_ejemplos_usan_las_versiones_del_paquete():
    for nombre in ("manifiesto", "lectura"):
        for ruta in _ejemplos(nombre):
            datos = _cargar(ruta)
            assert datos["version_normalizador"] == VERSION
            assert datos["version_parametros"] == VERSION_PARAMETROS


def _manifiesto():
    return _cargar(CONTRATO / "ejemplos" / "manifiesto_of002.json")


def _lectura():
    return _cargar(CONTRATO / "ejemplos" / "lectura_of002_carta.json")


def _por_estado(manifiesto, estado):
    return next(a for a in manifiesto["archivos"] if a["estado"] == estado)


def _cambiar_manifiesto(estado, campo, valor):
    def cambio(m):
        _por_estado(m, estado)[campo] = valor
    return cambio


CASOS_INVALIDOS = {
    "error_sin_codigo": ("manifiesto", _cambiar_manifiesto("error_entrada", "error", None)),
    "error_con_pdf": ("manifiesto", _cambiar_manifiesto("error_entrada", "pdf", "file:///x.pdf")),
    "normalizado_sin_pdf": ("manifiesto", _cambiar_manifiesto("normalizado", "pdf", None)),
    "normalizado_con_error": (
        "manifiesto",
        _cambiar_manifiesto("normalizado", "error", {"codigo": "DANADO", "detalle": "x"}),
    ),
    "duplicado_sin_original": ("manifiesto", _cambiar_manifiesto("duplicado", "duplicado_de", None)),
    "anexo_en_un_pdf": ("manifiesto", _cambiar_manifiesto("normalizado", "anexo_nativo", "file:///x.xlsx")),
    "codigo_de_error_desconocido": (
        "manifiesto",
        _cambiar_manifiesto("error_entrada", "error", {"codigo": "OTRO", "detalle": "x"}),
    ),
    "firma_sin_leer_con_firmante": (
        "manifiesto",
        lambda m: _por_estado(m, "normalizado")["firma_digital"][0].update(leida=False),
    ),
    "motivo_de_descarte_desconocido": ("manifiesto", lambda m: m["descartados"][0].update(motivo="otro")),
    "hash_corto": ("manifiesto", _cambiar_manifiesto("normalizado", "hash", "abc")),
    "otro_contrato": ("manifiesto", lambda m: m.update(contrato="modulo3-normalizacion/9.9")),
    "imagen_con_origen": ("lectura", lambda l: l["paginas"][2].update(origen_texto="nativo")),
    "texto_con_ocr": ("lectura", lambda l: l["paginas"][0].update(origen_texto="ocr_escaner")),
    "imagen_con_anclas": ("lectura", lambda l: l["paginas"][2].update(anclas=l["paginas"][0]["anclas"])),
    "caja_de_tres": ("lectura", lambda l: l["paginas"][0]["anclas"][0].update(caja=[1, 2, 3])),
    "rotacion_rara": ("lectura", lambda l: l["paginas"][0].update(rotacion=45)),
    "cobertura_mayor_que_uno": ("lectura", lambda l: l["paginas"][0].update(cobertura_imagen=1.2)),
}


@pytest.mark.parametrize("caso", CASOS_INVALIDOS)
def test_el_esquema_rechaza(caso):
    nombre, cambio = CASOS_INVALIDOS[caso]
    datos = copy.deepcopy(_manifiesto() if nombre == "manifiesto" else _lectura())
    assert validador(nombre).is_valid(datos)
    cambio(datos)
    assert not validador(nombre).is_valid(datos)
