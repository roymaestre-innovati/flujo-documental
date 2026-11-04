"""Conversión a PDF: R7 a R10, tiempo máximo y reintento."""

import hashlib
import io
import os
import stat

import pikepdf
import pytest

import fabrica
from normalizacion.conversion import CONFIGURACION_SEGURA, convertir, pdf_reproducible
from normalizacion.errores import CONTRASENA, CONVERSION_FALLIDA, DANADO, NO_SOPORTADO, error_documento
from normalizacion.tipos import detectar


def _convertir_caso(tmp_path, caso, **opciones):
    (ruta,) = fabrica.CASOS[caso](tmp_path)
    return ruta, convertir(ruta, detectar(ruta), **opciones)


def _paginas(datos):
    with pikepdf.open(io.BytesIO(datos), attempt_recovery=False) as pdf:
        return len(pdf.pages)


def _con_error(conversion, codigo):
    assert not conversion.ok
    assert conversion.error == error_documento(codigo)
    assert conversion.datos is None and conversion.anexo is None


# R7: Word ------------------------------------------------------------------------


@pytest.mark.libreoffice
@pytest.mark.parametrize("caso", ["docx", "odt", "doc", "extension_falsa"])
def test_r7_word_a_pdf(tmp_path, caso):
    _, conversion = _convertir_caso(tmp_path, caso)
    assert conversion.ok
    assert _paginas(conversion.datos) >= 1
    assert conversion.anexo is None


@pytest.mark.libreoffice
def test_r7_las_macros_no_se_ejecutan(tmp_path):
    _, conversion = _convertir_caso(tmp_path, "odt_con_macro")
    assert conversion.ok
    assert not (tmp_path / fabrica.MARCA_MACRO).exists()


# R8: imágenes ----------------------------------------------------------------------


@pytest.mark.parametrize(("caso", "paginas"), [("jpg", 1), ("png", 1), ("png_transparente", 1), ("tiff_tres_paginas", 3)])
def test_r8_una_pagina_por_imagen(tmp_path, caso, paginas):
    _, conversion = _convertir_caso(tmp_path, caso)
    assert conversion.ok
    assert _paginas(conversion.datos) == paginas
    assert conversion.anexo is None


def test_r8_el_jpeg_no_se_recomprime(tmp_path):
    ruta, conversion = _convertir_caso(tmp_path, "jpg")
    assert ruta.read_bytes() in conversion.datos


def test_r8_imagen_que_no_abre_es_danada(tmp_path):
    ruta = tmp_path / "foto.jpg"
    ruta.write_bytes(bytes.fromhex("FFD8FFE0") + bytes(200))
    _con_error(convertir(ruta, detectar(ruta)), DANADO)


