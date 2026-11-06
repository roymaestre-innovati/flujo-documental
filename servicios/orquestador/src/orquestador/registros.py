"""Registros (logs) del orquestador, en JSON, con el mismo formato y las mismas
reglas que la normalización: solo identificadores, nunca texto de los documentos
ni rutas de origen, y de las excepciones solo el tipo y el lugar (principio 6).

Las alertas para operación van al registro `orquestador.alertas` con nivel
ERROR. En la entrega 2 se conectan a Application Insights.
"""

import contextlib
import logging
import sys

from normalizacion import registros as base
from normalizacion.registros import FormatoJson, lugar_de_la_excepcion

__all__ = ["alertas", "configurar", "contexto_de", "lugar_de_la_excepcion"]

alertas = logging.getLogger("orquestador.alertas")


@contextlib.contextmanager
def contexto_de(cuerpo: dict):
    """Pone en el contexto de los registros los identificadores que traiga el mensaje."""
    entrega = cuerpo.get("entrega", cuerpo.get("id_oferente"))
    with base.contexto(id_proceso=cuerpo.get("id_proceso"), id_oferente=entrega,
                       id_documento=cuerpo.get("id_segmento") or cuerpo.get("id_documento")):
        yield


def configurar(nivel: int = logging.INFO, salida=None) -> None:
    """Registros del orquestador y de la normalización en JSON hacia `salida`."""
    base.configurar(nivel, salida)
    manejador = logging.StreamHandler(salida or sys.stderr)
    manejador.setFormatter(FormatoJson())
    paquete = logging.getLogger("orquestador")
    for anterior in list(paquete.handlers):
        if isinstance(anterior.formatter, FormatoJson):
            paquete.removeHandler(anterior)
    paquete.addHandler(manejador)
    paquete.setLevel(nivel)
    paquete.propagate = False
