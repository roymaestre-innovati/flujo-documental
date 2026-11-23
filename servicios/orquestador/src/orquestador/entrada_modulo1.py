"""El aviso de un evento, armado con las tablas del módulo 1 (T03 de
`specs/005-orquestador/tasks-entrada-onelake.md`).

Es provisional: el módulo 1 prometió una vista con lo que necesitamos. Mientras
tanto se leen sus tablas internas de `lkh_evaluacionofertas_bronce`, que pueden
cambiar sin aviso. Cuando llegue la vista, solo cambia este módulo: la apertura
sigue repartiendo con la lista `archivos` del aviso, como define el contrato.

Para un evento (`event_id`, que es el `id_proceso`, decisión del 2026-11-20):

1. El evento debe estar en `DESCARGADO` en `eventos_control`, sin archivos
   fallidos. La fecha del aviso es la de su último cambio ahí.
2. Cada fila de `adjuntos_metadata` es un archivo. `DOCUMENTOS_PROCESO` va a la
   entrega del proceso; `OFERENTE`, a la del `sm_vendor_id` que le corresponde en
   `oferentes_control` por `event_id` e `invitation_id`.
3. Los ZIP y RAR no entran (decisión del usuario, 2026-11-18): el módulo 1 ya
   los descomprimió y sus archivos tienen fila propia. Un comprimido sin ninguna
   fila hija queda aparte, para crearle una tarea al evaluador.
4. Lo que no está en la tabla no entra: los JSON del módulo 1 y los archivos
   huérfanos de corridas viejas (nota de T01).

Cualquier dato que no cuadre rechaza el aviso (`EventoRechazado`): no se reparte
a ciegas ni se evalúa a nadie con documentos de menos. Los mensajes llevan
conteos y nombres de columnas, nunca rutas ni nombres de oferentes.
"""

import datetime
import io
import logging
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from normalizacion.inventario import ENTREGA_DEL_PROCESO

from . import CONTRATO, contratos
from .apertura import AvisoRechazado
from .errores import ErrorDeConfiguracion, ErrorTransitorio
from .origen import ErrorOrigen, _ruta_segura
from .origen_onelake import ENDPOINT, ErrorDeAcceso, traducir_fallas

registro = logging.getLogger("orquestador.entrada_modulo1")

ADJUNTOS = "bronce/tbl_evaluacionofertas_adjuntos_metadata"
OFERENTES = "bronce/tbl_evaluacionofertas_oferentes_control"
EVENTOS = "control/tbl_evaluacionofertas_eventos_control"

SHORTCUT = "informacion-adjuntos"
PREFIJO = "fase2"
"""Las rutas de `adjuntos_metadata` son relativas al shortcut y empiezan con
`fase2/<event_id>/` (lo fija el notebook del módulo 1)."""

DESCARGADO = "DESCARGADO"
DEL_PROCESO = "DOCUMENTOS_PROCESO"
DE_OFERENTE = "OFERENTE"
ESTADOS_BAJADOS = {"EXITOSO", "YA_EXISTIA_IDENTICO"}

COLUMNAS_ADJUNTOS = ["event_id", "doc_category", "invitation_id", "adls_path", "downloaded_bytes", "md5_hex",
                     "is_compressed_archive", "idempotency_key", "parent_archive_key", "file_status"]
COLUMNAS_OFERENTES = ["event_id", "invitation_id", "sm_vendor_id"]
COLUMNAS_EVENTOS = ["event_id", "parent_project_id", "control_status", "total_files_failed", "updated_at_epoch_ms"]


class EventoRechazado(AvisoRechazado):
    """Con las tablas del módulo 1 no se puede armar el aviso de este evento."""


class Tablas(Protocol):
    def leer(self, tabla: str, columnas: list[str]) -> list[dict]:
        """Las filas vigentes de `tabla`, con esas columnas. Una columna que no
        existe en un archivo viejo de la tabla llega como None."""


class TablasEnMemoria:
    """Para las pruebas y para correr sin OneLake."""

    def __init__(self, tablas: dict[str, list[dict]]) -> None:
        self._tablas = tablas

    def leer(self, tabla: str, columnas: list[str]) -> list[dict]:
        if tabla not in self._tablas:
            raise ErrorDeConfiguracion(f"No existe la tabla {tabla}")
        return [{c: fila.get(c) for c in columnas} for fila in self._tablas[tabla]]


