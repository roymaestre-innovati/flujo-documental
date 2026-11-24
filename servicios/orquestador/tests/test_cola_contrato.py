"""Contrato que comparten las implementaciones de Cola."""

from copy import deepcopy
from time import monotonic, sleep

import pytest
from orquestador import cola as c
from orquestador.cola_servicebus import ColaServiceBus
from servicebus_falso import ServiceBusFalso

NOMBRE = c.CLASIFICAR


@pytest.fixture
def cola_en_memoria():
    return c.ColaEnMemoria(), 0.3, 2


@pytest.fixture
def cola_servicebus_falso():
    cliente = ServiceBusFalso()
    with ColaServiceBus(cliente, espera_recibir_s=0.05, crear_renovador=cliente.crear_renovador) as cola:
        yield cola, 0.3, 2


# Cada implementación agrega un fixture con la cola, la demora y el plazo en segundos.
# Si recibir espera, su tiempo máximo debe ser menor que la demora de la prueba.
# Para Azure, ese fixture hará el peek inicial y la limpieza aun si falla la prueba.
@pytest.fixture(params=[
    pytest.param("cola_en_memoria", id="memoria"),
    pytest.param("cola_servicebus_falso", id="servicebus_falso"),
])
def implementacion_cola(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def cola(implementacion_cola):
    instancia, _, _ = implementacion_cola
    yield instancia
    assert instancia.pendientes(NOMBRE) == 0
    assert instancia.errores(NOMBRE) == []


@pytest.fixture(params=["completar", "abandonar", "a_errores"])
def resolver(cola, request):
    if request.param == "a_errores":
        return lambda mensaje: cola.a_errores(mensaje, "bug")
    return getattr(cola, request.param)


def test_cola_entrega_en_orden_y_bloquea(cola):
    primero_id = cola.publicar(NOMBRE, {"n": 1})
    segundo_id = cola.publicar(NOMBRE, {"n": 2})
    primero = cola.recibir(NOMBRE)
    segundo = cola.recibir(NOMBRE)
    assert (primero.id, primero.cuerpo) == (primero_id, {"n": 1})
    assert (segundo.id, segundo.cuerpo) == (segundo_id, {"n": 2})
    assert cola.recibir(NOMBRE) is None
    assert cola.pendientes(NOMBRE) == 2

    cola.completar(primero)
    assert cola.pendientes(NOMBRE) == 1
    assert cola.recibir(NOMBRE) is None
    cola.completar(segundo)


def test_cola_abandonar_vuelve_a_entregar(cola):
    id_mensaje = cola.publicar(NOMBRE, {"n": 1})
    primero = cola.recibir(NOMBRE)
    assert primero.entregas == 1
    cola.abandonar(primero)

    otra_vez = cola.recibir(NOMBRE)
    assert (otra_vez.id, otra_vez.cuerpo) == (id_mensaje, {"n": 1})
    assert otra_vez.entregas == 2
    cola.completar(otra_vez)


def test_cola_demora_con_reloj_real(cola, implementacion_cola):
    _, demora_s, plazo_s = implementacion_cola
    id_mensaje = cola.publicar(NOMBRE, {"n": 1}, demora_s=demora_s)
    assert cola.recibir(NOMBRE) is None

    limite = monotonic() + plazo_s
    while monotonic() < limite:
        mensaje = cola.recibir(NOMBRE)
        if mensaje is not None:
            a_tiempo = monotonic() <= limite
            cola.completar(mensaje)
            assert a_tiempo, f"El mensaje {id_mensaje} llegó después de {plazo_s} s"
            assert mensaje.id == id_mensaje
            return
        sleep(0.01)
    pytest.fail(f"El mensaje {id_mensaje} no llegó en {plazo_s} s")


def test_cola_lleva_las_propiedades_aparte_del_cuerpo(cola):
    cuerpo = {"n": 1}
    propiedades = {"intento": 2, "esperas": 3, "origen": "revisión"}
    cola.publicar(NOMBRE, cuerpo, propiedades=propiedades)
    mensaje = cola.recibir(NOMBRE)
    assert mensaje.cuerpo == cuerpo
    assert mensaje.propiedades == propiedades
    for clave, valor in propiedades.items():
        assert type(mensaje.propiedades[clave]) is type(valor)
    cola.completar(mensaje)


def test_cola_rechaza_resolver_un_mensaje_sin_entrega(cola, resolver):
    id_mensaje = cola.publicar(NOMBRE, {})
    with pytest.raises(c.ErrorCola):
        resolver(c.Mensaje(id_mensaje, NOMBRE, {}))

    mensaje = cola.recibir(NOMBRE)
    cola.completar(mensaje)
    with pytest.raises(c.ErrorCola):
        resolver(mensaje)


def test_cola_rechaza_una_entrega_vieja(cola, resolver):
    id_mensaje = cola.publicar(NOMBRE, {})
    primera = cola.recibir(NOMBRE)
    copia = deepcopy(primera)
    cola.abandonar(primera)
    with pytest.raises(c.BloqueoPerdido):
        resolver(copia)

    vigente = cola.recibir(NOMBRE)
    assert vigente.id == id_mensaje
    with pytest.raises(c.BloqueoPerdido):
        resolver(copia)
    cola.completar(vigente)


def test_cola_copia_el_cuerpo(cola):
    cuerpo = {"lista": [1]}
    cola.publicar(NOMBRE, cuerpo)
    cuerpo["lista"].append(2)
    mensaje = cola.recibir(NOMBRE)
    assert mensaje.cuerpo == {"lista": [1]}
    cola.completar(mensaje)


def test_cola_publicar_exige_json_y_una_cola_conocida(cola):
    with pytest.raises(TypeError):
        cola.publicar(NOMBRE, {"no_json": object()})
    with pytest.raises(c.ErrorCola):
        cola.publicar("otra", {})


def test_cola_pendientes_cuenta_visibles_y_bloqueados_sin_errores(cola):
    cola.publicar(NOMBRE, {"n": 1})
    primero = cola.recibir(NOMBRE)
    cola.a_errores(primero, "bug")
    [en_errores] = cola.errores(NOMBRE)
    assert (en_errores.mensaje.id, en_errores.mensaje.cuerpo, en_errores.motivo) == (primero.id, {"n": 1}, "bug")
    assert cola.pendientes(NOMBRE) == 0

    cola.publicar(NOMBRE, {"n": 2})
    bloqueado = cola.recibir(NOMBRE)
    cola.publicar(NOMBRE, {"n": 3})
    assert cola.pendientes(NOMBRE) == 2
    cola.completar(bloqueado)
    cola.completar(cola.recibir(NOMBRE))

    assert cola.reenviar_errores(NOMBRE) == 1
    cola.completar(cola.recibir(NOMBRE))


def test_cola_reenvia_errores_en_orden_y_desde_la_primera_entrega(cola):
    propiedades = {"intento": 4, "esperas": 2, "origen": "prueba", "prioridad": 7}
    ids_originales = []
    for n in (1, 2):
        ids_originales.append(cola.publicar(NOMBRE, {"n": n}, propiedades=propiedades))
        cola.abandonar(cola.recibir(NOMBRE))
        mensaje = cola.recibir(NOMBRE)
        assert mensaje.entregas == 2
        cola.a_errores(mensaje, "bug")

    assert cola.reenviar_errores(NOMBRE) == 2
    assert cola.errores(NOMBRE) == []
    for n in (1, 2):
        mensaje = cola.recibir(NOMBRE)
        assert mensaje.id not in ids_originales
        assert mensaje.cuerpo == {"n": n}
        assert mensaje.propiedades == {"origen": "prueba", "prioridad": 7}
        assert mensaje.entregas == 1
        cola.completar(mensaje)


def test_cola_reenviar_errores_vacia_devuelve_cero(cola):
    assert cola.reenviar_errores(NOMBRE) == 0
