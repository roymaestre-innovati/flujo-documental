"""Registros (logs) de la extracción, en JSON, con el formato de la normalización.

Una línea por segmento, con identificadores y conteos: `id_segmento`, TD,
versión, estado, campos, motivos, tokens, duración, reintentos y código de error.
Nunca valores, citas, texto, nombres de archivo ni el mensaje al LLM
(principio 6). De las excepciones solo el tipo y el lugar.
"""

import contextlib
import json
import logging
import sys
from collections import Counter

from normalizacion import registros as base
from normalizacion.registros import FormatoJson

registro = logging.getLogger("extraccion")


class FormatoExtraccion(FormatoJson):
    """El formato de la normalización más los conteos que trae `extra={"datos": …}`."""

    def format(self, linea: logging.LogRecord) -> str:
        texto = super().format(linea)
        datos = getattr(linea, "datos", None)
        if not datos:
            return texto
        return json.dumps({**json.loads(texto), **datos}, ensure_ascii=False)


@contextlib.contextmanager
def contexto_de(solicitud: dict):
    with base.contexto(id_proceso=solicitud.get("id_proceso"), id_oferente=solicitud.get("id_oferente"),
                       id_documento=solicitud.get("id_segmento")):
        yield


def resumen(resultado: dict) -> dict:
    """Lo que se registra de un resultado: solo identificadores y conteos."""
    ejecucion = resultado["ejecucion"]
    motivos = Counter(m for r in resultado["resultados"] for m in r["motivos"])
    datos = {
        "id_segmento": resultado["id_segmento"],
        "tipo_documental": resultado["tipo_documental"],
        "version_modelo": resultado["version_modelo"],
        "estado": resultado["estado"],
        "campos": len(resultado["resultados"]),
        "campos_en_revision": len(resultado["campos_en_revision"]),
        "motivos": dict(sorted(motivos.items())),
        "tokens_entrada": ejecucion.get("tokens_entrada", 0),
        "tokens_salida": ejecucion.get("tokens_salida", 0),
        "duracion_ms": ejecucion["duracion_ms"],
        "reintentos": ejecucion.get("reintentos", 0),
        "desde_cache": ejecucion.get("desde_cache", False),
    }
    if "error" in resultado:
        datos["codigo_error"] = resultado["error"]["codigo"]
    return datos


def configurar(nivel: int = logging.INFO, salida=None) -> None:
    """Registros de la extracción y de la normalización en JSON hacia `salida`."""
    base.configurar(nivel, salida)
    manejador = logging.StreamHandler(salida or sys.stderr)
    manejador.setFormatter(FormatoExtraccion())
    for anterior in list(registro.handlers):
        if isinstance(anterior.formatter, FormatoJson):
            registro.removeHandler(anterior)
    registro.addHandler(manejador)
    registro.setLevel(nivel)
    registro.propagate = False
