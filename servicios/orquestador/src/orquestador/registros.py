"""Registros (logs) del orquestador, en JSON, con el mismo formato y las mismas
reglas que la normalización: solo identificadores, nunca texto de los documentos
ni rutas de origen, y de las excepciones solo el tipo y el lugar (principio 6).

Las alertas para operación van al registro `mensajeria.alertas` con nivel
ERROR. En la entrega 2 se conectan a Application Insights.
"""

import logging
import sys

from mensajeria.registros import alertas, contexto_de, lugar_de_la_excepcion
from normalizacion import registros as base
from normalizacion.registros import FormatoJson

__all__ = ["alertas", "configurar", "contexto_de", "lugar_de_la_excepcion"]


def configurar(nivel: int = logging.INFO, salida=None) -> None:
    """Registros del orquestador y de la normalización en JSON hacia `salida`."""
    base.configurar(nivel, salida)
    # En DEBUG los SDK pueden escribir el cuerpo de los mensajes, el host y los documentos.
    logging.getLogger("azure").setLevel(max(nivel, logging.ERROR))
    logging.getLogger("pymongo").setLevel(max(nivel, logging.WARNING))
    manejador = logging.StreamHandler(salida or sys.stderr)
    manejador.setFormatter(FormatoJson())
    # El bucle y la cola viven en la mensajería y escriben bajo `mensajeria`.
    for nombre in ("orquestador", "mensajeria"):
        paquete = logging.getLogger(nombre)
        for anterior in list(paquete.handlers):
            if isinstance(anterior.formatter, FormatoJson):
                paquete.removeHandler(anterior)
        paquete.addHandler(manejador)
        paquete.setLevel(nivel)
        paquete.propagate = False
