"""Colas de Azure Service Bus en modo PeekLock.

Los receptores del SDK requieren una instancia por hilo. Los envíos pueden venir
de varios hilos: van de a uno, con un candado.
El comando local usa ColaEnMemoria.
"""

import json
import threading
import logging
import os
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import partial
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
    AutoLockRenewer,
    ServiceBusClient,
    ServiceBusMessage,
    ServiceBusReceivedMessage,
    ServiceBusReceiveMode,
    ServiceBusReceiver,
    ServiceBusSender,
    ServiceBusSubQueue,
)
from azure.servicebus.amqp import AmqpMessageBodyType
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

from .cola import (
    COLAS, _METADATOS_ERRORES, BloqueoPerdido, Cola, ErrorCola, Mensaje, MensajeEnErrores,
    _serializar_cuerpo, _validar_propiedades,
)
from .errores import ErrorDeConfiguracion, ErrorTransitorio
from .parametros import PARAMETROS, Parametros

registro = logging.getLogger(__name__)

PREFIJO_COLAS = "evaluacion-ofertas-"
ESPERA_SERVICIO_OCUPADO_S = 10
ESPERA_REENVIO_S = 1
LIMITE_TOKENS_ABANDONADOS = 1000
LIMITE_LECTURAS_POR_RECEPCION = 10
MOTIVO_MENSAJE_ILEGIBLE = "Mensaje ilegible: se esperaba un objeto JSON con propiedades legibles"
# Un hilo para el despachador del SDK y otro para renovar la entrega del worker.
HILOS_RENOVADOR = 2
TAMANO_PAGINA = 100
# Standard admite 256 KiB por mensaje. Dejamos margen para las cabeceras y el motivo de errores.
LIMITE_MENSAJE_BYTES = 248_000
LIMITE_RAZON = 200
# El SDK de Python envía los campos tal cual. La API de .NET documenta un límite de 4096 unidades UTF-16.
LIMITE_DESCRIPCION_UTF16 = 4096
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


class _EntregaYaResuelta(ErrorCola):
    """El SDK confirma que la entrega ya se resolvió."""


class _MensajeIlegible(ErrorCola):
    """El cuerpo o las propiedades del mensaje no se pueden leer."""


def _causa_conocida(error: ServiceBusError) -> BaseException:
    # pyamqp envuelve fallas de la credencial y el TimeoutError de CBS en ServiceBusError.
    pendientes = [error.__context__, error.__cause__, error.inner_exception]
    vistos = {id(error)}
    while pendientes:
        causa = pendientes.pop()
        if not isinstance(causa, BaseException) or id(causa) in vistos:
            continue
        if isinstance(causa, _FALLAS_DE_ACCESO + _FALLAS_DE_RED + (OSError,)):
            return causa
        vistos.add(id(causa))
        pendientes.extend((causa.__context__, causa.__cause__, getattr(causa, "inner_exception", None)))
    return error


@contextmanager
def _traducir_fallas(operacion: str, cola: str | None = None, *, tamano: int | None = None) -> Iterator[None]:
    try:
        yield
    except (ServiceBusError, ClientAuthenticationError, ServiceRequestError, ServiceResponseError,
            MessageAlreadySettled) as error:
        if type(error) is ServiceBusError:
            error = _causa_conocida(error)
        destino = f" en {cola}" if cola else ""
        mensaje = f"Service Bus {operacion}{destino} ({type(error).__name__})"
        if isinstance(error, _FALLAS_DE_ACCESO):
            raise ErrorDeConfiguracion(
                f"{mensaje}. Revisa el rol de Service Bus, `az login` y el nombre y estado de la cola."
            ) from None
        if isinstance(error, ServiceBusServerBusyError):
            raise ErrorTransitorio(mensaje, espera_s=ESPERA_SERVICIO_OCUPADO_S) from None
        if isinstance(error, _FALLAS_DE_RED + (OSError,)):
            raise ErrorTransitorio(mensaje) from None
        if isinstance(error, MessageLockLostError):
            raise BloqueoPerdido(mensaje) from None
        if isinstance(error, MessageAlreadySettled):
            raise _EntregaYaResuelta(mensaje) from None
        if isinstance(error, MessageSizeExceededError):
            detalle = f": mensaje de {tamano} bytes" if tamano is not None else ""
            raise ErrorCola(f"{mensaje}{detalle}") from None
        raise ErrorServiceBus(mensaje) from None


