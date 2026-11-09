"""Normalizar: el manejador de la cola `normalizar` (T06; requisitos R3, R6 a R8).

Por cada entrega (la del proceso o la de un oferente):

1. Revisa que la versión del normalizador sea la fijada en el proceso (R5).
2. Baja los originales del origen a una carpeta temporal, que se borra al
   terminar: no se guarda copia de los originales (R3, decisión 32).
3. Llama a `normalizar_entrega` de la iniciativa 003 (R6).
4. Registra cada documento del manifiesto con su estado (R7) y crea una tarea
   "documento con error" por cada uno que no se pudo procesar (R8).
5. Publica un `clasificar` por cada documento normalizado. Las copias exactas y
   los documentos con error no se clasifican.
6. Pasa la entrega a `procesando`. Es el último paso a propósito: si el
   trabajador se cae antes, el mensaje se repite y todo se hace de nuevo; la
   normalización reusa lo que ya hizo, y crear documentos, tareas y mensajes
   repetidos no duplica nada.

Si la normalización falla entera (un bug en algún documento, sin manifiesto), la
entrega queda en `error_proceso` y el mensaje va a errores (R21). Las demás
entregas siguen (R23).
"""

import logging
import tempfile
from pathlib import Path, PurePosixPath

import normalizacion
from normalizacion.almacen import Almacen
from normalizacion.entrega import normalizar_entrega
from normalizacion.inventario import ENTREGA_DEL_PROCESO
from normalizacion.parametros import PARAMETROS as PARAMETROS_NORMALIZACION

from . import estados
from .tareas import DOCUMENTO_CON_ERROR, crear_tarea
from .cola import CLASIFICAR, NORMALIZAR, Cola
from .errores import ErrorTransitorio
from .estado import Estado
from .origen import ErrorOrigen, Origen
from .reloj import Reloj

registro = logging.getLogger("orquestador.normalizar")

CAMPOS_DEL_MANIFIESTO = ("ruta_origen", "hash", "tipo_origen", "pdf", "anexo_nativo", "lectura", "paginas",
                         "duplicado_de", "error")


class VersionNoCoincide(Exception):
    """El normalizador instalado no es el que fijó el proceso. No se normaliza con
    otra versión sin un `reprocesar` explícito (entrega 2)."""


def ruta_en_la_entrega(archivo: str, entrega: str) -> str:
    """La ruta con que el oferente entregó el archivo, sin la carpeta de la entrega.

    `OF-001/sub/carta.pdf` queda `sub/carta.pdf`, que es lo que la normalización
    guarda como `ruta_origen` y de donde saca el `id_documento`. Si el archivo no
    está bajo la carpeta de la entrega (con la lista del aviso puede pasar), se
    deja la ruta completa.
    """
    partes = PurePosixPath(archivo).parts
    if len(partes) > 1 and partes[0] == entrega:
        return PurePosixPath(*partes[1:]).as_posix()
    return archivo


class Normalizar:
    cola = NORMALIZAR

    def __init__(
        self,
        cola: Cola,
        estado: Estado,
        origen: Origen,
        almacen: Almacen,
        reloj: Reloj,
        soffice: str | None = None,
    ) -> None:
        self._cola = cola
        self._estado = estado
        self._origen = origen
        self._almacen = almacen
        self._reloj = reloj
        self._soffice = soffice

    def procesar(self, cuerpo: dict) -> None:
        id_proceso, entrega = cuerpo["id_proceso"], cuerpo["entrega"]
        oferente = self._estado.leer(id_proceso, estados.OFERENTE, entrega)
        proceso = self._estado.leer(id_proceso, estados.PROCESO, id_proceso)
        if oferente is None or proceso is None:
            raise estados.NoExiste(f"No existe la entrega {entrega} o su proceso")
        if oferente.datos["estado"] == estados.PROCESANDO:
            registro.info("Entrega ya normalizada: mensaje repetido")
            return

        versiones = proceso.datos["versiones"]
        instaladas = (normalizacion.VERSION, PARAMETROS_NORMALIZACION.version)
        if (versiones["normalizador"], versiones["parametros_normalizacion"]) != instaladas:
            raise VersionNoCoincide(
                f"El proceso fijó el normalizador {versiones['normalizador']} con parámetros "
                f"{versiones['parametros_normalizacion']}, y está instalado {instaladas[0]} con {instaladas[1]}")

        with tempfile.TemporaryDirectory(prefix="entrega-") as temporal:
            carpeta = Path(temporal)
            for archivo in oferente.datos["archivos"]:
                try:
                    self._origen.bajar(f"{proceso.datos['ruta']}/{archivo}",
                                       carpeta / ruta_en_la_entrega(archivo, entrega))
                except ErrorOrigen:
                    raise ErrorTransitorio("No se pudo bajar un archivo del origen") from None
            resultado = normalizar_entrega(
                carpeta, id_proceso, None if entrega == ENTREGA_DEL_PROCESO else entrega, self._almacen,
                soffice=self._soffice)

        manifiesto = resultado.manifiesto
        normalizados = 0
        for archivo in manifiesto["archivos"]:
            self._registrar(id_proceso, entrega, archivo)
            if archivo["estado"] == estados.NORMALIZADO:
                normalizados += 1
                self._cola.publicar(CLASIFICAR, {"id_proceso": id_proceso, "entrega": entrega,
                                                 "id_documento": archivo["id_documento"]})

        uri_manifiesto = self._almacen.uri(f"{id_proceso}/{entrega}/manifiesto.json")
        estados.cambiar(
            self._estado, self._reloj, id_proceso, estados.OFERENTE, entrega,
            (estados.RECIBIDO, estados.ERROR_PROCESO), estados.PROCESANDO, "entrega normalizada",
            {"manifiesto": uri_manifiesto, "documentos": len(manifiesto["archivos"]),
             "descartados": len(manifiesto["descartados"]), "error": None},
        )
        registro.info("Entrega normalizada: %s documentos, %s para clasificar",
                      len(manifiesto["archivos"]), normalizados)

    def _registrar(self, id_proceso: str, entrega: str, archivo: dict) -> None:
        id_documento = archivo["id_documento"]
        estados.crear(
            self._estado, self._reloj, id_proceso, estados.DOCUMENTO, id_documento, archivo["estado"],
            "normalización", {k: archivo[k] for k in CAMPOS_DEL_MANIFIESTO}, entrega=entrega,
        )
        if archivo["estado"] == estados.ERROR_ENTRADA:
            error = archivo["error"]
            crear_tarea(self._estado, self._reloj, id_proceso, entrega, DOCUMENTO_CON_ERROR, id_documento,
                        error["codigo"], {"detalle": error["detalle"], "id_documento": id_documento})

    def al_fallar(self, cuerpo: dict, motivo: str) -> None:
        try:
            estados.cambiar(
                self._estado, self._reloj, cuerpo["id_proceso"], estados.OFERENTE, cuerpo["entrega"],
                estados.RECIBIDO, estados.ERROR_PROCESO, "falla al normalizar",
                {"error": motivo, "error_desde": self._reloj.ahora().isoformat()},
            )
        except estados.EstadoInesperado as e:
            registro.warning("La entrega ya estaba en %s: no se marca el error", e.registro.datos["estado"])
