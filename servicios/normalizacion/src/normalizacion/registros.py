"""Registros (logs) en JSON, una línea por evento.

Cada línea lleva `id_proceso`, `id_oferente`, `id_documento` y `hash` (los primeros
12 caracteres), tomados del contexto que fija la entrega. Nunca llevan texto de las
páginas ni la ruta de origen, que puede traer nombres de personas (principio 6):
los mensajes del paquete no los incluyen, y de las excepciones solo se anota el tipo
y el lugar del código donde ocurrieron, no su mensaje.
"""

import contextlib
import contextvars
import json
import logging
import sys
import traceback

CAMPOS = ("id_proceso", "id_oferente", "id_documento", "hash")

_contexto: contextvars.ContextVar[dict] = contextvars.ContextVar("contexto_registro", default={})


@contextlib.contextmanager
def contexto(**campos):
    """Agrega campos al contexto de los registros mientras dura el bloque."""
    anterior = _contexto.get()
    token = _contexto.set({**anterior, **{k: v for k, v in campos.items() if k in CAMPOS}})
    try:
        yield
    finally:
        _contexto.reset(token)


def lugar_de_la_excepcion(error: BaseException) -> str:
    """`Tipo en archivo.py:línea`, del último marco. Sin el mensaje de la excepción."""
    marcos = traceback.extract_tb(error.__traceback__)
    if not marcos:
        return type(error).__name__
    ultimo = marcos[-1]
    archivo = ultimo.filename.rsplit("/", 1)[-1]
    return f"{type(error).__name__} en {archivo}:{ultimo.lineno}"


class FormatoJson(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        linea = {
            "momento": self.formatTime(registro, "%Y-%m-%dT%H:%M:%S"),
            "nivel": registro.levelname,
            "modulo": registro.name,
            "mensaje": registro.getMessage(),
        }
        linea.update(_contexto.get())
        if registro.exc_info and registro.exc_info[1] is not None:
            linea["excepcion"] = lugar_de_la_excepcion(registro.exc_info[1])
        return json.dumps(linea, ensure_ascii=False)


def configurar(nivel: int = logging.INFO, salida=None) -> logging.Handler:
    """Registros del paquete en JSON hacia `salida` (stderr por defecto)."""
    manejador = logging.StreamHandler(salida or sys.stderr)
    manejador.setFormatter(FormatoJson())
    paquete = logging.getLogger("normalizacion")
    for anterior in list(paquete.handlers):
        if isinstance(anterior.formatter, FormatoJson):
            paquete.removeHandler(anterior)
    paquete.addHandler(manejador)
    paquete.setLevel(nivel)
    paquete.propagate = False
    return manejador