class TablasOneLake:
    """Tablas Delta de un lakehouse, leídas por OneLake.

    `deltalake` solo resuelve qué archivos parquet están vigentes. Los parquet
    se bajan con el SDK de Azure y se leen con `pyarrow`: si `deltalake` lee los
    datos, el proceso no termina al salir (nota de T03). Sirve porque las tablas
    del módulo 1 usan el protocolo 1 de Delta, sin particiones ni vectores de
    borrado; si eso cambia, se rechaza en lugar de leer mal.
    """

    def __init__(
        self,
        workspace: str,
        lakehouse: str,
        *,
        credencial: Any = None,
        cliente: Any = None,
        abrir_delta: Callable[[str, dict], Any] | None = None,
    ) -> None:
        self._workspace = workspace
        self._item = lakehouse if lakehouse.endswith(".Lakehouse") else f"{lakehouse}.Lakehouse"
        if credencial is None and (cliente is None or abrir_delta is None):
            from azure.identity import DefaultAzureCredential

            credencial = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self._credencial = credencial
        if cliente is None:
            from azure.storage.filedatalake import DataLakeServiceClient

            cliente = DataLakeServiceClient(ENDPOINT, credential=credencial).get_file_system_client(workspace)
        self._cliente = cliente
        if abrir_delta is None:
            from deltalake import DeltaTable

            def abrir_delta(uri, opciones):
                return DeltaTable(uri, storage_options=opciones)
        self._abrir_delta = abrir_delta

    def _opciones(self) -> dict:
        if self._credencial is None:
            return {}
        try:
            token = self._credencial.get_token("https://storage.azure.com/.default").token
        except Exception as error:  # noqa: BLE001 - sin identidad no hay nada que reintentar
            raise ErrorDeAcceso(f"Sin identidad para leer las tablas ({type(error).__name__})") from None
        return {"bearer_token": token, "use_fabric_endpoint": "true"}

    def _archivos_vigentes(self, tabla: str) -> list[str]:
        raiz = f"abfss://{self._workspace}@onelake.dfs.fabric.microsoft.com/"
        uri = f"{raiz}{self._item}/Tables/{tabla}"
        try:
            delta = self._abrir_delta(uri, self._opciones())
            lector = delta.protocol().min_reader_version
            particiones = delta.metadata().partition_columns
            uris = delta.file_uris()
        except (ErrorDeConfiguracion, ErrorTransitorio):
            raise
        except Exception as error:  # noqa: BLE001 - deltalake no tiene clases por código HTTP
            texto = str(error)
            if "TableNotFound" in type(error).__name__ or "no log files" in texto.lower():
                raise ErrorDeConfiguracion(f"No existe la tabla {tabla}") from None
            if re.search(r"\b(401|403)\b", texto):
                raise ErrorDeAcceso(f"OneLake no dejó leer la tabla {tabla}") from None
            raise ErrorTransitorio(f"No se pudo leer el log de la tabla {tabla}: {type(error).__name__}") from None
        if lector > 1 or particiones:
            raise ErrorDeConfiguracion(
                f"La tabla {tabla} cambió de forma (protocolo {lector}, {len(particiones)} particiones): "
                "hay que revisar cómo se lee")
        rutas = []
        for archivo in uris:
            if not archivo.startswith(raiz):
                raise ErrorDeConfiguracion(f"La tabla {tabla} apunta a archivos fuera del workspace")
            rutas.append(archivo[len(raiz):])
        return rutas

    def leer(self, tabla: str, columnas: list[str]) -> list[dict]:
        import pyarrow.parquet as pq

        filas: list[dict] = []
        for ruta in self._archivos_vigentes(tabla):
            with traducir_fallas("leer una tabla"):
                datos = self._cliente.get_file_client(ruta).download_file().readall()
            archivo = pq.read_table(io.BytesIO(datos))
            presentes = [c for c in columnas if c in archivo.column_names]
            for fila in archivo.select(presentes).to_pylist():
                filas.append({c: fila.get(c) for c in columnas})
        return filas


@dataclass
class EntradaDelEvento:
    aviso: dict
    """Cumple `proceso-listo` 0.2: `ruta` es la carpeta del evento bajo `Files/`,
    cada archivo es relativo a ella y trae su tamaño y su MD5, y el aviso trae el
    proyecto y los comprimidos sin contenido."""
    proyecto: str | None
    sin_contenido: dict[str, list[str]] = field(default_factory=dict)
    """Entrega → comprimidos sin ninguna fila hija, relativos a `ruta`."""
    excluidos: Counter = field(default_factory=Counter)
    """Motivo → archivos que no entran."""


def _fecha(epoch_ms: Any) -> str:
    if not isinstance(epoch_ms, int) or isinstance(epoch_ms, bool):
        raise EventoRechazado("El evento no trae updated_at_epoch_ms en eventos_control")
    return datetime.datetime.fromtimestamp(epoch_ms / 1000, datetime.UTC).isoformat().replace("+00:00", "Z")


def _unicas(filas: list[dict]) -> list[dict]:
    """Una fila por ruta. Las repetidas deben decir lo mismo."""
    por_ruta: dict[str, dict] = {}
    for fila in filas:
        ruta = fila["adls_path"]
        if not ruta:
            raise EventoRechazado("Una fila de adjuntos_metadata no trae adls_path")
        previa = por_ruta.setdefault(ruta, fila)
        if previa is not fila and any(previa[c] != fila[c] for c in
                                      ("doc_category", "invitation_id", "downloaded_bytes", "md5_hex",
                                       "is_compressed_archive")):
            raise EventoRechazado("Una ruta aparece dos veces en adjuntos_metadata con datos distintos")
    return [por_ruta[r] for r in sorted(por_ruta)]


