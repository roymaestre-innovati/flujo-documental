"""Reintentos y concurrencia de la llamada, con el LLM falso y el reloj manual."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import respuesta_falsa
from extraccion.llamada import Llamada, LlamadaFallida, Llamador
from extraccion.llm import FallaPasajera, LimiteDeUso, LLMFalso, Respuesta
from extraccion.reloj import RelojManual

MENSAJES = [{"role": "system", "content": "prompt"}, {"role": "user", "content": "Tipo documental: TD-16"}]
VALIDA = respuesta_falsa("TD-16")


def llamador(llm: LLMFalso, **ajustes) -> tuple[Llamador, RelojManual]:
    reloj = RelojManual()
    base = {"concurrencia": 3, "reintentos_falla_pasajera": 3, "esperas_falla_pasajera_s": [2, 4, 8],
            "reintentos_respuesta_invalida": 2, "espera_limite_uso_s": 30, "espera_limite_uso_total_s": 900}
    return Llamador(llm, reloj, {**base, **ajustes}), reloj


def test_sin_fallas():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA})
    sujeto, reloj = llamador(llm)
    llamada = sujeto.llamar(MENSAJES)
    assert isinstance(llamada, Llamada)
    assert llamada.respuesta["corresponde"] is True
    assert llamada.reintentos == 0
    assert llamada.modelo == "llm-falso"
    assert reloj.esperas == []


def test_usa_los_parametros_del_servicio_por_defecto():
    sujeto = Llamador(LLMFalso(por_tipo={"TD-16": VALIDA}), RelojManual())
    assert sujeto.llamar(MENSAJES).reintentos == 0


def test_429_con_y_sin_espera_pedida_no_cuenta_como_reintento():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA})
    llm.programar(LimiteDeUso(12), LimiteDeUso(None), LimiteDeUso(0.5))
    sujeto, reloj = llamador(llm)
    llamada = sujeto.llamar(MENSAJES)
    assert reloj.esperas == [12, 30, 0.5]
    assert llamada.reintentos == 0
    assert len(llm.llamadas) == 4


def test_429_sin_fin_se_corta_en_la_espera_total():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA})
    llm.programar(*[LimiteDeUso(None)] * 40)
    sujeto, reloj = llamador(llm)
    with pytest.raises(LlamadaFallida) as error:
        sujeto.llamar(MENSAJES)
    assert sum(reloj.esperas) == 900
    assert len(reloj.esperas) == 30
    assert error.value.codigo == "LLM_NO_DISPONIBLE"
    assert error.value.estado == "error_proceso"
    assert error.value.reintentable is True
    assert error.value.reintentos == 0


def test_tres_fallas_pasajeras_y_luego_exito():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA})
    llm.programar(FallaPasajera(), FallaPasajera(), FallaPasajera())
    sujeto, reloj = llamador(llm)
    llamada = sujeto.llamar(MENSAJES)
    assert reloj.esperas == [2, 4, 8]
    assert llamada.reintentos == 3


def test_cuatro_fallas_pasajeras_agotan_los_reintentos():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA})
    llm.programar(*[FallaPasajera("tiempo agotado")] * 4)
    sujeto, reloj = llamador(llm)
    with pytest.raises(LlamadaFallida) as error:
        sujeto.llamar(MENSAJES)
    assert reloj.esperas == [2, 4, 8]
    assert len(llm.llamadas) == 4
    assert error.value.codigo == "LLM_NO_DISPONIBLE"
    assert error.value.reintentos == 3
    assert error.value.como_error() == {
        "codigo": "LLM_NO_DISPONIBLE",
        "mensaje": "El LLM no respondió después de 4 intentos: tiempo agotado",
        "reintentable": True,
    }


def test_dos_respuestas_invalidas_y_luego_valida():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA})
    llm.programar(Respuesta("esto no es JSON", 100, 10, "llm-falso"),
                  Respuesta('{"corresponde": true}', 100, 10, "llm-falso"))
    sujeto, reloj = llamador(llm)
    llamada = sujeto.llamar(MENSAJES)

    assert llamada.reintentos == 2
    assert reloj.esperas == []
    assert llamada.tokens_entrada > 200, "suma los dos intentos inválidos y el válido"
    primera, segunda, tercera = llm.llamadas
    assert primera == MENSAJES
    assert segunda[:2] == MENSAJES and len(segunda) == 3
    assert segunda[2]["role"] == "user"
    assert "no es JSON" in segunda[2]["content"]
    assert tercera[:2] == MENSAJES and len(tercera) == 3, "solo va el último error, no se acumulan"
    assert tercera[2]["content"] != segunda[2]["content"]
    assert "no es JSON" not in tercera[2]["content"]


def test_tres_respuestas_invalidas_agotan_los_reintentos():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA})
    llm.programar(*[Respuesta("[]", 100, 10, "gpt-5.4")] * 3)
    sujeto, _ = llamador(llm)
    with pytest.raises(LlamadaFallida) as error:
        sujeto.llamar(MENSAJES)
    assert len(llm.llamadas) == 3
    assert error.value.codigo == "RESPUESTA_INVALIDA"
    assert error.value.reintentable is True
    assert error.value.reintentos == 2
    assert (error.value.tokens_entrada, error.value.tokens_salida) == (300, 30)
    assert error.value.modelo == "gpt-5.4"


def test_tokens_suman_todos_los_intentos_con_respuesta():
    llm = LLMFalso()
    llm.programar(FallaPasajera(), Respuesta("{", 1000, 50, "gpt-5.4"), Respuesta(VALIDA, 1100, 400, "gpt-5.4"))
    sujeto, _ = llamador(llm)
    llamada = sujeto.llamar(MENSAJES)
    assert (llamada.tokens_entrada, llamada.tokens_salida) == (2100, 450)
    assert llamada.reintentos == 2
    assert llamada.modelo == "gpt-5.4"


def test_los_contadores_son_independientes():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA})
    llm.programar(FallaPasajera(), Respuesta("x", 1, 1, "m"), LimiteDeUso(5), FallaPasajera(),
                  Respuesta("x", 1, 1, "m"), FallaPasajera())
    sujeto, reloj = llamador(llm)
    llamada = sujeto.llamar(MENSAJES)
    assert reloj.esperas == [2, 5, 4, 8]
    assert llamada.reintentos == 5


def test_un_bug_no_se_reintenta():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA})
    llm.programar(ValueError("bug"))
    sujeto, reloj = llamador(llm)
    with pytest.raises(ValueError, match="bug"):
        sujeto.llamar(MENSAJES)
    assert len(llm.llamadas) == 1
    assert reloj.esperas == []


def test_nunca_mas_de_tres_llamadas_a_la_vez():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA}, demora=lambda: time.sleep(0.05))
    sujeto, _ = llamador(llm)
    with ThreadPoolExecutor(max_workers=10) as grupo:
        llamadas = list(grupo.map(lambda _: sujeto.llamar(MENSAJES), range(10)))
    assert len(llamadas) == 10
    assert llm.max_a_la_vez == 3


def test_el_semaforo_se_libera_si_la_llamada_falla():
    llm = LLMFalso(por_tipo={"TD-16": VALIDA})
    llm.programar(*[FallaPasajera()] * 4, *[ValueError("bug")] * 3)
    sujeto, _ = llamador(llm, concurrencia=1)
    with pytest.raises(LlamadaFallida):
        sujeto.llamar(MENSAJES)
    for _ in range(3):
        with pytest.raises(ValueError):
            sujeto.llamar(MENSAJES)
    hilo = threading.Thread(target=sujeto.llamar, args=(MENSAJES,))
    hilo.start()
    hilo.join(timeout=2)
    assert not hilo.is_alive()
