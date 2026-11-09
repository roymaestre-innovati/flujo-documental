"""Clasificar cada documento (T07; R9 a R14)."""

import json

import pytest

from fabrica import P, Mundo, escribir, pdf
from orquestador import cola as c
from orquestador import contratos, datos, estados
from orquestador.clasificador import ClasificadorFalso
from orquestador.clasificar import Clasificar, problemas_de_la_respuesta
from orquestador.errores import ErrorTransitorio, reenviar_errores

CSV = """id_oferente,ruta_origen,pagina_inicio,pagina_fin,tipo_documental,confianza,subtipo
OF-001,carta.pdf,,,TD-03,0.97,
OF-001,compuesto.pdf,1,2,TD-03,0.96,
OF-001,compuesto.pdf,3,3,TD-14,0.93,
OF-001,parafiscales.pdf,,,TD-16,0.82,
OF-001,borroso.pdf,,,TD-24,0.60,
OF-001,mujeres.pdf,,,TD-98,0.91,emprendimiento_mujeres
OF-001,justo.pdf,,,TD-16,0.90,
OF-001,piso.pdf,,,TD-16,0.75,
OF-001,hueco.pdf,1,1,TD-03,0.97,
OF-001,hueco.pdf,3,3,TD-03,0.97,
,CPC.pdf,,,TD-01,0.99,
"""

ARCHIVOS = {"carta.pdf": 1, "compuesto.pdf": 3, "parafiscales.pdf": 1, "borroso.pdf": 1, "mujeres.pdf": 1,
            "justo.pdf": 1, "piso.pdf": 1, "hueco.pdf": 3, "sin_fila.pdf": 1}


class Pedidos:
    """Doble de las solicitudes de extracción (T08)."""

    def __init__(self):
        self.pedidos = []

    def pedir(self, proceso, documento, segmento):
        self.pedidos.append(segmento.id)


class Contador:
    def __init__(self, clasificador):
        self.clasificador = clasificador
        self.solicitudes = []

    def clasificar(self, solicitud):
        self.solicitudes.append(solicitud)
        return self.clasificador.clasificar(solicitud)


@pytest.fixture
def mundo(tmp_path):
    for nombre, paginas in ARCHIVOS.items():
        escribir(tmp_path, f"OF-001/{nombre}", pdf(paginas, nombre))
    escribir(tmp_path, "PROCESO/CPC.pdf", pdf(2, "CPC"))
    (tmp_path / "clasificacion.csv").write_text(CSV, encoding="utf-8")
    mundo = Mundo(tmp_path)
    mundo.abrir()
    mundo.correr(mundo.normalizar)
    mundo.pedidos = Pedidos()
    mundo.clasificador = Contador(ClasificadorFalso(tmp_path / "clasificacion.csv"))
    mundo.clasificar = Clasificar(mundo.estado, mundo.almacen, mundo.clasificador, mundo.pedidos, mundo.reloj)
    return mundo


def _documento(mundo, ruta):
    return next(r for r in mundo.estado.listar(P, estados.DOCUMENTO) if r.datos["ruta_origen"] == ruta)


def _segmentos(mundo, ruta):
    doc = _documento(mundo, ruta)
    return [r.datos for r in mundo.estado.listar(P, estados.SEGMENTO) if r.datos["id_documento"] == doc.id]


def test_clasifica_todos_los_documentos(mundo):
    resultados = mundo.correr(mundo.clasificar)
    assert [r.desenlace for r in resultados] == ["ok"] * 10
    estados_docs = {r.datos["ruta_origen"]: r.datos["estado"] for r in mundo.estado.listar(P, estados.DOCUMENTO)}
    assert estados_docs.pop("hueco.pdf") == estados.ESPERANDO_CLASIFICACION_HUMANA
    assert set(estados_docs.values()) == {estados.CLASIFICADO}


def test_solicitud_segun_el_contrato(mundo):
    mundo.correr(mundo.clasificar)
    proceso = mundo.estado.leer(P, estados.PROCESO, P).datos
    for solicitud in mundo.clasificador.solicitudes:
        contratos.validar(contratos.CLASIFICACION_SOLICITUD, solicitud)
        assert solicitud["version_ontologia"] == proceso["versiones"]["ontologia"]
        lectura = json.loads(mundo.almacen.leer(solicitud["lectura"]))
        assert solicitud["pdf"]["sha256"] == lectura["hash_pdf"]
    cpc = next(s for s in mundo.clasificador.solicitudes if s["ruta_origen"] == "CPC.pdf")
    assert cpc["id_oferente"] is None
    carta = next(s for s in mundo.clasificador.solicitudes if s["ruta_origen"] == "carta.pdf")
    assert carta["id_oferente"] == "OF-001"


