"""Clasificar: el manejador de la cola `clasificar` (T07; requisitos R9 a R14).

Por cada documento normalizado:

1. Arma la solicitud del contrato (R9) y llama al clasificador. Las copias
   exactas no llegan aquí: la normalización no las manda a clasificar (R10).
2. Revisa la respuesta (R11): que cumpla el contrato, que los segmentos cubran
   todas las páginas sin huecos ni solapes, que cada TD exista en la versión de
   tipos fijada y que hable del mismo documento y la misma ontología. Si algo
   falla, la pide una vez más; si vuelve a fallar, el documento queda esperando
   una persona, con una tarea de clasificación.
3. Crea un segmento por cada uno de la respuesta y decide con los umbrales
   fijados en el proceso (R12, R13):
   - TD-98 y TD-99: sin extracción (R14);
   - desde el umbral del TD: se extrae;
   - entre el piso (0,75) y el umbral: se extrae marcado como dudoso;
   - por debajo del piso: espera a una persona, con una tarea de clasificación.
4. Pide la extracción de cada segmento que se extrae (T08).
5. Pasa el documento a `clasificado`. Es el último paso, como en la
   normalización: si el trabajador se cae antes, el mensaje se repite sin
   duplicar segmentos ni tareas.
"""

import json
import logging
from typing import Protocol

from normalizacion.almacen import Almacen
from normalizacion.inventario import ENTREGA_DEL_PROCESO

from . import CONTRATO, contratos, datos, estados
from .clasificador import Clasificador
from .cola import CLASIFICAR
from .estado import Estado, Registro
from .reloj import Reloj
from .tareas import CLASIFICACION, crear_tarea

registro = logging.getLogger("orquestador.clasificar")

SIN_EXTRACCION = ("TD-98", "TD-99")
INTENTOS_RESPUESTA = 2
"""Una respuesta inválida se pide una vez más (paso 3 del diseño)."""


class Solicitudes(Protocol):
    """Quien pide la extracción de un segmento (T08)."""

    def pedir(self, proceso: Registro, documento: Registro, segmento: Registro) -> None: ...


def id_segmento(id_documento: str, pagina_inicio: int, pagina_fin: int) -> str:
    return f"{id_documento}-p{pagina_inicio}-{pagina_fin}"


def problemas_de_la_respuesta(respuesta: dict, solicitud: dict, tipos: datos.TiposDocumentales) -> list[str]:
    """Lo que está mal en la respuesta del clasificador. Vacía si está bien.

    Solo códigos y números de página, sin valores del documento.
    """
    problemas = contratos.errores(contratos.CLASIFICACION_RESPUESTA, respuesta)
    if problemas:
        return problemas
    if respuesta["id_documento"] != solicitud["id_documento"]:
        problemas.append("id_documento distinto al de la solicitud")
    if respuesta["version_ontologia"] != solicitud["version_ontologia"]:
        problemas.append("version_ontologia distinta a la fijada")
    esperada = 1
    for segmento in respuesta["segmentos"]:
        inicio, fin = segmento["pagina_inicio"], segmento["pagina_fin"]
        if inicio > fin:
            problemas.append(f"segmento al revés: {inicio}-{fin}")
        if inicio > esperada:
            problemas.append(f"hueco: páginas {esperada}-{inicio - 1}")
        elif inicio < esperada:
            problemas.append(f"solape desde la página {inicio}")
        esperada = max(esperada, fin + 1)
        if not tipos.existe(segmento["tipo_documental"]):
            problemas.append(f"TD desconocido en {inicio}-{fin}")
    if esperada <= solicitud["paginas"]:
        problemas.append(f"faltan las páginas {esperada}-{solicitud['paginas']}")
    elif esperada > solicitud["paginas"] + 1:
        problemas.append(f"páginas de más: hasta la {esperada - 1} de {solicitud['paginas']}")
    return problemas


