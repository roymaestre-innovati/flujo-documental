"""Borra los registros de prueba por partición, con reintentos acotados."""

from collections.abc import Iterable
from time import sleep

from pymongo.collection import Collection

from orquestador.errores import ErrorTransitorio
from orquestador.estado_mongo import _traducir_fallas


class ErrorLimpieza(Exception):
    """Identifica los procesos de prueba que quedaron pendientes de borrar."""


def limpiar_procesos(coleccion: Collection[dict], procesos: Iterable[str]) -> None:
    fallidos = []
    for id_proceso in procesos:
        for intento in range(1, 6):
            try:
                with _traducir_fallas("delete_many"):
                    coleccion.delete_many({"id_proceso": id_proceso})
            except ErrorTransitorio as error:
                if intento < 5:
                    sleep(0.5 if error.espera_s is None else error.espera_s)
                    continue
                fallidos.append(id_proceso)
            except Exception:  # noqa: BLE001 - se intenta el resto y se informa solo el identificador.
                fallidos.append(id_proceso)
            break
    if fallidos:
        raise ErrorLimpieza(f"No se pudieron borrar los procesos de prueba: {', '.join(fallidos)}") from None
