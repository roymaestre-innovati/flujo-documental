"""Resolver una tarea de clasificación (T09; requisito R15).

Cuando una persona asigna el tipo documental, el segmento sigue a extracción con
ese tipo y queda registrado quién lo asignó. Hay dos clases de tarea:

- **De un segmento** (confianza bajo el piso): la persona da el TD de ese
  segmento.
- **De un documento entero** (el clasificador respondió mal dos veces): la
  persona parte el documento en segmentos, cada uno con su TD. Se revisa igual
  que una respuesta del clasificador: todas las páginas, sin huecos ni solapes.

En los dos casos, TD-98 y TD-99 quedan sin extracción y los demás se piden a la
extracción, sin confianza (la asignó una persona) y sin marca de dudosa.

La tarea se marca resuelta al final: si algo falla a la mitad, se puede volver a
llamar con lo mismo sin duplicar nada. Con la tarea ya resuelta, no hace nada.

En la entrega 2 esto lo dispara la corrección que llega de la Power App (A-2).
"""

from dataclasses import dataclass

from . import CONTRATO, datos, estados
from .clasificar import SIN_EXTRACCION, Solicitudes, id_segmento, problemas_de_la_respuesta
from .estado import Estado, Registro
from .reloj import Reloj
from .tareas import CLASIFICACION


class ResolucionInvalida(Exception):
    """Lo que asignó la persona no se puede aplicar. El texto no lleva datos del documento."""


@dataclass(frozen=True)
class Asignacion:
    pagina_inicio: int
    pagina_fin: int
    tipo_documental: str
    subtipo: str | None = None


def resolver_clasificacion(
    estado: Estado,
    reloj: Reloj,
    solicitudes: Solicitudes,
    id_proceso: str,
    id_tarea: str,
    asignaciones: list[Asignacion],
    quien: str,
) -> Registro:
    """Aplica lo que asignó la persona y devuelve la tarea resuelta.

    Para la tarea de un segmento, `asignaciones` trae uno solo, con las páginas
    de ese segmento.
    """
    tarea = estado.leer(id_proceso, estados.TAREA, id_tarea)
    if tarea is None:
        raise estados.NoExiste(f"No existe la tarea {id_tarea}")
    if tarea.datos["clase"] != CLASIFICACION:
        raise ResolucionInvalida(f"La tarea {id_tarea} no es de clasificación")
    if tarea.datos["estado"] == estados.RESUELTA:
        return tarea
    if not quien:
        raise ResolucionInvalida("Falta quién asignó el tipo")

    proceso = estado.leer(id_proceso, estados.PROCESO, id_proceso)
    documento = estado.leer(id_proceso, estados.DOCUMENTO, tarea.datos["id_documento"])
    versiones = proceso.datos["versiones"]
    tipos = datos.tipos_documentales(versiones["tipos_documentales"])
    cuando = reloj.ahora().isoformat()

    if tarea.datos["id_segmento"] is not None:
        segmento = estado.leer(id_proceso, estados.SEGMENTO, tarea.datos["id_segmento"])
        if len(asignaciones) != 1 or (asignaciones[0].pagina_inicio, asignaciones[0].pagina_fin) != (
                segmento.datos["pagina_inicio"], segmento.datos["pagina_fin"]):
            raise ResolucionInvalida("La tarea es de un segmento: va un solo tipo, con las páginas del segmento")
        [asignacion] = asignaciones
        if not tipos.existe(asignacion.tipo_documental):
            raise ResolucionInvalida("TD desconocido")
        destino = estados.SIN_EXTRACCION if asignacion.tipo_documental in SIN_EXTRACCION else estados.PENDIENTE
        cambio = estados.cambiar(
            estado, reloj, id_proceso, estados.SEGMENTO, segmento.id, estados.ESPERANDO_CLASIFICACION_HUMANA, destino,
            f"tipo asignado por {quien}",
            {"tipo_documental": asignacion.tipo_documental, "subtipo": asignacion.subtipo, "confianza": None,
             "clasificacion_dudosa": False, "asignado_por": quien, "asignado_en": cuando,
             "tipo_sugerido": segmento.datos["tipo_documental"]},
        )
        if destino == estados.PENDIENTE:
            solicitudes.pedir(proceso, documento, cambio.registro)
    else:
        respuesta = {
            "contrato": CONTRATO, "id_documento": documento.id, "version_ontologia": versiones["ontologia"],
            "segmentos": [{"pagina_inicio": a.pagina_inicio, "pagina_fin": a.pagina_fin,
                           "tipo_documental": a.tipo_documental, "subtipo": a.subtipo, "confianza": 1.0}
                          for a in sorted(asignaciones, key=lambda a: a.pagina_inicio)],
        }
        solicitud = {"id_documento": documento.id, "version_ontologia": versiones["ontologia"],
                     "paginas": documento.datos["paginas"]}
        if problemas := problemas_de_la_respuesta(respuesta, solicitud, tipos):
            raise ResolucionInvalida("; ".join(problemas))
        ids = []
        for a in sorted(asignaciones, key=lambda a: a.pagina_inicio):
            inicial = estados.SIN_EXTRACCION if a.tipo_documental in SIN_EXTRACCION else estados.PENDIENTE
            segmento = estados.crear(
                estado, reloj, id_proceso, estados.SEGMENTO, id_segmento(documento.id, a.pagina_inicio, a.pagina_fin),
                inicial, f"tipo asignado por {quien}",
                {"id_documento": documento.id, "pagina_inicio": a.pagina_inicio, "pagina_fin": a.pagina_fin,
                 "tipo_documental": a.tipo_documental, "subtipo": a.subtipo, "confianza": None,
                 "clasificacion_dudosa": False, "asignado_por": quien, "asignado_en": cuando,
                 "version_ontologia": versiones["ontologia"]},
                entrega=documento.datos["entrega"],
            ).registro
            ids.append(segmento.id)
            if segmento.datos["estado"] == estados.PENDIENTE:
                solicitudes.pedir(proceso, documento, segmento)
        estados.cambiar(estado, reloj, id_proceso, estados.DOCUMENTO, documento.id,
                        estados.ESPERANDO_CLASIFICACION_HUMANA, estados.CLASIFICADO, f"tipos asignados por {quien}",
                        {"segmentos": ids, "version_ontologia": versiones["ontologia"]})

    return estados.cambiar(
        estado, reloj, id_proceso, estados.TAREA, id_tarea, estados.ABIERTA, estados.RESUELTA, f"resuelta por {quien}",
        {"resolucion": {"asignaciones": [vars(a) for a in asignaciones], "quien": quien, "cuando": cuando}},
    ).registro
