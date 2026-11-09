"""Tareas humanas (paso 4 del diseño, "Tipos de tarea humana").

En la entrega 1 las tareas quedan en el estado; cómo llegan a la Power App se
decide con A-2 (entrega 2). El identificador es determinista, `<clase>-<id del
documento o segmento>`, así crear la misma tarea dos veces no la duplica (R27).

El motivo es un código y el detalle una frase sin texto de los documentos.
"""

from . import estados
from .estado import Estado, Registro
from .reloj import Reloj

CLASIFICACION = "clasificacion"
DOCUMENTO_CON_ERROR = "documento_con_error"
FALLA_TECNICA = "falla_tecnica"
CLASES = (CLASIFICACION, DOCUMENTO_CON_ERROR, FALLA_TECNICA)


def id_tarea(clase: str, id_referencia: str) -> str:
    return f"{clase}-{id_referencia}"


def crear_tarea(
    estado: Estado,
    reloj: Reloj,
    id_proceso: str,
    entrega: str,
    clase: str,
    id_referencia: str,
    motivo: str,
    datos: dict | None = None,
) -> Registro:
    """Crea la tarea abierta, o devuelve la que ya existía."""
    if clase not in CLASES:
        raise estados.TransicionNoPermitida(f"Clase de tarea desconocida: {clase}")
    return estados.crear(
        estado, reloj, id_proceso, estados.TAREA, id_tarea(clase, id_referencia), estados.ABIERTA, motivo,
        {"clase": clase, "motivo": motivo, **(datos or {})}, entrega=entrega,
    ).registro
