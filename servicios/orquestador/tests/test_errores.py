"""El bucle común y las clases de error (R18 a R21 y R23), con manejadores de juguete."""

import io
import json
import logging

import pytest

from orquestador import cola as c
from orquestador import registros
from orquestador.errores import (
    ErrorDelDocumento, ErrorTransitorio, RespuestaInvalida, procesar_uno, reenviar_errores,
)
from orquestador.parametros import Parametros
from orquestador.reloj import RelojManual


class Juguete:
    """Falla según una lista: un elemento por llamada; None es "sale bien"."""

    cola = c.CLASIFICAR

    def __init__(self, *fallas):
        self.fallas = list(fallas)
        self.procesados = []
        self.fallidos = []

    def procesar(self, cuerpo):
        falla = self.fallas.pop(0) if self.fallas else None
        if falla is not None:
            raise falla
        self.procesados.append(cuerpo)

    def al_fallar(self, cuerpo, motivo):
        self.fallidos.append((cuerpo, motivo))


@pytest.fixture
def reloj():
    return RelojManual()


@pytest.fixture
def cola(reloj):
    return c.ColaEnMemoria(reloj)


def _correr(cola, reloj, manejador, parametros=Parametros()):
    """Procesa hasta que no quede nada, adelantando el reloj en las demoras."""
    resultados = []
    while True:
        r = procesar_uno(cola, manejador, parametros)
        if r is not None:
            resultados.append(r)
            continue
        proxima = cola.proxima_visible()
        if proxima is None:
            return resultados
        reloj.adelantar((proxima - reloj.ahora()).total_seconds())


CUERPO = {"id_proceso": "SR1", "entrega": "OF-001", "id_documento": "OF-001-aaa"}


def test_sale_bien(cola, reloj):
    cola.publicar(c.CLASIFICAR, CUERPO)
    manejador = Juguete()
    assert [r.desenlace for r in _correr(cola, reloj, manejador)] == ["ok"]
    assert manejador.procesados == [CUERPO]
    assert cola.pendientes(c.CLASIFICAR) == 0


def test_cola_vacia(cola):
    assert procesar_uno(cola, Juguete()) is None


def test_error_del_documento_completa_sin_reintentar(cola, reloj):
    cola.publicar(c.CLASIFICAR, CUERPO)
    manejador = Juguete(ErrorDelDocumento())
    assert [r.desenlace for r in _correr(cola, reloj, manejador)] == ["error_documento"]
    assert manejador.fallidos == []
    assert cola.errores(c.CLASIFICAR) == []


def test_transitoria_se_reintenta_con_espera_creciente(cola, reloj):
    inicio = reloj.ahora()
    cola.publicar(c.CLASIFICAR, CUERPO)
    manejador = Juguete(ErrorTransitorio(), ErrorTransitorio())
    momentos = []
    original = manejador.procesar

    def procesar(cuerpo):
        momentos.append((reloj.ahora() - inicio).total_seconds())
        original(cuerpo)

    manejador.procesar = procesar
    desenlaces = [r.desenlace for r in _correr(cola, reloj, manejador)]
    assert desenlaces == ["reintento", "reintento", "ok"]
    assert momentos == [0, 120, 120 + 240]
    assert manejador.procesados == [CUERPO]


def test_transitoria_agotada_va_a_errores(cola, reloj):
    cola.publicar(c.CLASIFICAR, CUERPO)
    manejador = Juguete(*[ErrorTransitorio("caído")] * 4)
    desenlaces = [r.desenlace for r in _correr(cola, reloj, manejador)]
    assert desenlaces == ["reintento"] * 3 + ["a_errores"]
    [(cuerpo, motivo)] = manejador.fallidos
    assert cuerpo == CUERPO
    assert motivo.startswith("Transitoria sin resolver tras 4 intentos: ErrorTransitorio en")
    assert "caído" not in motivo, "el motivo no lleva el mensaje de la excepción"
    [en_errores] = cola.errores(c.CLASIFICAR)
    assert en_errores.motivo == motivo


def test_espera_pedida_no_cuenta_como_intento(cola, reloj):
    inicio = reloj.ahora()
    cola.publicar(c.CLASIFICAR, CUERPO)
    fallas = [ErrorTransitorio(espera_s=7)] * 5 + [ErrorTransitorio()] * 3
    manejador = Juguete(*fallas)
    desenlaces = [r.desenlace for r in _correr(cola, reloj, manejador)]
    assert desenlaces == ["espera"] * 5 + ["reintento"] * 3 + ["ok"]
    assert (reloj.ahora() - inicio).total_seconds() == 5 * 7 + 120 + 240 + 480


