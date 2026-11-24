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
import functools
import threading
import datetime
import itertools
import json
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from uuid import uuid4

from .reloj import Reloj, RelojSistema

PROCESOS_LISTOS = "procesos-listos"
NORMALIZAR = "normalizar"
CLASIFICAR = "clasificar"
EXTRAER = "extraer"
COLAS = (PROCESOS_LISTOS, NORMALIZAR, CLASIFICAR, EXTRAER)


class ErrorCola(Exception):
    """Uso incorrecto de la cola: un bug (clase 4)."""


class BloqueoPerdido(Exception):
    """El bloqueo de esta entrega venció o el mensaje se volvió a entregar."""


@dataclass
class Mensaje:
    id: str
    cola: str
    cuerpo: dict
    propiedades: dict = field(default_factory=dict)
    entregas: int = 0
    """Cuántas veces se recibió. Service Bus lo lleva como DeliveryCount."""
    visible_desde: datetime.datetime | None = None
    bloqueo: str | None = None
    """Identifica la entrega actual del mensaje."""


@dataclass
class MensajeEnErrores:
    mensaje: Mensaje
    motivo: str
    cuando: datetime.datetime


class Cola(ABC):
    """Completar, abandonar o mandar a errores requiere el bloqueo de la entrega.

    Si se perdió el bloqueo, da BloqueoPerdido. Si el mensaje ya salió de la cola
    o nunca se recibió, da ErrorCola.
    """

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
    def reenviar_errores(self, cola: str) -> int:
        """Republica los mensajes de errores desde el más viejo y devuelve cuántos reenvió.

        Conserva el cuerpo y las propiedades salvo `intento` y `esperas`. Cada
        mensaje reenviado es nuevo y se quita de errores tras publicarlo.
        """

    @abstractmethod
    def pendientes(self, cola: str) -> int:
        """Mensajes que faltan por completar, visibles o no, sin contar errores."""



def _con_candado(metodo):
    """Una operación a la vez: el comando local normaliza varias entregas en
    hilos, y la versión en memoria debe portarse como el servicio real, donde
    cada operación es atómica."""

    @functools.wraps(metodo)
    def envuelto(self, *args, **kwargs):
        with self._candado:
            return metodo(self, *args, **kwargs)

    return envuelto


class ColaEnMemoria(Cola):
    def __init__(self, reloj: Reloj | None = None) -> None:
        self._reloj = reloj or RelojSistema()
        self._colas: dict[str, list[Mensaje]] = defaultdict(list)
        self._bloqueados: dict[str, Mensaje] = {}
        self._errores: dict[str, deque[MensajeEnErrores]] = defaultdict(deque)
        self._ids = itertools.count(1)
        self._candado = threading.RLock()

    @staticmethod
    def _revisar_cola(cola: str) -> None:
        if cola not in COLAS:
            raise ErrorCola(f"Cola desconocida: {cola}")

    @_con_candado
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

    @_con_candado
    def recibir(self, cola: str) -> Mensaje | None:
        self._revisar_cola(cola)
        ahora = self._reloj.ahora()
        visibles = [m for m in self._colas[cola] if m.visible_desde <= ahora]
        if not visibles:
            return None
        mensaje = min(visibles, key=lambda m: (m.visible_desde, m.id))
        self._colas[cola].remove(mensaje)
        mensaje.entregas += 1
        mensaje.bloqueo = uuid4().hex
        self._bloqueados[mensaje.id] = mensaje
        return copy.deepcopy(mensaje)

    def _soltar(self, mensaje: Mensaje) -> Mensaje:
        if mensaje.bloqueo is not None:
            vigente = self._bloqueados.get(mensaje.id)
            if vigente is not None and mensaje.bloqueo == vigente.bloqueo:
                return self._bloqueados.pop(mensaje.id)
            if vigente is not None or any(
                pendiente.id == mensaje.id and pendiente.entregas > 0 for pendiente in self._colas.get(mensaje.cola, ())
            ):
                raise BloqueoPerdido(f"Se perdió el bloqueo del mensaje {mensaje.id}")
        raise ErrorCola(f"El mensaje {mensaje.id} no está bloqueado: ya salió de la cola o nunca se recibió")

    @_con_candado
    def completar(self, mensaje: Mensaje) -> None:
        self._soltar(mensaje)

    @_con_candado
    def abandonar(self, mensaje: Mensaje) -> None:
        original = self._soltar(mensaje)
        original.visible_desde = self._reloj.ahora()
        self._colas[original.cola].append(original)

    @_con_candado
    def a_errores(self, mensaje: Mensaje, motivo: str) -> None:
        original = self._soltar(mensaje)
        self._errores[original.cola].append(MensajeEnErrores(original, motivo, self._reloj.ahora()))

    @_con_candado
    def errores(self, cola: str) -> list[MensajeEnErrores]:
        self._revisar_cola(cola)
        return copy.deepcopy(list(self._errores[cola]))

    @_con_candado
    def reenviar_errores(self, cola: str) -> int:
        self._revisar_cola(cola)
        en_errores = self._errores[cola]
        reenviados = 0
        while en_errores:
            mensaje = en_errores[0].mensaje
            propiedades = {k: v for k, v in mensaje.propiedades.items() if k not in ("intento", "esperas")}
            self.publicar(cola, mensaje.cuerpo, propiedades=propiedades)
            en_errores.popleft()
            reenviados += 1
        return reenviados

    @_con_candado
    def pendientes(self, cola: str) -> int:
        self._revisar_cola(cola)
        en_curso = sum(1 for m in self._bloqueados.values() if m.cola == cola)
        return len(self._colas[cola]) + en_curso

    @_con_candado
    def proxima_visible(self) -> datetime.datetime | None:
        """Cuándo se vuelve visible el próximo mensaje con demora, en cualquier cola.

        Solo existe en la versión en memoria: el comando local la usa para
        adelantar el reloj en vez de esperar.
        """
        fechas = [m.visible_desde for cola in self._colas.values() for m in cola]
        return min(fechas) if fechas else None
