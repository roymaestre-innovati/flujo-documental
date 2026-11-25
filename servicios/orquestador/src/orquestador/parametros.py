"""Parámetros de operación del orquestador: reintentos, esperas y paralelo.

No son condiciones del proceso, así que no se fijan por proceso. Cambiarlos no
cambia ningún resultado, solo cuándo y cuántas veces se intenta algo.
"""

from dataclasses import dataclass

from mensajeria.parametros import Parametros as ParametrosMensajeria


@dataclass(frozen=True)
class Parametros(ParametrosMensajeria):
    """Los del bucle y la cola (`mensajeria.parametros`), más los del orquestador."""

    horas_escalamiento: float = 24
    """Un error de proceso sin resolver pasa a tarea humana después de esto (R22)."""
    paralelo_normalizar: int = 2
    """Entregas que se normalizan a la vez (acordado el 2026-11-06)."""
    paralelo_bajar: int = 8
    """Archivos de una misma entrega que se bajan a la vez (T04)."""
    reserva_normalizar_s: float = 2400
    """Cuánto dura la reserva de una entrega mientras se normaliza: más que el tiempo
    máximo de un job (30 minutos), para que la ejecución que la tenía ya no exista
    cuando otra la tome (decisión 6 de `tasks-workers.md`)."""
    espera_limite_estado_s: float = 1
    """Espera cuando Cosmos limita las RU y no indica cuándo reintentar."""


PARAMETROS = Parametros()
