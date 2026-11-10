"""Lectura por página: R14, R18 a R20, R22 y R23."""

import hashlib
import io
import logging

import pikepdf
import pytest
from reportlab.lib.utils import ImageReader

import fabrica
from normalizacion import lectura as modulo_lectura
from normalizacion.conversion import convertir
from normalizacion.firma import leer_firmas
from normalizacion.lectura import (
    ESCANEO_CON_OCR,
    IMAGEN,
    TEXTO,
    VACIA,
    cobertura,
    contar_caracteres,
    leer,
    tipo_de_pagina,
)
from normalizacion.parametros import PARAMETROS
from normalizacion.tipos import detectar

from contrato import validador

URI_PALABRAS = "file:///salida/SR0000000001/OF-002/palabras/OF-002-000000000000.json"


def _leer(datos, firmas=()):
    return leer(datos, "OF-002-000000000000", list(firmas), URI_PALABRAS)


def _leer_caso(tmp_path, caso):
    (ruta,) = fabrica.CASOS[caso](tmp_path)[:1]
    return _leer(ruta.read_bytes())


def _valida(resultado):
    validador("lectura").validate(resultado.lectura)
    validador("palabras").validate(resultado.palabras)
    return resultado


def _pdf(texto: str = "", imagen: tuple[float, float, float, float] | None = None, invisible: bool = False) -> bytes:
    """Una página con `texto` en una línea y, si se pide, una imagen en la caja
    (x, y, ancho, alto) en puntos, con el origen abajo a la izquierda."""
    salida, lienzo = fabrica._lienzo()
    if imagen:
        x, y, ancho, alto = imagen
        lienzo.drawImage(ImageReader(fabrica._imagen_escaneo(200, 200)), x, y, width=ancho, height=alto)
    if texto:
        objeto = lienzo.beginText(72, 700)
        objeto.setFont("Helvetica", 9)
        objeto.setTextRenderMode(3 if invisible else 0)
        objeto.textLine(texto)
        lienzo.drawText(objeto)
    lienzo.showPage()
    lienzo.save()
    return salida.getvalue()


# R19 y R20: tipo de página y origen del texto -------------------------------------


@pytest.mark.parametrize(
    ("caso", "tipo", "origen"),
    [
        ("pdf_texto", TEXTO, "nativo"),
        ("pdf_escaneo_con_ocr", ESCANEO_CON_OCR, "ocr_escaner"),
        ("pdf_escaneo_sin_texto", IMAGEN, None),
        ("pdf_vacio", VACIA, None),
        ("pdf_solo_restricciones", TEXTO, "nativo"),
        ("pdf_anclas", TEXTO, "nativo"),
        ("pdf_firmado", TEXTO, "nativo"),
    ],
)
def test_r19_r20_tipo_y_origen(tmp_path, caso, tipo, origen):
    resultado = _valida(_leer_caso(tmp_path, caso))
    (pagina,) = resultado.lectura["paginas"]
    assert pagina["tipo"] == tipo
    assert pagina["origen_texto"] == origen


def test_r19_escaneo_con_ocr_trae_el_texto_invisible(tmp_path):
    (pagina,) = _leer_caso(tmp_path, "pdf_escaneo_con_ocr").lectura["paginas"]
    assert fabrica.OFERENTE in pagina["texto"]
    assert pagina["cobertura_imagen"] == 1.0


@pytest.mark.parametrize(
    ("caracteres", "cobertura_imagen", "tipo"),
    [
        (0, 0.0, VACIA),
        (19, 0.0, VACIA),
        (20, 0.0, TEXTO),
        (19, 0.79, VACIA),  # foto chica en página casi blanca: vacia en v0 (plan)
        (19, 0.80, IMAGEN),
        (20, 0.80, ESCANEO_CON_OCR),
        (20, 0.79, TEXTO),
        (5000, 1.0, ESCANEO_CON_OCR),
    ],
)
def test_r19_reglas_y_umbrales(caracteres, cobertura_imagen, tipo):
    assert tipo_de_pagina(caracteres, cobertura_imagen) == tipo
    assert PARAMETROS.min_caracteres_texto == 20 and PARAMETROS.cobertura_escaneo == 0.80


def test_r19_umbral_de_caracteres_en_un_pdf():
    diecinueve = _leer(_pdf("x" * 19)).lectura["paginas"][0]
    veinte = _leer(_pdf("x" * 20)).lectura["paginas"][0]
    assert (diecinueve["caracteres"], diecinueve["tipo"]) == (19, VACIA)
    assert (veinte["caracteres"], veinte["tipo"]) == (20, TEXTO)