def _cerrar(recurso, operacion: str, cola: str | None = None) -> None:
    with _traducir_fallas(operacion, cola):
        recurso.close()


def _texto(valor):
    return valor.decode("utf-8") if isinstance(valor, bytes) else valor


def _rechazar_constante_json(_valor: str) -> None:
    raise _MensajeIlegible(MOTIVO_MENSAJE_ILEGIBLE)


def _mensaje(cola: str, original: ServiceBusReceivedMessage, *, en_errores: bool = False,
             tolerar_ilegible: bool = False) -> Mensaje:
    """El SDK lee delivery_count del encabezado AMQP 1.0, §3.2.1.

    AMQP cuenta los intentos fallidos anteriores y su valor inicial es 0.
    La interfaz Cola cuenta también la entrega actual.
    """
    try:
        datos = original.body
        if not isinstance(datos, (str, bytes, bytearray)) and original.body_type == AmqpMessageBodyType.DATA:
            datos = b"".join(datos)
        cuerpo = json.loads(datos, parse_constant=_rechazar_constante_json)
        if not isinstance(cuerpo, dict):
            raise _MensajeIlegible(MOTIVO_MENSAJE_ILEGIBLE)
        propiedades = {_texto(k): _texto(v) for k, v in (original.application_properties or {}).items()}
    except (TypeError, ValueError, RecursionError, _MensajeIlegible):
        if not tolerar_ilegible:
            raise _MensajeIlegible(MOTIVO_MENSAJE_ILEGIBLE) from None
        cuerpo, propiedades = {}, {}
    if en_errores:
        for clave in _METADATOS_ERRORES:
            propiedades.pop(clave, None)
    bloqueo = original.lock_token
    return Mensaje(id=original.message_id, cola=cola, cuerpo=cuerpo, propiedades=propiedades,
                   entregas=(original.delivery_count or 0) + 1, bloqueo=str(bloqueo) if bloqueo is not None else None)


def _motivo_en_errores(original: ServiceBusReceivedMessage) -> str:
    motivo_por_defecto = ""
    for campo in ("dead_letter_error_description", "dead_letter_reason"):
        try:
            if motivo := getattr(original, campo):
                return motivo
        except UnicodeError:
            motivo_por_defecto = MOTIVO_MENSAJE_ILEGIBLE
    return motivo_por_defecto


@dataclass
class _Entrega:
    cola: str
    original: ServiceBusReceivedMessage
    receptor: ServiceBusReceiver


