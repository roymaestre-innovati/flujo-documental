"""El aviso de un evento armado con las tablas del módulo 1 (T03), con tablas
inventadas en memoria y, para la lectura de Delta, un log y unos parquet falsos."""

import copy
import hashlib
import io

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from orquestador import cola as c
from orquestador import estados
from orquestador.apertura import Apertura
from orquestador.entrada_modulo1 import (
    ADJUNTOS,
    EVENTOS,
    OFERENTES,
    EventoRechazado,
    OrigenRevisado,
    TablasEnMemoria,
    TablasOneLake,
    armar_entrada,
    crear_tareas_sin_contenido,
)
from orquestador.errores import ErrorDeConfiguracion, ErrorTransitorio, procesar_uno
from orquestador.estado import EstadoEnMemoria
from orquestador.origen import ArchivoDistinto, Esperado, OrigenLocal
from orquestador.origen_onelake import ErrorDeAcceso
from orquestador.reloj import RelojManual
from orquestador.tareas import DOCUMENTO_CON_ERROR

EVENTO = "Doc0000000001"
CARPETA = f"fase2/{EVENTO}"


def _adjunto(ruta, categoria, invitacion="inv-proceso", clave=None, padre=None, comprimido=False, datos=b"x",
             estado="EXITOSO"):
    return {"event_id": EVENTO, "doc_category": categoria, "invitation_id": invitacion,
            "adls_path": f"{CARPETA}/{ruta}", "downloaded_bytes": len(datos),
            "md5_hex": hashlib.md5(datos).hexdigest(), "is_compressed_archive": comprimido,
            "idempotency_key": clave or ruta, "parent_archive_key": padre, "file_status": estado}


def _tablas():
    return {
        EVENTOS: [
            {"event_id": EVENTO, "parent_project_id": "WS0000000001", "control_status": "DESCARGADO",
             "total_files_failed": 0, "updated_at_epoch_ms": 1_763_000_000_000},
            {"event_id": "Doc0000000002", "parent_project_id": "WS0000000002", "control_status": "ELEGIBLE",
             "total_files_failed": 0, "updated_at_epoch_ms": 1_763_000_000_000},
        ],
        OFERENTES: [
            {"event_id": EVENTO, "invitation_id": "inv-a", "sm_vendor_id": "S100"},
            {"event_id": EVENTO, "invitation_id": "inv-b", "sm_vendor_id": "S200"},
            {"event_id": "Doc0000000002", "invitation_id": "inv-a", "sm_vendor_id": "S999"},
        ],
        ADJUNTOS: [
            _adjunto("Documentos del proceso/cpc.pdf", "DOCUMENTOS_PROCESO"),
            _adjunto("Documentos del proceso/anexos.rar", "DOCUMENTOS_PROCESO", clave="k-rar", comprimido=True),
            _adjunto("Documentos del proceso/_contenido/anexos/a.pdf", "DOCUMENTOS_PROCESO", padre="k-rar"),
            _adjunto("Documentos del proceso/_contenido/anexos/b.zip", "DOCUMENTOS_PROCESO", clave="k-zip",
                     padre="k-rar", comprimido=True),
            _adjunto("Documentos del proceso/_contenido/anexos/_contenido/b/c.xlsx", "DOCUMENTOS_PROCESO",
                     padre="k-zip"),
            _adjunto("Oferentes/Empresa A/carta.pdf", "OFERENTE", "inv-a", datos=b"carta"),
            _adjunto("Oferentes/Empresa A/carta.pdf", "OFERENTE", "inv-a", datos=b"carta", estado="YA_EXISTIA_IDENTICO"),
            _adjunto("Oferentes/Empresa A/roto.rar", "OFERENTE", "inv-a", clave="k-roto", comprimido=True),
            _adjunto("Oferentes/Empresa B/oferta.xlsx", "OFERENTE", "inv-b"),
            {**_adjunto("otro.pdf", "OFERENTE", "inv-a"), "event_id": "Doc0000000002",
             "adls_path": "fase2/Doc0000000002/otro.pdf"},
        ],
    }


