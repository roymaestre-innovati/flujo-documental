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
    ODP,
    ODT,
    PDF,
    PPT,
    PPTX,
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
    "pdf_sin_paginas": TipoReal(PDF),
    "pdf_con_contrasena": TipoReal(PDF),
    "pdf_solo_restricciones": TipoReal(PDF),
    "pdf_danado_reparable": TipoReal(PDF),
    "pdf_danado_irreparable": TipoReal(PDF),
    "pdf_firmado": TipoReal(PDF),
    "pdf_firma_ilegible": TipoReal(PDF),
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
    "png_transparente": TipoReal(IMAGEN, "png"),
    "odt_con_macro": TipoReal(ODT),
    "tiff_tres_paginas": TipoReal(IMAGEN, "tiff"),
    "extension_falsa": TipoReal(DOCX),
    "pptx": TipoReal(PPTX),
    "ppt": TipoReal(PPT),
    "odp": TipoReal(ODP),
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
    "dibujo.odg": _zip({"mimetype": b"application/vnd.oasis.opendocument.graphics"}),
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


# Documentos de Office con contraseña -----------------------------------------


@pytest.mark.parametrize("caso", ["docx_con_contrasena", "xlsx_con_contrasena"])
def test_ooxml_con_contrasena(tmp_path, caso):
    (ruta,) = fabrica.CASOS[caso](tmp_path)
    assert detectar(ruta) == TipoReal(NO_SOPORTADO, cifrado=True)


def test_los_documentos_sin_contrasena_no_salen_cifrados(tmp_path):
    for caso in ("docx", "xlsx_ancho", "pdf_con_contrasena"):
        (ruta,) = fabrica.CASOS[caso](tmp_path / caso)
        assert not detectar(ruta).cifrado


def _marcar_en_ole(ruta, flujo, cambio):
    """Cambia bytes de un flujo OLE sin cambiar su tamaño."""
    import olefile

    with olefile.OleFileIO(str(ruta), write_mode=True) as ole:
        datos = bytearray(ole.openstream(flujo).read())
        cambio(datos)
        ole.write_stream(flujo, bytes(datos))


@pytest.mark.libreoffice
def test_doc_con_contrasena(tmp_path):
    (ruta,) = fabrica.doc(tmp_path)
    assert detectar(ruta) == TipoReal(DOC)

    def marcar(datos):
        datos[11] |= 0x01  # bit fEncrypted (0x0100) de las banderas del FIB

    _marcar_en_ole(ruta, "WordDocument", marcar)
    assert detectar(ruta) == TipoReal(DOC, cifrado=True)


@pytest.mark.libreoffice
def test_xls_con_contrasena(tmp_path):
    import struct

    (ruta,) = fabrica.xls(tmp_path)
    assert detectar(ruta) == TipoReal(XLS)

    def marcar(datos):
        (largo_bof,) = struct.unpack_from("<H", datos, 2)
        struct.pack_into("<H", datos, 4 + largo_bof, 0x002F)  # FILEPASS después del BOF

    _marcar_en_ole(ruta, "Workbook", marcar)
    assert detectar(ruta) == TipoReal(XLS, cifrado=True)


@pytest.mark.parametrize(("mimetype", "esperado"), [
    (b"application/vnd.oasis.opendocument.text", ODT),
    (b"application/vnd.oasis.opendocument.spreadsheet", ODS),
    (b"application/vnd.oasis.opendocument.presentation", ODP),
])
def test_odf_con_contrasena(tmp_path, mimetype, esperado):
    manifiesto = (
        b'<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
        b'<manifest:file-entry manifest:full-path="content.xml">'
        b'<manifest:encryption-data manifest:checksum-type="SHA1/1K"/>'
        b"</manifest:file-entry></manifest:manifest>"
    )
    ruta = tmp_path / f"cifrado.{esperado}"
    ruta.write_bytes(_zip({"mimetype": mimetype, "META-INF/manifest.xml": manifiesto}))
    assert detectar(ruta) == TipoReal(esperado, cifrado=True)


@pytest.mark.libreoffice
def test_odt_sin_contrasena_no_sale_cifrado(tmp_path):
    (ruta,) = fabrica.odt(tmp_path)
    assert detectar(ruta) == TipoReal(ODT)