class ColaServiceBus(Cola):
    """Renueva los bloqueos de la cola principal con un renovador por instancia.

    Al completar, abandonar o mandar a errores, el receptor del SDK marca el
    mensaje como `_settled` y `AutoLockRenewer` deja de renovarlo automáticamente.
    """

    def __init__(
        self, cliente: ServiceBusClient, prefijo: str = PREFIJO_COLAS, espera_recibir_s: float = 5, *,
        parametros: Parametros = PARAMETROS, crear_renovador: Callable[..., AutoLockRenewer] = AutoLockRenewer,
        _credencial_propia: DefaultAzureCredential | None = None,
    ) -> None:
        if espera_recibir_s <= 0:
            raise ValueError("espera_recibir_s debe ser mayor que cero")
        self._cliente = cliente
        self._prefijo = prefijo
        self._espera_recibir_s = espera_recibir_s
        self._parametros = parametros
        self._crear_renovador = crear_renovador
        self._renovador: AutoLockRenewer | None = None
        self._emisores: dict[str, ServiceBusSender] = {}
        self._candado_envio = threading.Lock()
        """Los emisores del SDK no aceptan dos envíos a la vez: varios hilos del
        worker publican con la misma cola."""
        self._receptores: dict[tuple[str, ServiceBusSubQueue | None], ServiceBusReceiver] = {}
        self._bloqueados: dict[str, _Entrega] = {}
        self._abandonados: dict[str, tuple[str, str]] = {}
        self._recursos = ExitStack()
        if _credencial_propia is not None:
            self._recursos.callback(_cerrar, _credencial_propia, "cerrar credencial")
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
            with _traducir_fallas("get_queue_receiver", cola):
                receptor = self._cliente.get_queue_receiver(
                    queue_name=nombre, sub_queue=subcola, receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
                    prefetch_count=0, max_wait_time=self._espera_recibir_s,
                )
            self._recursos.callback(_cerrar, receptor, "cerrar receptor", cola)
            self._receptores[clave] = receptor
        return self._receptores[clave]

    def publicar(self, cola: str, cuerpo: dict, demora_s: float = 0, propiedades: dict | None = None) -> str:
        nombre = self._nombre(cola)
        if demora_s < 0:
            raise ErrorCola("La demora no puede ser negativa")
        datos = _serializar_cuerpo(cuerpo).encode("utf-8")
        propiedades = _validar_propiedades(propiedades)
        tamano = len(datos) + len(json.dumps(propiedades, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if tamano > LIMITE_MENSAJE_BYTES:
            raise ErrorCola(f"Service Bus publicar en {cola}: mensaje de {tamano} bytes, límite {LIMITE_MENSAJE_BYTES}")
        id_mensaje = str(uuid4())
        programado = datetime.now(timezone.utc) + timedelta(seconds=demora_s) if demora_s > 0 else None
        with _traducir_fallas("send_messages", cola, tamano=tamano):
            mensaje = ServiceBusMessage(datos, application_properties=propiedades, message_id=id_mensaje,
                                        content_type="application/json", scheduled_enqueue_time_utc=programado)
            with self._candado_envio:
                self._emisor(cola, nombre).send_messages(mensaje)
        return id_mensaje

    @staticmethod
    def _recibir(cola: str, receptor: ServiceBusReceiver, espera: float) -> ServiceBusReceivedMessage | None:
        with _traducir_fallas("receive_messages", cola):
            mensajes = receptor.receive_messages(max_message_count=1, max_wait_time=espera)
        return mensajes[0] if mensajes else None

    def recibir(self, cola: str) -> Mensaje | None:
        receptor = self._receptor(cola)
        for _ in range(LIMITE_LECTURAS_POR_RECEPCION):
            original = self._recibir(cola, receptor, self._espera_recibir_s)
            if original is None:
                return None
            try:
                mensaje = _mensaje(cola, original)
            except _MensajeIlegible:
                registro.warning("Mensaje ilegible %s en %s", original.message_id, cola)
                self._resolver_sdk(cola, receptor, original, "dead_letter_message",
                                   reason=MOTIVO_MENSAJE_ILEGIBLE, error_description=MOTIVO_MENSAJE_ILEGIBLE)
                continue
            if mensaje.bloqueo is None:
                raise ErrorCola(f"Service Bus recibir en {cola}: entrega sin bloqueo")
            self._registrar_renovacion(cola, receptor, original)
            self._bloqueados[mensaje.bloqueo] = _Entrega(cola, original, receptor)
            return mensaje
        return None

    def _registrar_renovacion(self, cola: str, receptor: ServiceBusReceiver,
                              original: ServiceBusReceivedMessage) -> None:
        with _traducir_fallas("registrar renovación", cola):
            if self._renovador is None:
                self._renovador = self._crear_renovador(
                    max_lock_renewal_duration=self._parametros.renovacion_bloqueo_max_s,
                    max_workers=HILOS_RENOVADOR,
                )
            self._renovador.register(receptor, original, on_lock_renew_failure=partial(self._avisar_falla_renovacion, cola))

    @staticmethod
    def _avisar_falla_renovacion(cola: str, original: ServiceBusReceivedMessage, error: Exception | None) -> None:
        tipo_error = type(error).__name__ if error is not None else "sin excepción"
        registro.warning("Falló la renovación del bloqueo del mensaje %s en %s (%s)",
                         original.message_id, cola, tipo_error)

    @staticmethod
    def _resolver_sdk(cola: str, receptor: ServiceBusReceiver, original: ServiceBusReceivedMessage,
                      operacion: str, **opciones) -> None:
        with _traducir_fallas(operacion, cola):
            # El SDK puede cerrar el enlace tras un fallo. Reabre el mismo receptor
            # para que pyamqp pueda resolver por el token si perdió el enlace original.
            receptor.__enter__()
            getattr(receptor, operacion)(original, **opciones)

    def _resolver(self, mensaje: Mensaje, operacion: str, **opciones) -> None:
        bloqueo = mensaje.bloqueo
        if bloqueo is None:
            raise ErrorCola("La entrega ya se resolvió o nunca se recibió")
        clave = (mensaje.cola, mensaje.id)
        entrega = self._bloqueados.get(bloqueo)
        if entrega is None:
            if self._abandonados.get(bloqueo) == clave:
                raise BloqueoPerdido(f"Service Bus {operacion} en {mensaje.cola}: entrega abandonada")
            raise ErrorCola("La entrega ya se resolvió o nunca se recibió")
        if clave != (entrega.cola, entrega.original.message_id):
            raise BloqueoPerdido(f"Service Bus {operacion} en {mensaje.cola}: el bloqueo corresponde a otro mensaje")
        try:
            self._resolver_sdk(entrega.cola, entrega.receptor, entrega.original, operacion, **opciones)
        except (BloqueoPerdido, _EntregaYaResuelta):
            del self._bloqueados[bloqueo]
            raise
        del self._bloqueados[bloqueo]
        if operacion == "abandon_message":
            self._abandonados[bloqueo] = clave
            if len(self._abandonados) > LIMITE_TOKENS_ABANDONADOS:
                del self._abandonados[next(iter(self._abandonados))]
        else:
            for anterior, abandonado in tuple(self._abandonados.items()):
                if abandonado == clave:
                    del self._abandonados[anterior]

    def completar(self, mensaje: Mensaje) -> None:
        self._resolver(mensaje, "complete_message")

    def abandonar(self, mensaje: Mensaje) -> None:
        self._resolver(mensaje, "abandon_message")

    def a_errores(self, mensaje: Mensaje, motivo: str) -> None:
        unidades = motivo[:LIMITE_DESCRIPCION_UTF16].encode("utf-16-le")
        descripcion = unidades[:2 * LIMITE_DESCRIPCION_UTF16].decode("utf-16-le", errors="ignore")
        self._resolver(mensaje, "dead_letter_message", reason=motivo[:LIMITE_RAZON], error_description=descripcion)

    def _ver(self, cola: str, subcola: ServiceBusSubQueue | None = None, *,
             timeout: float | None = None) -> Iterator[ServiceBusReceivedMessage]:
        receptor = self._receptor(cola, subcola)
        # El SDK interpreta 0 como continuar desde lo último recibido. Pedimos el principio explícitamente.
        secuencia = 1
        while True:
            with _traducir_fallas("peek_messages", cola):
                pagina = receptor.peek_messages(sequence_number=secuencia, max_message_count=TAMANO_PAGINA,
                                                timeout=timeout)
            if not pagina:
                return
            yield from pagina
            secuencia = pagina[-1].sequence_number + 1

    def _ver_errores(self, cola: str, *, timeout: float | None = None) -> Iterator[MensajeEnErrores]:
        for original in self._ver(cola, ServiceBusSubQueue.DEAD_LETTER, timeout=timeout):
            yield MensajeEnErrores(
                _mensaje(cola, original, en_errores=True, tolerar_ilegible=True),
                _motivo_en_errores(original), original.enqueued_time_utc,
            )

    def errores(self, cola: str) -> list[MensajeEnErrores]:
        return sorted(self._ver_errores(cola), key=lambda error: error.cuando)

    def pendientes(self, cola: str) -> int:
        """Conteo de diagnóstico que incluye bloqueados y programados. No usar como condición de salida."""
        return sum(1 for _ in self._ver(cola))

    def _abandonar_reenvio(self, cola: str, receptor: ServiceBusReceiver, original: ServiceBusReceivedMessage) -> None:
        # Si falla el abandono, el bloqueo vence y el original queda en errores.
        with suppress(BloqueoPerdido, ErrorCola, ErrorServiceBus, ErrorTransitorio, ErrorDeConfiguracion):
            self._resolver_sdk(cola, receptor, original, "abandon_message")

    def reenviar_errores(self, cola: str) -> int:
        subcola = ServiceBusSubQueue.DEAD_LETTER
        pendientes = {original.sequence_number for original in self._ver(cola, subcola)}
        receptor = self._receptor(cola, subcola)
        espera = self._espera_recibir_s
        reenviados = 0
        with ExitStack() as llegadas:
            # Acotamos también las lecturas si siguen llegando mensajes a errores.
            for _ in range(2 * len(pendientes)):
                if not pendientes or (original := self._recibir(cola, receptor, espera)) is None:
                    break
                espera = min(self._espera_recibir_s, ESPERA_REENVIO_S)
                if original.sequence_number not in pendientes:
                    # Se devuelve al final para poder leer los originales que siguen.
                    llegadas.callback(self._abandonar_reenvio, cola, receptor, original)
                    continue
                try:
                    mensaje = _mensaje(cola, original, en_errores=True)
                    mensaje.propiedades.pop("intento", None)
                    mensaje.propiedades.pop("esperas", None)
                    self.publicar(cola, mensaje.cuerpo, propiedades=mensaje.propiedades)
                except Exception:
                    self._abandonar_reenvio(cola, receptor, original)
                    raise
                self._resolver_sdk(cola, receptor, original, "complete_message")
                pendientes.remove(original.sequence_number)
                reenviados += 1
        return reenviados

    def cerrar(self) -> None:
        self._cerrada = True
        self._bloqueados.clear()
        self._abandonados.clear()
        self._receptores.clear()
        self._emisores.clear()
        renovador, self._renovador = self._renovador, None
        with self._recursos:
            if renovador is not None:
                _cerrar(renovador, "cerrar renovador")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.cerrar()


def cola_desde_entorno(
    crear_cliente: Callable[..., ServiceBusClient] = ServiceBusClient, *, credencial: TokenCredential | None = None,
    espera_recibir_s: float = 5,
) -> ColaServiceBus:
    """Arma el cliente con el nombre completo y la identidad del entorno."""
    namespace = os.environ.get("SERVICEBUS_NAMESPACE", "").strip()
    if not namespace:
        raise ErrorDeConfiguracion("Falta SERVICEBUS_NAMESPACE")
    prefijo = os.environ.get("COLAS_PREFIJO", PREFIJO_COLAS)
    with ExitStack() as recursos:
        propia = None
        with _traducir_fallas("crear cliente"):
            try:
                if credencial is None:
                    propia = credencial = DefaultAzureCredential(exclude_interactive_browser_credential=True)
                    recursos.callback(_cerrar, propia, "cerrar credencial")
                cliente = crear_cliente(fully_qualified_namespace=namespace, credential=credencial)
            except (MessageAlreadySettled, ServiceBusError):
                raise
            except ValueError as error:
                raise ErrorDeConfiguracion(
                    f"Service Bus crear cliente ({type(error).__name__}). Revisa SERVICEBUS_NAMESPACE y la identidad."
                ) from None
        recursos.callback(_cerrar, cliente, "cerrar cliente")
        cola = ColaServiceBus(cliente, prefijo, espera_recibir_s, _credencial_propia=propia)
        recursos.pop_all()
        return cola
