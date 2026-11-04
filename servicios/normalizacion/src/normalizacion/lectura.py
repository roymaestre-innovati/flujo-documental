"""Lectura por página de un PDF normalizado (R14, R18 a R20, R22 y R23).

Por página: tipo, texto, origen del texto, caracteres, cobertura de imagen,
rotación y anclas. Las palabras con su posición van en un archivo aparte.

Es determinista: el mismo PDF con los mismos parámetros da siempre la misma
lectura. No hay LLM ni OCR propio.

**Rotación.** pdfplumber devuelve las coordenadas ya giradas según `/Rotate`, y
el texto de una página girada sale con una palabra por línea. El contrato pide
las cajas sobre la página sin rotar, así que se lee una copia interna del PDF con
`/Rotate` en 0. La rotación que va en la lectura es la del PDF normalizado.
"""

import hashlib
import io
import logging
import math
from dataclasses import dataclass

import pdfplumber
import pikepdf

from . import CONTRATO, VERSION, anclas
from .firma import FirmaDigital
from .parametros import PARAMETROS, Parametros

registro = logging.getLogger(__name__)

TEXTO = "texto"
ESCANEO_CON_OCR = "escaneo_con_ocr"
IMAGEN = "imagen"
VACIA = "vacia"

ORIGEN_POR_TIPO = {TEXTO: "nativo", ESCANEO_CON_OCR: "ocr_escaner", IMAGEN: None, VACIA: None}

DECIMALES_CAJA = 2


@dataclass(frozen=True)
class Lectura:
    lectura: dict
    """Cumple lectura.schema.json."""
    palabras: dict
    """Cumple palabras.schema.json."""

    @property
    def paginas_sin_texto(self) -> list[int]:
        """Páginas con 0 caracteres (R14). No es lo mismo que las de tipo imagen."""
        return [pagina["pagina"] for pagina in self.lectura["paginas"] if pagina["caracteres"] == 0]


# ---------------------------------------------------------------------------
# Reglas


def contar_caracteres(texto: str) -> int:
    """Caracteres sin contar espacios en blanco."""
    return sum(1 for caracter in texto if not caracter.isspace())


def tipo_de_pagina(caracteres: int, cobertura_imagen: float, parametros: Parametros = PARAMETROS) -> str:
    """Reglas del plan, en orden (R19)."""
    con_texto = caracteres >= parametros.min_caracteres_texto
    escaneada = cobertura_imagen >= parametros.cobertura_escaneo
    if not con_texto:
        return IMAGEN if escaneada else VACIA
    return ESCANEO_CON_OCR if escaneada else TEXTO


def cobertura(cajas: list[tuple[float, float, float, float]], pagina: tuple[float, float, float, float], celdas: int) -> float:
    """Fracción de la página cubierta por la unión de las cajas.

    La página se divide en una grilla fija de `celdas` × `celdas`. Una celda cuenta
    como cubierta si su centro cae dentro de alguna caja, ya recortada al borde de
    la página. Es determinista y no depende del orden de las cajas.
    """
    x0p, y0p, x1p, y1p = pagina
    ancho, alto = x1p - x0p, y1p - y0p
    if ancho <= 0 or alto <= 0 or not cajas:
        return 0.0
    cubiertas = bytearray(celdas * celdas)
    for x0, y0, x1, y1 in cajas:
        x0, x1 = max(min(x0, x1), x0p), min(max(x0, x1), x1p)
        y0, y1 = max(min(y0, y1), y0p), min(max(y0, y1), y1p)
        if x1 <= x0 or y1 <= y0:
            continue
        # Columnas y filas cuyo centro (i + 0.5) / celdas cae dentro de la caja.
        columnas = _indices(x0 - x0p, x1 - x0p, ancho, celdas)
        filas = _indices(y0 - y0p, y1 - y0p, alto, celdas)
        for fila in filas:
            base = fila * celdas
            for columna in columnas:
                cubiertas[base + columna] = 1
    return sum(cubiertas) / (celdas * celdas)


def _indices(desde: float, hasta: float, largo: float, celdas: int) -> range:
    primero = max(0, math.ceil(desde / largo * celdas - 0.5))
    ultimo = min(celdas - 1, math.floor(hasta / largo * celdas - 0.5))
    return range(primero, ultimo + 1)


def _rotacion(valor) -> int:
    try:
        grados = int(valor) % 360
    except (TypeError, ValueError):
        return 0
    return grados if grados in (0, 90, 180, 270) else 0


# ---------------------------------------------------------------------------
# Lectura


