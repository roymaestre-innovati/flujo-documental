"""Tipo real por contenido (R6)."""

import io
import zipfile

import pytest

import fabrica
from normalizacion.tipos import (
    DOC,
    DOCX,
    IMAGEN,
    NO_SOPORTADO,
    ODS,
    ODT,
    PDF,
    XLS,
    XLSX,
    TipoReal,
    detectar,
)

ESPERADOS = {
    "pdf_texto": TipoReal(PDF),
    "pdf_escaneo_sin_texto": TipoReal(PDF),
    "pdf_escaneo_con_ocr": TipoReal(PDF),
    "pdf_vacio": TipoReal(PDF),
    "pdf_rotado": TipoReal(PDF),
    "pdf_con_contrasena": TipoReal(PDF),
    "pdf_solo_restricciones": TipoReal(PDF),
    "pdf_danado_reparable": TipoReal(PDF),
    "pdf_danado_irreparable": TipoReal(PDF),
    "pdf_firmado": TipoReal(PDF),
    "pdf_modificado_despues_de_firmar": TipoReal(PDF),
    "pdf_anclas": TipoReal(PDF),
    "docx": TipoReal(DOCX),
    "odt": TipoReal(ODT),
    "doc": TipoReal(DOC),
    "xlsx_ancho": TipoReal(XLSX),
    "xls": TipoReal(XLS),
    "ods": TipoReal(ODS),
    "jpg": TipoReal(IMAGEN, "jpeg"),
    "png": TipoReal(IMAGEN, "png"),
    "tiff_tres_paginas": TipoReal(IMAGEN, "tiff"),
    "extension_falsa": TipoReal(DOCX),
}


def _parametros():
    for caso, esperado in ESPERADOS.items():
        marcas = [pytest.mark.libreoffice] if caso in fabrica.CASOS_CON_LIBREOFFICE else []
        yield pytest.param(caso, esperado, id=caso, marks=marcas)


@pytest.mark.parametrize(("caso", "esperado"), list(_parametros()))
def test_cada_caso_de_la_fabrica(tmp_path, caso, esperado):
    (ruta,) = fabrica.CASOS[caso](tmp_path)
    assert detectar(ruta) == esperado


def test_la_extension_no_importa(tmp_path):
    (jpg,) = fabrica.jpg(tmp_path)
    renombrado = jpg.rename(tmp_path / "carta.docx")
    assert detectar(renombrado) == TipoReal(IMAGEN, "jpeg")


def test_tiff_big_endian(tmp_path):
    ruta = tmp_path / "escaneo.tif"
    ruta.write_bytes(b"MM\x00*" + bytes(64))
    assert detectar(ruta) == TipoReal(IMAGEN, "tiff")


def _zip(archivos: dict[str, bytes]) -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as zip_:
        for nombre, datos in archivos.items():
            zip_.writestr(nombre, datos)
    return salida.getvalue()


NO_SOPORTADOS = {
    "vacio.pdf": b"",
    "notas.txt": "Notas del oferente.\n".encode(),
    "cabecera_corta.pdf": b"%PD",
    "zip_cualquiera.zip": _zip({"notas.txt": b"x"}),
    "zip_con_carpeta_word.docx": _zip({"word/notas.txt": b"x"}),
    "zip_word_sin_content_types.docx": _zip({"word/document.xml": b"<x/>"}),
    "presentacion.odp": _zip({"mimetype": b"application/vnd.oasis.opendocument.presentation"}),
    "zip_roto.docx": b"PK\x03\x04" + bytes(100),
    "ole_roto.doc": bytes.fromhex("D0CF11E0A1B11AE1") + bytes(100),
    "appledouble.pdf": fabrica.CABECERA_APPLEDOUBLE + bytes(64),
}


@pytest.mark.parametrize("nombre", NO_SOPORTADOS)
def test_no_soportados(tmp_path, nombre):
    ruta = tmp_path / nombre
    ruta.write_bytes(NO_SOPORTADOS[nombre])
    assert detectar(ruta) == TipoReal(NO_SOPORTADO)


def test_zip_y_txt_de_la_fabrica(tmp_path):
    for ruta in fabrica.no_soportados(tmp_path):
        assert detectar(ruta) == TipoReal(NO_SOPORTADO)


def test_thumbs_db_de_la_fabrica_no_es_doc_ni_xls(tmp_path):
    thumbs = next(r for r in fabrica.archivos_de_sistema(tmp_path) if r.name == "Thumbs.db")
    assert detectar(thumbs) == TipoReal(NO_SOPORTADO)


def test_ooxml_con_contenido_minimo(tmp_path):
    for piezas, esperado in (
        ({"[Content_Types].xml": b"<x/>", "word/document.xml": b"<x/>"}, DOCX),
        ({"[Content_Types].xml": b"<x/>", "xl/workbook.xml": b"<x/>"}, XLSX),
    ):
        ruta = tmp_path / f"archivo.{esperado}"
        ruta.write_bytes(_zip(piezas))
        assert detectar(ruta) == TipoReal(esperado)