def test_arma_el_aviso_con_las_tablas():
    entrada = armar_entrada(EVENTO, TablasEnMemoria(_tablas()))
    x = {"tamano": 1, "md5": hashlib.md5(b"x").hexdigest()}
    carta_md5 = {"tamano": 5, "md5": hashlib.md5(b"carta").hexdigest()}
    assert entrada.aviso == {
        "contrato": "modulo5-orquestador/0.2", "id_proceso": EVENTO, "id_proyecto": "WS0000000001",
        "ruta": f"informacion-adjuntos/{CARPETA}", "fecha": "2025-11-13T02:13:20Z",
        "archivos": [
            {"ruta": "Documentos del proceso/_contenido/anexos/_contenido/b/c.xlsx", "id_oferente": None, **x},
            {"ruta": "Documentos del proceso/_contenido/anexos/a.pdf", "id_oferente": None, **x},
            {"ruta": "Documentos del proceso/cpc.pdf", "id_oferente": None, **x},
            {"ruta": "Oferentes/Empresa A/carta.pdf", "id_oferente": "S100", **carta_md5},
            {"ruta": "Oferentes/Empresa B/oferta.xlsx", "id_oferente": "S200", **x},
        ],
        "comprimidos_sin_contenido": [{"ruta": "Oferentes/Empresa A/roto.rar", "id_oferente": "S100"}]}
    assert entrada.proyecto == "WS0000000001"
    assert entrada.excluidos == {"comprimido": 3}
    assert entrada.sin_contenido == {"S100": ["Oferentes/Empresa A/roto.rar"]}
    carta = f"informacion-adjuntos/{CARPETA}/Oferentes/Empresa A/carta.pdf"
    assert entrada.esperados[carta] == Esperado(5, hashlib.md5(b"carta").hexdigest())
    assert len(entrada.esperados) == 5


def _cambiar(tablas, tabla, indice, **cambios):
    tablas[tabla][indice].update(cambios)
    return tablas


@pytest.mark.parametrize("tablas, texto", [
    (_cambiar(_tablas(), EVENTOS, 0, control_status="EN_SEGUIMIENTO"), "no está DESCARGADO"),
    (_cambiar(_tablas(), EVENTOS, 0, total_files_failed=2), "2 archivos que no se bajaron"),
    (_cambiar(_tablas(), EVENTOS, 0, event_id="Doc9"), "aparece 0 veces"),
    (_cambiar(_tablas(), EVENTOS, 0, updated_at_epoch_ms=None), "updated_at_epoch_ms"),
    (_cambiar(_tablas(), ADJUNTOS, 0, doc_category="OTRA"), "doc_category desconocida"),
    (_cambiar(_tablas(), ADJUNTOS, 8, invitation_id="inv-c"), "0 candidatos"),
    (_cambiar(_tablas(), OFERENTES, 1, invitation_id="inv-a"), "2 candidatos"),
    (_cambiar(_tablas(), ADJUNTOS, 6, md5_hex="otro"), "datos distintos"),
    (_cambiar(_tablas(), ADJUNTOS, 0, adls_path="fase2/Doc0000000009/cpc.pdf"), "fuera de su carpeta"),
    (_cambiar(_tablas(), ADJUNTOS, 0, adls_path=f"{CARPETA}/a/../../x.pdf"), "ruta no válida"),
    (_cambiar(_tablas(), ADJUNTOS, 0, file_status="FALLIDO"), "file_status FALLIDO"),
])
def test_rechaza_lo_que_no_cuadra(tablas, texto):
    with pytest.raises(EventoRechazado, match=texto) as error:
        armar_entrada(EVENTO, TablasEnMemoria(tablas))
    assert "Empresa" not in str(error.value)


def test_rechaza_un_evento_sin_archivos_que_no_sean_comprimidos():
    tablas = _tablas()
    tablas[ADJUNTOS] = [_adjunto("x.rar", "DOCUMENTOS_PROCESO", comprimido=True)]
    with pytest.raises(EventoRechazado, match="ningún archivo"):
        armar_entrada(EVENTO, TablasEnMemoria(tablas))


def test_una_tabla_que_falta_es_configuracion():
    tablas = _tablas()
    del tablas[OFERENTES]
    with pytest.raises(ErrorDeConfiguracion):
        armar_entrada(EVENTO, TablasEnMemoria(tablas))


def test_la_apertura_reparte_con_el_aviso_y_se_crean_las_tareas(tmp_path):
    reloj = RelojManual()
    cola = c.ColaEnMemoria(reloj)
    estado = EstadoEnMemoria()
    entrada = armar_entrada(EVENTO, TablasEnMemoria(_tablas()))
    cola.publicar(c.PROCESOS_LISTOS, entrada.aviso)
    assert procesar_uno(cola, Apertura(cola, estado, OrigenLocal(tmp_path), reloj)).desenlace == "ok"

    entregas = {r.id: r.datos["archivos"] for r in estado.listar(EVENTO, estados.OFERENTE)}
    assert sorted(entregas) == ["PROCESO", "S100", "S200"]
    assert entregas["S100"] == ["Oferentes/Empresa A/carta.pdf"]
    assert not any(r.endswith((".rar", ".zip")) for rutas in entregas.values() for r in rutas)

    assert crear_tareas_sin_contenido(estado, reloj, entrada) == 1
    crear_tareas_sin_contenido(estado, reloj, entrada)
    tareas = estado.listar(EVENTO, estados.TAREA)
    assert len(tareas) == 1
    tarea = tareas[0]
    assert tarea.datos["clase"] == DOCUMENTO_CON_ERROR
    assert tarea.datos["motivo"] == "COMPRIMIDO_SIN_CONTENIDO"
    assert tarea.datos["entrega"] == "S100"
    assert tarea.datos["ruta_origen"] == "Oferentes/Empresa A/roto.rar"


