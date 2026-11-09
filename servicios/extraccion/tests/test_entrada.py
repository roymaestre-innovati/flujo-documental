"""Entrada: solicitud válida, archivos ubicados, huellas y rango (R26 a R30)."""

import json
import shutil

import pytest

from extraccion.entrada import ErrorDeSolicitud, SolicitudInvalida, preparar, ubicar

from fabrica import Corrida, pdf


@pytest.fixture
def corrida(tmp_path):
    return Corrida(tmp_path / "corrida")


@pytest.fixture
def documento(corrida):
    (documento,) = corrida.normalizar({"certificado.pdf": pdf(3, "Certificado de aportes")})
    return documento


def test_prepara_un_segmento(corrida, documento):
    entrada = preparar(corrida.solicitud(documento, 2, 3), corrida.almacen)
    assert [p["pagina"] for p in entrada.paginas()] == [2, 3]
    assert "página 2" in entrada.paginas()[0]["texto"]
    assert entrada.pdf.startswith(b"%PDF-")
    assert entrada.anexos == ()


def test_solicitud_que_no_cumple_el_contrato_es_un_bug(corrida, documento):
    solicitud = corrida.solicitud(documento, 1, 1, tipo_documental="TD-99")
    with pytest.raises(SolicitudInvalida) as error:
        preparar(solicitud, corrida.almacen)
    assert error.value.errores == ["tipo_documental: no cumple 'not'"]


def test_sin_version_no_se_usa_la_vigente(corrida, documento):
    solicitud = corrida.solicitud(documento, 1, 1)
    del solicitud["version_modelo"]
    with pytest.raises(ErrorDeSolicitud) as error:
        preparar(solicitud, corrida.almacen)
    assert (error.value.estado, error.value.codigo, error.value.reintentable) == ("error_proceso", "VERSION_NO_INDICADA", False)


@pytest.mark.parametrize("desde,hasta", [(1, 4), (3, 2)])
def test_paginas_fuera_de_rango_es_error_del_documento(corrida, documento, desde, hasta):
    with pytest.raises(ErrorDeSolicitud) as error:
        preparar(corrida.solicitud(documento, desde, hasta), corrida.almacen)
    assert error.value.estado == "error_entrada"
    assert error.value.como_error() == {
        "codigo": "PAGINAS_FUERA_DE_RANGO",
        "mensaje": f"El archivo tiene 3 páginas y se pidió de la {desde} a la {hasta}.",
        "reintentable": False,
    }


def test_corrida_movida_de_carpeta(tmp_path, corrida, documento):
    solicitud = corrida.solicitud(documento, 1, 3)
    shutil.move(corrida.raiz, tmp_path / "movida")
    movida = Corrida(tmp_path / "movida")
    assert len(preparar(solicitud, movida.almacen).paginas()) == 3


def test_uri_que_no_es_del_almacen_local_queda_como_viene(corrida):
    uri = "https://cuenta.blob.core.windows.net/flujo/SR1/OF-001/pdf/a.pdf"
    assert ubicar(corrida.almacen, uri) == uri


def test_lectura_que_falta_es_falla_tecnica_reintentable(corrida, documento):
    solicitud = corrida.solicitud(documento, 1, 1)
    (corrida.raiz / "almacen" / solicitud["lectura"].split("/almacen/")[1]).unlink()
    with pytest.raises(ErrorDeSolicitud) as error:
        preparar(solicitud, corrida.almacen)
    assert (error.value.estado, error.value.codigo, error.value.reintentable) == ("error_proceso", "ARCHIVO_NO_ENCONTRADO", True)


def test_uri_de_otro_almacen_no_se_encuentra(corrida, documento):
    solicitud = corrida.solicitud(documento, 1, 1)
    solicitud["archivo"]["uri"] = "https://cuenta.blob.core.windows.net/flujo/x.pdf"
    with pytest.raises(ErrorDeSolicitud) as error:
        preparar(solicitud, corrida.almacen)
    assert error.value.codigo == "ARCHIVO_NO_ENCONTRADO"


def test_lectura_de_otro_documento(corrida, documento):
    solicitud = corrida.solicitud(documento, 1, 1, id_documento="OF-001-000000000000")
    with pytest.raises(ErrorDeSolicitud) as error:
        preparar(solicitud, corrida.almacen)
    assert (error.value.codigo, error.value.reintentable) == ("LECTURA_INVALIDA", False)


def test_huella_distinta_de_la_solicitud(corrida, documento):
    solicitud = corrida.solicitud(documento, 1, 1)
    solicitud["archivo"]["sha256"] = "0" * 64
    with pytest.raises(ErrorDeSolicitud) as error:
        preparar(solicitud, corrida.almacen)
    assert (error.value.estado, error.value.codigo, error.value.reintentable) == ("error_proceso", "ARCHIVO_DISTINTO", False)


def test_pdf_cambiado_despues_de_leerse(corrida, documento):
    solicitud = corrida.solicitud(documento, 1, 1)
    del solicitud["archivo"]["sha256"]
    corrida.almacen.escribir(corrida.almacen.uri(solicitud["archivo"]["uri"].split("/almacen/")[1]), pdf(3, "Otro"))
    with pytest.raises(ErrorDeSolicitud) as error:
        preparar(solicitud, corrida.almacen)
    assert error.value.codigo == "ARCHIVO_DISTINTO"


def test_lectura_que_no_es_json(corrida, documento):
    solicitud = corrida.solicitud(documento, 1, 1)
    corrida.almacen.escribir(corrida.almacen.uri(solicitud["lectura"].split("/almacen/")[1]), b"no es json")
    with pytest.raises(ErrorDeSolicitud) as error:
        preparar(solicitud, corrida.almacen)
    assert error.value.codigo == "LECTURA_INVALIDA"


def test_mensajes_de_error_sin_datos_del_documento(corrida, documento):
    solicitud = corrida.solicitud(documento, 1, 1)
    solicitud["archivo"]["sha256"] = "0" * 64
    with pytest.raises(ErrorDeSolicitud) as error:
        preparar(solicitud, corrida.almacen)
    texto = json.dumps(error.value.como_error())
    assert documento["id_documento"] not in texto and "certificado" not in texto
