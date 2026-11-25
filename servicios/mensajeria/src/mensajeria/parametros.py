"""Parámetros del bucle de mensajes y de la cola: reintentos, esperas y bloqueo.

No son condiciones del proceso. Cambiarlos no cambia ningún resultado, solo
cuándo y cuántas veces se intenta algo. Cada servicio puede extenderlos con los
suyos (el orquestador lo hace en `orquestador.parametros`).
"""

from dataclasses import dataclass, field


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
    renovacion_bloqueo_max_s: float = field(default=1800, kw_only=True)
    """Tiempo máximo de renovación del bloqueo de una entrega de Service Bus."""


PARAMETROS = Parametros()
