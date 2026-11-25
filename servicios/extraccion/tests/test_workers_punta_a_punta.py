"""Los cuatro workers, uno tras otro, dan lo mismo que la corrida local (T08 de tasks-workers.md).

Cola y estado en memoria, almacén Blob sobre el contenedor falso, LLM falso. Se
compara contra `orquestador.local.Corrida` (estados y solicitudes) y contra
`extraer_segmento` llamado directo (sobres).
"""

import copy

import pytest
from mensajeria.cola import EXTRAER, RESULTADOS, ColaEnMemoria
from mensajeria.reloj import RelojSistema
from normalizacion.almacen import AlmacenLocal
from normalizacion.almacen_blob import AlmacenBlob
from orquestador import workers as workers_orquestador
from orquestador.clasificador import COLUMNAS, ClasificadorFalso
from orquestador.entorno import VARIABLES_COMUNES, VARIABLES_ORIGEN
from orquestador.entorno import Fabricas as FabricasOrquestador
from orquestador.estado import EstadoEnMemoria
from orquestador.local import Corrida, aviso
from orquestador.origen import OrigenLocal

from conftest import respuesta_falsa
from extraccion import worker as worker_extraccion
from extraccion.llamada import Llamador
from extraccion.llm import LLMFalso
from extraccion.reloj import RelojManual
from extraccion.resultados import ResultadosEnCarpeta
from extraccion.servicio import Servicio, extraer_segmento
from fabrica import PROCESO, pdf

RUTA = f"procesos/{PROCESO}"
FILAS = [
    ["OF-001", "certificado.pdf", "", "", "TD-16", "0.97", ""],
    ["OF-002", "certificado.pdf", "", "", "TD-16", "0.95", ""],
    ["", "condiciones.pdf", "", "", "TD-99", "1", ""],
]


@pytest.fixture
def datalake(tmp_path):
    raiz = tmp_path / "datalake"
    for ruta, texto in [("OF-001/certificado.pdf", "Certificado de aportes uno"),
                        ("OF-002/certificado.pdf", "Certificado de aportes dos"),
                        ("PROCESO/condiciones.pdf", "Condiciones del proceso")]:
        archivo = raiz / RUTA / ruta
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(pdf(2, texto))
    return raiz


@pytest.fixture
def csv():
    return ",".join(COLUMNAS) + "\n" + "".join(",".join(f) + "\n" for f in FILAS)


def _llm():
    return LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16")}, modelo="gpt-5.4")


def _estados(estado):
    return sorted((r.tipo, r.id, r.datos["estado"]) for r in estado.listar(PROCESO))


def _sin_uris(solicitud):
    return {k: v for k, v in solicitud.items() if k not in ("archivo", "lectura", "anexos")}


@pytest.fixture
def corrida_local(tmp_path, datalake, csv):
    (tmp_path / "clasificacion.csv").write_text(csv, encoding="utf-8")
    corrida = Corrida(OrigenLocal(datalake), AlmacenLocal(tmp_path / "local"),
                      ClasificadorFalso(tmp_path / "clasificacion.csv"))
    corrida.publicar_aviso(aviso(PROCESO, RUTA, corrida.reloj))
    corrida.correr()
    return corrida


def test_los_workers_dan_lo_mismo_que_la_corrida_local(
    corrida_local, datalake, csv, contenedor_blob_falso, monkeypatch, fuente_modelo, tmp_path,
):
    for nombre in VARIABLES_COMUNES + VARIABLES_ORIGEN + worker_extraccion.VARIABLES:
        monkeypatch.setenv(nombre, "valor-inventado")
    monkeypatch.setenv("CLASIFICADOR", "falso")
    monkeypatch.setenv("CLASIFICADOR_CSV", "config/clasificacion.csv")

    cola = ColaEnMemoria(RelojSistema())
    estado = EstadoEnMemoria()

    def blob():
        # Cada worker arma y cierra su almacén, sobre el mismo contenedor.
        return AlmacenBlob("cuentafalsa", "evaluacion-ofertas", cliente=contenedor_blob_falso)

    with blob() as almacen:
        almacen.escribir(almacen.uri("config/clasificacion.csv"), csv.encode("utf-8"))
    fabricas = FabricasOrquestador(cola=lambda: cola, estado=lambda: (estado, None),
                                   almacen=blob, origen=lambda: OrigenLocal(datalake))
    llm = _llm()
    fabricas_extraccion = worker_extraccion.Fabricas(cola=lambda: cola, almacen=blob,
                                                     fuente=lambda: fuente_modelo, cliente=lambda: llm)

    cola.publicar("procesos-listos", aviso(PROCESO, RUTA, RelojSistema()))
    for worker in ("apertura", "normalizar", "clasificar"):
        assert workers_orquestador.main([worker], fabricas=fabricas) == 0
    # Se miran las solicitudes sin sacarlas: se reciben todas y se devuelven.
    recibidos = []
    while (m := cola.recibir(EXTRAER)) is not None:
        recibidos.append(m)
    solicitudes = [copy.deepcopy(m.cuerpo) for m in recibidos]
    for m in recibidos:
        cola.abandonar(m)

    # Estados y solicitudes, como la corrida local.
    assert len(solicitudes) == 2
    assert {s["tipo_documental"] for s in solicitudes} == {"TD-16"}
    assert _estados(estado) == _estados(corrida_local.estado)
    assert sorted(map(_sin_uris, solicitudes), key=lambda s: s["id_segmento"]) == \
        sorted(map(_sin_uris, corrida_local.solicitudes), key=lambda s: s["id_segmento"])
    assert all(s["archivo"]["uri"].startswith("https://cuentafalsa.blob.core.windows.net/") for s in solicitudes)

    # Extracción con el worker, y los mismos sobres que llamando a extraer_segmento.
    assert worker_extraccion.main(["--hilos", "2"], fabricas=fabricas_extraccion) == 0
    sobres = {}
    while (m := cola.recibir(RESULTADOS)) is not None:
        sobres[m.cuerpo["id_segmento"]] = m.cuerpo
        cola.completar(m)
    assert set(sobres) == {s["id_segmento"] for s in solicitudes}
    assert {s["estado"] for s in sobres.values()} == {"ok"}

    reloj = RelojManual()
    with blob() as almacen:
        directo = Servicio(almacen=almacen, fuente=fuente_modelo, llamador=Llamador(_llm(), reloj),
                           resultados=ResultadosEnCarpeta(tmp_path / "directo"), reloj=reloj)
        for solicitud in solicitudes:
            esperado = extraer_segmento(solicitud, directo)
            obtenido = sobres[solicitud["id_segmento"]]
            assert {**obtenido, "ejecucion": None} == {**esperado, "ejecucion": None}
