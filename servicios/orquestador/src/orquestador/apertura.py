"""Apertura: el manejador de la cola `procesos-listos` (T05; requisitos R1 a R5).

Por cada aviso del módulo 1:

1. Valida el aviso contra su contrato (R1).
2. Reparte los archivos entre la entrega del proceso y la de cada oferente (R4),
   con la lista del aviso o, si no la trae, listando la carpeta en el origen.
3. Abre el proceso con las versiones vigentes, que quedan fijas (R5). Si ya
   estaba abierto, se queda con las suyas (R2).
4. Registra cada entrega con sus archivos y publica un mensaje `normalizar` por
   entrega.
5. Anota en el proceso que ya publicó las entregas.

Si el trabajador se cae entre 3 y 5, el aviso se vuelve a entregar y, como el
proceso no tiene la marca del paso 5, publica otra vez todas las entregas. Un
`normalizar` repetido lo absorbe la normalización (T06). Con la marca puesta, un
aviso repetido no hace nada.

Los originales no se copian (R3): aquí solo se listan. Los baja la
normalización, uno por uno, a una carpeta temporal.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from pathlib import PurePosixPath

import normalizacion
from normalizacion.inventario import ENTREGA_DEL_PROCESO
from normalizacion.parametros import PARAMETROS as PARAMETROS_NORMALIZACION

from . import contratos, datos, estados
from .cola import NORMALIZAR, PROCESOS_LISTOS, Cola
from .errores import MensajeRechazado
from .estado import Estado
from .origen import ErrorOrigen, Origen
from .reloj import Reloj

registro = logging.getLogger("orquestador.apertura")


class AvisoRechazado(MensajeRechazado):
    """El aviso cumple su contrato, pero lo que dice no se puede procesar."""


def repartir(aviso: dict, origen: Origen) -> dict[str, list[str]]:
    """Las entregas del proceso: `PROCESO` o `id_oferente` → archivos, como rutas
    relativas a la carpeta del proceso y ordenadas.

    Es lo único que cambia cuando el módulo 1 responda A-1 (plan, "Entregas del
    proceso"). Mientras tanto:

    - si el aviso trae `archivos`, manda esa lista y no se lee el origen;
    - si no, la carpeta trae `PROCESO/` y una subcarpeta por oferente, nombrada
      con su identificador. Un archivo suelto en la raíz rechaza el aviso: podría
      ser de un oferente, y no se evalúa a nadie con documentos de menos.
    """
    entregas: dict[str, list[str]] = defaultdict(list)
    if "archivos" in aviso:
        for archivo in aviso["archivos"]:
            id_oferente = archivo["id_oferente"]
            if id_oferente == ENTREGA_DEL_PROCESO:
                raise AvisoRechazado(f"'{ENTREGA_DEL_PROCESO}' no puede ser el identificador de un oferente")
            entregas[id_oferente or ENTREGA_DEL_PROCESO].append(archivo["ruta"])
    else:
        try:
            archivos = origen.listar(aviso["ruta"])
        except ErrorOrigen:
            raise AvisoRechazado("La carpeta del proceso no existe en el origen o no es válida") from None
        sueltos = 0
        for ruta in archivos:
            partes = PurePosixPath(ruta).parts
            if len(partes) < 2:
                sueltos += 1
                continue
            entregas[partes[0]].append(ruta)
        if sueltos:
            raise AvisoRechazado(f"{sueltos} archivo(s) sueltos en la raíz de la carpeta del proceso, fuera de una entrega")
    if not entregas:
        raise AvisoRechazado("El proceso no trae ningún archivo")
    if len(entregas) == 1 and ENTREGA_DEL_PROCESO in entregas:
        raise AvisoRechazado("El proceso no trae ningún oferente")
    return {entrega: sorted(set(rutas)) for entrega, rutas in sorted(entregas.items())}


def versiones_del_proceso(vigentes: datos.Versiones) -> dict:
    """Lo que se fija en el proceso al abrirlo (R5)."""
    return {
        **vigentes.como_dict(),
        "normalizador": normalizacion.VERSION,
        "parametros_normalizacion": PARAMETROS_NORMALIZACION.version,
    }


class Apertura:
    cola = PROCESOS_LISTOS

    def __init__(
        self,
        cola: Cola,
        estado: Estado,
        origen: Origen,
        reloj: Reloj,
        vigentes: Callable[[], datos.Versiones] = datos.vigentes,
    ) -> None:
        self._cola = cola
        self._estado = estado
        self._origen = origen
        self._reloj = reloj
        self._vigentes = vigentes

    def procesar(self, aviso: dict) -> None:
        contratos.validar(contratos.PROCESO_LISTO, aviso)
        id_proceso = aviso["id_proceso"]

        anterior = self._estado.leer(id_proceso, estados.PROCESO, id_proceso)
        if anterior is not None and anterior.datos.get("entregas_publicadas"):
            if anterior.datos["ruta"] != aviso["ruta"] or anterior.datos["fecha_aviso"] != aviso["fecha"]:
                registro.warning("Aviso repetido con datos distintos al primero: se ignora")
            else:
                registro.info("Aviso repetido: el proceso ya estaba abierto")
            return

        entregas = repartir(aviso, self._origen)

        proceso = estados.crear(
            self._estado, self._reloj, id_proceso, estados.PROCESO, id_proceso, estados.ABIERTO, "aviso del módulo 1",
            {"ruta": aviso["ruta"], "fecha_aviso": aviso["fecha"], "versiones": versiones_del_proceso(self._vigentes()),
             "entregas": list(entregas), "entregas_publicadas": False},
        ).registro
        # Si el proceso ya existía, el trabajador anterior se cayó a la mitad. Los
        # archivos no cambian después del aviso (contrato), así que el reparto
        # debe dar lo mismo; si no, se avisa y las entregas ya registradas
        # conservan sus archivos (crear no pisa lo que existe).
        if proceso.datos["entregas"] != list(entregas):
            registro.warning("El reparto cambió desde la primera apertura")

        for entrega, archivos in entregas.items():
            estados.crear(self._estado, self._reloj, id_proceso, estados.OFERENTE, entrega, estados.RECIBIDO,
                          "aviso del módulo 1", {"archivos": archivos}, entrega=entrega)
            self._cola.publicar(NORMALIZAR, {"id_proceso": id_proceso, "entrega": entrega})

        estados.anotar(self._estado, id_proceso, estados.PROCESO, id_proceso, {"entregas_publicadas": True})
        registro.info("Proceso abierto: %s entregas", len(entregas))

    def al_fallar(self, aviso: dict, motivo: str) -> None:
        # El proceso no tiene un estado de error: un aviso que falla no abrió
        # nada que el evaluador deba ver. Queda en la cola de errores y le llega
        # a operación por la alerta.
        registro.error("El aviso no se pudo procesar")