def test_r19_foto_chica_en_pagina_con_texto():
    pagina = _leer(_pdf(fabrica.PARRAFO, imagen=(72, 72, 150, 150))).lectura["paginas"][0]
    assert pagina["tipo"] == TEXTO
    assert 0 < pagina["cobertura_imagen"] < 0.1


def test_r19_texto_invisible_sobre_media_pagina_es_texto():
    """Imagen sobre la mitad de la página: no llega al 80 %."""
    pagina = _leer(_pdf(fabrica.PARRAFO, imagen=(0, 0, fabrica.ANCHO, fabrica.ALTO / 2), invisible=True)).lectura[
        "paginas"
    ][0]
    assert pagina["cobertura_imagen"] == pytest.approx(0.5, abs=0.01)
    assert pagina["tipo"] == TEXTO


# Cobertura ------------------------------------------------------------------------


def test_cobertura_grilla():
    pagina = (0.0, 0.0, 100.0, 100.0)
    assert cobertura([], pagina, 200) == 0.0
    assert cobertura([(0, 0, 100, 100)], pagina, 200) == 1.0
    assert cobertura([(0, 0, 50, 100)], pagina, 200) == 0.5
    # La unión no cuenta dos veces lo que se superpone.
    assert cobertura([(0, 0, 50, 100), (25, 0, 75, 100)], pagina, 200) == 0.75
    # Lo que sale de la página se recorta.
    assert cobertura([(-50, -50, 50, 150)], pagina, 200) == 0.5
    assert cobertura([(200, 200, 300, 300)], pagina, 200) == 0.0
    # Cajas al revés se ordenan.
    assert cobertura([(50, 100, 0, 0)], pagina, 200) == 0.5


def test_cobertura_no_depende_del_orden():
    cajas = [(0, 0, 30, 40), (10, 10, 90, 20), (50, 60, 100, 100)]
    pagina = (0.0, 0.0, 100.0, 100.0)
    assert cobertura(cajas, pagina, 200) == cobertura(list(reversed(cajas)), pagina, 200)


def test_caracteres_sin_espacios():
    assert contar_caracteres("  A b\nc\t ") == 3
    assert contar_caracteres("") == 0


# R18: lo que va por página --------------------------------------------------------


def test_r18_campos_de_la_lectura(tmp_path):
    (ruta,) = fabrica.pdf_firmado(tmp_path)
    datos = ruta.read_bytes()
    firmas = leer_firmas(datos)
    resultado = _valida(_leer(datos, firmas))
    lectura = resultado.lectura
    assert lectura["contrato"] == "modulo3-normalizacion/0.2"
    assert lectura["hash_pdf"] == hashlib.sha256(datos).hexdigest()
    assert lectura["version_normalizador"] == "0.3.0" and lectura["version_parametros"] == "2"
    assert lectura["firma_digital"] == [firma.como_dict() for firma in firmas]
    assert lectura["palabras"] == URI_PALABRAS
    (pagina,) = lectura["paginas"]
    assert pagina["pagina"] == 1
    assert fabrica.OFERENTE in pagina["texto"]
    assert pagina["caracteres"] == contar_caracteres(pagina["texto"])
    assert pagina["rotacion"] == 0
    assert pagina["anclas"] == []


def test_r18_paginas_numeradas_sobre_el_documento_completo():
    resultado = _valida(_leer(fabrica.pdf_texto_bytes(paginas=3)))
    assert [p["pagina"] for p in resultado.lectura["paginas"]] == [1, 2, 3]
    assert [p["pagina"] for p in resultado.palabras["paginas"]] == [1, 2, 3]
    assert "página 2" in resultado.lectura["paginas"][1]["texto"]


# Rotación -------------------------------------------------------------------------


def test_rotacion_texto_y_cajas_sobre_la_pagina_sin_rotar(tmp_path):
    rotada = _valida(_leer_caso(tmp_path, "pdf_rotado"))
    derecha = _leer(fabrica.pdf_texto_bytes())
    (pagina,) = rotada.lectura["paginas"]
    assert pagina["rotacion"] == 90
    assert pagina["texto"] == derecha.lectura["paginas"][0]["texto"]
    assert pagina["texto"].startswith("CARTA DE PRESENTACIÓN")
    assert rotada.palabras == derecha.palabras


