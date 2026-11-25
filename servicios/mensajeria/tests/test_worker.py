"""El bucle de un worker: vaciar, límites, señales, hilos y código de salida (T02)."""

import logging
import os
import signal
import threading

import pytest

from mensajeria import worker
from mensajeria.cola import NORMALIZAR, ColaEnMemoria
from mensajeria.errores import ErrorDeConfiguracion, ErrorTransitorio
from mensajeria.parametros import Parametros
from mensajeria.reloj import RelojManual
from mensajeria.worker import Limites, atender_senales, informar, vaciar


class Manejador:
    cola = NORMALIZAR

    def __init__(self, al_procesar=None):
        self.vistos = []
        self.fallidos = []
        self._al_procesar = al_procesar
        self._candado = threading.Lock()

    def procesar(self, cuerpo):
        with self._candado:
            self.vistos.append(cuerpo["n"])
        if self._al_procesar:
            self._al_procesar(cuerpo)

    def al_fallar(self, cuerpo, motivo):
        self.fallidos.append(cuerpo["n"])


class RelojDePrueba:
    """Reloj monótono que avanza lo que se le pida."""

    def __init__(self):
        self.ahora = 0.0

    def __call__(self):
        return self.ahora


@pytest.fixture
def cola():
    return ColaEnMemoria(RelojManual())


def _publicar(cola, cuantos):
    for n in range(cuantos):
        cola.publicar(NORMALIZAR, {"id_proceso": "SR1", "entrega": f"OF-{n:03}", "n": n})


def test_vacia_la_cola_y_termina(cola):
    _publicar(cola, 3)
    manejador = Manejador()
    resumen = vaciar([cola], manejador)
    assert manejador.vistos == [0, 1, 2]
    assert (resumen.mensajes, resumen.motivo_fin, resumen.codigo_salida) == (3, worker.VACIA, 0)
    assert resumen.desenlaces == {"ok": 3}


def test_los_mensajes_con_demora_no_hacen_esperar(cola):
    cola.publicar(NORMALIZAR, {"n": 0}, demora_s=600)
    resumen = vaciar([cola], Manejador())
    assert (resumen.mensajes, resumen.motivo_fin) == (0, worker.VACIA)
    assert cola.pendientes(NORMALIZAR) == 1


def test_un_reintento_cuenta_y_queda_en_la_cola(cola):
    _publicar(cola, 1)

    def fallar(_):
        raise ErrorTransitorio("servicio caído")

    resumen = vaciar([cola], Manejador(fallar), parametros=Parametros(demora_base_s=60))
    assert resumen.desenlaces == {"reintento": 1}
    assert (resumen.motivo_fin, resumen.codigo_salida) == (worker.VACIA, 0)
    assert cola.pendientes(NORMALIZAR) == 1


def test_un_mensaje_a_errores_no_cambia_el_codigo_de_salida(cola):
    _publicar(cola, 2)

    def fallar(cuerpo):
        if cuerpo["n"] == 0:
            raise KeyError("bug")

    manejador = Manejador(fallar)
    resumen = vaciar([cola], manejador)
    assert resumen.desenlaces == {"a_errores": 1, "ok": 1}
    assert manejador.fallidos == [0]
    assert resumen.codigo_salida == 0


def test_deja_de_tomar_mensajes_al_cumplir_el_limite_de_tiempo(cola):
    _publicar(cola, 5)
    reloj = RelojDePrueba()

    def avanzar(_):
        reloj.ahora += 10

    resumen = vaciar([cola], Manejador(avanzar), limites=Limites(tomar_mensajes_s=25), reloj=reloj)
    assert (resumen.mensajes, resumen.motivo_fin) == (3, worker.TIEMPO)
    assert cola.pendientes(NORMALIZAR) == 2
    assert resumen.duracion_s == 30


def test_respeta_el_maximo_de_mensajes(cola):
    _publicar(cola, 5)
    resumen = vaciar([cola], Manejador(), limites=Limites(max_mensajes=2))
    assert (resumen.mensajes, resumen.motivo_fin) == (2, worker.MENSAJES)
    assert cola.pendientes(NORMALIZAR) == 3


