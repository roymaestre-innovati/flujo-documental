"""Mide las RU de EstadoMongo con un oferente sintético de 80 archivos.

    uv run python scripts/medir_ru_estado.py

Lee ESTADO_MONGO_URL del entorno y borra su proceso de prueba al terminar.
"""

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from time import perf_counter
from uuid import uuid4
from warnings import catch_warnings

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import OperationFailure

from orquestador.estado import Conflicto, ErrorEstado
from orquestador.estado_mongo import EstadoMongo, coleccion_desde_entorno


@contextmanager
def _medir(base: Database[dict], operacion: str) -> Iterator[None]:
    inicio = perf_counter()
    yield
    milisegundos = (perf_counter() - inicio) * 1000
    try:
        estadisticas = base.command("getLastRequestStatistics")
    except OperationFailure as error:
        if error.code != 59 and (error.details or {}).get("codeName") != "CommandNotFound":
            raise
        ru = "no disponible (comando getLastRequestStatistics desconocido)"
    else:
        ru = f"{float(estadisticas['RequestCharge']):g}"
    print(f"{operacion}\t{ru}\t{milisegundos:.1f}")


def _medir_operaciones(coleccion: Collection[dict], id_proceso: str) -> None:
    estado = EstadoMongo(coleccion)
    base = coleccion.database
    clave = (id_proceso, "oferente", "OF-001")
    esperados = {
        f"OF-001/Oferta técnica/Anexo {n:03d}.pdf": {"tamano": 40_000 + n * 1_111, "md5": f"{n:032x}"}
        for n in range(1, 81)
    }
    datos = {"estado": "recibido", "archivos": list(esperados), "esperados": esperados}

    print("Operación\tRU\tMilisegundos")
    with _medir(base, "leer inexistente"):
        estado.leer(*clave)
    with _medir(base, "crear"):
        original, _ = estado.crear_si_no_existe(*clave, datos)
    with _medir(base, "crear repetido"):
        estado.crear_si_no_existe(*clave, datos)
    with _medir(base, "leer"):
        estado.leer(*clave)
    with _medir(base, "reemplazar"):
        estado.reemplazar(original, {**datos, "estado": "procesando"})
    with _medir(base, "reemplazar con conflicto"):
        try:
            estado.reemplazar(original, datos)
        except Conflicto:
            pass
        else:
            raise ErrorEstado("Se esperaba un conflicto al reemplazar con la versión anterior")
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
                coleccion.delete_many({"id_proceso": id_proceso})
                restantes = coleccion.count_documents({"id_proceso": {"$regex": "^PRUEBA-"}})
                print(f"Documentos con id_proceso PRUEBA- después de la limpieza: {restantes}")
    except Exception as error:  # noqa: BLE001 - el texto del controlador puede incluir datos de conexión.
        codigo = getattr(error, "code", None)
        detalle = f", código {codigo}" if isinstance(codigo, int) else ""
        print(f"Falló la medición ({type(error).__name__}{detalle})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
