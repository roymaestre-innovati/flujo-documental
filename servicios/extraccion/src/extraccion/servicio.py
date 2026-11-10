"""`extraer_segmento`: une los pasos de la extracción para una solicitud (R26 a R56).

    solicitud ─► ¿ya está guardada? (idempotencia, R53)
              ─► entrada ─► ficha ─► preprocesamiento ─► mensaje ─► llamada ─► posvalidación
              ─► resultado validado contra el contrato, guardado y registrado

Lo que sale siempre es un resultado del contrato, salvo dos casos que son bugs y
se lanzan: una solicitud que no cumple el contrato de entrada (`SolicitudInvalida`)
y cualquier excepción inesperada.

Se guardan `ok`, `no_corresponde` y `error_entrada`. Un `error_proceso` no se
guarda, para que el reintento del orquestador vuelva a extraer.
"""

import copy
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from normalizacion.almacen import Almacen

from . import VERSION
from .entrada import ERROR_PROCESO, ErrorDeSolicitud, preparar, validar
from .ficha import FichaNoEncontrada, FuenteModelo
from .llamada import LlamadaFallida, Llamador
from .mensaje import VERSION_PROMPT, mensajes
from .posvalidacion import sobre, sobre_de_error
from .preproceso import preparar_contenido
from .registros import contexto_de, registro, resumen
from .reloj import Reloj
from .resultados import Clave, Resultados


def id_de_ejecucion() -> str:
    return f"ej-{uuid.uuid4().hex[:12]}"


@dataclass
class Servicio:
    """Lo que necesita la extracción. Un mismo `Servicio` sirve para todos los segmentos."""

    almacen: Almacen
    fuente: FuenteModelo
    llamador: Llamador
    """Compartido: su semáforo limita las llamadas a la vez de todo el proceso (R52)."""
    resultados: Resultados
    reloj: Reloj
    nuevo_id: Callable[[], str] = field(default=id_de_ejecucion)


@dataclass
class _Gasto:
    tokens_entrada: int = 0
    tokens_salida: int = 0
    reintentos: int = 0
    modelo: str | None = None


def _ejecucion(servicio: Servicio, id_ejecucion: str, inicio, comienzo: float, gasto: _Gasto) -> dict:
    duracion = servicio.reloj.monotono() - comienzo
    return {
        "id": id_ejecucion,
        "inicio": inicio.isoformat(),
        "duracion_ms": max(0, round(duracion * 1000)),
        "tokens_entrada": gasto.tokens_entrada,
        "tokens_salida": gasto.tokens_salida,
        "modelo_llm": gasto.modelo or servicio.llamador.modelo,
        "version_prompt": VERSION_PROMPT,
        "version_unidad": VERSION,
        "reintentos": gasto.reintentos,
        "desde_cache": False,
    }


def _extraer(servicio: Servicio, solicitud: dict, gasto: _Gasto) -> Callable[[dict], dict]:
    """Corre los pasos y devuelve cómo armar el resultado con su `ejecucion`."""
    entrada = preparar(solicitud, servicio.almacen)
    try:
        ficha = servicio.fuente.ficha(solicitud["version_modelo"], solicitud["tipo_documental"])
    except FichaNoEncontrada:
        raise ErrorDeSolicitud(
            ERROR_PROCESO, "FICHA_NO_ENCONTRADA",
            f"El modelo no tiene la versión {solicitud['version_modelo']} o el tipo documental "
            f"{solicitud['tipo_documental']}.", reintentable=False,
        ) from None
    contenido = preparar_contenido(entrada)
    llamada = servicio.llamador.llamar(mensajes(entrada, ficha, contenido))
    gasto.tokens_entrada, gasto.tokens_salida = llamada.tokens_entrada, llamada.tokens_salida
    gasto.reintentos, gasto.modelo = llamada.reintentos, llamada.modelo
    return lambda ejecucion: sobre(solicitud, ficha, contenido, llamada.respuesta, ejecucion)


def extraer_segmento(solicitud: dict, servicio: Servicio) -> dict:
    """El resultado de una solicitud, con la forma de `modulo3-extraccion/0.2`."""
    validar(solicitud)
    with contexto_de(solicitud):
        clave = Clave.de(solicitud)
        if not solicitud.get("forzar_reproceso", False):
            guardado = servicio.resultados.buscar(clave)
            if guardado is not None:
                repetido = copy.deepcopy(guardado)
                repetido["ejecucion"]["desde_cache"] = True
                registro.info("Segmento repetido", extra={"datos": resumen(repetido)})
                return repetido

        id_ejecucion = servicio.nuevo_id()
        inicio, comienzo = servicio.reloj.ahora(), servicio.reloj.monotono()
        gasto = _Gasto()
        try:
            armar = _extraer(servicio, solicitud, gasto)
            resultado = armar(_ejecucion(servicio, id_ejecucion, inicio, comienzo, gasto))
        except ErrorDeSolicitud as error:
            if isinstance(error, LlamadaFallida):
                gasto = _Gasto(error.tokens_entrada, error.tokens_salida, error.reintentos, error.modelo)
            resultado = sobre_de_error(solicitud, error, _ejecucion(servicio, id_ejecucion, inicio, comienzo, gasto))

        if resultado["estado"] != ERROR_PROCESO:
            servicio.resultados.guardar(clave, resultado)
        registro.info("Segmento extraído", extra={"datos": resumen(resultado)})
        return resultado
