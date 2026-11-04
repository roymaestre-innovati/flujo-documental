"""Anclas (zonas visuales): R21."""

import io

import pikepdf
import pytest
from reportlab.lib.utils import ImageReader

import fabrica
from normalizacion.anclas import (
    CASILLA,
    LINEA_FIRMA,
    TABLA_SI_NO,
    Palabra,
    casillas,
    distancia,
    es_casilla,
    frases,
    lineas_de_firma,
    normalizar,
    tablas_si_no,
)
from normalizacion.lectura import IMAGEN, VACIA, leer
from normalizacion.parametros import PARAMETROS

from contrato import validador


def _anclas(datos, tipo=None):
    lectura = leer(datos, "OF-002-000000000000", [], "file:///palabras.json").lectura
    validador("lectura").validate(lectura)
    anclas = [a for pagina in lectura["paginas"] for a in pagina["anclas"]]
    return [a for a in anclas if tipo is None or a["tipo"] == tipo]


def _renglon(texto, x=72.0, y=100.0, ancho_letra=6.0, alto=12.0):
    """Palabras de un renglón, cada letra de `ancho_letra` puntos, separadas por 4."""
    palabras = []
    for palabra in texto.split():
        ancho = ancho_letra * len(palabra)
        palabras.append(Palabra(palabra, (x, y, x + ancho, y + alto)))
        x += ancho + 4.0
    return palabras


# Utilidades ---------------------------------------------------------------------------


def test_normalizar_sin_mayusculas_ni_tildes():
    assert normalizar("FÍRMA Sí") == "firma si"


def test_distancia_entre_cajas():
    assert distancia((0, 0, 10, 10), (5, 5, 20, 20)) == 0
    assert distancia((0, 0, 10, 10), (13, 0, 20, 10)) == 3
    assert distancia((0, 0, 10, 10), (13, 14, 20, 20)) == 5


def test_frases_cortan_en_huecos_grandes():
    palabras = _renglon("Firma del representante") + _renglon("Firma del revisor", x=330)
    assert [f.texto for f in frases(palabras, PARAMETROS)] == ["Firma del representante", "Firma del revisor"]


# Línea de firma ----------------------------------------------------------------------------


def test_linea_dibujada_con_rotulo_debajo():
    linea = (72.0, 90.0, 272.0, 90.5)
    (ancla,) = lineas_de_firma(_renglon("Representante legal", y=95), [linea])
    assert ancla["tipo"] == LINEA_FIRMA
    assert ancla["texto"] == "Representante legal"
    assert ancla["caja"] == [72.0, 90.0, 272.0, 107.0]


@pytest.mark.parametrize("clave", ["Firma", "FIRMA", "firmado por", "Representante", "Revisor fiscal", "Contador público"])
def test_rotulos_que_cuentan(clave):
    assert lineas_de_firma(_renglon(clave, y=95), [(72.0, 90.0, 272.0, 90.5)])


def test_linea_sin_rotulo_no_es_ancla():
    assert lineas_de_firma(_renglon("Fecha de expedición", y=95), [(72.0, 90.0, 272.0, 90.5)]) == []


def test_rotulo_a_60_puntos_o_mas_no_cuenta():
    linea = (72.0, 90.0, 272.0, 90.0)
    assert lineas_de_firma(_renglon("Revisor fiscal", y=149.0), [linea])
    assert lineas_de_firma(_renglon("Revisor fiscal", y=150.0), [linea]) == []


def test_ocho_guiones_bajos_cuentan_siete_no():
    rotulo = _renglon("Representante legal", y=115)
    ocho = [Palabra("_" * 8, (72.0, 100.0, 120.0, 112.0))]
    siete = [Palabra("_" * 7, (72.0, 100.0, 114.0, 112.0))]
    (ancla,) = lineas_de_firma(ocho + rotulo, [])
    assert ancla["texto"] == "Representante legal"
    assert lineas_de_firma(siete + rotulo, []) == []


def test_frase_que_empieza_por_firma_sin_linea():
    (ancla,) = lineas_de_firma(_renglon("Firma: Revisor fiscal"), [])
    assert ancla["texto"] == "Firma: Revisor fiscal"


def test_firma_en_medio_de_un_parrafo_no_es_ancla():
    assert lineas_de_firma(_renglon("La firma del contrato se hará en Bogotá"), []) == []


def test_el_rotulo_de_una_linea_no_se_repite():
    palabras = _renglon("Firma del representante legal", y=95)
    (ancla,) = lineas_de_firma(palabras, [(72.0, 90.0, 272.0, 90.5)])
    assert ancla["caja"][1] == 90.0


def test_cada_linea_toma_su_rotulo_mas_cercano():
    palabras = _renglon("Firma del representante", y=95) + _renglon("Firma del revisor", x=330, y=95)
    anclas = lineas_de_firma(palabras, [(72.0, 90.0, 272.0, 90.5), (330.0, 90.0, 530.0, 90.5)])
    assert [a["texto"] for a in anclas] == ["Firma del representante", "Firma del revisor"]


# Casilla ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ancho", "alto", "es"),
    [(5, 5, False), (6, 6, True), (10, 10, True), (20, 20, True), (21, 21, False), (10, 12, True), (10, 13, False)],
)
def test_casilla_por_tamano_y_forma(ancho, alto, es):
    assert es_casilla((100.0, 100.0, 100.0 + ancho, 100.0 + alto)) is es


def test_casilla_repetida_cuenta_una_vez():
    caja = (100.0, 100.0, 110.0, 110.0)
    assert casillas([caja, caja, (100.001, 100.0, 110.0, 110.0)]) == [caja]


