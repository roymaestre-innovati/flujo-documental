"""Una sola ejecución normaliza una entrega a la vez (T04 de tasks-workers.md, decisión 6)."""

import datetime

import pytest

from fabrica import P, Mundo, escribir, pdf
from orquestador import cola as c
from orquestador import estados
from orquestador.errores import ErrorTransitorio, procesar_uno
from orquestador.normalizar import Normalizar
from orquestador.parametros import Parametros


@pytest.fixture
def mundo(tmp_path):
    escribir(tmp_path, "OF-001/carta.pdf", pdf(2, "Carta de presentación"))
    mundo = Mundo(tmp_path)
    mundo.abrir()
    return mundo


def _otra_ejecucion(mundo, **parametros):
    """Otro worker sobre el mismo estado, cola y almacén."""
    return Normalizar(mundo.cola, mundo.estado, mundo.origen, mundo.almacen, mundo.reloj,
                      parametros=Parametros(**parametros))


def _oferente(mundo):
    return mundo.estado.leer(P, estados.OFERENTE, "OF-001")


def _reservar_para(mundo, dueno, duracion_s=2400):
    return estados.reservar(mundo.estado, mundo.reloj, P, estados.OFERENTE, "OF-001",
                            (estados.RECIBIDO, estados.ERROR_PROCESO), estados.NORMALIZANDO, dueno,
                            duracion_s, "normalización empezada")


def test_reservar_gana_uno_solo_y_el_otro_ve_la_reserva(mundo):
    registro = _reservar_para(mundo, "a")
    assert registro.datos["estado"] == estados.NORMALIZANDO
    assert registro.datos["reserva"]["dueno"] == "a"
    assert registro.datos["reserva"]["desde"] == estados.RECIBIDO
    with pytest.raises(estados.Reservado) as reservado:
        _reservar_para(mundo, "b")
    assert reservado.value.vence == mundo.reloj.ahora() + datetime.timedelta(seconds=2400)
    assert _reservar_para(mundo, "a").version == registro.version


def test_dos_ejecuciones_a_la_vez_normalizan_una_sola_vez(mundo):
    mundo.cola.publicar(c.NORMALIZAR, {"id_proceso": P, "entrega": "OF-001"})
    _reservar_para(mundo, "otra-ejecucion")

    resultados = mundo.correr(_otra_ejecucion(mundo))

    assert [r.desenlace for r in resultados] == ["espera", "espera"]
    assert _oferente(mundo).datos["reserva"]["dueno"] == "otra-ejecucion"
    assert not list((mundo.salida).glob("**/*.pdf"))
    assert mundo.cola.pendientes(c.NORMALIZAR) == 2


def test_la_espera_dura_lo_que_le_queda_a_la_reserva(mundo):
    _reservar_para(mundo, "otra", duracion_s=600)
    mundo.reloj.adelantar(100)
    with pytest.raises(ErrorTransitorio) as error:
        _otra_ejecucion(mundo).procesar({"id_proceso": P, "entrega": "OF-001"})
    assert error.value.espera_s == 501


def test_una_reserva_vencida_se_toma_y_se_termina(mundo):
    _reservar_para(mundo, "ejecucion-muerta")
    mundo.reloj.adelantar(2401)
    mundo.cola.publicar(c.NORMALIZAR, {"id_proceso": P, "entrega": "OF-001"})

    assert [r.desenlace for r in mundo.correr(_otra_ejecucion(mundo))] == ["ok", "ok"]

    oferente = _oferente(mundo)
    assert oferente.datos["estado"] == estados.PROCESANDO
    assert oferente.datos["reserva"] is None
    pasos = [(h["de"], h["a"], h["motivo"]) for h in oferente.datos["historial"]]
    assert (estados.NORMALIZANDO, estados.NORMALIZANDO, "reserva vencida") in pasos
    assert len(mundo.sacar(c.CLASIFICAR)) == 1


def test_un_intento_fallido_suelta_la_reserva_y_el_reintento_no_espera(mundo, monkeypatch):
    normalizar = _otra_ejecucion(mundo)
    caidas = []

    def bajar_y_fallar(*args, **kwargs):
        if not caidas:
            caidas.append(1)
            raise ErrorTransitorio("origen caído")
        return bajar(*args, **kwargs)

    bajar = normalizar._bajar_entrega
    monkeypatch.setattr(normalizar, "_bajar_entrega", bajar_y_fallar)

    assert [r.desenlace for r in mundo.correr(normalizar)] == ["reintento"]
    mundo.reloj.adelantar(120)
    assert [r.desenlace for r in mundo.correr(normalizar)] == ["ok"]
    pasos = [(h["de"], h["a"]) for h in _oferente(mundo).datos["historial"]]
    assert pasos == [(None, estados.RECIBIDO), (estados.RECIBIDO, estados.NORMALIZANDO),
                     (estados.NORMALIZANDO, estados.RECIBIDO), (estados.RECIBIDO, estados.NORMALIZANDO),
                     (estados.NORMALIZANDO, estados.PROCESANDO)]


