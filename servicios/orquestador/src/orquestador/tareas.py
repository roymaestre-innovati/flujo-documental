"""Tareas humanas (paso 4 del diseño, "Tipos de tarea humana").

En la entrega 1 las tareas quedan en el estado; cómo llegan a la Power App se
decide con A-2 (entrega 2). El identificador es determinista, `<clase>-<id del
documento o segmento>`, así crear la misma tarea dos veces no la duplica (R27).

El motivo es un código y el detalle una frase sin texto de los documentos.
"""

import datetime
import logging

from . import estados
from .estado import Estado, Registro
from .parametros import PARAMETROS, Parametros
from .reloj import Reloj

registro = logging.getLogger("orquestador.tareas")

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


def escalar_fallas(estado: Estado, reloj: Reloj, parametros: Parametros = PARAMETROS) -> list[Registro]:
    """Crea una tarea "falla técnica" por cada entrega o documento que lleva más
    de `horas_escalamiento` en `error_proceso` (R22).

    Así el evaluador puede revisar a mano lo que operación no ha resuelto, y el
    proceso no se queda frenado. En producción corre como un trabajo periódico.
    Devuelve las tareas creadas en esta pasada; las que ya existían no se repiten.
    """
    limite = reloj.ahora() - datetime.timedelta(hours=parametros.horas_escalamiento)
    creadas = []
    for id_proceso in estado.procesos():
        for r in estado.listar(id_proceso):
            if r.tipo not in (estados.OFERENTE, estados.DOCUMENTO) or r.datos["estado"] != estados.ERROR_PROCESO:
                continue
            desde = r.datos.get("error_desde")
            if desde is None or datetime.datetime.fromisoformat(desde) > limite:
                continue
            que = "La entrega completa" if r.tipo == estados.OFERENTE else "El documento"
            cambio = estados.crear(
                estado, reloj, id_proceso, estados.TAREA, id_tarea(FALLA_TECNICA, r.id), estados.ABIERTA,
                "falla técnica sin resolver",
                {"clase": FALLA_TECNICA, "motivo": "FALLA_TECNICA", "referencia": {"tipo": r.tipo, "id": r.id},
                 "detalle": f"{que} no se pudo procesar por una falla técnica desde {desde}. "
                            "Operación ya fue avisada; revíselo a mano si no puede esperar."},
                entrega=r.datos["entrega"],
            )
            if cambio.aplicado:
                creadas.append(cambio.registro)
    if creadas:
        registro.warning("Escaladas %s fallas técnicas a tareas humanas", len(creadas))
    return creadas

