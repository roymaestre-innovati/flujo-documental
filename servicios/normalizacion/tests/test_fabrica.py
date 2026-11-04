"""Una prueba por caso de la fábrica: confirma que el archivo se fabricó y que
tiene la propiedad que el caso promete. No usa el código del normalizador."""

import io
import zipfile

import pikepdf
import pytest
from PIL import Image

import fabrica


def _un_archivo(rutas):
    assert len(rutas) == 1
    ruta = rutas[0]
    assert ruta.is_file() and ruta.stat().st_size > 0
    return ruta


def _texto_contenido(pagina) -> bytes:
    return b"".join(
        bloque.read_bytes()
        for bloque in ([pagina.Contents] if isinstance(pagina.Contents, pikepdf.Stream) else pagina.Contents)
    )


def _tiene_imagen(pagina) -> bool:
    return bool(pagina.get_images())


def test_todos_los_casos_estan_registrados():
    assert len(fabrica.CASOS) == 24
    assert fabrica.CASOS_CON_LIBREOFFICE <= set(fabrica.CASOS)


def test_pdf_texto(tmp_path):
    ruta = _un_archivo(fabrica.pdf_texto(tmp_path))
    with pikepdf.open(ruta) as pdf:
        assert len(pdf.pages) == 1
        assert not _tiene_imagen(pdf.pages[0])
        assert b"Tj" in _texto_contenido(pdf.pages[0])


def test_el_mismo_caso_da_los_mismos_bytes(tmp_path):
    uno = _un_archivo(fabrica.pdf_texto(tmp_path / "uno")).read_bytes()
    dos = _un_archivo(fabrica.pdf_texto(tmp_path / "dos")).read_bytes()
    assert uno == dos


def test_pdf_escaneo_sin_texto(tmp_path):
    ruta = _un_archivo(fabrica.pdf_escaneo_sin_texto(tmp_path))
    with pikepdf.open(ruta) as pdf:
        pagina = pdf.pages[0]
        assert _tiene_imagen(pagina)
        assert b"Tj" not in _texto_contenido(pagina)


def test_pdf_escaneo_con_ocr(tmp_path):
    ruta = _un_archivo(fabrica.pdf_escaneo_con_ocr(tmp_path))
    with pikepdf.open(ruta) as pdf:
        contenido = _texto_contenido(pdf.pages[0])
        assert _tiene_imagen(pdf.pages[0])
        assert b"3 Tr" in contenido and b"Tj" in contenido


def test_pdf_vacio(tmp_path):
    ruta = _un_archivo(fabrica.pdf_vacio(tmp_path))
    with pikepdf.open(ruta) as pdf:
        assert len(pdf.pages) == 1
        assert not _tiene_imagen(pdf.pages[0])
        assert b"Tj" not in _texto_contenido(pdf.pages[0])


def test_pdf_rotado(tmp_path):
    ruta = _un_archivo(fabrica.pdf_rotado(tmp_path))
    with pikepdf.open(ruta) as pdf:
        assert pdf.pages[0].obj.Rotate == 90


def test_pdf_con_contrasena(tmp_path):
    ruta = _un_archivo(fabrica.pdf_con_contrasena(tmp_path))
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(ruta)
    with pikepdf.open(ruta, password=fabrica.CONTRASENA_USUARIO) as pdf:
        assert len(pdf.pages) == 1


def test_pdf_solo_restricciones(tmp_path):
    ruta = _un_archivo(fabrica.pdf_solo_restricciones(tmp_path))
    with pikepdf.open(ruta) as pdf:
        assert pdf.is_encrypted
        assert not pdf.allow.extract
        assert not pdf.allow.print_highres
        assert len(pdf.pages) == 1


def test_pdf_danado_reparable(tmp_path):
    ruta = _un_archivo(fabrica.pdf_danado_reparable(tmp_path))
    with pytest.raises(pikepdf.PdfError):
        pikepdf.open(ruta, attempt_recovery=False)
    with pikepdf.open(ruta) as pdf:
        assert len(pdf.pages) == 1


def test_pdf_danado_irreparable(tmp_path):
    ruta = _un_archivo(fabrica.pdf_danado_irreparable(tmp_path))
    assert ruta.read_bytes().startswith(b"%PDF-")
    with pytest.raises(pikepdf.PdfError):
        pikepdf.open(ruta)


def _estado_firma(ruta):
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    with ruta.open("rb") as archivo:
        firmas = PdfFileReader(archivo).embedded_signatures
        assert len(firmas) == 1
        # Sin autoridades raíz: no se valida la confianza del certificado (R15).
        return validate_pdf_signature(firmas[0], ValidationContext(trust_roots=[]))


