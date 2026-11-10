"""El LLM real: gpt-5.4 en Azure OpenAI, por chat completions (D21, plan B).

Una vuelta, sin tools y con la respuesta en modo `json_object`. El cliente de
`openai` no reintenta (`max_retries=0`): los reintentos los hace `llamada.py`.
Las fallas se traducen a las excepciones de `llm.py`:

- 429: `LimiteDeUso`, con la espera que pidió el servicio si la dijo.
- Tiempo agotado, error de conexión, 408 y 5xx: `FallaPasajera`.
- 400 o 413 (pedido muy grande, demasiadas imágenes, filtro de contenido):
  `PedidoRechazado`, con el código del error. No se reintenta.
- Cualquier otra (401, 403, 404…): se deja pasar. Es un bug o una mala
  configuración, y no se reintenta.

gpt-5.4-mini no respeta las reglas de evidencia, así que un deployment con
`mini` en el nombre se rechaza al crear el cliente.
"""

from collections.abc import Mapping

import httpx2
import openai

from .llm import ClienteLLM, FallaPasajera, LimiteDeUso, PedidoRechazado, Respuesta
from .parametros import parametros

VARIABLES = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT")


class DeploymentNoPermitido(ValueError):
    """El deployment configurado no es gpt-5.4 completo."""


class ConfiguracionIncompleta(ValueError):
    """Faltan variables de entorno del LLM. El mensaje dice cuáles, nunca sus valores."""


def url_base(endpoint: str) -> str:
    """Acepta el endpoint del recurso o la URL completa que muestra Foundry; deja `…/openai/v1/`."""
    raiz = endpoint.split("/openai/")[0].rstrip("/")
    return f"{raiz}/openai/v1/"


def _espera_pedida(cabeceras: Mapping[str, str]) -> float | None:
    """Segundos de `retry-after-ms` o `retry-after`. Una fecha u otro formato da None."""
    for nombre, escala in (("retry-after-ms", 1000), ("retry-after", 1)):
        valor = cabeceras.get(nombre)
        if valor is None:
            continue
        try:
            segundos = float(valor) / escala
        except ValueError:
            continue
        if segundos >= 0:
            return segundos
    return None


class LLMAzureOpenAI(ClienteLLM):
    def __init__(
        self,
        endpoint: str,
        clave: str,
        deployment: str,
        tiempo_limite_s: float | None = None,
        http: httpx2.Client | None = None,
    ) -> None:
        """`http` es solo para las pruebas: un cliente con un transporte falso, sin red."""
        if "mini" in deployment.lower():
            raise DeploymentNoPermitido(
                f"El deployment {deployment!r} parece gpt-5.4-mini, que no respeta las reglas de evidencia. "
                "La extracción usa gpt-5.4."
            )
        if tiempo_limite_s is None:
            tiempo_limite_s = parametros()["llamada"]["tiempo_limite_s"]
        self.deployment = self.modelo = deployment
        self._cliente = openai.OpenAI(
            base_url=url_base(endpoint), api_key=clave, timeout=tiempo_limite_s, max_retries=0, http_client=http,
        )

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str], **opciones) -> "LLMAzureOpenAI":
        faltantes = [v for v in VARIABLES if not entorno.get(v)]
        if faltantes:
            raise ConfiguracionIncompleta(f"Faltan variables de entorno: {', '.join(faltantes)}")
        return cls(entorno["AZURE_OPENAI_ENDPOINT"], entorno["AZURE_OPENAI_API_KEY"],
                   entorno["AZURE_OPENAI_DEPLOYMENT"], **opciones)

    def responder(self, mensajes: list[dict]) -> Respuesta:
        try:
            respuesta = self._cliente.chat.completions.create(
                model=self.deployment, messages=mensajes, response_format={"type": "json_object"},
            )
        except openai.RateLimitError as error:
            raise LimiteDeUso(_espera_pedida(error.response.headers)) from None
        except openai.APIConnectionError as error:  # incluye el tiempo agotado
            raise FallaPasajera(f"El LLM no respondió: {type(error).__name__}") from None
        except openai.APIStatusError as error:
            if error.status_code >= 500 or error.status_code == 408:
                raise FallaPasajera(f"El LLM respondió {error.status_code}") from None
            if error.status_code in (400, 413):
                codigo = getattr(error, "code", None) or (f"http_{error.status_code}" if error.status_code == 413 else None)
                raise PedidoRechazado(codigo) from None
            raise
        uso = respuesta.usage
        # Sin texto (por ejemplo, cortada por largo o por el filtro de contenido) queda vacía:
        # la posvalidación la toma como respuesta inválida y se pide otra vez.
        texto = respuesta.choices[0].message.content if respuesta.choices else None
        return Respuesta(
            texto=texto or "",
            tokens_entrada=uso.prompt_tokens if uso else 0,
            tokens_salida=uso.completion_tokens if uso else 0,
            modelo=respuesta.model or self.deployment,
        )