def test_origen_revisado_aplica_lo_esperado(tmp_path):
    (tmp_path / "o/x").mkdir(parents=True)
    (tmp_path / "o/x/a.pdf").write_bytes(b"abc")
    origen = OrigenRevisado(OrigenLocal(tmp_path / "o"), {"x/a.pdf": Esperado(tamano=4)})
    with pytest.raises(ArchivoDistinto):
        origen.bajar("x/a.pdf", tmp_path / "d/a.pdf")
    origen = OrigenRevisado(OrigenLocal(tmp_path / "o"), {})
    origen.bajar("x/a.pdf", tmp_path / "d/a.pdf")
    assert origen.listar("x") == ["a.pdf"]


# --- Lectura de Delta por OneLake, con un log y unos parquet falsos ---

RAIZ = "abfss://ws@onelake.dfs.fabric.microsoft.com/"


def _parquet(filas):
    salida = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(filas), salida)
    return salida.getvalue()


class _Delta:
    def __init__(self, uris, lector=1, particiones=()):
        self._uris, self._lector, self._particiones = uris, lector, list(particiones)

    def protocol(self):
        return type("P", (), {"min_reader_version": self._lector})()

    def metadata(self):
        return type("M", (), {"partition_columns": self._particiones})()

    def file_uris(self):
        return self._uris


class _Cliente:
    def __init__(self, archivos):
        self.archivos = archivos

    def get_file_client(self, ruta):
        datos = self.archivos[ruta]
        return type("F", (), {"download_file": lambda self: type("D", (), {"readall": lambda s: datos})()})()


def _tablas_onelake(delta):
    base = "lkh.Lakehouse/Tables/bronce/t"
    cliente = _Cliente({
        f"{base}/part-1.parquet": _parquet([{"a": 1, "b": "x"}]),
        f"{base}/part-2.parquet": _parquet([{"a": 2}]),  # archivo viejo, sin la columna b
    })
    return TablasOneLake("ws", "lkh", cliente=cliente, abrir_delta=delta, credencial=None)


def test_lee_solo_los_parquet_vigentes_y_rellena_columnas_que_faltan():
    vistos = []

    def abrir(uri, opciones):
        vistos.append(uri)
        return _Delta([f"{RAIZ}lkh.Lakehouse/Tables/bronce/t/part-1.parquet",
                       f"{RAIZ}lkh.Lakehouse/Tables/bronce/t/part-2.parquet"])

    filas = _tablas_onelake(abrir).leer("bronce/t", ["a", "b"])
    assert filas == [{"a": 1, "b": "x"}, {"a": 2, "b": None}]
    assert vistos == [f"{RAIZ}lkh.Lakehouse/Tables/bronce/t"]


@pytest.mark.parametrize("delta", [_Delta([], lector=3), _Delta([], particiones=["fecha"]),
                                   _Delta(["abfss://otro@onelake.dfs.fabric.microsoft.com/x.parquet"])])
def test_rechaza_tablas_con_otra_forma(delta):
    with pytest.raises(ErrorDeConfiguracion):
        _tablas_onelake(lambda uri, opciones: delta).leer("bronce/t", ["a"])


@pytest.mark.parametrize("falla, clase", [
    (type("TableNotFoundError", (Exception,), {})("no hay"), ErrorDeConfiguracion),
    (OSError("Generic MicrosoftAzure error: status 403 Forbidden"), ErrorDeAcceso),
    (OSError("Connection reset"), ErrorTransitorio),
])
def test_traduce_las_fallas_al_abrir_la_tabla(falla, clase):
    def abrir(uri, opciones):
        raise falla

    with pytest.raises(clase):
        _tablas_onelake(abrir).leer("bronce/t", ["a"])


def test_las_tablas_en_memoria_no_se_modifican():
    tablas = _tablas()
    copia = copy.deepcopy(tablas)
    armar_entrada(EVENTO, TablasEnMemoria(tablas))
    assert tablas == copia
