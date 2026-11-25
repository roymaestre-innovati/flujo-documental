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
from azure.servicebus._pyamqp.cbs import CBSAuthenticator, CbsAuthState
from azure.servicebus._transport._pyamqp_transport import PyamqpTransport
from orquestador import cola_servicebus as sb
from orquestador.cola import CLASIFICAR, RESULTADOS, BloqueoPerdido, ErrorCola
from orquestador.errores import ErrorDeConfiguracion, ErrorTransitorio, procesar_uno
from orquestador.parametros import Parametros
from servicebus_azure import ERRORES, limpiar_colas
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
    with pytest.raises(TypeError, match="propiedades"):
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


@pytest.mark.parametrize("espera", [0, -1])
def test_rechaza_esperas_no_positivas(espera):
    cliente = ServiceBusFalso()
    with pytest.raises(ValueError, match="espera_recibir_s"):
        sb.ColaServiceBus(cliente, espera_recibir_s=espera)
    with pytest.raises(ValueError, match="max_wait_time"):
        cliente.get_queue_receiver(CLASIFICAR, max_wait_time=espera)
    receptor = cliente.get_queue_receiver(CLASIFICAR, max_wait_time=1)
    with pytest.raises(ValueError, match="max_wait_time"):
        receptor.receive_messages(max_message_count=1, max_wait_time=espera)


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


def test_traduce_timeout_de_cbs_envuelto_por_pyamqp(adaptador):
    cola, cliente = adaptador
    autenticador = Mock(auth_state=CbsAuthState.TIMEOUT)
    autenticador._cbs_link_ready.return_value = True
    with pytest.raises(TimeoutError, match="Authentication attempt timed-out") as timeout:
        CBSAuthenticator.handle_token(autenticador)
    envuelta = PyamqpTransport.create_servicebus_exception(Mock(), timeout.value)
    assert type(envuelta) is ServiceBusError and envuelta.inner_exception is timeout.value
    cliente.fallas["receive_messages"] = envuelta
    with pytest.raises(ErrorTransitorio, match=r"receive_messages en clasificar \(TimeoutError\)$") as error:
        cola.recibir(CLASIFICAR)
    assert error.value.__suppress_context__


@pytest.mark.parametrize(("atributo", "clase"), [
    ("__cause__", ConnectionError), ("__context__", OSError), ("inner_exception", TimeoutError),
])
def test_traduce_fallas_de_transporte_en_cadenas_de_causas(adaptador, atributo, clase):
    cola, cliente = adaptador
    falla = ServiceBusError(DETALLE)
    intermedia = RuntimeError(DETALLE)
    intermedia.__cause__ = clase(DETALLE)
    setattr(falla, atributo, intermedia)
    cliente.fallas["receive_messages"] = falla
    with pytest.raises(ErrorTransitorio, match=clase.__name__) as error:
        cola.recibir(CLASIFICAR)
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
])
def test_completar_retira_la_entrega_si_el_sdk_confirma_que_ya_no_esta_activa(adaptador, falla, traducida):
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


@pytest.mark.parametrize(("resolver", "operacion", "argumentos"), [
    ("completar", "complete_message", ()), ("abandonar", "abandon_message", ()),
    ("a_errores", "dead_letter_message", ("motivo",)),
])
@pytest.mark.parametrize(("falla", "traducida"), [
    (OperationTimeoutError(message=DETALLE), ErrorTransitorio),
    (ServiceBusError(DETALLE), sb.ErrorServiceBus),
])
def test_puede_reintentar_solo_la_resolucion(adaptador, resolver, operacion, argumentos, falla, traducida):
    cola, cliente = adaptador
    cola.publicar(CLASIFICAR, {})
    recibido = cola.recibir(CLASIFICAR)
    resolver = getattr(cola, resolver)
    cliente.fallas[operacion] = falla
    with pytest.raises(traducida) as error:
        resolver(recibido, *argumentos)
    assert str(error.value) == f"Service Bus {operacion} en clasificar ({type(falla).__name__})"
    assert error.value.__suppress_context__
    assert cliente.receptores[0].abierto == (traducida is ErrorTransitorio)

    del cliente.fallas[operacion]
    resolver(recibido, *argumentos)
    assert cliente.operaciones.count(operacion) == 2
    assert cliente.operaciones.count("receive_messages") == 1
    assert cliente.operaciones.count("send_messages") == 1