def test_confianza_alta_se_extrae(mundo):
    mundo.correr(mundo.clasificar)
    [segmento] = _segmentos(mundo, "carta.pdf")
    assert (segmento["estado"], segmento["tipo_documental"], segmento["clasificacion_dudosa"]) == (
        estados.PENDIENTE, "TD-03", False)
    doc = _documento(mundo, "carta.pdf")
    assert f"{doc.id}-p1-1" in mundo.pedidos.pedidos
    assert doc.datos["segmentos"] == [f"{doc.id}-p1-1"]


def test_documento_compuesto_da_varios_segmentos(mundo):
    mundo.correr(mundo.clasificar)
    segmentos = _segmentos(mundo, "compuesto.pdf")
    assert [(s["pagina_inicio"], s["pagina_fin"], s["tipo_documental"]) for s in segmentos] == [
        (1, 2, "TD-03"), (3, 3, "TD-14")]
    assert all(s["estado"] == estados.PENDIENTE for s in segmentos)


@pytest.mark.parametrize("ruta,estado,dudosa", [
    ("parafiscales.pdf", estados.PENDIENTE, True),    # 0,82 con umbral 0,90
    ("justo.pdf", estados.PENDIENTE, False),          # justo en el umbral
    ("piso.pdf", estados.PENDIENTE, True),            # justo en el piso
    ("borroso.pdf", estados.ESPERANDO_CLASIFICACION_HUMANA, False),  # 0,60
])
def test_umbrales(mundo, ruta, estado, dudosa):
    mundo.correr(mundo.clasificar)
    [segmento] = _segmentos(mundo, ruta)
    assert (segmento["estado"], segmento["clasificacion_dudosa"]) == (estado, dudosa)


def test_confianza_baja_crea_tarea_y_no_se_extrae(mundo):
    mundo.correr(mundo.clasificar)
    doc = _documento(mundo, "borroso.pdf")
    id_seg = f"{doc.id}-p1-1"
    assert id_seg not in mundo.pedidos.pedidos
    tarea = mundo.estado.leer(P, estados.TAREA, f"clasificacion-{id_seg}").datos
    assert (tarea["clase"], tarea["motivo"], tarea["id_segmento"], tarea["entrega"]) == (
        "clasificacion", "CONFIANZA_BAJA", id_seg, "OF-001")
    assert "TD-24" in tarea["detalle"]
    assert doc.datos["estado"] == estados.CLASIFICADO


@pytest.mark.parametrize("ruta,td", [("mujeres.pdf", "TD-98"), ("sin_fila.pdf", "TD-99")])
def test_desempate_y_sin_tipo_no_se_extraen(mundo, ruta, td):
    mundo.correr(mundo.clasificar)
    [segmento] = _segmentos(mundo, ruta)
    assert (segmento["estado"], segmento["tipo_documental"]) == (estados.SIN_EXTRACCION, td)
    assert not any(p.startswith(_documento(mundo, ruta).id) for p in mundo.pedidos.pedidos)


def test_subtipo_se_guarda(mundo):
    mundo.correr(mundo.clasificar)
    [segmento] = _segmentos(mundo, "mujeres.pdf")
    assert segmento["subtipo"] == "emprendimiento_mujeres"


def test_respuesta_invalida_dos_veces_va_a_una_persona(mundo):
    mundo.correr(mundo.clasificar)
    doc = _documento(mundo, "hueco.pdf")
    assert doc.datos["estado"] == estados.ESPERANDO_CLASIFICACION_HUMANA
    assert sum(1 for s in mundo.clasificador.solicitudes if s["id_documento"] == doc.id) == 2
    tarea = mundo.estado.leer(P, estados.TAREA, f"clasificacion-{doc.id}").datos
    assert (tarea["motivo"], tarea["id_segmento"]) == ("RESPUESTA_INVALIDA", None)
    assert tarea["detalle"] == "hueco: páginas 2-2"
    assert _segmentos(mundo, "hueco.pdf") == []


