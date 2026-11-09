"""Solicitudes de extracción (T08; requisitos R16 y R17).

Por cada segmento que se extrae se publica en la cola `extraer` una solicitud con
la forma del contrato `modulo3-extraccion/0.2`, con la versión del modelo fijada
en el proceso. Los documentos del proceso (condiciones, adendas) van sin oferente.

La solicitud se valida contra el esquema antes de publicarla: si no lo cumple, es
un bug del orquestador (clase 4), no un problema del documento.

Un segmento puede pedirse dos veces si un trabajador se cae a la mitad; la
extracción lo absorbe con su clave de idempotencia (`id_segmento`, TD y versión
del modelo, D22).
"""

import json
import logging

from normalizacion.almacen import Almacen
from normalizacion.inventario import ENTREGA_DEL_PROCESO

from . import CONTRATO_EXTRACCION, contratos
from .cola import EXTRAER, Cola
from .estado import Registro

registro = logging.getLogger("orquestador.extraer")


class SolicitudInvalida(Exception):
    """El orquestador armó una solicitud que no cumple el contrato: un bug."""


def solicitud(proceso: Registro, documento: Registro, segmento: Registro, hash_pdf: str) -> dict:
    entrega = segmento.datos["entrega"]
    anexo = documento.datos["anexo_nativo"]
    return {
        "contrato": CONTRATO_EXTRACCION,
        "id_proceso": proceso.id,
        "id_oferente": None if entrega == ENTREGA_DEL_PROCESO else entrega,
        "id_segmento": segmento.id,
        "id_documento": documento.id,
        "archivo": {"uri": documento.datos["pdf"], "sha256": hash_pdf},
        "paginas": {"desde": segmento.datos["pagina_inicio"], "hasta": segmento.datos["pagina_fin"]},
        "tipo_documental": segmento.datos["tipo_documental"],
        "lectura": documento.datos["lectura"],
        "anexos": [anexo] if anexo else [],
        "clasificacion_dudosa": segmento.datos["clasificacion_dudosa"],
        "version_modelo": proceso.datos["versiones"]["modelo_extraccion"],
        "confianza_clasificacion": segmento.datos["confianza"],
    }


class Extraer:
    """Pide la extracción de un segmento publicando su solicitud en la cola."""

    def __init__(self, cola: Cola, almacen: Almacen) -> None:
        self._cola = cola
        self._almacen = almacen

    def pedir(self, proceso: Registro, documento: Registro, segmento: Registro) -> None:
        lectura = json.loads(self._almacen.leer(documento.datos["lectura"]))
        mensaje = solicitud(proceso, documento, segmento, lectura["hash_pdf"])
        problemas = contratos.errores(contratos.EXTRACCION_ENTRADA, mensaje)
        if problemas:
            raise SolicitudInvalida("La solicitud de extracción no cumple el contrato: " + "; ".join(problemas))
        self._cola.publicar(EXTRAER, mensaje)
        registro.info("Extracción pedida: %s", segmento.id)
