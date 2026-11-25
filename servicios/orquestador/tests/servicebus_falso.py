"""El subconjunto del SDK de Service Bus que usa el adaptador, sin red."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from time import monotonic, sleep
from uuid import UUID, uuid4

from azure.servicebus import (
    ServiceBusMessage,
    ServiceBusReceiveMode,
    ServiceBusSubQueue,
)
from azure.servicebus.exceptions import MessageAlreadySettled, MessageLockLostError, ServiceBusError


@dataclass
class _EnCola:
    enviado: ServiceBusMessage
    secuencia: int
    cuando: datetime
    disponible: datetime
    entregas_fallidas: int = 0
    bloqueo: UUID | None = None
    motivo: str | None = None
    descripcion: str | None = None


class MensajeRecibidoFalso:
    def __init__(self, mensaje: _EnCola, receptor: "ReceptorFalso", *, recibido: bool):
        self._original = mensaje
        self._receptor = receptor
        self._resuelto = False
        self._bloqueo = mensaje.bloqueo if recibido else None
        self.delivery_count = mensaje.entregas_fallidas
        self.body_type = mensaje.enviado.body_type
        self.message_id = mensaje.enviado.message_id
        self.sequence_number = mensaje.secuencia
        self.enqueued_time_utc = mensaje.cuando
        self.dead_letter_reason = mensaje.motivo
        self.dead_letter_error_description = mensaje.descripcion
        propiedades = dict(mensaje.enviado.application_properties or {})
        if mensaje.motivo is not None:
            propiedades["DeadLetterReason"] = mensaje.motivo
        if mensaje.descripcion is not None:
            propiedades["DeadLetterErrorDescription"] = mensaje.descripcion
        self.application_properties = {
            (clave.encode("utf-8") if isinstance(clave, str) else clave):
            valor.encode("utf-8") if isinstance(valor, str) else valor
            for clave, valor in propiedades.items()
        } or None

    @property
    def body(self):
        cuerpo = self._original.enviado.body
        datos = cuerpo if isinstance(cuerpo, bytes) else b"".join(cuerpo)
        mitad = len(datos) // 2
        yield datos[:mitad]
        yield datos[mitad:]

    @property
    def lock_token(self):
        return None if self._resuelto else self._bloqueo


class EmisorFalso:
    def __init__(self, cliente: "ServiceBusFalso", nombre: str):
        self.cliente = cliente
        self.nombre = nombre
        self.cerrado = False

    def send_messages(self, mensaje: ServiceBusMessage) -> None:
        self.cliente.operar("send_messages")
        assert not self.cerrado and isinstance(mensaje, ServiceBusMessage)
        ahora = datetime.now(timezone.utc)
        self.cliente.envios.append((self.nombre, mensaje))
        registro = _EnCola(mensaje, next(self.cliente.secuencias), ahora, mensaje.scheduled_enqueue_time_utc or ahora)
        self.cliente.colas[self.nombre, None].append(registro)

    def close(self) -> None:
        self.cliente.operar("close_sender")
        self.cerrado = True


class ReceptorFalso:
    def __init__(self, cliente: "ServiceBusFalso", nombre: str, subcola, modo, prefetch: int, espera: float | None):
        if espera is not None and espera <= 0:
            raise ValueError("The max_wait_time must be greater than 0.")
        self.cliente = cliente
        self.nombre = nombre
        self.subcola = subcola
        self.modo = modo
        self.prefetch = prefetch
        self.espera = espera
        self.cerrado = False
        self.abierto = False
        self.llamadas_recibir = []
        self.llamadas_peek = []
        self.entregas = []

    @property
    def _mensajes(self):
        return self.cliente.colas[self.nombre, self.subcola]

    def __enter__(self):
        assert not self.cerrado
        self.abierto = True
        return self

    def receive_messages(self, *, max_message_count: int, max_wait_time: float | None = None):
        self.cliente.operar("receive_messages")
        assert not self.cerrado and self.modo == ServiceBusReceiveMode.PEEK_LOCK and self.prefetch == 0
        if max_wait_time is not None and max_wait_time <= 0:
            raise ValueError("The max_wait_time must be greater than 0.")
        self.abierto = True
        self.llamadas_recibir.append((max_message_count, max_wait_time))
        espera = max_wait_time if max_wait_time is not None else self.espera or 60
        limite = monotonic() + espera
        while True:
            ahora = datetime.now(timezone.utc)
            visibles = [m for m in self._mensajes if m.bloqueo is None and m.disponible <= ahora][:max_message_count]
            if visibles:
                entregas = []
                for mensaje in visibles:
                    mensaje.bloqueo = uuid4()
                    entregas.append(MensajeRecibidoFalso(mensaje, self, recibido=True))
                self.entregas.extend(entregas)
                return entregas
            restante = limite - monotonic()
            if restante <= 0:
                return []
            sleep(min(restante, 0.005))

    def peek_messages(self, *, sequence_number: int, max_message_count: int, timeout: float | None = None):
        self.cliente.operar("peek_messages")
        assert not self.cerrado
        if timeout is not None and timeout <= 0:
            raise ValueError("The timeout must be greater than 0.")
        self.abierto = True
        self.llamadas_peek.append((sequence_number, max_message_count))
        mensajes = sorted(self._mensajes, key=lambda mensaje: mensaje.secuencia)
        limite = min(max_message_count, self.cliente.tope_peek)
        pagina = [m for m in mensajes if m.secuencia >= sequence_number][:limite]
        return [MensajeRecibidoFalso(mensaje, self, recibido=False) for mensaje in pagina]

    def _resolver(self, mensaje: MensajeRecibidoFalso, operacion: str) -> _EnCola:
        assert not self.cerrado and mensaje._receptor is self
        if mensaje._resuelto:
            raise MessageAlreadySettled(action=operacion)
        if not self.abierto:
            raise ValueError("El enlace del receptor está cerrado")
        try:
            self.cliente.operar(operacion)
        except ServiceBusError as error:
            if error._shutdown_handler:
                self.abierto = False
            raise
        original = mensaje._original
        if mensaje.lock_token is None or mensaje.lock_token != original.bloqueo:
            raise MessageLockLostError()
        original.bloqueo = None
        mensaje._resuelto = True
        return original

    def complete_message(self, mensaje: MensajeRecibidoFalso) -> None:
        original = self._resolver(mensaje, "complete_message")
        self._mensajes.remove(original)

    def abandon_message(self, mensaje: MensajeRecibidoFalso) -> None:
        original = self._resolver(mensaje, "abandon_message")
        original.entregas_fallidas += 1

    def vencer_bloqueo(self, mensaje: MensajeRecibidoFalso) -> None:
        assert mensaje._receptor is self and mensaje.lock_token == mensaje._original.bloqueo
        mensaje._original.bloqueo = None
        mensaje._original.entregas_fallidas += 1

    def dead_letter_message(self, mensaje: MensajeRecibidoFalso, *, reason: str, error_description: str) -> None:
        original = self._resolver(mensaje, "dead_letter_message")
        self._mensajes.remove(original)
        original.motivo = reason
        original.descripcion = error_description
        self.cliente.colas[self.nombre, ServiceBusSubQueue.DEAD_LETTER].append(original)

    def close(self) -> None:
        self.cliente.operar("close_receiver")
        self.cerrado = True


class RenovadorFalso:
    def __init__(self, cliente: "ServiceBusFalso", *, max_lock_renewal_duration: float,
                 max_workers: int, on_lock_renew_failure=None):
        self.cliente = cliente
        self.max_lock_renewal_duration = max_lock_renewal_duration
        self.on_lock_renew_failure = on_lock_renew_failure
        self.max_workers = max_workers
        self.registros: list[tuple[ReceptorFalso, MensajeRecibidoFalso]] = []
        self._avisos = {}
        self.cerrado = False

    def register(self, receptor: ReceptorFalso, mensaje: MensajeRecibidoFalso, *, on_lock_renew_failure=None) -> None:
        assert not self.cerrado and mensaje._receptor is receptor
        self.registros.append((receptor, mensaje))
        self._avisos[mensaje] = on_lock_renew_failure or self.on_lock_renew_failure

    def fallar(self, mensaje: MensajeRecibidoFalso, error: Exception | None) -> None:
        if aviso := self._avisos[mensaje]:
            aviso(mensaje, error)

    def close(self) -> None:
        self.cliente.operar("close_renewer")
        self.cerrado = True


class ServiceBusFalso:
    def __init__(self, *, tope_peek: int = 100):
        self.colas = defaultdict(list)
        self.secuencias = count(1)
        self.tope_peek = tope_peek
        self.emisores = []
        self.receptores = []
        self.renovadores: list[RenovadorFalso] = []
        self.envios = []
        self.fallas: dict[str, Exception] = {}
        self.operaciones: list[str] = []
        self.cerrado = False

    def operar(self, operacion: str) -> None:
        self.operaciones.append(operacion)
        if falla := self.fallas.get(operacion):
            raise falla

    def get_queue_sender(self, queue_name: str) -> EmisorFalso:
        self.operar("get_queue_sender")
        assert not self.cerrado
        emisor = EmisorFalso(self, queue_name)
        self.emisores.append(emisor)
        return emisor

    def get_queue_receiver(self, queue_name: str, *, sub_queue=None, receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
                           prefetch_count=0, max_wait_time=None) -> ReceptorFalso:
        self.operar("get_queue_receiver")
        assert not self.cerrado
        receptor = ReceptorFalso(self, queue_name, sub_queue, receive_mode, prefetch_count, max_wait_time)
        self.receptores.append(receptor)
        return receptor

    def crear_renovador(self, **opciones) -> RenovadorFalso:
        renovador = RenovadorFalso(self, **opciones)
        self.renovadores.append(renovador)
        return renovador

    def close(self) -> None:
        self.operar("close_client")
        self.cerrado = True
