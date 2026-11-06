"""Colas de mensajes. En producción, Service Bus (entrega 2); aquí, en memoria.

Se imita lo que importa de Service Bus:

- un mensaje recibido queda bloqueado (no lo ve nadie más) hasta que se
  completa, se manda a errores o se abandona;
- un mensaje abandonado vuelve a la cola y se puede entregar otra vez, como
  cuando un trabajador se cae a la mitad;
- se puede publicar con demora;
- cada cola tiene su cola de errores (dead-letter).

El cuerpo de cada mensaje es un dict que se pueda pasar a JSON. Aparte van las
`propiedades`, como las application properties de Service Bus: ahí el bucle
lleva `intento` y `esperas`, sin tocar el cuerpo, que debe seguir cumpliendo su
contrato (el aviso del módulo 1 no admite campos extra).
"""

import copy
import datetime
import itertools
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field

from .reloj import Reloj, RelojSistema

PROCESOS_LISTOS = "procesos-listos"
NORMALIZAR = "normalizar"
CLASIFICAR = "clasificar"
EXTRAER = "extraer"
COLAS = (PROCESOS_LISTOS, NORMALIZAR, CLASIFICAR, EXTRAER)


class ErrorCola(Exception):
    """Uso incorrecto de la cola: un bug (clase 4)."""


@dataclass
class Mensaje:
    id: str
    cola: str
    cuerpo: dict
    propiedades: dict = field(default_factory=dict)
    entregas: int = 0
    """Cuántas veces se recibió. Service Bus lo lleva como DeliveryCount."""
    visible_desde: datetime.datetime | None = None


@dataclass
class MensajeEnErrores:
    mensaje: Mensaje
    motivo: str
    cuando: datetime.datetime


class Cola(ABC):
    @abstractmethod
    def publicar(self, cola: str, cuerpo: dict, demora_s: float = 0, propiedades: dict | None = None) -> str:
        """Publica un mensaje y devuelve su id. Con demora, no se ve hasta que pase."""

    @abstractmethod
    def recibir(self, cola: str) -> Mensaje | None:
        """El siguiente mensaje visible, bloqueado para quien lo recibe, o None."""

    @abstractmethod
    def completar(self, mensaje: Mensaje) -> None:
        """Lo borra de la cola: el trabajo terminó."""

    @abstractmethod
    def abandonar(self, mensaje: Mensaje) -> None:
        """Lo devuelve a la cola sin cambios, para que se entregue otra vez."""

    @abstractmethod
    def a_errores(self, mensaje: Mensaje, motivo: str) -> None:
        """Lo pasa a la cola de errores de su cola, con el motivo."""

    @abstractmethod
    def errores(self, cola: str) -> list[MensajeEnErrores]:
        """Los mensajes en la cola de errores, del más viejo al más nuevo."""

    @abstractmethod
    def sacar_de_errores(self, cola: str) -> list[MensajeEnErrores]:
        """Vacía la cola de errores y devuelve lo que tenía, para reenviarlo."""

    @abstractmethod
    def pendientes(self, cola: str) -> int:
        """Mensajes que faltan por completar, visibles o no, sin contar errores."""


class ColaEnMemoria(Cola):
    def __init__(self, reloj: Reloj | None = None) -> None:
        self._reloj = reloj or RelojSistema()
        self._colas: dict[str, list[Mensaje]] = defaultdict(list)
        self._bloqueados: dict[str, Mensaje] = {}
        self._errores: dict[str, list[MensajeEnErrores]] = defaultdict(list)
        self._ids = itertools.count(1)

    @staticmethod
    def _revisar_cola(cola: str) -> None:
        if cola not in COLAS:
            raise ErrorCola(f"Cola desconocida: {cola}")

    def publicar(self, cola: str, cuerpo: dict, demora_s: float = 0, propiedades: dict | None = None) -> str:
        self._revisar_cola(cola)
        if demora_s < 0:
            raise ErrorCola("La demora no puede ser negativa")
        # Como en Service Bus, el mensaje viaja serializado: se copia y debe ser JSON.
        cuerpo = json.loads(json.dumps(cuerpo, ensure_ascii=False))
        propiedades = json.loads(json.dumps(propiedades or {}, ensure_ascii=False))
        visible = self._reloj.ahora() + datetime.timedelta(seconds=demora_s)
        mensaje = Mensaje(id=f"m{next(self._ids):06d}", cola=cola, cuerpo=cuerpo, propiedades=propiedades,
                          visible_desde=visible)
        self._colas[cola].append(mensaje)
        return mensaje.id

    def recibir(self, cola: str) -> Mensaje | None:
        self._revisar_cola(cola)
        ahora = self._reloj.ahora()
        visibles = [m for m in self._colas[cola] if m.visible_desde <= ahora]
        if not visibles:
            return None
        mensaje = min(visibles, key=lambda m: (m.visible_desde, m.id))
        self._colas[cola].remove(mensaje)
        mensaje.entregas += 1
        self._bloqueados[mensaje.id] = mensaje
        return copy.deepcopy(mensaje)

    def _soltar(self, mensaje: Mensaje) -> Mensaje:
        try:
            return self._bloqueados.pop(mensaje.id)
        except KeyError:
            raise ErrorCola(f"El mensaje {mensaje.id} no está bloqueado: ya se completó o nunca se recibió") from None

    def completar(self, mensaje: Mensaje) -> None:
        self._soltar(mensaje)

    def abandonar(self, mensaje: Mensaje) -> None:
        original = self._soltar(mensaje)
        original.visible_desde = self._reloj.ahora()
        self._colas[original.cola].append(original)

    def a_errores(self, mensaje: Mensaje, motivo: str) -> None:
        original = self._soltar(mensaje)
        self._errores[original.cola].append(MensajeEnErrores(original, motivo, self._reloj.ahora()))

    def errores(self, cola: str) -> list[MensajeEnErrores]:
        self._revisar_cola(cola)
        return copy.deepcopy(self._errores[cola])

    def sacar_de_errores(self, cola: str) -> list[MensajeEnErrores]:
        self._revisar_cola(cola)
        sacados, self._errores[cola] = self._errores[cola], []
        return sacados

    def pendientes(self, cola: str) -> int:
        self._revisar_cola(cola)
        en_curso = sum(1 for m in self._bloqueados.values() if m.cola == cola)
        return len(self._colas[cola]) + en_curso

    def proxima_visible(self) -> datetime.datetime | None:
        """Cuándo se vuelve visible el próximo mensaje con demora, en cualquier cola.

        Solo existe en la versión en memoria: el comando local la usa para
        adelantar el reloj en vez de esperar.
        """
        fechas = [m.visible_desde for cola in self._colas.values() for m in cola]
        return min(fechas) if fechas else None
