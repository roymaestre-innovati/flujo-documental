"""Datos con versión del orquestador (principio 2).

`versiones.json` dice cuáles son las vigentes. Las de umbrales y tipos
documentales tienen un archivo por versión, porque un proceso abierto sigue
usando la que fijó aunque se publique una nueva (principio 7). Para cambiar un
umbral se agrega un archivo con una versión nueva y se apunta `versiones.json` a
él; los archivos ya publicados no se editan.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DATOS = Path(__file__).parent / "datos"


class ErrorDatos(Exception):
    """Falta una versión o un archivo de datos está mal. Es un bug (clase 4)."""


@dataclass(frozen=True)
class Versiones:
    """Las versiones que se fijan en un proceso al abrirlo (R5)."""

    modelo_extraccion: int
    ontologia: str
    reglas: str | None
    """None mientras no existan reglas publicadas (módulo 4)."""
    umbrales: str
    tipos_documentales: str

    def como_dict(self) -> dict:
        return {
            "modelo_extraccion": self.modelo_extraccion,
            "ontologia": self.ontologia,
            "reglas": self.reglas,
            "umbrales": self.umbrales,
            "tipos_documentales": self.tipos_documentales,
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> "Versiones":
        return cls(**datos)


@dataclass(frozen=True)
class Umbrales:
    version: str
    piso: float
    """Por debajo de esto no se extrae: va a clasificación humana."""
    por_td: dict[str, float]

    def de(self, tipo_documental: str) -> float:
        try:
            return self.por_td[tipo_documental]
        except KeyError:
            raise ErrorDatos(f"Sin umbral para {tipo_documental} en la versión {self.version}") from None


@dataclass(frozen=True)
class TiposDocumentales:
    version: str
    tipos: dict[str, str]
    """TD-NN → nombre."""

    def existe(self, tipo_documental: str) -> bool:
        return tipo_documental in self.tipos


def _leer(ruta: Path) -> dict:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErrorDatos(f"No existe {ruta.relative_to(DATOS)}") from None


def vigentes(datos: Path = DATOS) -> Versiones:
    return Versiones.desde_dict(_leer(datos / "versiones.json"))


@cache
def umbrales(version: str, datos: Path = DATOS) -> Umbrales:
    contenido = _leer(datos / "umbrales" / f"{version}.json")
    if contenido["version"] != version:
        raise ErrorDatos(f"umbrales/{version}.json dice ser la versión {contenido['version']}")
    return Umbrales(version=version, piso=contenido["piso"], por_td=contenido["por_td"])


@cache
def tipos_documentales(version: str, datos: Path = DATOS) -> TiposDocumentales:
    contenido = _leer(datos / "tipos_documentales" / f"{version}.json")
    if contenido["version"] != version:
        raise ErrorDatos(f"tipos_documentales/{version}.json dice ser la versión {contenido['version']}")
    return TiposDocumentales(version=version, tipos=contenido["tipos"])
