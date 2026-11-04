"""Umbrales y palabras clave de la normalización y la lectura.

Son datos con versión (principio 2): si se cambia cualquier valor, sube
`VERSION_PARAMETROS`, que va en el manifiesto y en cada lectura (R24).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Parametros:
    version: str

    # Tipo de página (plan, "Tipo de página")
    min_caracteres_texto: int
    cobertura_escaneo: float
    celdas_grilla_cobertura: int

    # Anclas (plan, "Anclas")
    prefijo_firma: str
    palabras_rotulo_firma: tuple[str, ...]
    min_guiones_bajos_firma: int
    distancia_rotulo_firma: float
    lado_min_casilla: float
    lado_max_casilla: float
    tolerancia_cuadrado_casilla: float
    palabras_si_no: tuple[str, str]
    distancia_si_no: float

    # Conversión (plan, "Conversión")
    tiempo_max_conversion_s: int
    reintentos_conversion: int


PARAMETROS = Parametros(
    version="1",
    min_caracteres_texto=20,
    cobertura_escaneo=0.80,
    celdas_grilla_cobertura=200,
    prefijo_firma="firma",
    palabras_rotulo_firma=("firma", "representante", "revisor", "contador"),
    min_guiones_bajos_firma=8,
    distancia_rotulo_firma=60.0,
    lado_min_casilla=6.0,
    lado_max_casilla=20.0,
    tolerancia_cuadrado_casilla=0.2,
    palabras_si_no=("si", "no"),
    distancia_si_no=20.0,
    tiempo_max_conversion_s=120,
    reintentos_conversion=1,
)

VERSION_PARAMETROS = PARAMETROS.version
