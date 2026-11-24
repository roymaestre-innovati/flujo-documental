"""Inspección y limpieza de las entregas propias en las colas de desarrollo."""

from contextlib import suppress
from time import monotonic, sleep

from azure.servicebus import ServiceBusSubQueue
from orquestador.cola import CLASIFICAR, BloqueoPerdido, Mensaje
from orquestador.cola_servicebus import ErrorServiceBus, _EntregaYaResuelta
from orquestador.errores import ErrorTransitorio

COLA_PRUEBA_AZURE = CLASIFICAR
ESPERA_SERVICEBUS_AZURE_S = 2
PLAZO_LIMPIEZA_AZURE_S = 40
ERRORES = ServiceBusSubQueue.DEAD_LETTER


def nombre_corto(subcola):
    return f"{COLA_PRUEBA_AZURE}/$DeadLetter" if subcola == ERRORES else COLA_PRUEBA_AZURE


def ids_en_colas(cola, *, timeout=None):
    nombre = COLA_PRUEBA_AZURE
    return {
        None: [m.message_id for m in cola._ver(nombre, timeout=timeout)],
        ERRORES: [e.mensaje.id for e in cola._ver_errores(nombre, timeout=timeout)],
    }


def _resolver_entrega(cola, receptor, original, operacion):
    token = original.lock_token
    if token is None:
        return
    nombre = COLA_PRUEBA_AZURE
    try:
        if str(token) in cola._bloqueados:
            cola._resolver(Mensaje(original.message_id, nombre, {}, bloqueo=str(token)), operacion)
        else:
            cola._resolver_sdk(nombre, receptor, original, operacion)
    except (BloqueoPerdido, _EntregaYaResuelta):
        # Se volverá a buscar por id si el mensaje sigue en la cola.
        pass


def limpiar_colas(cola, publicados, recibidos, *, plazo_s=PLAZO_LIMPIEZA_AZURE_S):
    """Completa solo los ids propios y devuelve los ids que aún muestra peek."""
    limite = monotonic() + plazo_s
    try:
        while monotonic() < limite:
            try:
                for receptor, original in recibidos:
                    if original.message_id in publicados:
                        _resolver_entrega(cola, receptor, original, "complete_message")
                restantes = ids_en_colas(cola, timeout=ESPERA_SERVICEBUS_AZURE_S)
                if not any(restantes.values()):
                    return restantes
                if not any(publicados.intersection(ids) for ids in restantes.values()):
                    break
                for subcola, ids in restantes.items():
                    espera = min(ESPERA_SERVICEBUS_AZURE_S, limite - monotonic())
                    if espera > 0 and publicados.intersection(ids):
                        receptor = cola._receptor(COLA_PRUEBA_AZURE, subcola)
                        original = cola._recibir(COLA_PRUEBA_AZURE, receptor, espera)
                        if original is not None:
                            recibidos.append((receptor, original))
            except (ErrorTransitorio, ErrorServiceBus):
                sleep(min(0.2, max(0, limite - monotonic())))
    finally:
        # Retener temporalmente una entrega ajena permite recibir las que siguen
        # sin volver a abandonar el mismo mensaje varias veces.
        for receptor, original in recibidos:
            if original.message_id not in publicados:
                with suppress(ErrorTransitorio, ErrorServiceBus):
                    _resolver_entrega(cola, receptor, original, "abandon_message")
    return ids_en_colas(cola, timeout=ESPERA_SERVICEBUS_AZURE_S)
