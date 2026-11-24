"""Colas de Azure Service Bus en modo PeekLock.

Los receptores del SDK requieren una instancia por hilo.
El comando local usa ColaEnMemoria.
"""

import json
import os
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Self
from uuid import uuid4

from azure.core.credentials import TokenCredential
from azure.core.exceptions import (
    ClientAuthenticationError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.identity import DefaultAzureCredential
from azure.servicebus import (
    ServiceBusClient,
    ServiceBusMessage,
    ServiceBusReceivedMessage,
    ServiceBusReceiveMode,
    ServiceBusReceiver,
    ServiceBusSender,
    ServiceBusSubQueue,
)
from azure.servicebus.exceptions import (
    MessageAlreadySettled,
    MessageLockLostError,
    MessageSizeExceededError,
    MessagingEntityDisabledError,
    MessagingEntityNotFoundError,
    OperationTimeoutError,
    ServiceBusAuthenticationError,
    ServiceBusAuthorizationError,
    ServiceBusCommunicationError,
    ServiceBusConnectionError,
    ServiceBusError,
    ServiceBusServerBusyError,
)

from .cola import COLAS, BloqueoPerdido, Cola, ErrorCola, Mensaje, MensajeEnErrores
from .errores import ErrorDeConfiguracion, ErrorTransitorio

PREFIJO_COLAS = "evaluacion-ofertas-"
ESPERA_SERVICIO_OCUPADO_S = 10
ESPERA_REENVIO_S = 1
TAMANO_PAGINA = 100
# Standard admite 256 KiB por mensaje. Dejamos margen para las cabeceras y el motivo de errores.
LIMITE_MENSAJE_BYTES = 248_000
LIMITE_RAZON = 200
# El SDK de Python envía los campos tal cual. La API de .NET documenta un límite de 4096 unidades UTF-16.
LIMITE_DESCRIPCION_UTF16 = 4096
_METADATOS_ERRORES = {"DeadLetterReason", "DeadLetterErrorDescription"}
_FALLAS_DE_ACCESO = (
    ClientAuthenticationError, ServiceBusAuthenticationError, ServiceBusAuthorizationError,
    MessagingEntityDisabledError, MessagingEntityNotFoundError,
)
_FALLAS_DE_RED = (
    ServiceBusConnectionError, ServiceBusCommunicationError, OperationTimeoutError,
    ServiceRequestError, ServiceResponseError,
)


class ErrorServiceBus(Exception):
    """Falla inesperada de Service Bus, sin detalles del servidor."""


@contextmanager
def _traducir_fallas(operacion: str, cola: str | None = None, *, tamano: int | None = None) -> Iterator[None]:
    try:
        yield
    except (ServiceBusError, ClientAuthenticationError, ServiceRequestError, ServiceResponseError,
            MessageAlreadySettled) as error:
        # El transporte pyamqp puede envolver una excepción de la credencial en ServiceBusError.
        causa = error.inner_exception if type(error) is ServiceBusError else None
        if isinstance(causa, _FALLAS_DE_ACCESO + _FALLAS_DE_RED):
            error = causa
        destino = f" en {cola}" if cola else ""
        mensaje = f"Service Bus {operacion}{destino} ({type(error).__name__})"
        if isinstance(error, _FALLAS_DE_ACCESO):
            raise ErrorDeConfiguracion(
                f"{mensaje}. Revisa el rol de Service Bus, `az login` y el nombre y estado de la cola."
            ) from None
        if isinstance(error, ServiceBusServerBusyError):
            raise ErrorTransitorio(mensaje, espera_s=ESPERA_SERVICIO_OCUPADO_S) from None
        if isinstance(error, _FALLAS_DE_RED):
            raise ErrorTransitorio(mensaje) from None
        if isinstance(error, MessageLockLostError):
            raise BloqueoPerdido(mensaje) from None
        if isinstance(error, MessageAlreadySettled):
            raise ErrorCola(mensaje) from None
        if isinstance(error, MessageSizeExceededError):
            detalle = f": mensaje de {tamano} bytes" if tamano is not None else ""
            raise ErrorCola(f"{mensaje}{detalle}") from None
        raise ErrorServiceBus(mensaje) from None


def _cerrar(recurso, operacion: str, cola: str | None = None) -> None:
    with _traducir_fallas(operacion, cola):
        recurso.close()


def _texto(valor):
    return valor.decode("utf-8") if isinstance(valor, bytes) else valor


def _mensaje(cola: str, original: ServiceBusReceivedMessage, *, en_errores: bool = False) -> Mensaje:
    """El SDK lee delivery_count del encabezado AMQP 1.0, §3.2.1.

    AMQP cuenta los intentos fallidos anteriores y su valor inicial es 0.
    La interfaz Cola cuenta también la entrega actual.
    """
    cuerpo = original.body
    if not isinstance(cuerpo, (str, bytes)):
        cuerpo = b"".join(cuerpo)
    propiedades = {_texto(clave): _texto(valor) for clave, valor in (original.application_properties or {}).items()}
    if en_errores:
        for clave in _METADATOS_ERRORES:
            propiedades.pop(clave, None)
    bloqueo = original.lock_token
    return Mensaje(id=original.message_id, cola=cola, cuerpo=json.loads(cuerpo), propiedades=propiedades,
                   entregas=(original.delivery_count or 0) + 1, bloqueo=str(bloqueo) if bloqueo is not None else None)


class ColaServiceBus(Cola):
    def __init__(self, cliente: ServiceBusClient, prefijo: str = PREFIJO_COLAS, espera_recibir_s: float = 5) -> None:
        self._cliente = cliente
        self._prefijo = prefijo
        self._espera_recibir_s = espera_recibir_s
        self._emisores: dict[str, ServiceBusSender] = {}
        self._receptores: dict[tuple[str, ServiceBusSubQueue | None], ServiceBusReceiver] = {}
        self._bloqueados: dict[str, tuple[str, ServiceBusReceivedMessage, ServiceBusReceiver]] = {}
        self._abandonados: dict[tuple[str, str], set[str]] = {}
        self._recursos = ExitStack()
        self._recursos.callback(_cerrar, cliente, "cerrar cliente")
        self._cerrada = False

    def _nombre(self, cola: str) -> str:
        if cola not in COLAS:
            raise ErrorCola("Cola desconocida")
        if self._cerrada:
            raise ErrorCola("La conexión a Service Bus está cerrada")
        return self._prefijo + cola

    def _emisor(self, cola: str, nombre: str) -> ServiceBusSender:
        if cola not in self._emisores:
            with _traducir_fallas("get_queue_sender", cola):
                emisor = self._cliente.get_queue_sender(queue_name=nombre)
            self._recursos.callback(_cerrar, emisor, "cerrar emisor", cola)
            self._emisores[cola] = emisor
        return self._emisores[cola]

    def _receptor(self, cola: str, subcola: ServiceBusSubQueue | None = None) -> ServiceBusReceiver:
        nombre = self._nombre(cola)
        clave = (cola, subcola)
        if clave not in self._receptores:
            espera = self._espera_recibir_s if subcola is None else min(self._espera_recibir_s, ESPERA_REENVIO_S)
            with _traducir_fallas("get_queue_receiver", cola):
                receptor = self._cliente.get_queue_receiver(
                    queue_name=nombre, sub_queue=subcola, receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
                    prefetch_count=0, max_wait_time=espera,
                )
            self._recursos.callback(_cerrar, receptor, "cerrar receptor", cola)
            self._receptores[clave] = receptor
        return self._receptores[clave]

    def publicar(self, cola: str, cuerpo: dict, demora_s: float = 0, propiedades: dict | None = None) -> str:
        nombre = self._nombre(cola)
        if demora_s < 0:
            raise ErrorCola("La demora no puede ser negativa")
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        if propiedades is None:
            propiedades = {}
        if not isinstance(propiedades, dict) or any(
            not isinstance(clave, str) or not isinstance(valor, (str, int, float, bool))
            for clave, valor in propiedades.items()
        ):
            raise TypeError("Las propiedades de Service Bus requieren claves de texto y valores JSON simples")
        tamano = len(datos) + len(json.dumps(propiedades, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if tamano > LIMITE_MENSAJE_BYTES:
            raise ErrorCola(f"Service Bus publicar en {cola}: mensaje de {tamano} bytes, límite {LIMITE_MENSAJE_BYTES}")
        id_mensaje = str(uuid4())
        programado = datetime.now(timezone.utc) + timedelta(seconds=demora_s) if demora_s > 0 else None
        with _traducir_fallas("send_messages", cola, tamano=tamano):
            mensaje = ServiceBusMessage(datos, application_properties=propiedades, message_id=id_mensaje,
                                        content_type="application/json", scheduled_enqueue_time_utc=programado)
            self._emisor(cola, nombre).send_messages(mensaje)
        return id_mensaje

    @staticmethod
    def _recibir(cola: str, receptor: ServiceBusReceiver, espera: float) -> ServiceBusReceivedMessage | None:
        with _traducir_fallas("receive_messages", cola):
            mensajes = receptor.receive_messages(max_message_count=1, max_wait_time=espera)
        return mensajes[0] if mensajes else None

    def recibir(self, cola: str) -> Mensaje | None:
        receptor = self._receptor(cola)
        original = self._recibir(cola, receptor, self._espera_recibir_s)
        if original is None:
            return None
        mensaje = _mensaje(cola, original)
        if mensaje.bloqueo is None:
            raise ErrorCola(f"Service Bus recibir en {cola}: entrega sin bloqueo")
        self._bloqueados[mensaje.bloqueo] = (cola, original, receptor)
        return mensaje

    @staticmethod
    def _resolver_sdk(cola: str, receptor: ServiceBusReceiver, original: ServiceBusReceivedMessage,
                      operacion: str, **opciones) -> None:
        with _traducir_fallas(operacion, cola):
            getattr(receptor, operacion)(original, **opciones)

    def _resolver(self, mensaje: Mensaje, operacion: str, **opciones) -> None:
        bloqueo = mensaje.bloqueo
        clave = (mensaje.cola, mensaje.id)
        entrega = self._bloqueados.pop(bloqueo, None) if bloqueo is not None else None
        if entrega is None:
            if bloqueo in self._abandonados.get(clave, ()):
                raise BloqueoPerdido(f"Service Bus {operacion} en {mensaje.cola}: entrega abandonada")
            raise ErrorCola("La entrega ya se resolvió o nunca se recibió")
        cola, original, receptor = entrega
        self._resolver_sdk(cola, receptor, original, operacion, **opciones)
        clave_original = (cola, original.message_id)
        if operacion == "abandon_message":
            # Conservamos solo el token anterior, para distinguir una copia obsoleta de una entrega desconocida.
            self._abandonados.setdefault(clave_original, set()).add(bloqueo)
        else:
            self._abandonados.pop(clave_original, None)

    def completar(self, mensaje: Mensaje) -> None:
        self._resolver(mensaje, "complete_message")

    def abandonar(self, mensaje: Mensaje) -> None:
        self._resolver(mensaje, "abandon_message")

    def a_errores(self, mensaje: Mensaje, motivo: str) -> None:
        unidades = motivo[:LIMITE_DESCRIPCION_UTF16].encode("utf-16-le")
        descripcion = unidades[:2 * LIMITE_DESCRIPCION_UTF16].decode("utf-16-le", errors="ignore")
        self._resolver(mensaje, "dead_letter_message", reason=motivo[:LIMITE_RAZON], error_description=descripcion)

    def _ver(self, cola: str, subcola: ServiceBusSubQueue | None = None) -> Iterator[ServiceBusReceivedMessage]:
        receptor = self._receptor(cola, subcola)
        # El SDK interpreta 0 como continuar desde lo último recibido. Pedimos el principio explícitamente.
        secuencia = 1
        while True:
            with _traducir_fallas("peek_messages", cola):
                pagina = receptor.peek_messages(sequence_number=secuencia, max_message_count=TAMANO_PAGINA)
            if not pagina:
                return
            yield from pagina
            secuencia = pagina[-1].sequence_number + 1

    def errores(self, cola: str) -> list[MensajeEnErrores]:
        mensajes = [
            MensajeEnErrores(_mensaje(cola, original, en_errores=True),
                             original.dead_letter_error_description or original.dead_letter_reason or "",
                             original.enqueued_time_utc)
            for original in self._ver(cola, ServiceBusSubQueue.DEAD_LETTER)
        ]
        return sorted(mensajes, key=lambda error: error.cuando)

    def pendientes(self, cola: str) -> int:
        """Conteo de diagnóstico que incluye bloqueados y programados. No usar como condición de salida."""
        return sum(1 for _ in self._ver(cola))

    def reenviar_errores(self, cola: str) -> int:
        receptor = self._receptor(cola, ServiceBusSubQueue.DEAD_LETTER)
        espera = min(self._espera_recibir_s, ESPERA_REENVIO_S)
        reenviados = 0
        while (original := self._recibir(cola, receptor, espera)) is not None:
            try:
                mensaje = _mensaje(cola, original, en_errores=True)
                mensaje.propiedades.pop("intento", None)
                mensaje.propiedades.pop("esperas", None)
                self.publicar(cola, mensaje.cuerpo, propiedades=mensaje.propiedades)
            except Exception:
                # Si también falla el abandono, el bloqueo vence y el original queda en errores.
                with suppress(BloqueoPerdido, ErrorCola, ErrorServiceBus, ErrorTransitorio, ErrorDeConfiguracion):
                    self._resolver_sdk(cola, receptor, original, "abandon_message")
                raise
            self._resolver_sdk(cola, receptor, original, "complete_message")
            reenviados += 1
        return reenviados

    def cerrar(self) -> None:
        self._cerrada = True
        self._bloqueados.clear()
        self._abandonados.clear()
        self._receptores.clear()
        self._emisores.clear()
        self._recursos.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.cerrar()


def cola_desde_entorno(
    crear_cliente: Callable[..., ServiceBusClient] = ServiceBusClient, *, credencial: TokenCredential | None = None,
) -> ColaServiceBus:
    """Arma el cliente con el nombre completo y la identidad del entorno."""
    namespace = os.environ.get("SERVICEBUS_NAMESPACE", "").strip()
    if not namespace:
        raise ErrorDeConfiguracion("Falta SERVICEBUS_NAMESPACE")
    prefijo = os.environ.get("COLAS_PREFIJO", PREFIJO_COLAS)
    with _traducir_fallas("crear cliente"):
        try:
            if credencial is None:
                credencial = DefaultAzureCredential(exclude_interactive_browser_credential=True)
            cliente = crear_cliente(fully_qualified_namespace=namespace, credential=credencial)
        except (MessageAlreadySettled, ServiceBusError):
            raise
        except ValueError as error:
            raise ErrorDeConfiguracion(
                f"Service Bus crear cliente ({type(error).__name__}). Revisa SERVICEBUS_NAMESPACE y la identidad."
            ) from None
    return ColaServiceBus(cliente, prefijo)
