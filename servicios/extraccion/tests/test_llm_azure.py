"""El cliente de Azure OpenAI con un transporte HTTP falso: nunca toca la red."""

import json

import httpx2
import openai
import pytest

from extraccion.llm import FallaPasajera, LimiteDeUso, PedidoRechazado
from extraccion.llm_azure import (
    ConfiguracionIncompleta, DeploymentNoPermitido, LLMAzureOpenAI, _espera_pedida, url_base,
)

ENDPOINT = "https://recurso-falso.openai.azure.com/"
MENSAJES = [{"role": "system", "content": "prompt"}, {"role": "user", "content": "Tipo documental: TD-16"}]


def completado(texto: str | None = '{"corresponde": true}', modelo: str = "gpt-5.4-2026-03-05") -> dict:
    return {
        "id": "chatcmpl-falso", "object": "chat.completion", "created": 0, "model": modelo,
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": texto}}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 340, "total_tokens": 1540},
    }


class Servidor:
    """Responde cada pedido con lo que haya en la fila y guarda los pedidos."""

    def __init__(self, *salidas) -> None:
        self.salidas = list(salidas)
        self.pedidos: list[httpx2.Request] = []

    def __call__(self, pedido: httpx2.Request) -> httpx2.Response:
        self.pedidos.append(pedido)
        salida = self.salidas.pop(0)
        if isinstance(salida, Exception):
            raise salida
        return salida


def cliente(servidor: Servidor, deployment: str = "gpt-5.4") -> LLMAzureOpenAI:
    http = httpx2.Client(transport=httpx2.MockTransport(servidor))
    return LLMAzureOpenAI(ENDPOINT, "clave-falsa", deployment, tiempo_limite_s=5, http=http)


def test_manda_un_pedido_en_modo_json_y_devuelve_texto_y_tokens():
    servidor = Servidor(httpx2.Response(200, json=completado()))
    respuesta = cliente(servidor).responder(MENSAJES)

    assert respuesta.texto == '{"corresponde": true}'
    assert (respuesta.tokens_entrada, respuesta.tokens_salida) == (1200, 340)
    assert respuesta.modelo == "gpt-5.4-2026-03-05"
    [pedido] = servidor.pedidos
    assert str(pedido.url) == "https://recurso-falso.openai.azure.com/openai/v1/chat/completions"
    cuerpo = json.loads(pedido.content)
    assert cuerpo["model"] == "gpt-5.4"
    assert cuerpo["messages"] == MENSAJES
    assert cuerpo["response_format"] == {"type": "json_object"}
    assert "tools" not in cuerpo


def test_sin_texto_devuelve_cadena_vacia():
    servidor = Servidor(httpx2.Response(200, json=completado(texto=None)))
    assert cliente(servidor).responder(MENSAJES).texto == ""


@pytest.mark.parametrize("cabeceras, espera", [
    ({"retry-after": "12"}, 12.0),
    ({"retry-after-ms": "1500"}, 1.5),
    ({}, None),
    ({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
])
def test_429_es_limite_de_uso_con_la_espera_pedida(cabeceras, espera):
    servidor = Servidor(httpx2.Response(429, headers=cabeceras, json={"error": {"message": "lento"}}))
    with pytest.raises(LimiteDeUso) as error:
        cliente(servidor).responder(MENSAJES)
    assert error.value.espera == espera
    assert len(servidor.pedidos) == 1, "el cliente de openai no reintenta por su cuenta"


@pytest.mark.parametrize("salida", [
    httpx2.Response(500, json={"error": {"message": "falla"}}),
    httpx2.Response(503, json={"error": {"message": "falla"}}),
    httpx2.Response(408, json={"error": {"message": "tarde"}}),
    httpx2.TimeoutException("tiempo agotado"),
    httpx2.ConnectError("sin conexión"),
])
def test_fallas_pasajeras(salida):
    servidor = Servidor(salida)
    with pytest.raises(FallaPasajera):
        cliente(servidor).responder(MENSAJES)
    assert len(servidor.pedidos) == 1


@pytest.mark.parametrize("estado, cuerpo, codigo", [
    (400, {"error": {"code": "too_many_images", "message": "texto que podría citar el contenido"}}, "too_many_images"),
    (400, {"error": {"message": "sin código"}}, "sin_codigo"),
    (413, {"error": {"message": "muy grande"}}, "http_413"),
])
def test_pedido_rechazado_lleva_solo_el_codigo(estado, cuerpo, codigo):
    servidor = Servidor(httpx2.Response(estado, json=cuerpo))
    with pytest.raises(PedidoRechazado) as error:
        cliente(servidor).responder(MENSAJES)
    assert error.value.codigo == codigo
    assert "citar" not in str(error.value)


@pytest.mark.parametrize("estado, excepcion", [
    (401, openai.AuthenticationError),
    (404, openai.NotFoundError),
])
def test_otros_errores_se_dejan_pasar(estado, excepcion):
    servidor = Servidor(httpx2.Response(estado, json={"error": {"message": "no"}}))
    with pytest.raises(excepcion):
        cliente(servidor).responder(MENSAJES)


@pytest.mark.parametrize("deployment", ["gpt-5.4-mini", "GPT-5.4-Mini", "extraccion-mini"])
def test_rechaza_un_deployment_mini(deployment):
    with pytest.raises(DeploymentNoPermitido):
        cliente(Servidor(), deployment=deployment)


def test_desde_entorno_dice_que_falta_sin_mostrar_valores():
    with pytest.raises(ConfiguracionIncompleta) as error:
        LLMAzureOpenAI.desde_entorno({"AZURE_OPENAI_API_KEY": "secreto-123"})
    assert "AZURE_OPENAI_ENDPOINT" in str(error.value)
    assert "AZURE_OPENAI_DEPLOYMENT" in str(error.value)
    assert "secreto-123" not in str(error.value)


def test_desde_entorno_rechaza_mini():
    entorno = {"AZURE_OPENAI_ENDPOINT": ENDPOINT, "AZURE_OPENAI_API_KEY": "k",
               "AZURE_OPENAI_DEPLOYMENT": "gpt-5.4-mini"}
    with pytest.raises(DeploymentNoPermitido):
        LLMAzureOpenAI.desde_entorno(entorno)


@pytest.mark.parametrize("endpoint", [
    "https://r.openai.azure.com",
    "https://r.openai.azure.com/",
    "https://r.openai.azure.com/openai/deployments/gpt-5.4/chat/completions?api-version=2025-01-01",
])
def test_url_base(endpoint):
    assert url_base(endpoint) == "https://r.openai.azure.com/openai/v1/"


def test_espera_pedida_ignora_negativos():
    assert _espera_pedida({"retry-after": "-3"}) is None