def _sin_rotacion(datos: bytes) -> tuple[bytes, list[int]]:
    """Copia interna con `/Rotate` en 0 en todas las páginas, y la rotación original
    de cada una (la de la página o la heredada de su padre)."""
    with pikepdf.open(io.BytesIO(datos)) as pdf:
        rotaciones = []
        for pagina in pdf.pages:
            rotaciones.append(_rotacion(_heredado(pagina.obj, "/Rotate", 0)))
        if not any(rotaciones):
            return datos, rotaciones
        for pagina in pdf.pages:
            pagina.obj.Rotate = 0
        salida = io.BytesIO()
        pdf.save(salida)
    return salida.getvalue(), rotaciones


def _heredado(objeto, clave, defecto):
    vistos = set()
    while isinstance(objeto, pikepdf.Dictionary):
        if clave in objeto:
            return objeto[clave]
        if objeto.is_indirect:
            if objeto.objgen in vistos:
                break
            vistos.add(objeto.objgen)
        objeto = objeto.get("/Parent")
    return defecto


def _caja(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    return [round(float(v), DECIMALES_CAJA) for v in (x0, y0, x1, y1)]


def _pagina_vacia(numero: int, rotacion: int) -> tuple[dict, dict]:
    pagina = {
        "pagina": numero,
        "tipo": VACIA,
        "texto": "",
        "origen_texto": None,
        "caracteres": 0,
        "cobertura_imagen": 0.0,
        "rotacion": rotacion,
        "anclas": [],
    }
    return pagina, {"pagina": numero, "palabras": []}


def _leer_pagina(pagina, numero: int, rotacion: int, parametros: Parametros) -> tuple[dict, dict]:
    texto = pagina.extract_text() or ""
    caracteres = contar_caracteres(texto)
    cajas = [(imagen["x0"], imagen["top"], imagen["x1"], imagen["bottom"]) for imagen in pagina.images]
    fraccion = cobertura(cajas, tuple(map(float, pagina.bbox)), parametros.celdas_grilla_cobertura)
    tipo = tipo_de_pagina(caracteres, fraccion, parametros)
    palabras_pdfplumber = pagina.extract_words()
    palabras = [
        {"t": palabra["text"], "caja": _caja(palabra["x0"], palabra["top"], palabra["x1"], palabra["bottom"])}
        for palabra in palabras_pdfplumber
    ]
    # Las páginas imagen no tienen anclas: no hay texto (plan, "Anclas").
    zonas = [] if tipo == IMAGEN else anclas.buscar(pagina, palabras_pdfplumber, parametros)
    lectura = {
        "pagina": numero,
        "tipo": tipo,
        "texto": texto,
        "origen_texto": ORIGEN_POR_TIPO[tipo],
        "caracteres": caracteres,
        "cobertura_imagen": fraccion,
        "rotacion": rotacion,
        "anclas": zonas,
    }
    return lectura, {"pagina": numero, "palabras": palabras}


def leer(
    datos: bytes,
    id_documento: str,
    firmas: list[FirmaDigital],
    uri_palabras: str,
    parametros: Parametros = PARAMETROS,
) -> Lectura:
    """Lee un PDF normalizado, que ya pasó por revision_pdf (abre y tiene páginas).

    Si una página no se puede leer, queda `vacia` y se sigue con las demás: el
    documento no queda con error. Se anota en el registro el número de página.
    """
    sin_rotar, rotaciones = _sin_rotacion(datos)
    paginas: list[dict] = []
    palabras: list[dict] = []
    try:
        with pdfplumber.open(io.BytesIO(sin_rotar)) as pdf:
            for indice, rotacion in enumerate(rotaciones):
                numero = indice + 1
                try:
                    lectura_pagina, palabras_pagina = _leer_pagina(pdf.pages[indice], numero, rotacion, parametros)
                except Exception as error:  # noqa: BLE001 - una página rota no frena el documento
                    registro.warning("Página %d sin leer: %s", numero, type(error).__name__)
                    lectura_pagina, palabras_pagina = _pagina_vacia(numero, rotacion)
                paginas.append(lectura_pagina)
                palabras.append(palabras_pagina)
    except Exception as error:  # noqa: BLE001
        registro.warning("Documento sin leer: %s", type(error).__name__)
        leidas = len(paginas)
        for indice in range(leidas, len(rotaciones)):
            lectura_pagina, palabras_pagina = _pagina_vacia(indice + 1, rotaciones[indice])
            paginas.append(lectura_pagina)
            palabras.append(palabras_pagina)

    lectura = {
        "contrato": CONTRATO,
        "id_documento": id_documento,
        "hash_pdf": hashlib.sha256(datos).hexdigest(),
        "version_normalizador": VERSION,
        "version_parametros": parametros.version,
        "firma_digital": [firma.como_dict() for firma in firmas],
        "palabras": uri_palabras,
        "paginas": paginas,
    }
    return Lectura(lectura=lectura, palabras={"id_documento": id_documento, "paginas": palabras})
