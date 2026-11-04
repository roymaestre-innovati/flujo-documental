"""Revisión del PDF: R11 a R13 y R16."""

import io
import logging

import pikepdf
import pytest

import fabrica
from normalizacion.errores import CONTRASENA, DANADO, SIN_PAGINAS, error_documento
from normalizacion.revision_pdf import revisar


def _revisar_caso(tmp_path, caso):
    (ruta,) = fabrica.CASOS[caso](tmp_path)
    datos = ruta.read_bytes()
    return datos, revisar(datos)


def _sin_error(revision):
    assert revision.ok and revision.error is None


def _con_error(revision, codigo):
    assert not revision.ok
    assert revision.error == error_documento(codigo, "El PDF")
    assert revision.datos is None and revision.paginas is None
    assert revision.restricciones is None and revision.reparado is False


# R11: un PDF que viene bien se usa tal cual ------------------------------------


@pytest.mark.parametrize(
    ("caso", "paginas"),
    [
        ("pdf_texto", 1),
        ("pdf_escaneo_sin_texto", 1),
        ("pdf_escaneo_con_ocr", 1),
        ("pdf_vacio", 1),
        ("pdf_rotado", 1),
        ("pdf_anclas", 1),
        ("duplicados", 2),
    ],
)
def test_r11_pdf_bien_formado_se_usa_tal_cual(tmp_path, caso, paginas):
    rutas = fabrica.CASOS[caso](tmp_path)
    datos = rutas[0].read_bytes()
    revision = revisar(datos)
    _sin_error(revision)
    assert revision.datos is datos
    assert revision.paginas == paginas
    assert revision.restricciones is False
    assert revision.reparado is False


@pytest.mark.parametrize("caso", ["pdf_firmado", "pdf_modificado_despues_de_firmar"])
def test_r10_r11_un_pdf_firmado_no_se_reescribe(tmp_path, caso):
    datos, revision = _revisar_caso(tmp_path, caso)
    _sin_error(revision)
    assert revision.datos == datos


# R12: dañado ---------------------------------------------------------------------


def test_r12_danado_reparable(tmp_path):
    datos, revision = _revisar_caso(tmp_path, "pdf_danado_reparable")
    _sin_error(revision)
    assert revision.reparado is True
    assert revision.paginas == 1
    assert revision.datos != datos
    # La copia reparada abre sin necesidad de recuperación.
    with pikepdf.open(io.BytesIO(revision.datos), attempt_recovery=False) as pdf:
        assert len(pdf.pages) == 1


def test_r12_reparar_dos_veces_da_los_mismos_bytes(tmp_path):
    datos, primera = _revisar_caso(tmp_path, "pdf_danado_reparable")
    assert revisar(datos).datos == primera.datos


def test_r12_danado_irreparable(tmp_path):
    _, revision = _revisar_caso(tmp_path, "pdf_danado_irreparable")
    _con_error(revision, DANADO)


@pytest.mark.parametrize("datos", [b"%PDF-", b"%PDF-1.7\n%%EOF\n", b""])
def test_r12_casi_nada_es_danado(datos):
    _con_error(revisar(datos), DANADO)


def test_r12_la_reparacion_queda_en_el_registro_sin_datos(tmp_path, caplog):
    (ruta,) = fabrica.pdf_danado_reparable(tmp_path)
    with caplog.at_level(logging.INFO, logger="normalizacion.revision_pdf"):
        revisar(ruta.read_bytes())
    assert "reparado" in caplog.text
    assert ruta.name not in caplog.text


def test_r12_danado_y_con_restricciones(tmp_path):
    (ruta,) = fabrica.pdf_solo_restricciones(tmp_path)
    datos = ruta.read_bytes()
    inicio = datos.rindex(b"startxref") + len(b"startxref")
    fin = datos.index(b"%%EOF", inicio)
    danado = datos[:inicio] + b"\n999999\n" + datos[fin:]
    revision = revisar(danado)
    _sin_error(revision)
    assert revision.reparado is True
    assert revision.restricciones is True


# R13: contraseña y restricciones --------------------------------------------------


def test_r13_con_contrasena_para_abrir(tmp_path):
    _, revision = _revisar_caso(tmp_path, "pdf_con_contrasena")
    _con_error(revision, CONTRASENA)
    assert "contraseña" in revision.error.detalle


def test_r13_solo_restricciones_se_procesa_normal(tmp_path):
    datos, revision = _revisar_caso(tmp_path, "pdf_solo_restricciones")
    _sin_error(revision)
    assert revision.restricciones is True
    assert revision.datos is datos
    assert revision.paginas == 1


def test_r13_cifrado_sin_restricciones_de_copia_ni_impresion():
    base = fabrica.pdf_texto_bytes()
    with pikepdf.open(io.BytesIO(base)) as pdf:
        salida = io.BytesIO()
        permisos = pikepdf.Permissions(modify_other=False)  # copia e impresión permitidas
        pdf.save(salida, encryption=pikepdf.Encryption(user="", owner="dueno", allow=permisos))
    revision = revisar(salida.getvalue())
    _sin_error(revision)
    assert revision.restricciones is False


# R16: sin páginas -------------------------------------------------------------------


def test_r16_sin_paginas(tmp_path):
    _, revision = _revisar_caso(tmp_path, "pdf_sin_paginas")
    _con_error(revision, SIN_PAGINAS)


def test_varias_paginas(tmp_path):
    revision = revisar(fabrica.pdf_texto_bytes(paginas=5))
    _sin_error(revision)
    assert revision.paginas == 5