@pytest.mark.filterwarnings("ignore:Corrupt EXIF data")
def test_r8_tiff_con_un_cuadro_roto_es_danado(tmp_path):
    (ruta,) = fabrica.tiff_tres_paginas(tmp_path)
    datos = ruta.read_bytes()
    ruta.write_bytes(datos[: len(datos) // 2])
    conversion = convertir(ruta, detectar(ruta))
    assert not conversion.ok


# R9: hojas de cálculo --------------------------------------------------------------


@pytest.mark.libreoffice
@pytest.mark.parametrize("caso", ["xlsx_ancho", "xls", "ods"])
def test_r9_hoja_de_calculo_a_pdf_con_anexo(tmp_path, caso):
    ruta, conversion = _convertir_caso(tmp_path, caso)
    assert conversion.ok
    assert conversion.anexo == ruta.read_bytes()
    # 40 columnas no caben en una página: se cortan en varias.
    assert _paginas(conversion.datos) > 1


# R10: el original no se toca ----------------------------------------------------------


@pytest.mark.libreoffice
@pytest.mark.parametrize("caso", ["docx", "xlsx_ancho", "jpg", "png_transparente"])
def test_r10_el_original_no_cambia(tmp_path, caso):
    (ruta,) = fabrica.CASOS[caso](tmp_path)
    antes = hashlib.sha256(ruta.read_bytes()).hexdigest()
    convertir(ruta, detectar(ruta))
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == antes
    assert sorted(p.name for p in tmp_path.iterdir()) == [ruta.name]


# R25: convertir dos veces da lo mismo ---------------------------------------------------


@pytest.mark.libreoffice
@pytest.mark.parametrize("caso", ["docx", "xlsx_ancho", "tiff_tres_paginas", "png_transparente"])
def test_r25_convertir_dos_veces_da_los_mismos_bytes(tmp_path, caso):
    (ruta,) = fabrica.CASOS[caso](tmp_path)
    assert convertir(ruta, detectar(ruta)).datos == convertir(ruta, detectar(ruta)).datos


def test_pdf_reproducible_quita_fechas_e_identificador():
    with pikepdf.open(io.BytesIO(fabrica.pdf_texto_bytes())) as pdf:
        pdf.docinfo["/CreationDate"] = "D:20260101000000Z"
        salida = io.BytesIO()
        pdf.save(salida, static_id=False)
    limpio = pdf_reproducible(salida.getvalue())
    with pikepdf.open(io.BytesIO(limpio)) as pdf:
        assert "/CreationDate" not in pdf.docinfo
    assert pdf_reproducible(limpio) == limpio


# Errores que no son de conversión ---------------------------------------------------------


@pytest.mark.parametrize("caso", ["docx_con_contrasena", "xlsx_con_contrasena"])
def test_office_con_contrasena(tmp_path, caso):
    _, conversion = _convertir_caso(tmp_path, caso)
    _con_error(conversion, CONTRASENA)
    assert conversion.error.detalle.startswith("El archivo pide contraseña")


def test_no_soportado(tmp_path):
    for ruta in fabrica.no_soportados(tmp_path):
        _con_error(convertir(ruta, detectar(ruta)), NO_SOPORTADO)


def test_un_pdf_no_se_convierte(tmp_path):
    (ruta,) = fabrica.pdf_texto(tmp_path)
    with pytest.raises(ValueError):
        convertir(ruta, detectar(ruta))


# LibreOffice: tiempo máximo, reintento y perfil seguro (con un soffice falso) -----------------


def _soffice_falso(carpeta, cuerpo):
    """Script que hace de soffice. Anota cada llamada en `llamadas.txt`."""
    script = carpeta / "soffice"
    lineas = [
        "#!/bin/bash",
        f'echo llamada >> "{carpeta}/llamadas.txt"',
        'for arg in "$@"; do',
        '  case "$prev" in --outdir) SALIDA="$arg";; esac',
        '  case "$arg" in -env:UserInstallation=file://*) PERFIL="${arg#-env:UserInstallation=file://}";; esac',
        '  prev="$arg"',
        "done",
        cuerpo,
    ]
    script.write_text("\n".join(lineas) + "\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def _llamadas(carpeta):
    archivo = carpeta / "llamadas.txt"
    return len(archivo.read_text().splitlines()) if archivo.exists() else 0


@pytest.fixture
def docx_y_falso(tmp_path):
    (ruta,) = fabrica.docx(tmp_path / "entrega")
    falso = tmp_path / "falso"
    falso.mkdir()
    pdf = tmp_path / "bueno.pdf"
    pdf.write_bytes(fabrica.pdf_texto_bytes())
    return ruta, falso, pdf


def test_se_pasa_del_tiempo_y_reintenta_una_vez(docx_y_falso):
    ruta, falso, _ = docx_y_falso
    soffice = _soffice_falso(falso, "sleep 30")
    conversion = convertir(ruta, detectar(ruta), soffice=soffice, tiempo_max_s=0.5, reintentos=1)
    _con_error(conversion, CONVERSION_FALLIDA)
    assert _llamadas(falso) == 2


def test_falla_una_vez_y_el_reintento_funciona(docx_y_falso):
    ruta, falso, pdf = docx_y_falso
    cuerpo = f'if [ "$(wc -l < "{falso}/llamadas.txt")" -lt 2 ]; then exit 1; fi\ncp "{pdf}" "$SALIDA/entrada.pdf"'
    conversion = convertir(ruta, detectar(ruta), soffice=_soffice_falso(falso, cuerpo), tiempo_max_s=10, reintentos=1)
    assert conversion.ok
    assert _paginas(conversion.datos) == 1
    assert _llamadas(falso) == 2


@pytest.mark.parametrize(
    "cuerpo",
    ["exit 0", 'echo "no es un pdf" > "$SALIDA/entrada.pdf"', "exit 77"],
    ids=["sin_salida", "salida_que_no_es_pdf", "codigo_de_error"],
)
def test_salidas_malas_de_libreoffice(docx_y_falso, cuerpo):
    ruta, falso, _ = docx_y_falso
    conversion = convertir(ruta, detectar(ruta), soffice=_soffice_falso(falso, cuerpo), tiempo_max_s=10, reintentos=1)
    _con_error(conversion, CONVERSION_FALLIDA)
    assert _llamadas(falso) == 2


def test_cada_conversion_usa_un_perfil_propio_con_macros_bloqueadas(docx_y_falso):
    ruta, falso, pdf = docx_y_falso
    cuerpo = (
        f'cp "$PERFIL/user/registrymodifications.xcu" "{falso}/perfil-$(wc -l < "{falso}/llamadas.txt").xcu"\n'
        f'echo "$PERFIL" >> "{falso}/perfiles.txt"\n'
        f'echo "$@" >> "{falso}/argumentos.txt"\n'
        f'cp "{pdf}" "$SALIDA/entrada.pdf"'
    )
    soffice = _soffice_falso(falso, cuerpo)
    convertir(ruta, detectar(ruta), soffice=soffice, tiempo_max_s=10, reintentos=0)
    convertir(ruta, detectar(ruta), soffice=soffice, tiempo_max_s=10, reintentos=0)
    perfiles = (falso / "perfiles.txt").read_text().splitlines()
    assert len(set(perfiles)) == 2
    assert not any(os.path.exists(p) for p in perfiles)  # se borran al terminar
    configuracion = (falso / "perfil-1.xcu").read_text()
    assert configuracion == CONFIGURACION_SEGURA
    assert '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value>' in configuracion
    assert '<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value>' in configuracion
    argumentos = (falso / "argumentos.txt").read_text()
    assert "--headless" in argumentos and "--norestore" in argumentos
    assert ruta.name not in argumentos  # el nombre del oferente no va en la línea de comandos


def test_sin_libreoffice_es_un_bug_de_despliegue(docx_y_falso, monkeypatch):
    ruta, _, _ = docx_y_falso
    monkeypatch.setattr("shutil.which", lambda nombre: None)
    with pytest.raises(RuntimeError):
        convertir(ruta, detectar(ruta))