def test_historial_de_abandonos_conserva_solo_los_tokens_mas_recientes(adaptador, monkeypatch):
    cola, _ = adaptador
    monkeypatch.setattr(sb, "LIMITE_TOKENS_ABANDONADOS", 2)
    cola.publicar(CLASIFICAR, {})
    viejas = []
    for _ in range(3):
        mensaje = cola.recibir(CLASIFICAR)
        cola.abandonar(mensaje)
        viejas.append(mensaje)

    with pytest.raises(ErrorCola):
        cola.completar(viejas[0])
    for reciente in viejas[1:]:
        with pytest.raises(BloqueoPerdido):
            cola.completar(reciente)
    cola.completar(cola.recibir(CLASIFICAR))


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


@pytest.mark.parametrize("bloqueo_vencido", [False, True])
def test_falla_de_renovacion_solo_avisa_y_el_sdk_comprueba_el_bloqueo(adaptador, caplog, bloqueo_vencido):
    cola, cliente = adaptador
    publicado = cola.publicar(CLASIFICAR, {"texto": "cuerpo privado"})
    recibido = cola.recibir(CLASIFICAR)
    [renovador] = cliente.renovadores
    [(receptor, original)] = renovador.registros
    renovador.fallar(original, OperationTimeoutError(message=DETALLE))

    if bloqueo_vencido:
        receptor.vencer_bloqueo(original)
        with pytest.raises(BloqueoPerdido, match="MessageLockLostError"):
            cola.completar(recibido)
        cola.completar(cola.recibir(CLASIFICAR))
    else:
        cola.completar(recibido)
    assert cliente.operaciones.count("complete_message") == (2 if bloqueo_vencido else 1)
    assert caplog.messages == [f"Falló la renovación del bloqueo del mensaje {publicado} en clasificar (OperationTimeoutError)"]


def test_procesar_uno_completa_tras_un_aviso_del_hilo_de_renovacion(adaptador):
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

    assert (resultado.id_mensaje, resultado.desenlace) == (publicado, "ok")
    assert "complete_message" in cliente.operaciones
    manejador.procesar.assert_called_once_with(cuerpo)
    manejador.al_fallar.assert_not_called()


@pytest.mark.parametrize(("cuerpo", "propiedades"), [
    (b"texto privado", None),
    (b'["texto privado"]', None),
    (b'{"dato": NaN}', None),
    (b'{}', {b"\xff": b"texto privado"}),
    (b'{}', {b"dato": b"\xff"}),
])
def test_recibir_manda_un_mensaje_ilegible_a_errores_y_sigue(adaptador, caplog, cuerpo, propiedades):
    cola, cliente = adaptador
    cola._emisor(CLASIFICAR, "prueba-clasificar").send_messages(
        ServiceBusMessage(cuerpo, application_properties=propiedades, message_id="ilegible")
    )
    id_valido = cola.publicar(CLASIFICAR, {"n": 1})
    recibido = cola.recibir(CLASIFICAR)
    assert recibido.id == id_valido
    [renovador] = cliente.renovadores
    assert [original.message_id for _, original in renovador.registros] == [id_valido]
    cola.completar(recibido)
    assert caplog.messages == ["Mensaje ilegible ilegible en clasificar"]

    [en_errores] = cola.errores(CLASIFICAR)
    assert (en_errores.mensaje.id, en_errores.mensaje.cuerpo, en_errores.motivo) == (
        "ilegible", {}, sb.MOTIVO_MENSAJE_ILEGIBLE,
    )
    with pytest.raises(ErrorCola, match=sb.MOTIVO_MENSAJE_ILEGIBLE):
        cola.reenviar_errores(CLASIFICAR)
    assert len(cliente.envios) == 2
    assert [error.mensaje.id for error in cola.errores(CLASIFICAR)] == ["ilegible"]


