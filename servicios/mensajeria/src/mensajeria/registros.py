"""Registros del bucle de mensajes, con las reglas de la normalización: solo
identificadores, y de las excepciones solo el tipo y el lugar (principio 6).

Las alertas para operación van al registro `mensajeria.alertas` con nivel ERROR.
Cada servicio conecta los registros `mensajeria` a su salida al configurar los
suyos (`orquestador.registros.configurar`).
"""

import contextlib
import logging

from normalizacion import registros as base
from normalizacion.registros import lugar_de_la_excepcion

__all__ = ["alertas", "contexto_de", "lugar_de_la_excepcion"]

alertas = logging.getLogger("mensajeria.alertas")


@contextlib.contextmanager
def contexto_de(cuerpo: dict):
    """Pone en el contexto de los registros los identificadores que traiga el mensaje."""
    entrega = cuerpo.get("entrega", cuerpo.get("id_oferente"))
    with base.contexto(id_proceso=cuerpo.get("id_proceso"), id_oferente=entrega,
                       id_documento=cuerpo.get("id_segmento") or cuerpo.get("id_documento")):
        yield
