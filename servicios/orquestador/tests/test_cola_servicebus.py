"""Formato, bloqueos y traducción de fallas de ColaServiceBus, sin red."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import UUID

import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.servicebus import (
    ServiceBusMessage,
    ServiceBusReceiveMode,
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
    ServiceBusQuotaExceededError,
    ServiceBusServerBusyError,
)
from orquestador import cola_servicebus as sb
from orquestador.cola import CLASIFICAR, RESULTADOS, BloqueoPerdido, ErrorCola
from orquestador.errores import ErrorDeConfiguracion, ErrorTransitorio, procesar_uno
from orquestador.parametros import Parametros
from servicebus_falso import ServiceBusFalso

DETALLE = "texto privado del SDK"


@pytest.fixture
def adaptador():
    cliente = ServiceBusFalso()
    with sb.ColaServiceBus(cliente, prefijo="prueba-", espera_recibir_s=0.01,
                           crear_renovador=cliente.crear_renovador) as cola:
        yield cola, cliente


def test_publicar_serializa_y_usa_el_prefijo_y_un_emisor_por_cola(adaptador):
    cola, cliente = adaptador
    cuerpo = {"texto": "Bogotá"}
    propiedades = {"origen": "revisión", "intento": 2, "puntaje": 1.25, "listo": True}
    primero = cola.publicar(CLASIFICAR, cuerpo, propiedades=propiedades)
    segundo = cola.publicar(CLASIFICAR, cuerpo)
    cola.publicar(RESULTADOS, {})

    [(nombre, enviado), _, _] = cliente.envios
    assert nombre == "prueba-clasificar"
    assert isinstance(enviado, ServiceBusMessage)
    assert b"".join(enviado.body) == json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
    assert enviado.content_type == "application/json"
    assert enviado.application_properties == propiedades
    assert enviado.scheduled_enqueue_time_utc is None
    assert enviado.message_id == primero and UUID(primero).version == 4
    assert primero != segundo
    assert [emisor.nombre for emisor in cliente.emisores] == ["prueba-clasificar", "prueba-resultados"]


def test_recibir_usa_peeklock_y_normaliza_entregas_y_propiedades(adaptador):
    cola, cliente = adaptador
    propiedades = {"intento": 3, "país": "Colombia"}
    publicado = cola.publicar(RESULTADOS, {"texto": "ñ"}, propiedades=propiedades)
    primera = cola.recibir(RESULTADOS)
    cola.abandonar(primera)
    segunda = cola.recibir(RESULTADOS)

    [receptor] = cliente.receptores
    assert (receptor.nombre, receptor.subcola, receptor.modo, receptor.prefetch, receptor.espera) == (
        "prueba-resultados", None, ServiceBusReceiveMode.PEEK_LOCK, 0, 0.01)
    assert receptor.llamadas_recibir == [(1, 0.01), (1, 0.01)]
    original, vigente = receptor.entregas
    assert (original.delivery_count, vigente.delivery_count) == (0, 1)
    assert original.application_properties == {b"intento": 3, "país".encode(): b"Colombia"}
    assert (primera.entregas, segunda.entregas) == (1, 2)
    assert primera.bloqueo != segunda.bloqueo == str(vigente.lock_token)
    assert primera.id == segunda.id == publicado
    assert segunda.cola == RESULTADOS
    assert segunda.cuerpo == {"texto": "ñ"}
    assert segunda.propiedades == propiedades
    cola.completar(segunda)


def test_recibir_registra_cada_entrega_una_vez_en_el_mismo_renovador():
    cliente = ServiceBusFalso()
    parametros = Parametros(renovacion_bloqueo_max_s=321.5)
    with sb.ColaServiceBus(cliente, espera_recibir_s=0.01, parametros=parametros,
                           crear_renovador=cliente.crear_renovador) as cola:
        assert cola.recibir(CLASIFICAR) is None
        assert cliente.renovadores == []

        cola.publicar(CLASIFICAR, {})
        primera = cola.recibir(CLASIFICAR)
        [renovador] = cliente.renovadores
        [receptor] = cliente.receptores
        [original] = receptor.entregas
        assert renovador.max_lock_renewal_duration == 321.5
        assert renovador.max_workers == 2
        assert renovador.registros == [(receptor, original)]

        cola.abandonar(primera)
        assert renovador.registros == [(receptor, original)]
        segunda = cola.recibir(CLASIFICAR)
        _, vigente = receptor.entregas
        cola.completar(segunda)
        assert cliente.renovadores == [renovador]
        assert renovador.registros == [(receptor, original), (receptor, vigente)]


def test_mismo_id_puede_tener_bloqueos_independientes(adaptador, monkeypatch):
    cola, _ = adaptador
    monkeypatch.setattr(sb, "uuid4", lambda: UUID(int=1))
    for i in (1, 2):
        cola.publicar(CLASIFICAR, {"n": i})
    primero, segundo = cola.recibir(CLASIFICAR), cola.recibir(CLASIFICAR)
    assert primero.id == segundo.id
    assert primero.bloqueo != segundo.bloqueo
    cola.completar(primero)
    cola.a_errores(segundo, "bug")
    assert cola.pendientes(CLASIFICAR) == 0
    assert [error.mensaje.cuerpo for error in cola.errores(CLASIFICAR)] == [{"n": 2}]


def test_programa_en_utc_y_peek_ve_el_mensaje(adaptador):
    cola, cliente = adaptador
    antes = datetime.now(timezone.utc)
    cola.publicar(CLASIFICAR, {}, demora_s=30)
    despues = datetime.now(timezone.utc)
    programado = cliente.envios[0][1].scheduled_enqueue_time_utc
    demora = timedelta(seconds=30)

    # El SDK guarda la fecha con precisión de milisegundos.
    assert antes + demora - timedelta(milliseconds=1) <= programado <= despues + demora
    assert programado.utcoffset() == timedelta(0)
    assert cola.recibir(CLASIFICAR) is None
    assert cola.pendientes(CLASIFICAR) == 1


@pytest.mark.parametrize("propiedades", [{"dato": []}, {"dato": None}, {"dato": object()}, {1: "valor"}, []])
def test_rechaza_propiedades_que_no_son_json_simple(adaptador, propiedades):
    cola, cliente = adaptador
    with pytest.raises(TypeError, match="valores JSON simples"):
        cola.publicar(CLASIFICAR, {}, propiedades=propiedades)
    assert cliente.operaciones == []


def test_rechaza_propiedades_con_numeros_no_finitos(adaptador):
    cola, cliente = adaptador
    with pytest.raises(ValueError):
        cola.publicar(CLASIFICAR, {}, propiedades={"dato": float("inf")})
    assert cliente.operaciones == []


def test_rechaza_demora_negativa(adaptador):
    cola, cliente = adaptador
    with pytest.raises(ErrorCola, match="negativa"):
        cola.publicar(CLASIFICAR, {}, demora_s=-1)
    assert cliente.operaciones == []


def test_limite_mide_cuerpo_y_propiedades_en_bytes(adaptador):
    cola, cliente = adaptador
    cuerpo = {"dato": "privado"}
    propiedades = {"dato": "método"}
    inicial = sum(len(json.dumps(datos, ensure_ascii=False).encode()) for datos in (cuerpo, propiedades))
    cuerpo["dato"] += "a" * (sb.LIMITE_MENSAJE_BYTES - inicial)
    cola.publicar(CLASIFICAR, cuerpo, propiedades=propiedades)
    cuerpo["dato"] += "ñ"

    with pytest.raises(ErrorCola, match=f"{sb.LIMITE_MENSAJE_BYTES + 2} bytes") as error:
        cola.publicar(CLASIFICAR, cuerpo, propiedades=propiedades)
    assert "privado" not in str(error.value)
    assert len(cliente.envios) == 1


def test_traduce_tamano_rechazado_por_el_sdk(adaptador):
    cola, cliente = adaptador
    cliente.fallas["send_messages"] = MessageSizeExceededError(message=DETALLE)
    with pytest.raises(ErrorCola) as error:
        cola.publicar(CLASIFICAR, {})
    assert str(error.value) == "Service Bus send_messages en clasificar (MessageSizeExceededError): mensaje de 4 bytes"
    assert error.value.__suppress_context__


@pytest.mark.parametrize(("clase", "espera"), [
    (ServiceBusConnectionError, None),
    (ServiceBusCommunicationError, None),
    (OperationTimeoutError, None),
    (ServiceRequestError, None),
    (ServiceResponseError, None),
    (ServiceBusServerBusyError, sb.ESPERA_SERVICIO_OCUPADO_S),
])
def test_fallas_transitorias(adaptador, clase, espera):
    cola, cliente = adaptador
    cliente.fallas["receive_messages"] = clase(message=DETALLE)
    with pytest.raises(ErrorTransitorio) as error:
        cola.recibir(CLASIFICAR)
    assert error.value.espera_s == espera
    assert str(error.value) == f"Service Bus receive_messages en clasificar ({clase.__name__})"
    assert error.value.__suppress_context__


@pytest.mark.parametrize("clase", [
    ServiceBusAuthenticationError, ServiceBusAuthorizationError, MessagingEntityNotFoundError,
    MessagingEntityDisabledError, ClientAuthenticationError,
])
def test_fallas_de_acceso_son_de_configuracion(adaptador, clase):
    cola, cliente = adaptador
    cliente.fallas["get_queue_receiver"] = clase(message=DETALLE)
    with pytest.raises(ErrorDeConfiguracion) as error:
        cola.errores(CLASIFICAR)
    mensaje = str(error.value)
    assert mensaje.startswith(f"Service Bus get_queue_receiver en clasificar ({clase.__name__})")
    assert all(pista in mensaje for pista in ("rol de Service Bus", "az login", "nombre"))
    assert all(privado not in mensaje for privado in (DETALLE, "prueba-clasificar"))
    assert error.value.__suppress_context__


def test_traduce_falla_de_credencial_envuelta_por_pyamqp(adaptador):
    cola, cliente = adaptador
    cliente.fallas["send_messages"] = ServiceBusError(DETALLE, error=ClientAuthenticationError(DETALLE))
    with pytest.raises(ErrorDeConfiguracion, match="ClientAuthenticationError") as error:
        cola.publicar(CLASIFICAR, {})
    assert DETALLE not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize("clase", [ServiceBusError, ServiceBusQuotaExceededError])
def test_otras_fallas_del_sdk_salen_limpias(adaptador, clase):
    cola, cliente = adaptador
    cliente.fallas["peek_messages"] = clase(message=DETALLE)
    with pytest.raises(sb.ErrorServiceBus) as error:
        cola.pendientes(CLASIFICAR)
    assert str(error.value) == f"Service Bus peek_messages en clasificar ({clase.__name__})"
    assert error.value.__suppress_context__


@pytest.mark.parametrize(("falla", "traducida"), [
    (MessageLockLostError(message=DETALLE), BloqueoPerdido),
    (MessageAlreadySettled(action=DETALLE), ErrorCola),
    (OperationTimeoutError(message=DETALLE), ErrorTransitorio),
])
def test_completar_traduce_y_retira_la_entrega_aun_si_falla(adaptador, falla, traducida):
    cola, cliente = adaptador
    cola.publicar(CLASIFICAR, {})
    recibido = cola.recibir(CLASIFICAR)
    cliente.fallas["complete_message"] = falla
    with pytest.raises(traducida) as error:
        cola.completar(recibido)
    assert str(error.value) == f"Service Bus complete_message en clasificar ({type(falla).__name__})"
    assert error.value.__suppress_context__

    del cliente.fallas["complete_message"]
    with pytest.raises(ErrorCola, match="ya se resolvió o nunca se recibió"):
        cola.completar(recibido)
    assert cliente.operaciones.count("complete_message") == 1


def test_el_falso_distingue_un_objeto_resuelto_de_un_token_viejo(adaptador):
    cola, cliente = adaptador
    cola.publicar(CLASIFICAR, {})
    primera = cola.recibir(CLASIFICAR)
    [receptor] = cliente.receptores
    [original] = receptor.entregas
    copia = copy(original)
    cola.abandonar(primera)
    vigente = cola.recibir(CLASIFICAR)

    with pytest.raises(MessageAlreadySettled):
        receptor.complete_message(original)
    with pytest.raises(MessageLockLostError):
        receptor.complete_message(copia)
    cola.completar(vigente)


def test_procesar_uno_informa_el_bloqueo_perdido(adaptador):
    cola, cliente = adaptador
    cuerpo = {"id_proceso": "P1"}
    publicado = cola.publicar(CLASIFICAR, cuerpo)
    cliente.fallas["complete_message"] = MessageLockLostError(message=DETALLE)
    manejador = Mock(cola=CLASIFICAR)

    resultado = procesar_uno(cola, manejador)

    assert (resultado.id_mensaje, resultado.desenlace) == (publicado, "bloqueo_perdido")
    manejador.procesar.assert_called_once_with(cuerpo)
    manejador.al_fallar.assert_not_called()


@pytest.mark.parametrize(("resolver", "argumentos"), [
    ("completar", ()), ("abandonar", ()), ("a_errores", ("motivo",)),
])
def test_falla_de_renovacion_impide_resolver_solo_el_token_perdido(adaptador, caplog, monkeypatch, resolver, argumentos):
    cola, cliente = adaptador
    monkeypatch.setattr(sb, "uuid4", lambda: UUID(int=1))
    publicado = cola.publicar(CLASIFICAR, {"texto": "cuerpo privado"})
    cola.publicar(CLASIFICAR, {})
    perdida, vigente = cola.recibir(CLASIFICAR), cola.recibir(CLASIFICAR)
    [renovador] = cliente.renovadores
    (_, original), _ = renovador.registros
    renovador.fallar(original, MessageLockLostError(message=DETALLE))
    operaciones = cliente.operaciones[:]

    with pytest.raises(BloqueoPerdido, match="falló la renovación"):
        getattr(cola, resolver)(perdida, *argumentos)
    assert cliente.operaciones == operaciones
    assert caplog.messages == [f"Falló la renovación del bloqueo del mensaje {publicado} en clasificar (MessageLockLostError)"]
    cola.completar(vigente)


def test_procesar_uno_informa_la_perdida_de_renovacion(adaptador):
    cola, cliente = adaptador
    cuerpo = {"id_proceso": "P1"}
    publicado = cola.publicar(CLASIFICAR, cuerpo)

    def fallar_renovacion(_cuerpo):
        [renovador] = cliente.renovadores
        [(_, original)] = renovador.registros
        with ThreadPoolExecutor(max_workers=1) as ejecutor:
            ejecutor.submit(renovador.fallar, original, None).result()

    manejador = Mock(cola=CLASIFICAR)
    manejador.procesar.side_effect = fallar_renovacion
    resultado = procesar_uno(cola, manejador)

    assert (resultado.id_mensaje, resultado.desenlace) == (publicado, "bloqueo_perdido")
    assert "complete_message" not in cliente.operaciones
    manejador.procesar.assert_called_once_with(cuerpo)
    manejador.al_fallar.assert_not_called()


@pytest.mark.parametrize(("motivo", "descripcion"), [
    ("revisión " * 60, "revisión " * 60),
    ("a" * 4095 + "😀" + "resto", "a" * 4095),
])
def test_a_errores_conserva_el_motivo_dentro_de_los_limites(adaptador, motivo, descripcion):
    cola, cliente = adaptador
    cola.publicar(CLASIFICAR, {})
    cola.a_errores(cola.recibir(CLASIFICAR), motivo)
    [en_errores] = cola.errores(CLASIFICAR)
    principal, receptor = cliente.receptores
    [original] = principal.entregas
    [visto] = receptor.peek_messages(sequence_number=1, max_message_count=1)

    assert receptor.subcola == ServiceBusSubQueue.DEAD_LETTER
    assert en_errores.cuando == original.enqueued_time_utc
    assert visto.dead_letter_reason == motivo[:200]
    assert visto.dead_letter_error_description == en_errores.motivo == descripcion


def test_peek_se_pagina_aun_si_service_bus_devuelve_paginas_cortas(adaptador):
    cola, cliente = adaptador
    cliente.tope_peek = 1
    for i in range(5):
        cola.publicar(CLASIFICAR, {"n": i})
    primero, segundo = cola.recibir(CLASIFICAR), cola.recibir(CLASIFICAR)
    cola.a_errores(segundo, "detalle")
    cola.a_errores(primero, "motivo")
    cola.recibir(CLASIFICAR)
    cola.publicar(CLASIFICAR, {}, demora_s=30)
    principal = cliente.receptores[0]
    assert cola.pendientes(CLASIFICAR) == 4
    assert [n for n, _ in principal.llamadas_peek] == [1, 4, 5, 6, 7]

    en_errores = cola.errores(CLASIFICAR)
    assert [e.mensaje.cuerpo for e in en_errores] == [{"n": 0}, {"n": 1}]
    assert [e.motivo for e in en_errores] == ["motivo", "detalle"]
    receptor = cliente.receptores[1]
    assert [n for n, _ in receptor.llamadas_peek] == [1, 2, 3]


def test_errores_usa_reason_si_no_hay_descripcion(adaptador):
    cola, cliente = adaptador
    cola.publicar(CLASIFICAR, {})
    cola.recibir(CLASIFICAR)
    [receptor] = cliente.receptores
    receptor.dead_letter_message(receptor.entregas[0], reason="motivo", error_description="")
    [en_errores] = cola.errores(CLASIFICAR)
    assert en_errores.motivo == "motivo"


def test_reenviar_abandona_el_original_si_falla_el_envio(adaptador):
    cola, cliente = adaptador
    viejo = cola.publicar(CLASIFICAR, {"n": 1}, propiedades={"intento": 4, "origen": "revisión"})
    cola.a_errores(cola.recibir(CLASIFICAR), "motivo")
    cliente.fallas["send_messages"] = ServiceBusConnectionError(message=DETALLE)

    with pytest.raises(ErrorTransitorio, match="send_messages"):
        cola.reenviar_errores(CLASIFICAR)
    assert cliente.operaciones[-3:] == ["receive_messages", "send_messages", "abandon_message"]
    assert cola.pendientes(CLASIFICAR) == 0
    assert [e.mensaje.id for e in cola.errores(CLASIFICAR)] == [viejo]

    del cliente.fallas["send_messages"]
    assert cola.reenviar_errores(CLASIFICAR) == 1
    assert cliente.operaciones[-4:] == ["receive_messages", "send_messages", "complete_message", "receive_messages"]
    copia = cola.recibir(CLASIFICAR)
    assert copia.id != viejo
    assert copia.propiedades == {"origen": "revisión"}


def test_reenviar_no_registra_entregas_de_la_subcola_de_errores(adaptador):
    cola, cliente = adaptador
    cola.publicar(CLASIFICAR, {})
    cola.a_errores(cola.recibir(CLASIFICAR), "motivo")
    [renovador] = cliente.renovadores
    [registro] = renovador.registros

    assert cola.reenviar_errores(CLASIFICAR) == 1
    assert cliente.renovadores == [renovador]
    assert renovador.registros == [registro]


def test_reenviar_conserva_la_falla_de_envio_si_falla_el_abandono(adaptador):
    cola, cliente = adaptador
    cola.publicar(CLASIFICAR, {})
    cola.a_errores(cola.recibir(CLASIFICAR), "motivo")
    cliente.fallas["send_messages"] = ServiceBusConnectionError(message=DETALLE)
    cliente.fallas["abandon_message"] = MessageLockLostError(message=DETALLE)

    with pytest.raises(ErrorTransitorio, match="send_messages"):
        cola.reenviar_errores(CLASIFICAR)
    assert cola.pendientes(CLASIFICAR) == 0
    assert len(cola.errores(CLASIFICAR)) == 1


def test_cola_desde_entorno_exige_namespace_antes_de_crear_recursos(monkeypatch):
    monkeypatch.delenv("SERVICEBUS_NAMESPACE", raising=False)
    crear_credencial, crear_cliente = Mock(), Mock()
    monkeypatch.setattr(sb, "DefaultAzureCredential", crear_credencial)

    with pytest.raises(ErrorDeConfiguracion, match="Falta SERVICEBUS_NAMESPACE"):
        sb.cola_desde_entorno(crear_cliente)
    crear_credencial.assert_not_called()
    crear_cliente.assert_not_called()


@pytest.mark.parametrize("prefijo", [None, "falso-"])
def test_cola_desde_entorno_configura_el_cliente_y_el_prefijo(monkeypatch, prefijo):
    namespace = "<namespace>.servicebus.windows.net"
    monkeypatch.setenv("SERVICEBUS_NAMESPACE", namespace)
    monkeypatch.delenv("COLAS_PREFIJO", raising=False)
    if prefijo is not None:
        monkeypatch.setenv("COLAS_PREFIJO", prefijo)
    cliente, credencial = ServiceBusFalso(), Mock()
    crear_cliente = Mock(return_value=cliente)

    with sb.cola_desde_entorno(crear_cliente, credencial=credencial) as cola:
        cola.publicar(RESULTADOS, {})
    crear_cliente.assert_called_once_with(fully_qualified_namespace=namespace, credential=credencial)
    assert cliente.envios[0][0] == (prefijo or "evaluacion-ofertas-") + "resultados"


def test_falla_autenticacion_al_armar_la_credencial(monkeypatch):
    monkeypatch.setenv("SERVICEBUS_NAMESPACE", "<namespace>.servicebus.windows.net")
    crear_credencial = Mock(side_effect=ClientAuthenticationError(DETALLE))
    monkeypatch.setattr(sb, "DefaultAzureCredential", crear_credencial)
    crear_cliente = Mock()

    with pytest.raises(ErrorDeConfiguracion, match="ClientAuthenticationError") as error:
        sb.cola_desde_entorno(crear_cliente)
    assert DETALLE not in str(error.value)
    crear_cliente.assert_not_called()


@pytest.mark.parametrize("recibir", [False, True])
def test_cerrar_cierra_el_renovador_antes_de_los_demas_recursos(recibir):
    cliente = ServiceBusFalso()
    with sb.ColaServiceBus(cliente, crear_renovador=cliente.crear_renovador) as cola:
        cola.publicar(CLASIFICAR, {})
        cola.pendientes(CLASIFICAR)
        cola.errores(CLASIFICAR)
        if recibir:
            cola.recibir(CLASIFICAR)
    cola.cerrar()

    assert cliente.cerrado and cliente.emisores[0].cerrado
    assert len(cliente.receptores) == 2 and all(r.cerrado for r in cliente.receptores)
    cierres = ["close_receiver", "close_receiver", "close_sender", "close_client"]
    if recibir:
        [renovador] = cliente.renovadores
        assert renovador.cerrado and renovador.max_lock_renewal_duration == 1800
        cierres.insert(0, "close_renewer")
    else:
        assert cliente.renovadores == []
    assert [operacion for operacion in cliente.operaciones if operacion.startswith("close_")] == cierres


@pytest.mark.parametrize(("operacion", "recurso"), [
    ("close_receiver", "receptor en clasificar"), ("close_renewer", "renovador"),
])
def test_cerrar_traduce_fallas_y_cierra_los_demas_recursos(operacion, recurso):
    cliente = ServiceBusFalso()
    cola = sb.ColaServiceBus(cliente, crear_renovador=cliente.crear_renovador)
    cola.publicar(CLASIFICAR, {})
    cola.recibir(CLASIFICAR)
    cliente.fallas[operacion] = ServiceBusCommunicationError(message=DETALLE)

    with pytest.raises(ErrorTransitorio) as error:
        cola.cerrar()
    assert str(error.value) == f"Service Bus cerrar {recurso} (ServiceBusCommunicationError)"
    assert cliente.operaciones[-4:] == ["close_renewer", "close_receiver", "close_sender", "close_client"]
    assert cliente.cerrado and cliente.emisores[0].cerrado