def test_esperas_sin_fin_terminan_como_transitoria(cola, reloj):
    cola.publicar(c.CLASIFICAR, CUERPO)
    manejador = Juguete(*[ErrorTransitorio(espera_s=1)] * 50)
    resultados = _correr(cola, reloj, manejador, Parametros(max_esperas=2, reintentos_transitorio=1))
    assert [r.desenlace for r in resultados] == ["espera", "espera", "reintento", "a_errores"]


def test_respuesta_invalida_se_reintenta_enseguida(cola, reloj):
    inicio = reloj.ahora()
    cola.publicar(c.CLASIFICAR, CUERPO)
    manejador = Juguete(RespuestaInvalida(), RespuestaInvalida(), RespuestaInvalida())
    desenlaces = [r.desenlace for r in _correr(cola, reloj, manejador)]
    assert desenlaces == ["reintento", "reintento", "a_errores"]
    assert reloj.ahora() == inicio
    assert manejador.fallidos[0][1].startswith("Respuesta inválida tras 3 intentos")


def test_bug_va_a_errores_sin_reintento(cola, reloj):
    cola.publicar(c.CLASIFICAR, CUERPO)
    manejador = Juguete(KeyError("ruta/de/Juan Pérez.pdf"))
    assert [r.desenlace for r in _correr(cola, reloj, manejador)] == ["a_errores"]
    [(_, motivo)] = manejador.fallidos
    assert motivo.startswith("Bug: KeyError en test_errores.py:")
    assert "Juan" not in motivo


def test_un_mensaje_fallido_no_frena_a_los_demas(cola, reloj):
    for n in range(3):
        cola.publicar(c.CLASIFICAR, {**CUERPO, "n": n})
    manejador = Juguete(None, ValueError(), None)
    desenlaces = [r.desenlace for r in _correr(cola, reloj, manejador)]
    assert desenlaces == ["ok", "a_errores", "ok"]
    assert [p["n"] for p in manejador.procesados] == [0, 2]


def test_si_al_fallar_tambien_falla_el_mensaje_va_a_errores_igual(cola, reloj):
    class Peor(Juguete):
        def al_fallar(self, cuerpo, motivo):
            raise RuntimeError("estado caído")

    cola.publicar(c.CLASIFICAR, CUERPO)
    assert [r.desenlace for r in _correr(cola, reloj, Peor(ValueError()))] == ["a_errores"]
    assert len(cola.errores(c.CLASIFICAR)) == 1


def test_reintentar_no_toca_el_cuerpo(cola, reloj):
    cola.publicar(c.CLASIFICAR, CUERPO, propiedades={"origen": "prueba"})
    manejador = Juguete(ErrorTransitorio())
    vistos = []
    original = manejador.procesar
    manejador.procesar = lambda cuerpo: (vistos.append(cuerpo), original(cuerpo))
    _correr(cola, reloj, manejador)
    assert vistos == [CUERPO, CUERPO]


def test_reenviar_errores_empieza_de_nuevo(cola, reloj):
    cola.publicar(c.CLASIFICAR, CUERPO, propiedades={"origen": "prueba"})
    _correr(cola, reloj, Juguete(*[ErrorTransitorio()] * 4))
    assert reenviar_errores(cola, c.CLASIFICAR) == 1
    assert cola.errores(c.CLASIFICAR) == []
    mensaje = cola.recibir(c.CLASIFICAR)
    assert mensaje.cuerpo == CUERPO
    assert mensaje.propiedades == {"origen": "prueba"}
    cola.abandonar(mensaje)
    # Arreglada la causa, sale bien al primer intento.
    manejador = Juguete()
    assert [r.desenlace for r in _correr(cola, reloj, manejador)] == ["ok"]
    assert reenviar_errores(cola, c.CLASIFICAR) == 0


def test_alerta_con_identificadores_y_sin_datos_personales(cola, reloj):
    salida = io.StringIO()
    registros.configurar(logging.INFO, salida)
    try:
        cola.publicar(c.CLASIFICAR, CUERPO)
        _correr(cola, reloj, Juguete(ValueError("Juan Pérez")))
    finally:
        registros.configurar(logging.INFO, io.StringIO())
    lineas = [json.loads(l) for l in salida.getvalue().splitlines()]
    [alerta] = [l for l in lineas if l["modulo"] == "orquestador.alertas"]
    assert alerta["nivel"] == "ERROR"
    assert (alerta["id_proceso"], alerta["id_oferente"], alerta["id_documento"]) == ("SR1", "OF-001", "OF-001-aaa")
    assert "Juan" not in salida.getvalue()