def test_recibir_acota_las_lecturas_si_solo_llegan_mensajes_ilegibles(adaptador, monkeypatch):
    cola, cliente = adaptador
    monkeypatch.setattr(sb, "LIMITE_LECTURAS_POR_RECEPCION", 2)
    emisor = cola._emisor(CLASIFICAR, "prueba-clasificar")
    for n in range(3):
        emisor.send_messages(ServiceBusMessage(b"ilegible", message_id=str(n)))
    assert cola.recibir(CLASIFICAR) is None
    assert cliente.operaciones.count("receive_messages") == 2
    assert cola.pendientes(CLASIFICAR) == 1
    assert cola.recibir(CLASIFICAR) is None
    assert cola.pendientes(CLASIFICAR) == 0
    assert len(cola.errores(CLASIFICAR)) == 3
    assert cliente.renovadores == []


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
    assert cliente.operaciones[-3:] == ["receive_messages", "send_messages", "complete_message"]
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


@pytest.mark.parametrize("regresa_la_copia", [False, True], ids=["llegada-nueva", "copia-que-regresa"])
def test_reenviar_se_acota_a_los_originales_vistos_al_empezar(monkeypatch, regresa_la_copia):
    cliente = ServiceBusFalso()
    with sb.ColaServiceBus(cliente, espera_recibir_s=2, crear_renovador=cliente.crear_renovador) as cola:
        nombre = "evaluacion-ofertas-clasificar"
        if not regresa_la_copia:
            # Ya estaba en la principal y su número de secuencia es menor.
            id_nuevo = cola.publicar(CLASIFICAR, {"n": 0})
            llega_durante_reenvio = cola.recibir(CLASIFICAR)
        for n in (1, 2):
            cola.publicar(CLASIFICAR, {"n": n})
            cola.a_errores(cola.recibir(CLASIFICAR), "motivo")

        [emisor] = cliente.emisores
        enviar = emisor.send_messages
        ids_copias = []

        def enviar_y_mandar_a_errores(copia):
            enviar(copia)
            ids_copias.append(copia.message_id)
            if regresa_la_copia:
                cola.a_errores(cola.recibir(CLASIFICAR), "la copia volvió a errores")
            elif len(ids_copias) == 1:
                cola.a_errores(llega_durante_reenvio, "llegó durante el reenvío")

        with monkeypatch.context() as parche:
            parche.setattr(emisor, "send_messages", enviar_y_mandar_a_errores)
            assert cola.reenviar_errores(CLASIFICAR) == 2
        assert len(ids_copias) == 2
        assert [error.mensaje.id for error in cola.errores(CLASIFICAR)] == (
            ids_copias if regresa_la_copia else [id_nuevo]
        )
        receptor = cliente.receptores[1]
        assert receptor.nombre == nombre and receptor.subcola == ServiceBusSubQueue.DEAD_LETTER
        assert receptor.espera == 2
        assert receptor.llamadas_recibir == [(1, 2), (1, sb.ESPERA_REENVIO_S)]


def test_reenviar_abandona_una_llegada_ajena_al_listado_inicial(adaptador, monkeypatch):
    cola, cliente = adaptador
    id_nuevo = cola.publicar(CLASIFICAR, {"n": 0})
    nuevo = cola.recibir(CLASIFICAR)
    id_inicial = cola.publicar(CLASIFICAR, {"n": 1})
    cola.a_errores(cola.recibir(CLASIFICAR), "motivo")
    [visto] = cola._ver(CLASIFICAR, ServiceBusSubQueue.DEAD_LETTER)

    def listado_inicial(*args):
        cola.a_errores(nuevo, "llegó después del listado")
        en_errores = cliente.colas["prueba-clasificar", ServiceBusSubQueue.DEAD_LETTER]
        en_errores.sort(key=lambda mensaje: mensaje.secuencia)
        return iter([visto])

    with monkeypatch.context() as parche:
        parche.setattr(cola, "_ver", listado_inicial)
        assert cola.reenviar_errores(CLASIFICAR) == 1
    assert [error.mensaje.id for error in cola.errores(CLASIFICAR)] == [id_nuevo]
    assert len(cliente.envios) == 3
    copia = cola.recibir(CLASIFICAR)
    assert copia.id != id_inicial and copia.cuerpo == {"n": 1}
    cola.completar(copia)
    assert cliente.operaciones.count("abandon_message") == 1


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