def test_la_senal_termina_el_mensaje_en_curso_y_no_toma_otro(cola):
    _publicar(cola, 3)
    detener = threading.Event()
    manejador = Manejador(lambda _: detener.set())
    resumen = vaciar([cola], manejador, detener=detener)
    assert manejador.vistos == [0]
    assert (resumen.desenlaces, resumen.motivo_fin) == ({"ok": 1}, worker.SENAL)
    assert cola.pendientes(NORMALIZAR) == 2


def test_atender_senales_convierte_sigterm_en_pedido_de_terminar():
    detener = threading.Event()
    anterior = signal.getsignal(signal.SIGTERM)
    with atender_senales(detener):
        os.kill(os.getpid(), signal.SIGTERM)
        assert detener.wait(1)
    assert signal.getsignal(signal.SIGTERM) is anterior


def test_varios_hilos_con_su_cola_procesan_cada_mensaje_una_vez(cola):
    _publicar(cola, 20)
    a_la_vez = []
    activos = 0
    candado = threading.Lock()
    juntos = threading.Barrier(3, timeout=5)

    def trabajar(cuerpo):
        nonlocal activos
        with candado:
            activos += 1
            a_la_vez.append(activos)
        if cuerpo["n"] < 3:
            juntos.wait()
        with candado:
            activos -= 1

    manejador = Manejador(trabajar)
    resumen = vaciar([cola, cola, cola], manejador)
    assert sorted(manejador.vistos) == list(range(20))
    assert resumen.desenlaces == {"ok": 20}
    assert max(a_la_vez) == 3


class ColaQueFalla(ColaEnMemoria):
    def __init__(self, reloj, error):
        super().__init__(reloj)
        self._error = error

    def recibir(self, nombre):
        raise self._error


@pytest.mark.parametrize(("error", "codigo"), [
    (ErrorDeConfiguracion("Service Bus recibir: sin permiso"), 2),
    (ConnectionError("red"), 1),
])
def test_una_falla_de_la_cola_corta_la_ejecucion_con_su_codigo(error, codigo):
    resumen = vaciar([ColaQueFalla(RelojManual(), error)], Manejador())
    assert (resumen.motivo_fin, resumen.falla, resumen.codigo_salida) == (worker.FALLA, error, codigo)


def test_una_falla_en_un_hilo_detiene_a_los_demas(cola):
    _publicar(cola, 50)
    fallo = threading.Event()

    class ColaQueAvisa(ColaQueFalla):
        def recibir(self, nombre):
            try:
                super().recibir(nombre)
            finally:
                fallo.set()

    def esperar_la_falla(cuerpo):
        if cuerpo["n"] == 0:
            assert fallo.wait(5)
            # Deja que el hilo roto marque el fin antes de pedir otro turno.
            threading.Event().wait(0.2)

    rota = ColaQueAvisa(RelojManual(), ConnectionError("red"))
    resumen = vaciar([cola, rota], Manejador(esperar_la_falla))
    assert (resumen.motivo_fin, resumen.codigo_salida) == (worker.FALLA, 1)
    assert resumen.mensajes == 1
    assert cola.pendientes(NORMALIZAR) == 49


def test_informar_registra_solo_conteos(cola, caplog):
    _publicar(cola, 2)
    resumen = vaciar([cola], Manejador())
    with caplog.at_level(logging.INFO, logger="mensajeria"):
        assert informar(resumen) == 0
    [linea] = [r for r in caplog.records if r.name == "mensajeria.worker"]
    assert linea.getMessage() == "Worker normalizar: 2 mensajes {'ok': 2}, terminó por vacia en 0.0 s"


def test_informar_una_falla_sin_su_mensaje(caplog):
    resumen = vaciar([ColaQueFalla(RelojManual(), ConnectionError("Juan Pérez"))], Manejador())
    with caplog.at_level(logging.INFO, logger="mensajeria"):
        assert informar(resumen) == 1
    assert "Juan" not in caplog.text
    assert "ConnectionError" in caplog.text


@pytest.mark.parametrize("limites", [{"tomar_mensajes_s": 0}, {"max_mensajes": 0}])
def test_limites_invalidos(limites):
    with pytest.raises(ValueError):
        Limites(**limites)
