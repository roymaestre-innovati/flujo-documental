"""Clases de error y el bucle común que corre cada manejador (paso 4 del diseño,
"Manejo de errores"; decisiones 17 y 18; requisitos R18 a R21 y R23).

Un manejador recibe el cuerpo de un mensaje y hace su trabajo. Si algo sale mal,
lanza una de estas excepciones y el bucle decide qué hacer:

| Excepción              | Clase | Qué hace el bucle                                          |
|------------------------|-------|------------------------------------------------------------|
| ErrorDelDocumento      | 1     | Completa el mensaje: el manejador ya registró el error y la |
|                        |       | tarea para el evaluador                                    |
| ErrorTransitorio       | 2     | Reintenta 3 veces, a los 2, 4 y 8 minutos. Si el servicio   |
|                        |       | dijo cuánto esperar, espera eso sin contar el intento      |
| RespuestaInvalida      | 3     | Reintenta 2 veces enseguida                                |
| MensajeRechazado       | 4     | El mensaje mismo está mal (por ejemplo, un aviso que no    |
|                        |       | cumple su contrato): sin reintento, a operación            |
| cualquier otra         | 4     | Un bug: sin reintento                                      |

Cuando se agotan los reintentos, o con un bug, el bucle llama a `al_fallar` del
manejador (que deja la entidad en `error_proceso`), manda el mensaje a la cola de
errores y avisa a operación. Un mensaje fallido no frena a los demás (R23): el
bucle sigue con el siguiente.

Reintentar es publicar el mismo cuerpo otra vez, con `intento` (o `esperas`)
aumentado en las propiedades, y completar el original. Si el trabajador se cae
entre las dos cosas, el mensaje se repite; por eso cada manejador es idempotente.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from .cola import Cola, Mensaje
from .parametros import PARAMETROS, Parametros
from .registros import alertas, contexto_de, lugar_de_la_excepcion

registro = logging.getLogger("orquestador.bucle")


class ErrorDelDocumento(Exception):
    """Clase 1: el documento no se puede procesar. Le llega al evaluador como tarea."""


class ErrorTransitorio(Exception):
    """Clase 2: el servicio está caído, tardó demasiado o pidió esperar."""

    def __init__(self, descripcion: str = "", espera_s: float | None = None) -> None:
        super().__init__(descripcion)
        self.espera_s = espera_s
        """Lo que pidió esperar el servicio (por ejemplo, Retry-After de un 429)."""


class RespuestaInvalida(Exception):
    """Clase 3: un servicio respondió algo que no cumple la forma esperada."""


class MensajeRechazado(Exception):
    """Clase 4: el mensaje no se puede procesar tal como llegó, y repetirlo no
    cambia nada. Va a errores para que operación lo revise con quien lo mandó.

    El texto de la excepción va al motivo y a los registros, así que no debe
    llevar rutas ni valores del mensaje: solo campos, conteos y códigos.
    """


class Manejador(Protocol):
    cola: str

    def procesar(self, cuerpo: dict) -> None:
        """Hace el trabajo del mensaje. Debe ser idempotente."""

    def al_fallar(self, cuerpo: dict, motivo: str) -> None:
        """Deja la entidad del mensaje en `error_proceso`. Debe ser idempotente."""


@dataclass(frozen=True)
class Resultado:
    id_mensaje: str
    desenlace: str
    """ok, error_documento, reintento, espera, a_errores."""
    motivo: str | None = None


def _reintentar(cola: Cola, mensaje: Mensaje, demora_s: float, **propiedades) -> None:
    cola.publicar(mensaje.cola, mensaje.cuerpo, demora_s, {**mensaje.propiedades, **propiedades})
    cola.completar(mensaje)


def _fallar(cola: Cola, manejador: Manejador, mensaje: Mensaje, motivo: str) -> Resultado:
    try:
        manejador.al_fallar(mensaje.cuerpo, motivo)
    except Exception as error:  # noqa: BLE001 - el mensaje va a errores igual
        registro.error("No se pudo marcar el error de proceso de %s: %s", mensaje.id, lugar_de_la_excepcion(error))
    cola.a_errores(mensaje, motivo)
    alertas.error("Mensaje %s de la cola %s a errores: %s", mensaje.id, mensaje.cola, motivo)
    return Resultado(mensaje.id, "a_errores", motivo)


def procesar_uno(cola: Cola, manejador: Manejador, parametros: Parametros = PARAMETROS) -> Resultado | None:
    """Recibe un mensaje de la cola del manejador y lo procesa. None si no había."""
    mensaje = cola.recibir(manejador.cola)
    if mensaje is None:
        return None
    intento = mensaje.propiedades.get("intento", 1)
    esperas = mensaje.propiedades.get("esperas", 0)
    with contexto_de(mensaje.cuerpo):
        try:
            manejador.procesar(mensaje.cuerpo)
        except ErrorDelDocumento as error:
            cola.completar(mensaje)
            registro.info("Error del documento, para el evaluador: %s", type(error).__name__)
            return Resultado(mensaje.id, "error_documento")
        except ErrorTransitorio as error:
            motivo = lugar_de_la_excepcion(error)
            if error.espera_s is not None and esperas < parametros.max_esperas:
                _reintentar(cola, mensaje, error.espera_s, esperas=esperas + 1)
                registro.warning("El servicio pidió esperar %s s: %s", error.espera_s, motivo)
                return Resultado(mensaje.id, "espera", motivo)
            if intento <= parametros.reintentos_transitorio:
                demora = parametros.demora_base_s * 2 ** (intento - 1)
                _reintentar(cola, mensaje, demora, intento=intento + 1)
                registro.warning("Falla transitoria, intento %s; se reintenta en %s s: %s", intento, demora, motivo)
                return Resultado(mensaje.id, "reintento", motivo)
            return _fallar(cola, manejador, mensaje, f"Transitoria sin resolver tras {intento} intentos: {motivo}")
        except RespuestaInvalida as error:
            motivo = lugar_de_la_excepcion(error)
            if intento <= parametros.reintentos_respuesta_invalida:
                _reintentar(cola, mensaje, 0, intento=intento + 1)
                registro.warning("Respuesta inválida, intento %s; se reintenta: %s", intento, motivo)
                return Resultado(mensaje.id, "reintento", motivo)
            return _fallar(cola, manejador, mensaje, f"Respuesta inválida tras {intento} intentos: {motivo}")
        except MensajeRechazado as error:
            return _fallar(cola, manejador, mensaje, f"Rechazado: {error}")
        except Exception as error:  # noqa: BLE001 - clase 4: cualquier otra cosa es un bug
            return _fallar(cola, manejador, mensaje, f"Bug: {lugar_de_la_excepcion(error)}")
    cola.completar(mensaje)
    return Resultado(mensaje.id, "ok")


def reenviar_errores(cola: Cola, nombre: str) -> int:
    """Vuelve a publicar todo lo que está en la cola de errores de `nombre`,
    desde el primer intento. Lo usa operación después de corregir la causa (R21).
    Devuelve cuántos mensajes reenvió."""
    sacados = cola.sacar_de_errores(nombre)
    for en_errores in sacados:
        propiedades = {k: v for k, v in en_errores.mensaje.propiedades.items() if k not in ("intento", "esperas")}
        cola.publicar(nombre, en_errores.mensaje.cuerpo, 0, propiedades)
    if sacados:
        registro.info("Reenviados %s mensajes de errores de la cola %s", len(sacados), nombre)
    return len(sacados)
