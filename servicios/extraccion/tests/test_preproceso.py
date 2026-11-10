"""Qué ve el LLM de cada página del segmento (R31 a R34, R36)."""

import io

import pytest
from PIL import Image

from extraccion.entrada import Entrada, preparar
from extraccion.preproceso import preparar_contenido, valores_de_hoja, zona_de_firma

from fabrica import Corrida, pdf_mixto, xlsx


@pytest.fixture(scope="module")
def mixto(tmp_path_factory):
    corrida = Corrida(tmp_path_factory.mktemp("corrida"))
    (documento,) = corrida.normalizar({"mixto.pdf": pdf_mixto()})
    return corrida, documento


def _contenido(mixto, desde=1, hasta=6):
    corrida, documento = mixto
    return preparar_contenido(preparar(corrida.solicitud(documento, desde, hasta), corrida.almacen))


def _abrir(imagen):
    return Image.open(io.BytesIO(imagen.jpeg))


def _oscuros(imagen: Image.Image) -> int:
    return sum(imagen.convert("L").histogram()[:100])


def test_cada_tipo_de_pagina(mixto):
    paginas = _contenido(mixto).paginas
    resumen = [(p.numero, p.tipo, bool(p.texto), p.texto_de_escaner, p.imagen and p.imagen.detalle, len(p.firmas)) for p in paginas]
    assert resumen == [
        (1, "texto", True, False, None, 0),
        (2, "texto", True, False, "high", 1),
        (3, "imagen", False, False, "original", 0),
        (4, "escaneo_con_ocr", True, True, "original", 1),
        (5, "vacia", False, False, None, 0),
        (6, "texto", True, False, "high", 1),
    ]
    assert "seguridad social" in paginas[0].texto


def test_lectura_de_la_salida(mixto):
    assert _contenido(mixto).lectura() == {
        "paginas_con_texto": [1, 2, 4, 6],
        "paginas_solo_imagen": [3],
        "ampliaciones_firma": [2, 4, 6],
    }


def test_solo_las_paginas_del_segmento(mixto):
    contenido = _contenido(mixto, 2, 3)
    assert [p.numero for p in contenido.paginas] == [2, 3]
    assert contenido.lectura() == {"paginas_con_texto": [2], "paginas_solo_imagen": [3], "ampliaciones_firma": [2]}


def test_imagen_de_pagina_a_100_dpi(mixto):
    imagen = _contenido(mixto, 3, 3).paginas[0].imagen
    assert (imagen.ancho, imagen.alto) == (850, 1100)  # carta (612 x 792 pt) a 100 dpi
    assert _abrir(imagen).format == "JPEG"


def test_pagina_girada_sale_como_se_ve(mixto):
    pagina = _contenido(mixto, 6, 6).paginas[0]
    assert (pagina.imagen.ancho, pagina.imagen.alto) == (1100, 850)
    firma = pagina.firmas[0]
    assert firma.alto > firma.ancho  # el recorte también se gira con la página
    assert _oscuros(_abrir(firma)) > 200


def test_firma_ampliada_a_300_dpi_con_la_linea_y_el_renglon_de_arriba(mixto):
    firma = _contenido(mixto, 2, 2).paginas[0].firmas[0]
    x0, y0, x1, y1 = zona_de_firma([72.0, 583.28, 267.71, 608.28], 612, 792)
    assert (x0, y1) == (36.0, 622.28)
    assert y0 == pytest.approx(583.28 - 42)
    assert firma.ancho == pytest.approx((x1 - x0) * 300 / 72, abs=2)
    assert firma.alto == pytest.approx((y1 - y0) * 300 / 72, abs=2)
    assert _oscuros(_abrir(firma)) > 200  # la línea y el rótulo quedaron adentro
    arriba = _abrir(firma).crop((0, 0, firma.ancho, int(firma.alto * 0.3)))
    assert _oscuros(arriba) == 0  # sobre la línea no hay trazo: la firma está vacía


def test_zona_de_firma_no_sale_de_la_pagina():
    assert zona_de_firma([5, 10, 600, 790], 612, 792) == (0.0, 0.0, 612, 792)


def test_hoja_de_calculo_con_sus_valores():
    texto = valores_de_hoja(xlsx())
    assert texto.splitlines()[:3] == ["Hoja: Experiencia", "Consecutivo\tContratante\tValor", "1\tContrato 1\t1000"]
    assert "Hoja: Totales\nTotal" in texto  # la fórmula sin valor guardado no se calcula


def _entrada_con_anexos(mixto, *anexos):
    corrida, documento = mixto
    base = preparar(corrida.solicitud(documento, 5, 5), corrida.almacen)
    return Entrada(solicitud=base.solicitud, lectura=base.lectura, pdf=base.pdf, anexos=anexos)


def test_anexo_en_el_contenido(mixto):
    contenido = preparar_contenido(_entrada_con_anexos(mixto, xlsx()))
    (anexo,) = contenido.anexos
    assert anexo.numero == 1 and "Contrato 3" in anexo.texto and not anexo.recortado
    assert contenido.alertas == ()


def test_anexo_muy_grande_se_recorta_con_alerta(mixto):
    contenido = preparar_contenido(_entrada_con_anexos(mixto, xlsx(filas=5000, texto="Contrato largo")))
    (anexo,) = contenido.anexos
    assert anexo.recortado and len(anexo.texto) == 60000
    assert [a["codigo"] for a in contenido.alertas] == ["ANEXO_RECORTADO"]


def test_anexo_que_no_se_puede_leer(mixto):
    contenido = preparar_contenido(_entrada_con_anexos(mixto, b"\xd0\xcf\x11\xe0 xls viejo"))
    assert contenido.anexos[0].texto is None
    assert [a["codigo"] for a in contenido.alertas] == ["ANEXO_NO_LEIDO"]


def test_varios_hilos_a_la_vez(mixto):
    # pdfium no admite dos hilos a la vez: sin el candado, esto rompe el proceso.
    from concurrent.futures import ThreadPoolExecutor

    corrida, documento = mixto
    entrada = preparar(corrida.solicitud(documento, 1, 6), corrida.almacen)
    with ThreadPoolExecutor(max_workers=8) as grupo:
        contenidos = list(grupo.map(lambda _: preparar_contenido(entrada), range(16)))
    primero = contenidos[0]
    assert all(c.lectura() == primero.lectura() for c in contenidos)
    assert all([p.imagen and p.imagen.jpeg for p in c.paginas] == [p.imagen and p.imagen.jpeg for p in primero.paginas]
               for c in contenidos)