def test_respuesta_invalida_y_despues_buena(mundo):
    class UnaMala:
        def __init__(self, bueno):
            self.bueno, self.llamadas = bueno, 0

        def clasificar(self, solicitud):
            self.llamadas += 1
            respuesta = self.bueno.clasificar(solicitud)
            if self.llamadas == 1:
                respuesta = {**respuesta, "version_ontologia": "otra"}
            return respuesta

    mundo.clasificar._clasificador = UnaMala(mundo.clasificador)
    mundo.sacar(c.CLASIFICAR)
    doc = _documento(mundo, "carta.pdf")
    mundo.cola.publicar(c.CLASIFICAR, {"id_proceso": P, "entrega": "OF-001", "id_documento": doc.id})
    assert [r.desenlace for r in mundo.correr(mundo.clasificar)] == ["ok"]
    assert _documento(mundo, "carta.pdf").datos["estado"] == estados.CLASIFICADO


def test_mensaje_repetido_no_hace_nada(mundo):
    mundo.correr(mundo.clasificar)
    antes = {(r.tipo, r.id): r.version for r in mundo.estado.listar(P)}
    pedidos = len(mundo.pedidos.pedidos)
    doc = _documento(mundo, "carta.pdf")
    mundo.cola.publicar(c.CLASIFICAR, {"id_proceso": P, "entrega": "OF-001", "id_documento": doc.id})
    assert [r.desenlace for r in mundo.correr(mundo.clasificar)] == ["ok"]
    assert {(r.tipo, r.id): r.version for r in mundo.estado.listar(P)} == antes
    assert len(mundo.pedidos.pedidos) == pedidos


def test_clasificador_caido_deja_el_documento_en_error_y_se_recupera(mundo):
    class Caido:
        def clasificar(self, solicitud):
            raise ErrorTransitorio("sin servicio")

    bueno = mundo.clasificar._clasificador
    mundo.clasificar._clasificador = Caido()
    mundo.sacar(c.CLASIFICAR)
    doc = _documento(mundo, "carta.pdf")
    mundo.cola.publicar(c.CLASIFICAR, {"id_proceso": P, "entrega": "OF-001", "id_documento": doc.id})
    while True:
        resultados = mundo.correr(mundo.clasificar)
        if any(r.desenlace == "a_errores" for r in resultados):
            break
        mundo.reloj.adelantar(3600)
    datos_doc = _documento(mundo, "carta.pdf").datos
    assert datos_doc["estado"] == estados.ERROR_PROCESO
    assert datos_doc["error"].startswith("Transitoria sin resolver")

    mundo.clasificar._clasificador = bueno
    reenviar_errores(mundo.cola, c.CLASIFICAR)
    assert [r.desenlace for r in mundo.correr(mundo.clasificar)] == ["ok"]
    datos_doc = _documento(mundo, "carta.pdf").datos
    assert (datos_doc["estado"], datos_doc["error"]) == (estados.CLASIFICADO, None)


# --- Revisión de la respuesta, sin mundo ---

TIPOS = datos.tipos_documentales("1")
SOLICITUD = {"id_documento": "D", "version_ontologia": "1", "paginas": 5}


def _respuesta(*segmentos, **extra):
    return {"contrato": "modulo5-orquestador/0.1", "id_documento": "D", "version_ontologia": "1",
            "segmentos": [{"pagina_inicio": a, "pagina_fin": b, "tipo_documental": t, "subtipo": None,
                           "confianza": 0.9} for a, b, t in segmentos], **extra}


@pytest.mark.parametrize("respuesta,problemas", [
    (_respuesta((1, 5, "TD-03")), []),
    (_respuesta((1, 2, "TD-03"), (3, 5, "TD-07")), []),
    (_respuesta((1, 3, "TD-03"), (3, 5, "TD-07")), ["solape desde la página 3"]),
    (_respuesta((1, 2, "TD-03")), ["faltan las páginas 3-5"]),
    (_respuesta((2, 5, "TD-03")), ["hueco: páginas 1-1"]),
    (_respuesta((1, 6, "TD-03")), ["páginas de más: hasta la 6 de 5"]),
    (_respuesta((1, 5, "TD-77")), ["TD desconocido en 1-5"]),
    (_respuesta((3, 2, "TD-03"), (3, 5, "TD-03")), ["hueco: páginas 1-2", "segmento al revés: 3-2"]),
    (_respuesta((1, 5, "TD-03"), id_documento="X"), ["id_documento distinto al de la solicitud"]),
    (_respuesta((1, 5, "TD-03"), version_ontologia="2"), ["version_ontologia distinta a la fijada"]),
    ({"segmentos": []}, ["(raíz): no cumple 'required'"] * 3 + ["segmentos: no cumple 'minItems'"]),
])
def test_problemas_de_la_respuesta(respuesta, problemas):
    assert sorted(problemas_de_la_respuesta(respuesta, SOLICITUD, TIPOS)) == sorted(problemas)
