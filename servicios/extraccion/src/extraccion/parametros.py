"""Parámetros del servicio, con su versión (principio 2).

Los números del preprocesamiento y de los reintentos viven en
`datos/parametros.json`, no en el código. Si cambia uno, cambia `version`.
"""

import json
from functools import cache
from importlib import resources


@cache
def parametros() -> dict:
    texto = resources.files("extraccion").joinpath("datos/parametros.json").read_text(encoding="utf-8")
    return json.loads(texto)


def version_parametros() -> str:
    return parametros()["version"]
