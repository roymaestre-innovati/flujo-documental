"""Zonas visuales de una página: líneas de firma, casillas y tablas SI/NO (R21).

Reglas simples y deterministas, por palabras clave y posición, sin LLM. Trabajan
sobre lo que pdfplumber ve en la página sin rotar: palabras, líneas y rectángulos.
Las cajas van en puntos, `[x0, y0, x1, y1]`, con el origen arriba a la izquierda.

- `linea_firma`: una línea dibujada horizontal o una secuencia de 8 o más `_`, con
  una frase a menos de 60 puntos que menciona firma, representante, revisor o
  contador; la caja cubre la línea y esa frase. También una frase que empieza
  por "firma" y que no es ya el rótulo de una línea.
- `casilla`: un rectángulo casi cuadrado, de 6 a 20 puntos de lado.
- `tabla_si_no`: un renglón con las palabras "SI" y "NO" sueltas, junto con al
  menos una casilla o una celda de tabla a menos de 20 puntos.

Las palabras se comparan sin mayúsculas ni tildes ("Sí" cuenta como "SI").
"""

import math
import re
import unicodedata
from dataclasses import dataclass

from .parametros import PARAMETROS, Parametros

LINEA_FIRMA = "linea_firma"
CASILLA = "casilla"
TABLA_SI_NO = "tabla_si_no"

_ORDEN_TIPO = {LINEA_FIRMA: 0, CASILLA: 1, TABLA_SI_NO: 2}
_DECIMALES = 2

Caja = tuple[float, float, float, float]


@dataclass(frozen=True)
class Palabra:
    texto: str
    caja: Caja


@dataclass(frozen=True)
class Frase:
    texto: str
    caja: Caja
    palabras: tuple[Palabra, ...]


# ---------------------------------------------------------------------------
# Utilidades


def normalizar(texto: str) -> str:
    """Sin mayúsculas ni tildes."""
    descompuesto = unicodedata.normalize("NFD", texto.casefold())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _fichas(texto: str) -> list[str]:
    return re.findall(r"\w+", normalizar(texto))


def _union(*cajas: Caja) -> Caja:
    return (
        min(c[0] for c in cajas),
        min(c[1] for c in cajas),
        max(c[2] for c in cajas),
        max(c[3] for c in cajas),
    )


def distancia(a: Caja, b: Caja) -> float:
    """Distancia entre los bordes de dos cajas; 0 si se tocan o se superponen."""
    dx = max(0.0, a[0] - b[2], b[0] - a[2])
    dy = max(0.0, a[1] - b[3], b[1] - a[3])
    return math.hypot(dx, dy)


def _redondear(caja: Caja) -> list[float]:
    return [round(float(v), _DECIMALES) for v in caja]


def _ancla(tipo: str, caja: Caja, texto: str | None) -> dict:
    return {"tipo": tipo, "caja": _redondear(caja), "texto": texto}


# ---------------------------------------------------------------------------
# Renglones y frases


def renglones(palabras: list[Palabra], parametros: Parametros) -> list[list[Palabra]]:
    """Palabras agrupadas por renglón, de arriba abajo y de izquierda a derecha."""
    resultado: list[list[Palabra]] = []
    for palabra in sorted(palabras, key=lambda p: (p.caja[1], p.caja[0])):
        if resultado and abs(resultado[-1][0].caja[1] - palabra.caja[1]) <= parametros.tolerancia_renglon:
            resultado[-1].append(palabra)
        else:
            resultado.append([palabra])
    return [sorted(renglon, key=lambda p: p.caja[0]) for renglon in resultado]


def _frase(palabras: list[Palabra]) -> Frase:
    return Frase(
        texto=" ".join(p.texto for p in palabras),
        caja=_union(*(p.caja for p in palabras)),
        palabras=tuple(palabras),
    )


def frases(palabras: list[Palabra], parametros: Parametros) -> list[Frase]:
    """Palabras seguidas de un mismo renglón, cortadas donde hay un hueco grande."""
    resultado = []
    for renglon in renglones(palabras, parametros):
        actual = [renglon[0]]
        for palabra in renglon[1:]:
            if palabra.caja[0] - actual[-1].caja[2] > parametros.separacion_max_frase:
                resultado.append(_frase(actual))
                actual = []
            actual.append(palabra)
        resultado.append(_frase(actual))
    return resultado


# ---------------------------------------------------------------------------
# Reglas


def _menciona_firma(frase: Frase, parametros: Parametros) -> bool:
    return any(
        ficha.startswith(clave) for ficha in _fichas(frase.texto) for clave in parametros.palabras_rotulo_firma
    )


def _empieza_por_firma(frase: Frase, parametros: Parametros) -> bool:
    fichas = _fichas(frase.texto)
    return bool(fichas) and fichas[0].startswith(parametros.prefijo_firma)


