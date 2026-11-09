"""Validación contra los contratos de `contracts/` y contra la respuesta interna del LLM.

Los esquemas del contrato se leen de la carpeta `contracts/` del repositorio, que es
la fuente de verdad. `EXTRACCION_CONTRATOS` permite apuntar a otra carpeta, por
ejemplo dentro de una imagen. El esquema de la respuesta del LLM es interno y va
con el paquete (`datos/respuesta.schema.json`).
"""

import json
import os
from functools import cache
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ENTRADA = "modulo3-extraccion/v0.2/entrada"
SALIDA = "modulo3-extraccion/v0.2/salida"
RESPUESTA = "respuesta"
"""La respuesta del LLM (interna)."""
ESQUEMAS = (ENTRADA, SALIDA, RESPUESTA)


def carpeta_contratos() -> Path:
    if otra := os.environ.get("EXTRACCION_CONTRATOS"):
        return Path(otra)
    # servicios/extraccion/src/extraccion/contratos.py → raíz del repositorio
    return Path(__file__).resolve().parents[4] / "contracts"


@cache
def validador(esquema: str) -> Draft202012Validator:
    if esquema == RESPUESTA:
        texto = resources.files("extraccion").joinpath("datos/respuesta.schema.json").read_text(encoding="utf-8")
    else:
        texto = (carpeta_contratos() / f"{esquema}.schema.json").read_text(encoding="utf-8")
    return Draft202012Validator(json.loads(texto), format_checker=Draft202012Validator.FORMAT_CHECKER)


def _describir(error: ValidationError) -> str:
    # Solo dónde y qué regla falló, nunca el valor: los mensajes traen datos
    # personales (nombres, cédulas) y esto puede terminar en los registros.
    donde = "/".join(str(p) for p in error.absolute_path) or "(raíz)"
    return f"{donde}: no cumple '{error.validator}'"


def errores(esquema: str, mensaje) -> list[str]:
    """Lo que no cumple, en orden estable. Vacía si el mensaje es válido."""
    return sorted(_describir(e) for e in validador(esquema).iter_errors(mensaje))
