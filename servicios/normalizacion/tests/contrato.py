"""Validadores de los esquemas del contrato modulo3-normalizacion/v0.

Los esquemas se refieren entre sí (la lectura usa la firma del manifiesto y las
palabras usan la caja de la lectura), así que se cargan juntos en un registro.
Lo usan la prueba del contrato y, más adelante, la prueba de punta a punta (T11).
"""

import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

CONTRATO = Path(__file__).resolve().parents[3] / "contracts" / "modulo3-normalizacion" / "v0"
NOMBRES = ("manifiesto", "lectura", "palabras")


@cache
def esquemas() -> dict[str, dict]:
    return {
        nombre: json.loads((CONTRATO / f"{nombre}.schema.json").read_text(encoding="utf-8"))
        for nombre in NOMBRES
    }


@cache
def validador(nombre: str) -> Draft202012Validator:
    registro = Registry().with_resources(
        (esquema["$id"], Resource.from_contents(esquema)) for esquema in esquemas().values()
    )
    return Draft202012Validator(
        esquemas()[nombre],
        registry=registro,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