def lineas_de_firma(
    palabras: list[Palabra],
    lineas: list[Caja],
    parametros: Parametros = PARAMETROS,
) -> list[dict]:
    todas = frases(palabras, parametros)
    guiones = "_" * parametros.min_guiones_bajos_firma
    candidatas = list(lineas) + [p.caja for p in palabras if guiones in p.texto]
    anclas = []
    rotulos_usados: set[Caja] = set()
    for linea in sorted(set(candidatas)):
        cercanas = [
            f for f in todas
            if _menciona_firma(f, parametros) and distancia(f.caja, linea) < parametros.distancia_rotulo_firma
        ]
        if not cercanas:
            continue
        rotulo = min(cercanas, key=lambda f: (distancia(f.caja, linea), f.caja[1], f.caja[0]))
        rotulos_usados.add(rotulo.caja)
        anclas.append(_ancla(LINEA_FIRMA, _union(linea, rotulo.caja), rotulo.texto))
    for frase in todas:
        if frase.caja not in rotulos_usados and _empieza_por_firma(frase, parametros):
            anclas.append(_ancla(LINEA_FIRMA, frase.caja, frase.texto))
    return anclas


def es_casilla(caja: Caja, parametros: Parametros = PARAMETROS) -> bool:
    ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
    menor, mayor = min(ancho, alto), max(ancho, alto)
    if menor < parametros.lado_min_casilla or mayor > parametros.lado_max_casilla:
        return False
    return (mayor - menor) / mayor <= parametros.tolerancia_cuadrado_casilla


def casillas(rectangulos: list[Caja], parametros: Parametros = PARAMETROS) -> list[Caja]:
    """Rectángulos que son casillas, sin repetir (un rectángulo con borde y relleno
    puede venir dos veces)."""
    vistas: dict[tuple[float, ...], Caja] = {}
    for rectangulo in rectangulos:
        if es_casilla(rectangulo, parametros):
            vistas.setdefault(tuple(_redondear(rectangulo)), rectangulo)
    return [vistas[clave] for clave in sorted(vistas)]


def tablas_si_no(
    palabras: list[Palabra],
    rectangulos: list[Caja],
    parametros: Parametros = PARAMETROS,
) -> list[dict]:
    si, no = parametros.palabras_si_no
    de_la_pagina = casillas(rectangulos, parametros)
    anclas = []
    for renglon in renglones(palabras, parametros):
        fichas = [ficha for p in renglon for ficha in _fichas(p.texto)]
        if si not in fichas or no not in fichas:
            continue
        caja = _union(*(p.caja for p in renglon))
        cerca = lambda r: distancia(r, caja) < parametros.distancia_si_no  # noqa: E731
        if not any(cerca(r) for r in rectangulos):
            continue
        # La caja suma solo las casillas de este renglón (que se cruzan con él en
        # vertical), no las del renglón de al lado aunque estén a menos de 20 puntos.
        cercanas = [c for c in de_la_pagina if cerca(c) and c[1] < caja[3] and c[3] > caja[1]]
        texto = " ".join(p.texto for p in renglon)
        anclas.append(_ancla(TABLA_SI_NO, _union(caja, *cercanas), texto))
    return anclas


# ---------------------------------------------------------------------------


def _caja_pdfplumber(objeto: dict) -> Caja:
    return (float(objeto["x0"]), float(objeto["top"]), float(objeto["x1"]), float(objeto["bottom"]))


def buscar(pagina, palabras_pdfplumber: list[dict], parametros: Parametros = PARAMETROS) -> list[dict]:
    """Anclas de una página de pdfplumber (leída sin rotar), en orden de arriba
    abajo y de izquierda a derecha."""
    palabras = [Palabra(p["text"], _caja_pdfplumber(p)) for p in palabras_pdfplumber]
    rectangulos = [_caja_pdfplumber(r) for r in pagina.rects]
    horizontales = [
        _caja_pdfplumber(objeto)
        for objeto in [*pagina.lines, *pagina.rects]
        if (float(objeto["bottom"]) - float(objeto["top"])) <= parametros.grosor_max_linea
        and (float(objeto["x1"]) - float(objeto["x0"])) > parametros.grosor_max_linea
    ]
    # Un rectángulo delgado es una línea, no una celda ni una casilla.
    rectangulos = [r for r in rectangulos if r not in horizontales]
    anclas = [
        *lineas_de_firma(palabras, horizontales, parametros),
        *(_ancla(CASILLA, c, None) for c in casillas(rectangulos, parametros)),
        *tablas_si_no(palabras, rectangulos, parametros),
    ]
    return sorted(anclas, key=lambda a: (a["caja"][1], a["caja"][0], _ORDEN_TIPO[a["tipo"]], a["caja"][2], a["caja"][3]))
