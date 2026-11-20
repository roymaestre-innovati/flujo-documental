"""Los ejemplos de los contratos cumplen sus esquemas, y los esquemas rechazan lo
que deben rechazar."""

import copy
import json

import pytest

from orquestador import CONTRATO, CONTRATO_EXTRACCION, contratos

EJEMPLOS = {
    contratos.PROCESO_LISTO: "modulo5-orquestador/v0.2/ejemplos/proceso-listo_*.json",
    contratos.CLASIFICACION_SOLICITUD: "modulo5-orquestador/v0.2/ejemplos/clasificacion-solicitud_*.json",
    contratos.CLASIFICACION_RESPUESTA: "modulo5-orquestador/v0.2/ejemplos/clasificacion-respuesta_*.json",
    contratos.EXTRACCION_ENTRADA: "modulo3-extraccion/v0.2/ejemplos/entrada_*.json",
}


def _ejemplos(esquema):
    return sorted(contratos.carpeta_contratos().glob(EJEMPLOS[esquema]))


def _cargar(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


@pytest.mark.parametrize("esquema", contratos.ESQUEMAS)
def test_ejemplos_cumplen_su_esquema(esquema):
    ejemplos = _ejemplos(esquema)
    assert ejemplos, f"No hay ejemplos de {esquema}"
    for ruta in ejemplos:
        assert contratos.errores(esquema, _cargar(ruta)) == [], ruta.name


def test_ejemplos_de_salida_de_extraccion_cumplen_su_esquema():
    v = contratos.validador("modulo3-extraccion/v0.2/salida")
    rutas = sorted(contratos.carpeta_contratos().glob("modulo3-extraccion/v0.2/ejemplos/salida_*.json"))
    assert rutas
    for ruta in rutas:
        assert list(v.iter_errors(_cargar(ruta))) == [], ruta.name


def test_versiones_del_codigo_coinciden_con_los_contratos():
    aviso = _ejemplos(contratos.PROCESO_LISTO)[0]
    assert _cargar(aviso)["contrato"] == CONTRATO
    solicitud = _ejemplos(contratos.EXTRACCION_ENTRADA)[0]
    assert _cargar(solicitud)["contrato"] == CONTRATO_EXTRACCION


@pytest.mark.parametrize("cambio", [
    {"tipo_documental": "TD-98"},
    {"tipo_documental": "TD-99"},
    {"contrato": "modulo3-extraccion/0.1"},
    {"archivo": {"uri": "no es una uri"}},
])
def test_extraccion_rechaza(cambio):
    solicitud = _cargar(_ejemplos(contratos.EXTRACCION_ENTRADA)[0])
    with pytest.raises(contratos.MensajeInvalido):
        contratos.validar(contratos.EXTRACCION_ENTRADA, {**solicitud, **cambio})


@pytest.mark.parametrize("falta", ["lectura", "anexos", "clasificacion_dudosa", "id_segmento", "id_oferente"])
def test_extraccion_exige(falta):
    solicitud = _cargar(_ejemplos(contratos.EXTRACCION_ENTRADA)[0])
    del solicitud[falta]
    assert contratos.errores(contratos.EXTRACCION_ENTRADA, solicitud)


def test_aviso_sin_ruta_es_invalido():
    aviso = _cargar(_ejemplos(contratos.PROCESO_LISTO)[0])
    del aviso["ruta"]
    assert contratos.errores(contratos.PROCESO_LISTO, aviso) == ["(raíz): no cumple 'required'"]


def test_los_errores_no_traen_valores_del_mensaje():
    aviso = _cargar(_ejemplos(contratos.PROCESO_LISTO)[0])
    aviso = copy.deepcopy(aviso)
    aviso["fecha"] = "Juan Pérez Gómez"
    encontrados = contratos.errores(contratos.PROCESO_LISTO, aviso)
    assert encontrados == ["fecha: no cumple 'format'"]
    assert "Juan" not in str(contratos.MensajeInvalido(contratos.PROCESO_LISTO, encontrados))


def _aviso_modulo1():
    ruta = contratos.carpeta_contratos() / "modulo5-orquestador/v0.2/ejemplos/proceso-listo_modulo1.json"
    return _cargar(ruta)


@pytest.mark.parametrize("cambio", [
    {"md5": "no-es-un-md5"},
    {"md5": "0f343b0931126a20f133d67c2b018a3"},
    {"tamano": -1},
    {"tamano": "1024"},
    {"otro": 1},
])
def test_proceso_listo_02_rechaza_archivos_mal_descritos(cambio):
    aviso = _aviso_modulo1()
    aviso["archivos"][0].update(cambio)
    with pytest.raises(contratos.MensajeInvalido):
        contratos.validar(contratos.PROCESO_LISTO, aviso)


def test_proceso_listo_02_acepta_un_aviso_01_con_solo_cambiar_la_version():
    ruta = contratos.carpeta_contratos() / "modulo5-orquestador/v0/ejemplos/proceso-listo_con_archivos.json"
    aviso = {**_cargar(ruta), "contrato": CONTRATO}
    contratos.validar(contratos.PROCESO_LISTO, aviso)
    with pytest.raises(contratos.MensajeInvalido):
        contratos.validar(contratos.PROCESO_LISTO, {**aviso, "comprimidos_sin_contenido": []})