def test_limpieza_de_pruebas_completa_solo_los_ids_propios(adaptador):
    cola, cliente = adaptador
    en_errores = cola.publicar(CLASIFICAR, {})
    cola.a_errores(cola.recibir(CLASIFICAR), "motivo")
    bloqueado = cola.publicar(CLASIFICAR, {})
    cola.recibir(CLASIFICAR)
    receptor = cliente.receptores[0]
    recibidos = [(receptor, receptor.entregas[-1])]
    ajeno = cola.publicar(CLASIFICAR, {})
    visible = cola.publicar(CLASIFICAR, {})

    restos = limpiar_colas(cola, {en_errores, bloqueado, visible}, recibidos, plazo_s=1)

    assert restos == {None: [ajeno], ERRORES: []}
    recibido = cola.recibir(CLASIFICAR)
    assert (recibido.id, recibido.entregas) == (ajeno, 2)
    cola.completar(recibido)


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
    credencial.close.assert_not_called()


def test_cola_desde_entorno_cierra_la_credencial_propia_al_cerrar(monkeypatch):
    monkeypatch.setenv("SERVICEBUS_NAMESPACE", "<namespace>.servicebus.windows.net")
    cliente = ServiceBusFalso()
    credencial = Mock()
    crear_credencial = Mock(return_value=credencial)
    monkeypatch.setattr(sb, "DefaultAzureCredential", crear_credencial)

    with sb.cola_desde_entorno(Mock(return_value=cliente), espera_recibir_s=0.01) as cola:
        assert cola.recibir(CLASIFICAR) is None
        credencial.close.assert_not_called()
    cola.cerrar()

    crear_credencial.assert_called_once_with(exclude_interactive_browser_credential=True)
    assert cliente.cerrado and cliente.receptores[0].espera == 0.01
    credencial.close.assert_called_once_with()


@pytest.mark.parametrize("credencial_inyectada", [False, True])
def test_falla_al_crear_cliente_cierra_solo_la_credencial_propia(monkeypatch, credencial_inyectada):
    monkeypatch.setenv("SERVICEBUS_NAMESPACE", "<namespace>.servicebus.windows.net")
    credencial = Mock()
    monkeypatch.setattr(sb, "DefaultAzureCredential", Mock(return_value=credencial))
    crear_cliente = Mock(side_effect=ServiceBusConnectionError(message=DETALLE))

    with pytest.raises(ErrorTransitorio, match="crear cliente"):
        sb.cola_desde_entorno(crear_cliente, credencial=credencial if credencial_inyectada else None)

    assert credencial.close.call_count == (0 if credencial_inyectada else 1)


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


def test_los_envios_de_varios_hilos_van_de_a_uno(adaptador, monkeypatch):
    import threading
    import time

    cola, cliente = adaptador
    from servicebus_falso import EmisorFalso

    dentro, maximo, candado = 0, 0, threading.Lock()
    original = EmisorFalso.send_messages

    def enviar(self, mensaje):
        nonlocal dentro, maximo
        with candado:
            dentro += 1
            maximo = max(maximo, dentro)
        time.sleep(0.005)
        try:
            return original(self, mensaje)
        finally:
            with candado:
                dentro -= 1

    monkeypatch.setattr(EmisorFalso, "send_messages", enviar)
    with ThreadPoolExecutor(max_workers=4) as grupo:
        list(grupo.map(lambda i: cola.publicar("normalizar", {"i": i}), range(20)))
    assert maximo == 1
    assert len(cliente.envios) == 20
    assert len(cliente.emisores) == 1
