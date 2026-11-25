"""El reloj, inyectable para probar demoras y plazos sin esperar."""

import datetime
from abc import ABC, abstractmethod


class Reloj(ABC):
    @abstractmethod
    def ahora(self) -> datetime.datetime:
        """Fecha y hora actual, siempre con zona horaria (UTC)."""


class RelojSistema(Reloj):
    def ahora(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)


class RelojManual(Reloj):
    """Un reloj que solo avanza cuando se le pide."""

    def __init__(self, inicio: datetime.datetime | None = None) -> None:
        self._ahora = inicio or datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        if self._ahora.tzinfo is None:
            raise ValueError("El reloj necesita una fecha con zona horaria")

    def ahora(self) -> datetime.datetime:
        return self._ahora

    def adelantar(self, segundos: float) -> None:
        if segundos < 0:
            raise ValueError("El reloj no retrocede")
        self._ahora += datetime.timedelta(seconds=segundos)