def test_rotacion_heredada_del_arbol_de_paginas():
    with pikepdf.open(io.BytesIO(fabrica.pdf_texto_bytes(paginas=2))) as pdf:
        pdf.Root.Pages.Rotate = 270
        if "/Rotate" in pdf.pages[0].obj:
            del pdf.pages[0].obj.Rotate  # reportlab pone /Rotate 0 en cada página
        pdf.pages[1].obj.Rotate = -90  # equivale a 270
        salida = io.BytesIO()
        pdf.save(salida)
    paginas = _leer(salida.getvalue()).lectura["paginas"]
    assert [p["rotacion"] for p in paginas] == [270, 270]
    assert all(p["texto"].startswith("CARTA") for p in paginas)


# R14: páginas sin texto -----------------------------------------------------------------


def test_r14_paginas_sin_texto():
    with pikepdf.open(io.BytesIO(fabrica.pdf_texto_bytes(paginas=1))) as pdf:
        for extra in (_pdf(), _pdf("x" * 5), fabrica._pdf_escaneo_bytes(con_texto=False)):
            with pikepdf.open(io.BytesIO(extra)) as otra:
                pdf.pages.append(otra.pages[0])
        salida = io.BytesIO()
        pdf.save(salida)
    resultado = _leer(salida.getvalue())
    tipos = [p["tipo"] for p in resultado.lectura["paginas"]]
    assert tipos == [TEXTO, VACIA, VACIA, IMAGEN]
    # La página con 5 caracteres es vacia, pero tiene texto: no cuenta como sin texto.
    assert resultado.paginas_sin_texto == [2, 4]


# R22: palabras aparte ---------------------------------------------------------------------


def test_r22_palabras_con_su_caja(tmp_path):
    resultado = _valida(_leer_caso(tmp_path, "pdf_texto"))
    palabras = resultado.palabras["paginas"][0]["palabras"]
    assert palabras[0]["t"] == "CARTA"
    x0, y0, x1, y1 = palabras[0]["caja"]
    # Origen arriba a la izquierda: el título está cerca del borde superior.
    assert x0 == pytest.approx(72, abs=0.5) and y0 < 60 and x1 > x0 and y1 > y0
    assert all(round(v, 2) == v for p in palabras for v in p["caja"])
    assert "palabras" not in resultado.lectura["paginas"][0]


def test_r22_paginas_sin_palabras_estan_igual(tmp_path):
    resultado = _valida(_leer_caso(tmp_path, "pdf_escaneo_sin_texto"))
    assert resultado.palabras["paginas"] == [{"pagina": 1, "palabras": []}]


# R23: determinismo --------------------------------------------------------------------------


@pytest.mark.parametrize("caso", ["pdf_texto", "pdf_escaneo_con_ocr", "pdf_rotado", "pdf_anclas"])
def test_r23_leer_dos_veces_da_lo_mismo(tmp_path, caso):
    (ruta,) = fabrica.CASOS[caso](tmp_path)
    datos = ruta.read_bytes()
    assert _leer(datos) == _leer(datos)


# Documentos convertidos ------------------------------------------------------------------------


@pytest.mark.parametrize(("caso", "tipo"), [("jpg", IMAGEN), ("tiff_tres_paginas", IMAGEN), ("png_transparente", IMAGEN)])
def test_imagenes_convertidas(tmp_path, caso, tipo):
    (ruta,) = fabrica.CASOS[caso](tmp_path)
    conversion = convertir(ruta, detectar(ruta))
    resultado = _valida(_leer(conversion.datos))
    assert all(p["tipo"] == tipo and p["cobertura_imagen"] == 1.0 for p in resultado.lectura["paginas"])


@pytest.mark.libreoffice
def test_word_convertido(tmp_path):
    (ruta,) = fabrica.docx(tmp_path)
    resultado = _valida(_leer(convertir(ruta, detectar(ruta)).datos))
    assert resultado.lectura["paginas"][0]["tipo"] == TEXTO
    assert fabrica.OFERENTE in resultado.lectura["paginas"][0]["texto"]


# Páginas que no se pueden leer (decisión del usuario) -------------------------------------------


