"""Los dobles de prueba: ficha de v21, respuestas falsas y LLM falso."""

import json
import threading
import time

import pytest

from extraccion import contratos
from extraccion.ficha import FichaNoEncontrada, FuenteModeloArchivo
from extraccion.llm import FallaPasajera, LimiteDeUso, LLMFalso, Respuesta

from conftest import EJEMPLOS, FICHA_V21, cargar, respuesta_falsa


def test_ficha_de_td16(fuente_modelo):
    ficha = fuente_modelo.ficha(21, "TD-16")
    assert ficha.version == 21 and ficha.tipo_documental == "TD-16"
    assert ficha.td_probado
    assert "Cómo interpretar el modelo" in ficha.guia
    ids = [e["id_tecnico"] for e in ficha.a_extraer()]
    salida = cargar(EJEMPLOS / "salida_td16.json")
    assert ids == [r["id_tecnico"] for r in salida["resultados"]]
    subtipo = ficha.a_extraer()[0]
    assert subtipo["valores_permitidos"] == ["PJ", "PN"]
    assert "trazabilidad" not in subtipo


def test_ficha_de_td29_sigue_el_orden_del_ejemplo(fuente_modelo):
    ficha = fuente_modelo.ficha(21, "TD-29")
    salida = cargar(EJEMPLOS / "salida_td29.json")
    assert [e["id_tecnico"] for e in ficha.a_extraer()] == [r["id_tecnico"] for r in salida["resultados"]]


def test_td_sin_marca_no_esta_probado(fuente_modelo):
    assert not fuente_modelo.ficha(21, "TD-01").td_probado


def test_version_o_td_que_no_existen(fuente_modelo):
    with pytest.raises(FichaNoEncontrada):
        fuente_modelo.ficha(20, "TD-16")
    with pytest.raises(FichaNoEncontrada):
        fuente_modelo.ficha(21, "TD-05")


def test_version_repetida_en_dos_archivos():
    with pytest.raises(ValueError):
        FuenteModeloArchivo(FICHA_V21, FICHA_V21)


@pytest.mark.parametrize("td", ["TD-16", "TD-29"])
def test_respuestas_falsas_cumplen_su_esquema(td):
    assert contratos.errores(contratos.RESPUESTA, json.loads(respuesta_falsa(td))) == []


def test_respuesta_con_revision_no_cumple():
    respuesta = json.loads(respuesta_falsa("TD-16"))
    respuesta["resultados"][0]["revision"] = True
    respuesta["resultados"][1]["motivos"] = ["NO_CUMPLE"]
    assert contratos.errores(contratos.RESPUESTA, respuesta) == [
        "resultados/0: no cumple 'additionalProperties'",
        "resultados/1/motivos/0: no cumple 'enum'",
    ]


def _mensajes(td):
    return [{"role": "system", "content": "…"},
            {"role": "user", "content": [{"type": "text", "text": f"Tipo documental: {td}\n…"}]}]


def test_llm_falso_responde_por_tipo():
    llm = LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16")})
    respuesta = llm.responder(_mensajes("TD-16"))
    assert json.loads(respuesta.texto)["corresponde"] is True
    assert respuesta.tokens_entrada > 0 and respuesta.modelo == "llm-falso"
    with pytest.raises(AssertionError):
        llm.responder(_mensajes("TD-29"))
    assert len(llm.llamadas) == 2


def test_llm_falso_con_fila_programada():
    llm = LLMFalso(por_tipo={"TD-16": "{}"})
    fija = Respuesta(texto="x", tokens_entrada=10, tokens_salida=2, modelo="gpt-5.4")
    llm.programar(LimiteDeUso(5), FallaPasajera("tiempo"), fija)
    with pytest.raises(LimiteDeUso) as limite:
        llm.responder(_mensajes("TD-16"))
    assert limite.value.espera == 5
    with pytest.raises(FallaPasajera):
        llm.responder(_mensajes("TD-16"))
    assert llm.responder(_mensajes("TD-16")) == fija
    assert llm.responder(_mensajes("TD-16")).texto == "{}"


def test_llm_falso_cuenta_llamadas_a_la_vez():
    barrera = threading.Barrier(3)
    llm = LLMFalso(responder_con=lambda m: "{}", demora=lambda: (barrera.wait(timeout=5), time.sleep(0.01)))
    hilos = [threading.Thread(target=llm.responder, args=(_mensajes("TD-16"),)) for _ in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert llm.max_a_la_vez == 3