class Clasificar:
    cola = CLASIFICAR

    def __init__(
        self,
        estado: Estado,
        almacen: Almacen,
        clasificador: Clasificador,
        solicitudes: Solicitudes,
        reloj: Reloj,
    ) -> None:
        self._estado = estado
        self._almacen = almacen
        self._clasificador = clasificador
        self._solicitudes = solicitudes
        self._reloj = reloj

    def procesar(self, cuerpo: dict) -> None:
        id_proceso, entrega, id_documento = cuerpo["id_proceso"], cuerpo["entrega"], cuerpo["id_documento"]
        proceso = self._estado.leer(id_proceso, estados.PROCESO, id_proceso)
        documento = self._estado.leer(id_proceso, estados.DOCUMENTO, id_documento)
        if proceso is None or documento is None:
            raise estados.NoExiste(f"No existe el documento {id_documento} o su proceso")
        actual = documento.datos["estado"]
        if actual in (estados.CLASIFICADO, estados.ESPERANDO_CLASIFICACION_HUMANA):
            registro.info("Documento ya clasificado: mensaje repetido")
            return
        if actual not in (estados.NORMALIZADO, estados.ERROR_PROCESO):
            raise estados.EstadoInesperado(documento, frozenset((estados.NORMALIZADO, estados.ERROR_PROCESO)))

        versiones = proceso.datos["versiones"]
        tipos = datos.tipos_documentales(versiones["tipos_documentales"])
        umbrales = datos.umbrales(versiones["umbrales"])
        solicitud = self._solicitud(proceso, documento, entrega)
        contratos.validar(contratos.CLASIFICACION_SOLICITUD, solicitud)

        for intento in range(1, INTENTOS_RESPUESTA + 1):
            respuesta = self._clasificador.clasificar(solicitud)
            problemas = problemas_de_la_respuesta(respuesta, solicitud, tipos)
            if not problemas:
                break
            registro.warning("Respuesta del clasificador inválida (intento %s): %s", intento, "; ".join(problemas))
        else:
            crear_tarea(self._estado, self._reloj, id_proceso, entrega, CLASIFICACION, id_documento,
                        "RESPUESTA_INVALIDA", {"id_documento": id_documento, "id_segmento": None,
                                               "detalle": "; ".join(problemas)})
            estados.cambiar(self._estado, self._reloj, id_proceso, estados.DOCUMENTO, id_documento,
                            (estados.NORMALIZADO, estados.ERROR_PROCESO), estados.ESPERANDO_CLASIFICACION_HUMANA,
                            "respuesta del clasificador inválida", {"error": None})
            return

        segmentos = []
        for parte in respuesta["segmentos"]:
            segmento = self._segmento(proceso, documento, entrega, parte, umbrales, respuesta["version_ontologia"])
            segmentos.append(segmento.id)
            if segmento.datos["estado"] == estados.PENDIENTE:
                self._solicitudes.pedir(proceso, documento, segmento)

        estados.cambiar(self._estado, self._reloj, id_proceso, estados.DOCUMENTO, id_documento,
                        (estados.NORMALIZADO, estados.ERROR_PROCESO), estados.CLASIFICADO, "clasificador",
                        {"segmentos": segmentos, "version_ontologia": respuesta["version_ontologia"], "error": None})
        registro.info("Documento clasificado: %s segmentos", len(segmentos))

    def _solicitud(self, proceso: Registro, documento: Registro, entrega: str) -> dict:
        lectura = json.loads(self._almacen.leer(documento.datos["lectura"]))
        return {
            "contrato": CONTRATO,
            "id_proceso": proceso.id,
            "id_oferente": None if entrega == ENTREGA_DEL_PROCESO else entrega,
            "id_documento": documento.id,
            "pdf": {"uri": documento.datos["pdf"], "sha256": lectura["hash_pdf"]},
            "paginas": documento.datos["paginas"],
            "ruta_origen": documento.datos["ruta_origen"],
            "lectura": documento.datos["lectura"],
            "version_ontologia": proceso.datos["versiones"]["ontologia"],
        }

    def _segmento(self, proceso, documento, entrega, parte, umbrales, version_ontologia) -> Registro:
        td, confianza = parte["tipo_documental"], parte["confianza"]
        inicio, fin = parte["pagina_inicio"], parte["pagina_fin"]
        identificador = id_segmento(documento.id, inicio, fin)
        dudosa = False
        if td in SIN_EXTRACCION:
            inicial, motivo = estados.SIN_EXTRACCION, f"{td}: no se extrae"
        elif confianza >= umbrales.de(td):
            inicial, motivo = estados.PENDIENTE, "confianza desde el umbral del TD"
        elif confianza >= umbrales.piso:
            inicial, motivo, dudosa = estados.PENDIENTE, "clasificación dudosa", True
        else:
            inicial, motivo = estados.ESPERANDO_CLASIFICACION_HUMANA, "confianza bajo el piso"
        segmento = estados.crear(
            self._estado, self._reloj, proceso.id, estados.SEGMENTO, identificador, inicial, motivo,
            {"id_documento": documento.id, "pagina_inicio": inicio, "pagina_fin": fin, "tipo_documental": td,
             "subtipo": parte["subtipo"], "confianza": confianza, "clasificacion_dudosa": dudosa,
             "asignado_por": "clasificador", "version_ontologia": version_ontologia},
            entrega=entrega,
        ).registro
        if inicial == estados.ESPERANDO_CLASIFICACION_HUMANA:
            crear_tarea(self._estado, self._reloj, proceso.id, entrega, CLASIFICACION, identificador,
                        "CONFIANZA_BAJA", {"id_documento": documento.id, "id_segmento": identificador,
                                           "detalle": f"Páginas {inicio}-{fin}: el clasificador sugiere {td} "
                                                      f"con confianza {confianza:.2f}"})
        return segmento

    def al_fallar(self, cuerpo: dict, motivo: str) -> None:
        try:
            estados.cambiar(self._estado, self._reloj, cuerpo["id_proceso"], estados.DOCUMENTO,
                            cuerpo["id_documento"], estados.NORMALIZADO, estados.ERROR_PROCESO, "falla al clasificar",
                            {"error": motivo, "error_desde": self._reloj.ahora().isoformat()})
        except estados.EstadoInesperado as e:
            registro.warning("El documento ya estaba en %s: no se marca el error", e.registro.datos["estado"])
