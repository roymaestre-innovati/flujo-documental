"""Validación de mensajes contra los contratos de `contracts/`.

Los esquemas se leen de la carpeta `contracts/` del repositorio, que es la fuente
de verdad. `ORQUESTADOR_CONTRATOS` permite apuntar a otra carpeta, por ejemplo
dentro de una imagen (entrega 2).
"""

import json
import os
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .errores import MensajeRechazado

PROCESO_LISTO = "modulo5-orquestador/v0/proceso-listo"
CLASIFICACION_SOLICITUD = "modulo5-orquestador/v0/clasificacion-solicitud"
CLASIFICACION_RESPUESTA = "modulo5-orquestador/v0/clasificacion-respuesta"
EXTRACCION_ENTRADA = "modulo3-extraccion/v0.2/entrada"
ESQUEMAS = (PROCESO_LISTO, CLASIFICACION_SOLICITUD, CLASIFICACION_RESPUESTA, EXTRACCION_ENTRADA)


def carpeta_contratos() -> Path:
    if otra := os.environ.get("ORQUESTADOR_CONTRATOS"):
        return Path(otra)
    # servicios/orquestador/src/orquestador/contratos.py → raíz del repositorio
    return Path(__file__).resolve().parents[4] / "contracts"


class MensajeInvalido(MensajeRechazado):
    """El mensaje no cumple su contrato. Su texto lleva solo campos y reglas, sin valores."""

    def __init__(self, esquema: str, errores: list[str]) -> None:
        self.esquema = esquema
        self.errores = errores
        super().__init__(f"No cumple {esquema}: " + "; ".join(errores))


@cache
def validador(esquema: str) -> Draft202012Validator:
    ruta = carpeta_contratos() / f"{esquema}.schema.json"
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    return Draft202012Validator(contenido, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _describir(error: ValidationError) -> str:
    # Solo dónde y qué regla falló, nunca el valor: el mensaje puede traer rutas
    # de archivos con nombres de personas, y esto termina en los registros.
    donde = "/".join(str(p) for p in error.absolute_path) or "(raíz)"
    return f"{donde}: no cumple '{error.validator}'"


def errores(esquema: str, mensaje: dict) -> list[str]:
    """Lo que no cumple, en orden estable. Vacía si el mensaje es válido."""
    return sorted(_describir(e) for e in validador(esquema).iter_errors(mensaje))


def validar(esquema: str, mensaje: dict) -> None:
    if encontrados := errores(esquema, mensaje):
        raise MensajeInvalido(esquema, encontrados)
