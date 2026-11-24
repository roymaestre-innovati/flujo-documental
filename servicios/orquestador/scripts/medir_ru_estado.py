"""Mide las RU de EstadoMongo con un oferente sintético de 80 archivos.

    uv run python scripts/medir_ru_estado.py

Lee ESTADO_MONGO_URL del entorno y borra su proceso de prueba al terminar.
"""

import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from time import perf_counter
from uuid import uuid4
from warnings import catch_warnings

from limpiar_estado_prueba import ErrorLimpieza, limpiar_procesos
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, OperationFailure

from orquestador.estado import ErrorEstado
from orquestador.estado_mongo import EstadoMongo, _documento, _filtro_registro, coleccion_desde_entorno


def _ru_ultima_solicitud(base: Database[dict]) -> float | None:
    try:
        estadisticas = base.command("getLastRequestStatistics")
    except OperationFailure as error:
        if error.code != 59 and (error.details or {}).get("codeName") != "CommandNotFound":
            raise
        return None
    return float(estadisticas["RequestCharge"])


def _formatear_ru(ru: float | None) -> str:
    return f"{ru:g}" if ru is not None else "no disponible (comando getLastRequestStatistics desconocido)"


@contextmanager
def _medir(base: Database[dict], operacion: str) -> Iterator[None]:
    inicio = perf_counter()
    yield
    milisegundos = (perf_counter() - inicio) * 1000
    print(f"{operacion}\t{_formatear_ru(_ru_ultima_solicitud(base))}\t{milisegundos:.1f}")


def _medir_compuesta(base: Database[dict], operacion: str, *solicitudes: tuple[str, Callable[[], None]]) -> None:
    milisegundos = 0.0
    cargos = []
    for nombre, solicitar in solicitudes:
        inicio = perf_counter()
        solicitar()
        milisegundos += (perf_counter() - inicio) * 1000
        cargos.append((nombre, _ru_ultima_solicitud(base)))
    total = sum(ru for _, ru in cargos if ru is not None) if all(ru is not None for _, ru in cargos) else None
    desglose = " + ".join(f"{nombre}: {_formatear_ru(ru)}" for nombre, ru in cargos)
    print(f"{operacion}\t{_formatear_ru(total)} ({desglose})\t{milisegundos:.1f}")


def _medir_operaciones(coleccion: Collection[dict], id_proceso: str) -> None:
    estado = EstadoMongo(coleccion)
    base = coleccion.database
    clave = (id_proceso, "oferente", "OF-001")
    esperados = {
        f"OF-001/Oferta técnica/Anexo {n:03d}.pdf": {"tamano": 40_000 + n * 1_111, "md5": f"{n:032x}"}
        for n in range(1, 81)
    }
    datos = {"estado": "recibido", "archivos": list(esperados), "esperados": esperados}
    filtro = _filtro_registro(*clave)

    def insertar_duplicado():
        try:
            coleccion.insert_one(_documento(*clave, 1, datos))
        except DuplicateKeyError:
            return
        raise ErrorEstado("Se esperaba un duplicado al crear el registro repetido")

    def reemplazar_version_anterior():
        resultado = coleccion.replace_one(
            {**filtro, "version": original.version}, _documento(*clave, original.version + 1, datos),
        )
        if resultado.matched_count:
            raise ErrorEstado("Se esperaba un conflicto al reemplazar con la versión anterior")

    def leer_registro():
        if coleccion.find_one(filtro) is None:
            raise ErrorEstado("No se encontró el registro de prueba")

    print("Operación\tRU\tMilisegundos")
    with _medir(base, "leer inexistente"):
        estado.leer(*clave)
    with _medir(base, "crear"):
        original, _ = estado.crear_si_no_existe(*clave, datos)
    _medir_compuesta(base, "crear repetido", ("insert_one", insertar_duplicado), ("find_one", leer_registro))
    with _medir(base, "leer"):
        estado.leer(*clave)
    with _medir(base, "reemplazar"):
        estado.reemplazar(original, {**datos, "estado": "procesando"})
    _medir_compuesta(base, "reemplazar con conflicto",
                     ("replace_one", reemplazar_version_anterior), ("find_one", leer_registro))
    with _medir(base, "listar"):
        estado.listar(id_proceso)
    with _medir(base, "listar por tipo"):
        estado.listar(id_proceso, "oferente")
    with _medir(base, "procesos"):
        estado.procesos()


def main() -> int:
    if not os.environ.get("ESTADO_MONGO_URL"):
        print("Falta ESTADO_MONGO_URL", file=sys.stderr)
        return 2

    id_proceso = f"PRUEBA-{uuid4()}"
    limpieza_fallida = False
    # Las operaciones y las estadísticas deben usar la misma conexión del primario.
    crear_cliente = partial(MongoClient, maxPoolSize=1, readPreference="primary")
    try:
        # Las advertencias de configuración pueden reproducir valores de la cadena.
        with catch_warnings(record=True):
            coleccion = coleccion_desde_entorno(crear_cliente)
        with coleccion.database.client:
            try:
                _medir_operaciones(coleccion, id_proceso)
            finally:
                try:
                    limpiar_procesos(coleccion, (id_proceso,))
                except ErrorLimpieza as error:
                    print(error, file=sys.stderr)
                    limpieza_fallida = True
                finally:
                    restantes = coleccion.count_documents({"id_proceso": {"$regex": "^PRUEBA-"}})
                    print(f"Documentos con id_proceso PRUEBA- después de la limpieza: {restantes}")
    except Exception as error:  # noqa: BLE001 - el texto del controlador puede incluir datos de conexión.
        codigo = getattr(error, "code", None)
        detalle = f", código {codigo}" if isinstance(codigo, int) else ""
        print(f"Falló la medición ({type(error).__name__}{detalle})", file=sys.stderr)
        return 1
    return int(limpieza_fallida)


if __name__ == "__main__":
    sys.exit(main())
