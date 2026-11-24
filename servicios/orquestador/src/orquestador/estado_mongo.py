"""Estado en Cosmos DB con la API de MongoDB.

El `_id` incluye proceso, tipo e id en un subdocumento. Las consultas por
registro también llevan `id_proceso`, la clave de partición. El filtro de
reemplazo incluye la versión leída para que dos trabajadores no se pisen.
Los datos del flujo quedan anidados y el límite BSON se comprueba antes de
escribir. Solo `procesos()` consulta entre particiones.

Las fallas de red se reintentan y el límite de RU se traduce en una espera.
Los errores traducidos incluyen la operación, el tipo de excepción y su código
cuando existe, sin reproducir el mensaje del servidor.
"""

import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy

import bson
import pymongo
from pymongo.collection import Collection
from pymongo.errors import (
    ConfigurationError,
    ConnectionFailure,
    DuplicateKeyError,
    ExecutionTimeout,
    OperationFailure,
    WTimeoutError,
)

from .errores import ErrorDeConfiguracion, ErrorTransitorio
from .estado import TIPOS, Conflicto, ErrorEstado, Estado, Registro, _revisar
from .parametros import PARAMETROS, Parametros

LIMITE_DOCUMENTO_BSON_BYTES = 2 * 1024 * 1024
_REINTENTO_MS = re.compile(r"\bRetryAfterMs['\"]?\s*[:=]\s*['\"]?([0-9]+(?:\.[0-9]+)?)\b")


@contextmanager
def _traducir_fallas(operacion: str, parametros: Parametros = PARAMETROS) -> Iterator[None]:
    try:
        yield
    except (ConfigurationError, ConnectionFailure, OperationFailure) as error:
        codigo = getattr(error, "code", None)
        detalle = f", código {codigo}" if codigo is not None else ""
        mensaje = f"MongoDB {operacion} ({type(error).__name__}{detalle})"
        if codigo == 16500:
            # PyMongo incluye `details` en el texto de OperationFailure.
            tiempo = _REINTENTO_MS.search(str(error))
            espera = float(tiempo[1]) / 1000 if tiempo else parametros.espera_limite_estado_s
            raise ErrorTransitorio(mensaje, espera_s=espera) from None
        if isinstance(error, ConfigurationError) or codigo in (13, 18):
            raise ErrorDeConfiguracion(mensaje) from None
        # ConnectionFailure incluye AutoReconnect y los tiempos de espera de red y de selección de servidor.
        if isinstance(error, (ConnectionFailure, ExecutionTimeout, WTimeoutError)):
            raise ErrorTransitorio(mensaje) from None
        raise


def coleccion_desde_entorno(
    crear_cliente: Callable[[str], pymongo.MongoClient[dict]] = pymongo.MongoClient,
) -> Collection[dict]:
    """Arma la colección con la cadena del entorno y las opciones que trae."""
    url = os.environ.get("ESTADO_MONGO_URL")
    if not url:
        raise ErrorDeConfiguracion("Falta ESTADO_MONGO_URL")
    base = os.environ.get("ESTADO_MONGO_BASE", "evaluacion_ofertas")
    coleccion = os.environ.get("ESTADO_MONGO_COLECCION", "estado")
    with _traducir_fallas("armar colección"):
        try:
            cliente = crear_cliente(url)
        except ValueError as error:
            raise ErrorDeConfiguracion(f"MongoDB crear cliente ({type(error).__name__})") from None
        return cliente[base][coleccion]


def _filtro_registro(id_proceso: str, tipo: str, id: str) -> dict:
    return {"_id": {"p": id_proceso, "t": tipo, "i": id}, "id_proceso": id_proceso}


def _documento(id_proceso: str, tipo: str, id: str, version: int, datos: dict) -> dict:
    documento = {
        **_filtro_registro(id_proceso, tipo, id),
        "tipo": tipo,
        "id": id,
        "version": version,
        "datos": _revisar(tipo, datos),
    }
    tamano = len(bson.encode(documento))
    if tamano > LIMITE_DOCUMENTO_BSON_BYTES:
        raise ErrorEstado(f"Documento BSON de {tamano} bytes supera el límite de {LIMITE_DOCUMENTO_BSON_BYTES} bytes")
    return documento


def _registro(documento: dict) -> Registro:
    return Registro(documento["id_proceso"], documento["tipo"], documento["id"],
                    documento["version"], deepcopy(documento["datos"]))


class EstadoMongo(Estado):
    def __init__(self, coleccion: Collection[dict], *, parametros: Parametros = PARAMETROS) -> None:
        self._coleccion = coleccion
        self._parametros = parametros

    def leer(self, id_proceso: str, tipo: str, id: str) -> Registro | None:
        with _traducir_fallas("find_one", self._parametros):
            documento = self._coleccion.find_one(_filtro_registro(id_proceso, tipo, id))
        return None if documento is None else _registro(documento)

    def crear_si_no_existe(self, id_proceso: str, tipo: str, id: str, datos: dict) -> tuple[Registro, bool]:
        documento = _documento(id_proceso, tipo, id, 1, datos)
        try:
            with _traducir_fallas("insert_one", self._parametros):
                self._coleccion.insert_one(documento)
        except DuplicateKeyError:
            pass
        else:
            return _registro(documento), True

        actual = self.leer(id_proceso, tipo, id)
        if actual is None:
            raise ErrorEstado(f"MongoDB rechazó el duplicado de {tipo} {id} en {id_proceso} y no se encontró el registro")
        return actual, False

    def reemplazar(self, registro: Registro, datos: dict) -> Registro:
        documento = _documento(registro.id_proceso, registro.tipo, registro.id, registro.version + 1, datos)
        filtro = {**_filtro_registro(registro.id_proceso, registro.tipo, registro.id), "version": registro.version}
        with _traducir_fallas("replace_one", self._parametros):
            resultado = self._coleccion.replace_one(filtro, documento)
        if resultado.matched_count:
            return _registro(documento)

        actual = self.leer(registro.id_proceso, registro.tipo, registro.id)
        if actual is None:
            raise ErrorEstado(f"No existe {registro.tipo} {registro.id} en {registro.id_proceso}")
        raise Conflicto(f"{registro.tipo} {registro.id}: se leyó la versión {registro.version} y va en la {actual.version}")

    def listar(self, id_proceso: str, tipo: str | None = None) -> list[Registro]:
        filtro = {"id_proceso": id_proceso}
        if tipo is not None:
            if tipo not in TIPOS:
                raise ErrorEstado(f"Tipo desconocido: {tipo}")
            filtro["tipo"] = tipo
        with _traducir_fallas("find", self._parametros):
            registros = [_registro(documento) for documento in self._coleccion.find(filtro)]
        return sorted(registros, key=lambda r: (TIPOS.index(r.tipo), r.id))

    def procesos(self) -> list[str]:
        with _traducir_fallas("distinct", self._parametros):
            procesos = self._coleccion.distinct("id_proceso")
        return sorted(procesos)