def armar_entrada(id_evento: str, tablas: Tablas) -> EntradaDelEvento:
    eventos = [e for e in tablas.leer(EVENTOS, COLUMNAS_EVENTOS) if e["event_id"] == id_evento]
    if len(eventos) != 1:
        raise EventoRechazado(f"El evento aparece {len(eventos)} veces en eventos_control")
    evento = eventos[0]
    if evento["control_status"] != DESCARGADO:
        raise EventoRechazado(f"El evento no está {DESCARGADO}")
    if evento["total_files_failed"]:
        raise EventoRechazado(f"El evento tiene {evento['total_files_failed']} archivos que no se bajaron")

    vendedores: dict[str, set] = defaultdict(set)
    for oferente in tablas.leer(OFERENTES, COLUMNAS_OFERENTES):
        if oferente["event_id"] == id_evento:
            vendedores[oferente["invitation_id"]].add(oferente["sm_vendor_id"])

    filas = _unicas([f for f in tablas.leer(ADJUNTOS, COLUMNAS_ADJUNTOS) if f["event_id"] == id_evento])
    if not filas:
        raise EventoRechazado("El evento no tiene filas en adjuntos_metadata")

    carpeta = f"{PREFIJO}/{id_evento}/"
    ruta_evento = f"{SHORTCUT}/{PREFIJO}/{id_evento}"
    try:
        _ruta_segura(ruta_evento)
    except ErrorOrigen:
        raise EventoRechazado("El evento tiene una ruta no válida") from None
    padres = {f["parent_archive_key"] for f in filas if f["parent_archive_key"]}
    entrada = EntradaDelEvento(aviso={}, proyecto=evento["parent_project_id"])
    archivos = []
    for fila in filas:
        if fila["file_status"] not in ESTADOS_BAJADOS:
            raise EventoRechazado("Un archivo tiene un file_status que no corresponde a una descarga exitosa")
        if not fila["adls_path"].startswith(carpeta):
            raise EventoRechazado("Un archivo del evento está fuera de su carpeta")
        relativa = fila["adls_path"][len(carpeta):]
        try:
            _ruta_segura(relativa)
        except ErrorOrigen:
            raise EventoRechazado("Un archivo del evento tiene una ruta no válida") from None

        if fila["doc_category"] == DEL_PROCESO:
            id_oferente = None
        elif fila["doc_category"] == DE_OFERENTE:
            candidatos = vendedores.get(fila["invitation_id"], set())
            if len(candidatos) != 1 or not next(iter(candidatos)):
                raise EventoRechazado(
                    f"Un archivo de oferente no cruza con un único sm_vendor_id en oferentes_control "
                    f"({len(candidatos)} candidatos)")
            id_oferente = next(iter(candidatos))
        else:
            raise EventoRechazado("doc_category desconocida")

        if fila["is_compressed_archive"]:
            entrada.excluidos["comprimido"] += 1
            if fila["idempotency_key"] not in padres:
                entrada.sin_contenido.setdefault(id_oferente or ENTREGA_DEL_PROCESO, []).append(relativa)
            continue
        archivo = {"ruta": relativa, "id_oferente": id_oferente}
        if isinstance(fila["downloaded_bytes"], int):
            archivo["tamano"] = fila["downloaded_bytes"]
        if fila["md5_hex"]:
            archivo["md5"] = fila["md5_hex"]
        archivos.append(archivo)

    if not archivos:
        raise EventoRechazado("El evento no tiene ningún archivo que no sea comprimido")
    entrada.aviso = {"contrato": CONTRATO, "id_proceso": id_evento, "ruta": ruta_evento,
                     "fecha": _fecha(evento["updated_at_epoch_ms"]), "archivos": archivos}
    if evento["parent_project_id"]:
        entrada.aviso["id_proyecto"] = evento["parent_project_id"]
    sin_contenido = [{"ruta": ruta, "id_oferente": None if entrega == ENTREGA_DEL_PROCESO else entrega}
                     for entrega, rutas in sorted(entrada.sin_contenido.items()) for ruta in rutas]
    if sin_contenido:
        entrada.aviso["comprimidos_sin_contenido"] = sin_contenido
    contratos.validar(contratos.PROCESO_LISTO, entrada.aviso)
    registro.info("Aviso armado con las tablas del módulo 1: %s archivos, %s entregas, excluidos %s, "
                  "comprimidos sin contenido %s", len(archivos),
                  len({a["id_oferente"] for a in archivos}), dict(entrada.excluidos),
                  sum(len(v) for v in entrada.sin_contenido.values()))
    return entrada