def test_al_fallar_no_pisa_la_reserva_de_otra_ejecucion(mundo):
    _reservar_para(mundo, "otra")
    _otra_ejecucion(mundo).al_fallar({"id_proceso": P, "entrega": "OF-001"}, "Bug: algo")
    assert _oferente(mundo).datos["estado"] == estados.NORMALIZANDO


def test_un_bug_deja_la_entrega_en_error_y_se_puede_reintentar(mundo, monkeypatch):
    normalizar = _otra_ejecucion(mundo)
    monkeypatch.setattr(normalizar, "_bajar_entrega", lambda *a, **k: (_ for _ in ()).throw(KeyError("bug")))
    assert [r.desenlace for r in mundo.correr(normalizar)] == ["a_errores"]
    oferente = _oferente(mundo)
    assert (oferente.datos["estado"], oferente.datos["reserva"]) == (estados.ERROR_PROCESO, None)

    monkeypatch.undo()
    mundo.cola.publicar(c.NORMALIZAR, {"id_proceso": P, "entrega": "OF-001"})
    assert [r.desenlace for r in mundo.correr(normalizar)] == ["ok"]
    assert _oferente(mundo).datos["estado"] == estados.PROCESANDO


def test_si_otra_ejecucion_tomo_la_reserva_no_se_publica_nada(mundo, monkeypatch):
    normalizar = _otra_ejecucion(mundo)
    original = normalizar._bajar_entrega

    def bajar_y_perder_la_reserva(*args, **kwargs):
        original(*args, **kwargs)
        # Mientras esta ejecución trabaja, su reserva vence y otra la toma.
        mundo.reloj.adelantar(2401)
        _reservar_para(mundo, "otra")

    monkeypatch.setattr(normalizar, "_bajar_entrega", bajar_y_perder_la_reserva)
    assert [r.desenlace for r in mundo.correr(normalizar)] == ["ok"]
    assert _oferente(mundo).datos["reserva"]["dueno"] == "otra"
    assert mundo.sacar(c.CLASIFICAR) == []
    assert mundo.estado.listar(P, estados.DOCUMENTO) == []


def test_el_paso_a_procesando_exige_la_reserva(mundo):
    with pytest.raises(estados.TransicionNoPermitida):
        estados.cambiar(mundo.estado, mundo.reloj, P, estados.OFERENTE, "OF-001",
                        estados.RECIBIDO, estados.PROCESANDO, "sin reservar")


def test_cambiar_con_respetar_reserva_no_pisa_una_reserva_ajena(mundo):
    _reservar_para(mundo, "otra")
    with pytest.raises(estados.Reservado):
        estados.cambiar(mundo.estado, mundo.reloj, P, estados.OFERENTE, "OF-001",
                        estados.NORMALIZANDO, estados.ERROR_PROCESO, "falla", respetar_reserva=True, dueno="a")
    estados.cambiar(mundo.estado, mundo.reloj, P, estados.OFERENTE, "OF-001",
                    estados.NORMALIZANDO, estados.ERROR_PROCESO, "falla", respetar_reserva=True, dueno="otra")
    assert _oferente(mundo).datos["estado"] == estados.ERROR_PROCESO


def test_al_fallar_no_pisa_una_reserva_tomada_entre_la_lectura_y_la_escritura(mundo, monkeypatch):
    original = mundo.estado.reemplazar
    tomada = []

    def reservar_antes(registro, nuevos):
        if not tomada:
            tomada.append(1)
            _reservar_para(mundo, "otra")  # cambia la versión: este reemplazo da Conflicto
        return original(registro, nuevos)

    monkeypatch.setattr(mundo.estado, "reemplazar", reservar_antes)
    _otra_ejecucion(mundo).al_fallar({"id_proceso": P, "entrega": "OF-001"}, "Bug: algo")

    oferente = _oferente(mundo)
    assert oferente.datos["estado"] == estados.NORMALIZANDO
    assert oferente.datos["reserva"]["dueno"] == "otra"


def test_el_cierre_no_pisa_una_reserva_tomada_mientras_se_publicaba(mundo, monkeypatch):
    normalizar = _otra_ejecucion(mundo)
    original = normalizar._registrar

    def registrar_y_perder_la_reserva(*args, **kwargs):
        original(*args, **kwargs)
        mundo.reloj.adelantar(2401)
        _reservar_para(mundo, "otra")

    monkeypatch.setattr(normalizar, "_registrar", registrar_y_perder_la_reserva)
    mundo.correr(normalizar)
    oferente = _oferente(mundo)
    assert oferente.datos["estado"] == estados.NORMALIZANDO
    assert oferente.datos["reserva"]["dueno"] == "otra"


def test_si_otra_ejecucion_termino_antes_de_reservar_es_un_mensaje_repetido(mundo, monkeypatch):
    normalizar = _otra_ejecucion(mundo)
    original = normalizar._reservar

    def otra_termina_antes(*args):
        _otra_ejecucion(mundo).procesar({"id_proceso": P, "entrega": "OF-001"})
        return original(*args)

    monkeypatch.setattr(normalizar, "_reservar", otra_termina_antes)
    assert [r.desenlace for r in mundo.correr(normalizar)] == ["ok"]
    assert _oferente(mundo).datos["estado"] == estados.PROCESANDO
    assert len(mundo.sacar(c.CLASIFICAR)) == 1
