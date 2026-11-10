"""El LLM detrás de una interfaz pequeña, y un LLM falso para las pruebas.

`ClienteLLM.responder` recibe los mensajes ya armados y devuelve el texto de la
respuesta con los tokens. Las fallas se traducen a dos excepciones, que son las
que se reintentan (R49):

- `LimiteDeUso`: el servicio pidió esperar (429). No cuenta como intento.
- `FallaPasajera`: tiempo agotado, error 5xx o de conexión.

Cualquier otra excepción es un bug y no se reintenta. La respuesta con forma
inválida no es una excepción del cliente: la detecta la posvalidación.
"""

import re
import threading
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


class LimiteDeUso(Exception):
    def __init__(self, espera: float | None = None) -> None:
        self.espera = espera
        """Segundos que pidió el servicio (`retry-after`), o None si no dijo."""
        super().__init__(f"Límite de uso del LLM (espera pedida: {espera})")


class FallaPasajera(Exception):
    """El LLM no respondió por una causa que puede pasar sola."""


class PedidoRechazado(Exception):
    """El LLM rechazó este pedido (400): muy grande, demasiadas imágenes, filtro de contenido.

    Mandarlo otra vez da lo mismo: no se reintenta. Lleva solo el código del error,
    nunca su mensaje, que podría citar el contenido.
    """

    def __init__(self, codigo: str | None) -> None:
        self.codigo = codigo or "sin_codigo"
        super().__init__(f"El LLM rechazó el pedido ({self.codigo})")


@dataclass(frozen=True)
class Respuesta:
    texto: str
    tokens_entrada: int
    tokens_salida: int
    modelo: str


class ClienteLLM(ABC):
    modelo: str
    """El modelo configurado (el deployment). Va en `ejecucion.modelo_llm` cuando no hubo respuesta."""

    @abstractmethod
    def responder(self, mensajes: list[dict]) -> Respuesta:
        """Una vuelta: los mensajes (formato chat completions) y la respuesta."""


TIPO_DOCUMENTAL = re.compile(r"Tipo documental: (TD-\d{2})")
"""El mensaje del usuario dice el TD con esta forma (ver `mensaje.py`)."""

Salida = str | Respuesta | BaseException
"""Lo que puede dar el LLM falso: un texto, una respuesta completa o una falla."""


def _textos(mensajes: list[dict]) -> str:
    partes = []
    for m in mensajes:
        contenido = m.get("content")
        if isinstance(contenido, str):
            partes.append(contenido)
        elif isinstance(contenido, list):
            partes.extend(p.get("text", "") for p in contenido if p.get("type") == "text")
    return "\n".join(partes)


class LLMFalso(ClienteLLM):
    """Responde sin red, con respuestas preparadas.

    - `programar(*salidas)` deja salidas en fila: cada llamada toma la primera.
      Una excepción en la fila se lanza, así se prueban los reintentos.
    - Sin nada en la fila, responde según el TD del mensaje, con `por_tipo`.
    - O con una función propia, `responder_con(mensajes) → salida`.

    Guarda los mensajes recibidos y cuántas llamadas hubo a la vez, para las
    pruebas de concurrencia.
    """

    def __init__(
        self,
        por_tipo: dict[str, str] | None = None,
        responder_con: Callable[[list[dict]], Salida] | None = None,
        modelo: str = "llm-falso",
        demora: Callable[[], None] | None = None,
    ) -> None:
        self._por_tipo = dict(por_tipo or {})
        self._responder_con = responder_con
        self._fila: deque[Salida] = deque()
        self.modelo = modelo
        self._demora = demora
        self._candado = threading.Lock()
        self._en_curso = 0
        self.max_a_la_vez = 0
        self.llamadas: list[list[dict]] = []

    def programar(self, *salidas: Salida) -> None:
        with self._candado:
            self._fila.extend(salidas)

    def responder(self, mensajes: list[dict]) -> Respuesta:
        with self._candado:
            self.llamadas.append(mensajes)
            self._en_curso += 1
            self.max_a_la_vez = max(self.max_a_la_vez, self._en_curso)
            salida = self._fila.popleft() if self._fila else None
        try:
            if self._demora:
                self._demora()
            if salida is None:
                salida = self._elegir(mensajes)
            if isinstance(salida, BaseException):
                raise salida
            if isinstance(salida, Respuesta):
                return salida
            return Respuesta(texto=salida, tokens_entrada=len(_textos(mensajes)) // 4,
                             tokens_salida=len(salida) // 4, modelo=self.modelo)
        finally:
            with self._candado:
                self._en_curso -= 1

    def _elegir(self, mensajes: list[dict]) -> Salida:
        if self._responder_con:
            return self._responder_con(mensajes)
        encontrado = TIPO_DOCUMENTAL.search(_textos(mensajes))
        if encontrado and encontrado.group(1) in self._por_tipo:
            return self._por_tipo[encontrado.group(1)]
        raise AssertionError("El LLM falso no tiene respuesta para este mensaje")
