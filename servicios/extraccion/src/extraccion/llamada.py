"""La llamada al LLM con sus reintentos y el tope de llamadas a la vez (R49 a R52).

| Falla               | Reintentos                          | Espera                                |
|---------------------|-------------------------------------|---------------------------------------|
| `LimiteDeUso` (429) | Sin tope, hasta una espera total    | La que pidió el servicio, o la fija   |
| `FallaPasajera`     | 3                                   | 2, 4 y 8 s                            |
| `RespuestaInvalida` | 2                                   | Ninguna; se agrega el error de forma  |
| Cualquier otra      | Ninguno: es un bug y se lanza       |                                       |

Los números salen de `parametros.json`. Agotados los reintentos, `LlamadaFallida`,
un `error_proceso` reintentable. Los 429 no cuentan como reintentos.

El semáforo rodea solo la llamada al cliente: las esperas se hacen afuera, para
no ocupar un lugar mientras tanto. Un mismo `Llamador` se comparte entre todos
los segmentos del proceso.
"""

import threading
from dataclasses import dataclass

from .entrada import ERROR_PROCESO, ErrorDeSolicitud
from .llm import ClienteLLM, FallaPasajera, LimiteDeUso
from .parametros import parametros
from .posvalidacion import RespuestaInvalida, interpretar
from .reloj import Reloj

MAX_ERRORES_DE_FORMA = 10
"""Cuántos errores de forma se le devuelven al LLM al pedirle otra vez la respuesta."""


@dataclass(frozen=True)
class Llamada:
    respuesta: dict
    """La respuesta del LLM ya interpretada, con la forma de `respuesta.schema.json`."""
    tokens_entrada: int
    tokens_salida: int
    """Sumados sobre todos los intentos: es lo que se pagó."""
    modelo: str
    reintentos: int


class LlamadaFallida(ErrorDeSolicitud):
    """Se agotaron los reintentos. Lleva lo gastado, para la `ejecucion` del resultado."""

    def __init__(self, codigo: str, mensaje: str, reintentos: int, tokens_entrada: int, tokens_salida: int,
                 modelo: str | None) -> None:
        super().__init__(ERROR_PROCESO, codigo, mensaje, reintentable=True)
        self.reintentos = reintentos
        self.tokens_entrada = tokens_entrada
        self.tokens_salida = tokens_salida
        self.modelo = modelo


def pedir_de_nuevo(errores: list[str]) -> dict:
    """El mensaje que se agrega cuando la respuesta no tenía la forma pedida."""
    lista = "; ".join(errores[:MAX_ERRORES_DE_FORMA])
    if len(errores) > MAX_ERRORES_DE_FORMA:
        lista += f"; y {len(errores) - MAX_ERRORES_DE_FORMA} más"
    return {
        "role": "user",
        "content": "Tu respuesta anterior no tenía la forma pedida: " + lista + ". "
                   "Responde de nuevo con un único objeto JSON con la forma indicada, sin texto antes ni después.",
    }


class Llamador:
    def __init__(self, cliente: ClienteLLM, reloj: Reloj, ajustes: dict | None = None) -> None:
        self._cliente = cliente
        self._reloj = reloj
        self._ajustes = ajustes or parametros()["llamada"]
        self._semaforo = threading.BoundedSemaphore(self._ajustes["concurrencia"])

    def llamar(self, mensajes: list[dict]) -> Llamada:
        a = self._ajustes
        pasajeras = invalidas = 0
        espera_por_limite = 0.0
        tokens_entrada = tokens_salida = 0
        modelo = None
        enviados = list(mensajes)

        def fallida(codigo: str, mensaje: str) -> LlamadaFallida:
            return LlamadaFallida(codigo, mensaje, pasajeras + invalidas, tokens_entrada, tokens_salida, modelo)

        while True:
            try:
                with self._semaforo:
                    respuesta = self._cliente.responder(enviados)
            except LimiteDeUso as limite:
                espera = limite.espera if limite.espera is not None else a["espera_limite_uso_s"]
                if espera_por_limite + espera > a["espera_limite_uso_total_s"]:
                    raise fallida("LLM_NO_DISPONIBLE",
                                  f"El LLM siguió pidiendo esperar después de {espera_por_limite:.0f} s") from None
                espera_por_limite += espera
                self._reloj.dormir(espera)
                continue
            except FallaPasajera as falla:
                if pasajeras >= a["reintentos_falla_pasajera"]:
                    raise fallida("LLM_NO_DISPONIBLE",
                                  f"El LLM no respondió después de {pasajeras + 1} intentos: {falla}") from None
                self._reloj.dormir(a["esperas_falla_pasajera_s"][pasajeras])
                pasajeras += 1
                continue

            tokens_entrada += respuesta.tokens_entrada
            tokens_salida += respuesta.tokens_salida
            modelo = respuesta.modelo
            try:
                interpretada = interpretar(respuesta.texto)
            except RespuestaInvalida as invalida:
                if invalidas >= a["reintentos_respuesta_invalida"]:
                    raise fallida("RESPUESTA_INVALIDA",
                                  f"El LLM no dio la forma pedida en {invalidas + 1} intentos") from None
                invalidas += 1
                enviados = [*mensajes, pedir_de_nuevo(invalida.errores)]
                continue
            return Llamada(interpretada, tokens_entrada, tokens_salida, modelo, pasajeras + invalidas)
