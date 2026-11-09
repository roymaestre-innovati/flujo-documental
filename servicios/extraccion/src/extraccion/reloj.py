"""El reloj, inyectable para probar esperas y reintentos sin esperar."""

import datetime
import time
from abc import ABC, abstractmethod


class Reloj(ABC):
    @abstractmethod
    def ahora(self) -> datetime.datetime:
        """Fecha y hora actual, siempre con zona horaria (UTC)."""

    @abstractmethod
    def dormir(self, segundos: float) -> None:
        """Espera antes de reintentar."""

    @abstractmethod
    def monotono(self) -> float:
        """Segundos de un contador que solo avanza, para medir duraciones."""


class RelojSistema(Reloj):
    def ahora(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)

    def dormir(self, segundos: float) -> None:
        time.sleep(segundos)

    def monotono(self) -> float:
        return time.monotonic()


class RelojManual(Reloj):
    """Un reloj que solo avanza cuando se le pide o cuando alguien duerme."""

    def __init__(self, inicio: datetime.datetime | None = None) -> None:
        self._ahora = inicio or datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        if self._ahora.tzinfo is None:
            raise ValueError("El reloj necesita una fecha con zona horaria")
        self._transcurrido = 0.0
        self.esperas: list[float] = []
        """Cada espera pedida, en orden, para que las pruebas las revisen."""

    def ahora(self) -> datetime.datetime:
        return self._ahora

    def monotono(self) -> float:
        return self._transcurrido

    def adelantar(self, segundos: float) -> None:
        if segundos < 0:
            raise ValueError("El reloj no retrocede")
        self._ahora += datetime.timedelta(seconds=segundos)
        self._transcurrido += segundos

    def dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.adelantar(segundos)