# Tabla SI/NO -------------------------------------------------------------------------------------


def test_si_no_con_casilla_cerca():
    palabras = _renglon("¿Acepta las condiciones? SI NO")
    fin = palabras[-1].caja[2]
    (ancla,) = tablas_si_no(palabras, [(fin + 5, 100.0, fin + 15, 110.0)])
    assert ancla["tipo"] == TABLA_SI_NO
    assert ancla["texto"] == "¿Acepta las condiciones? SI NO"


@pytest.mark.parametrize("texto", ["Sí No", "si no", "SÍ NO", "( SI ) ( NO )"])
def test_si_no_sin_mayusculas_ni_tildes(texto):
    assert tablas_si_no(_renglon(texto), [(72.0, 115.0, 400.0, 135.0)])


def test_si_no_sin_casilla_ni_celda_no_es_ancla():
    assert tablas_si_no(_renglon("Si el oferente no presenta el documento"), []) == []


def test_si_no_con_la_celda_lejos_no_es_ancla():
    assert tablas_si_no(_renglon("SI NO"), [(72.0, 140.0, 400.0, 160.0)]) == []


@pytest.mark.parametrize("texto", ["SI", "NO", "SINO", "SIN NOTA"])
def test_hacen_falta_las_dos_palabras_sueltas(texto):
    assert tablas_si_no(_renglon(texto), [(72.0, 100.0, 400.0, 120.0)]) == []


# En un PDF ---------------------------------------------------------------------------------------


def test_formulario_de_la_fabrica(tmp_path):
    (ruta,) = fabrica.pdf_anclas(tmp_path)
    anclas = _anclas(ruta.read_bytes())
    firmas = [a["texto"] for a in anclas if a["tipo"] == LINEA_FIRMA]
    assert firmas == ["Firma del representante legal", "Firma del revisor fiscal"]
    assert len([a for a in anclas if a["tipo"] == CASILLA]) == 4
    tablas = [a["texto"] for a in anclas if a["tipo"] == TABLA_SI_NO]
    assert tablas == [
        "SI NO",
        "¿Acepta las condiciones del proceso? SI NO",
        "¿Tiene inhabilidades o incompatibilidades? Sí No",
    ]
    # En orden de arriba abajo.
    assert [a["caja"][1] for a in anclas] == sorted(a["caja"][1] for a in anclas)


def test_la_linea_de_firma_cubre_linea_y_rotulo(tmp_path):
    (ruta,) = fabrica.pdf_anclas(tmp_path)
    representante, revisor = _anclas(ruta.read_bytes(), LINEA_FIRMA)
    # Guiones bajos (arriba) y rótulo (abajo), en la mitad izquierda.
    assert representante["caja"][0] == pytest.approx(72, abs=1) and representante["caja"][2] < 300
    # Línea dibujada de 330 a 530 y su rótulo.
    assert revisor["caja"][0] == pytest.approx(330, abs=1) and revisor["caja"][2] == pytest.approx(530, abs=1)
    assert revisor["caja"][3] - revisor["caja"][1] > 10


def test_pagina_rotada_da_las_mismas_anclas(tmp_path):
    (ruta,) = fabrica.pdf_anclas(tmp_path)
    datos = ruta.read_bytes()
    with pikepdf.open(io.BytesIO(datos)) as pdf:
        pdf.pages[0].obj.Rotate = 90
        salida = io.BytesIO()
        pdf.save(salida)
    assert _anclas(salida.getvalue()) == _anclas(datos)


def _pagina(rectangulos=(), texto="", imagen=False, rectangulo_delgado=None):
    salida, lienzo = fabrica._lienzo()
    if imagen:
        lienzo.drawImage(ImageReader(fabrica._imagen_escaneo(200, 200)), 0, 0, width=fabrica.ANCHO, height=fabrica.ALTO)
    for x, y, ancho, alto in rectangulos:
        lienzo.rect(x, y, ancho, alto)
    if rectangulo_delgado:
        lienzo.rect(*rectangulo_delgado, fill=1)
    if texto:
        lienzo.setFont("Helvetica", 11)
        lienzo.drawString(72, 186, texto)
    lienzo.showPage()
    lienzo.save()
    return salida.getvalue()


def test_pagina_imagen_no_tiene_anclas():
    datos = _pagina(rectangulos=[(100, 100, 10, 10)], imagen=True)
    lectura = leer(datos, "X", [], "file:///p.json").lectura
    assert lectura["paginas"][0]["tipo"] == IMAGEN
    assert lectura["paginas"][0]["anclas"] == []


def test_pagina_vacia_puede_tener_casillas():
    datos = _pagina(rectangulos=[(100, 100, 10, 10), (130, 100, 10, 10)])
    lectura = leer(datos, "X", [], "file:///p.json").lectura
    assert lectura["paginas"][0]["tipo"] == VACIA
    assert [a["tipo"] for a in lectura["paginas"][0]["anclas"]] == [CASILLA, CASILLA]


def test_rectangulo_delgado_es_una_linea_de_firma():
    datos = _pagina(texto="Representante legal", rectangulo_delgado=(72, 200, 200, 0.8))
    (ancla,) = _anclas(datos, LINEA_FIRMA)
    assert ancla["texto"] == "Representante legal"
    assert _anclas(datos, CASILLA) == []


def test_pagina_de_texto_sin_anclas(tmp_path):
    (ruta,) = fabrica.pdf_texto(tmp_path)
    assert _anclas(ruta.read_bytes()) == []