def test_una_pagina_que_falla_queda_vacia_y_las_demas_se_leen(monkeypatch, caplog):
    original = modulo_lectura._leer_pagina

    def falla_en_la_segunda(pagina, numero, rotacion, parametros):
        if numero == 2:
            raise ValueError("objeto roto")
        return original(pagina, numero, rotacion, parametros)

    monkeypatch.setattr(modulo_lectura, "_leer_pagina", falla_en_la_segunda)
    with caplog.at_level(logging.WARNING, logger="normalizacion.lectura"):
        resultado = _valida(_leer(fabrica.pdf_texto_bytes(paginas=3)))
    tipos = [p["tipo"] for p in resultado.lectura["paginas"]]
    assert tipos == [TEXTO, VACIA, TEXTO]
    assert resultado.lectura["paginas"][1]["texto"] == ""
    assert resultado.palabras["paginas"][1] == {"pagina": 2, "palabras": []}
    assert "Página 2 sin leer" in caplog.text
    assert fabrica.OFERENTE not in caplog.text


def test_si_pdfplumber_no_abre_todas_quedan_vacias(monkeypatch, caplog):
    def no_abre(*argumentos, **opciones):
        raise ValueError("no abre")

    monkeypatch.setattr(modulo_lectura.pdfplumber, "open", no_abre)
    with caplog.at_level(logging.WARNING, logger="normalizacion.lectura"):
        resultado = _valida(_leer(fabrica.pdf_texto_bytes(paginas=2)))
    assert [p["tipo"] for p in resultado.lectura["paginas"]] == [VACIA, VACIA]
    assert "Documento sin leer" in caplog.text


# Cajas fuera de la página ---------------------------------------------------------------


def test_las_cajas_se_recortan_al_borde_de_la_pagina():
    """Texto que se sale de la página (como una celda ancha de un Excel convertido):
    el contrato pide cajas desde 0."""
    salida, lienzo = fabrica._lienzo()
    lienzo.setFont("Helvetica", 11)
    lienzo.drawString(-20, 700, "Recortada adentro")  # empieza fuera, termina adentro
    lienzo.drawString(-300, 650, "Afuera")  # entera fuera de la página
    lienzo.drawString(560, 600, "Derecha recortada")  # se sale por la derecha
    lienzo.rect(-5, 100, 10, 10)  # casilla que se sale por la izquierda
    lienzo.showPage()
    lienzo.save()
    resultado = _valida(_leer(salida.getvalue()))
    palabras = {p["t"]: p["caja"] for p in resultado.palabras["paginas"][0]["palabras"]}
    assert "Afuera" not in palabras
    assert palabras["Recortada"][0] == 0.0
    assert palabras["recortada"][2] == fabrica.ANCHO
    for ancla in resultado.lectura["paginas"][0]["anclas"]:
        assert ancla["caja"][0] >= 0


# --- Páginas sin texto ni imagen grande (0.3.0) ---

def _pdf_vectores(trazos: int) -> bytes:
    """Una página sin texto ni imágenes, con `trazos` renglones dibujados como vectores (como un texto en curvas)."""
    salida, lienzo = fabrica._lienzo()
    for n in range(trazos):
        y = 720 - n * 14
        camino = lienzo.beginPath()
        camino.moveTo(72, y)
        for x in range(72, 520, 6):
            camino.curveTo(x + 1, y + 5, x + 3, y - 5, x + 6, y)
        lienzo.setLineWidth(2.5)
        lienzo.drawPath(camino, stroke=1, fill=0)
    lienzo.showPage()
    lienzo.save()
    return salida.getvalue()


def test_pagina_dibujada_con_vectores_es_imagen():
    resultado = _leer(_pdf_vectores(40))
    [pagina] = resultado.lectura["paginas"]
    assert pagina["caracteres"] == 0 and pagina["cobertura_imagen"] == 0
    assert pagina["tipo"] == "imagen" and pagina["origen_texto"] is None and pagina["anclas"] == []
    _valida(resultado)


def test_pagina_con_una_marca_minima_sigue_vacia():
    [pagina] = _leer(_pdf_vectores(1)).lectura["paginas"]
    assert pagina["tipo"] == "vacia"


def test_pagina_en_blanco_sigue_vacia():
    salida, lienzo = fabrica._lienzo()
    lienzo.showPage()
    lienzo.save()
    [pagina] = _leer(salida.getvalue()).lectura["paginas"]
    assert pagina["tipo"] == "vacia"


def test_fraccion_con_tinta_crece_con_el_dibujo():
    import pypdfium2

    def tinta(datos):
        pdf = pypdfium2.PdfDocument(datos)
        try:
            return modulo_lectura.fraccion_con_tinta(pdf[0])
        finally:
            pdf.close()

    assert tinta(_pdf_vectores(1)) < PARAMETROS.tinta_min_imagen <= tinta(_pdf_vectores(40))
