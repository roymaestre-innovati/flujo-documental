"""Parámetros de operación del orquestador: reintentos, esperas y paralelo.

No son condiciones del proceso, así que no se fijan por proceso. Cambiarlos no
cambia ningún resultado, solo cuándo y cuántas veces se intenta algo.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Parametros:
    reintentos_transitorio: int = 3
    """Reintentos de una falla transitoria, después del primer intento (decisión 18)."""
    demora_base_s: float = 120
    """Espera antes del primer reintento; se duplica en cada uno: 2, 4 y 8 minutos."""
    reintentos_respuesta_invalida: int = 2
    """Reintentos inmediatos de una respuesta que no cumple su forma (decisión 18)."""
    max_esperas: int = 20
    """Esperas pedidas por el servicio (límite de uso) que no cuentan como intento.
    Pasado este número se trata como una falla transitoria agotada, para que un
    mensaje no quede dando vueltas para siempre."""
    horas_escalamiento: float = 24
    """Un error de proceso sin resolver pasa a tarea humana después de esto (R22)."""
    paralelo_normalizar: int = 2
    """Entregas que se normalizan a la vez (acordado el 2026-11-06)."""
    paralelo_bajar: int = 8
    """Archivos de una misma entrega que se bajan a la vez (T04)."""
    espera_limite_estado_s: float = 1
    """Espera cuando Cosmos limita las RU y no indica cuándo reintentar."""
    renovacion_bloqueo_max_s: float = 1800
    """Tiempo máximo de renovación del bloqueo de una entrega de Service Bus."""


PARAMETROS = Parametros()