def test_pdf_firmado(tmp_path):
    estado = _estado_firma(_un_archivo(fabrica.pdf_firmado(tmp_path)))
    assert estado.intact and estado.valid
    assert estado.docmdp_ok
    assert estado.signing_cert.subject.native["common_name"] == fabrica.FIRMANTE_DIGITAL


def test_pdf_modificado_despues_de_firmar(tmp_path):
    estado = _estado_firma(_un_archivo(fabrica.pdf_modificado_despues_de_firmar(tmp_path)))
    # La parte firmada sigue intacta, pero hay cambios posteriores que no permite.
    assert estado.intact
    assert not estado.docmdp_ok


def test_docx(tmp_path):
    ruta = _un_archivo(fabrica.docx(tmp_path))
    with zipfile.ZipFile(ruta) as zip_:
        assert "word/document.xml" in zip_.namelist()
        assert fabrica.OFERENTE in zip_.read("word/document.xml").decode("utf-8")


@pytest.mark.libreoffice
def test_odt(tmp_path):
    ruta = _un_archivo(fabrica.odt(tmp_path))
    with zipfile.ZipFile(ruta) as zip_:
        assert zip_.read("mimetype") == b"application/vnd.oasis.opendocument.text"


@pytest.mark.libreoffice
def test_doc(tmp_path):
    import olefile

    ruta = _un_archivo(fabrica.doc(tmp_path))
    assert olefile.isOleFile(str(ruta))
    with olefile.OleFileIO(str(ruta)) as ole:
        assert ole.exists("WordDocument")


def test_xlsx_ancho(tmp_path):
    from openpyxl import load_workbook

    ruta = _un_archivo(fabrica.xlsx_ancho(tmp_path))
    hoja = load_workbook(ruta).active
    assert hoja.max_column == 40
    assert hoja.max_row == 31


def test_jpg(tmp_path):
    with Image.open(_un_archivo(fabrica.jpg(tmp_path))) as imagen:
        assert imagen.format == "JPEG"


def test_png(tmp_path):
    with Image.open(_un_archivo(fabrica.png(tmp_path))) as imagen:
        assert imagen.format == "PNG"


def test_tiff_tres_paginas(tmp_path):
    with Image.open(_un_archivo(fabrica.tiff_tres_paginas(tmp_path))) as imagen:
        assert imagen.format == "TIFF"
        assert imagen.n_frames == 3


def test_archivos_de_sistema(tmp_path):
    rutas = fabrica.archivos_de_sistema(tmp_path)
    relativas = sorted(r.relative_to(tmp_path).as_posix() for r in rutas)
    assert relativas == [
        ".DS_Store",
        "._carta_presentacion.pdf",
        "__MACOSX/._carta_presentacion.pdf",
        "__MACOSX/anexos/._experiencia.xlsx",
        "imagenes/Thumbs.db",
    ]
    for ruta in rutas:
        if ruta.name.startswith("._"):
            assert ruta.read_bytes().startswith(bytes.fromhex("00051607"))


def test_appledouble_sin_prefijo(tmp_path):
    ruta = _un_archivo(fabrica.appledouble_sin_prefijo(tmp_path))
    assert not ruta.name.startswith("._")
    assert ruta.read_bytes().startswith(bytes.fromhex("00051607"))


def test_extension_falsa(tmp_path):
    ruta = _un_archivo(fabrica.extension_falsa(tmp_path))
    assert ruta.suffix == ".pdf"
    assert ruta.read_bytes().startswith(b"PK")
    with zipfile.ZipFile(ruta) as zip_:
        assert "word/document.xml" in zip_.namelist()


def test_no_soportados(tmp_path):
    rutas = fabrica.no_soportados(tmp_path)
    assert sorted(r.name for r in rutas) == ["notas.txt", "soportes.zip"]
    assert all(r.stat().st_size > 0 for r in rutas)
    assert zipfile.is_zipfile(tmp_path / "soportes.zip")


def test_duplicados(tmp_path):
    original, copia = fabrica.duplicados(tmp_path)
    assert original.parent != copia.parent
    assert original.read_bytes() == copia.read_bytes()
    with pikepdf.open(io.BytesIO(original.read_bytes())) as pdf:
        assert len(pdf.pages) == 2


def test_pdf_anclas(tmp_path):
    ruta = _un_archivo(fabrica.pdf_anclas(tmp_path))
    with pikepdf.open(ruta) as pdf:
        contenido = _texto_contenido(pdf.pages[0])
    assert b"____" in contenido  # línea de firma con guiones bajos
    assert b" re" in contenido  # casillas y celdas
    assert b"Firma del representante legal" in contenido
