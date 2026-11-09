"""Tareas humanas: resolver una clasificación (R15) y escalar fallas (R22). T09."""

import pytest

from fabrica import P, Mundo, escribir, pdf
from orquestador import cola as c
from orquestador import contratos, estados
from orquestador.clasificador import ClasificadorFalso
from orquestador.clasificar import Clasificar
from orquestador.errores import ErrorTransitorio
from orquestador.extraer import Extraer
from orquestador.parametros import Parametros
from orquestador.resolucion import Asignacion, ResolucionInvalida, resolver_clasificacion
from orquestador.tareas import escalar_fallas

CSV = """id_oferente,ruta_origen,pagina_inicio,pagina_fin,tipo_documental,confianza,subtipo
OF-001,borroso.pdf,,,TD-24,0.60,
OF-001,mixto.pdf,1,1,TD-03,0.97,
OF-001,mixto.pdf,2,2,TD-16,0.50,
OF-001,hueco.pdf,1,1,TD-03,0.97,
OF-001,hueco.pdf,3,3,TD-07,0.97,
"""


@pytest.fixture
def mundo(tmp_path):
    escribir(tmp_path, "OF-001/borroso.pdf", pdf(1, "borroso"))
    escribir(tmp_path, "OF-001/mixto.pdf", pdf(2, "mixto"))
    escribir(tmp_path, "OF-001/hueco.pdf", pdf(3, "hueco"))
    escribir(tmp_path, "PROCESO/CPC.pdf", pdf(1, "CPC"))
    (tmp_path / "c.csv").write_text(CSV, encoding="utf-8")
    mundo = Mundo(tmp_path)
    mundo.abrir()
    mundo.correr(mundo.normalizar)
    mundo.extraer = Extraer(mundo.cola, mundo.almacen)
    mundo.clasificar = Clasificar(mundo.estado, mundo.almacen, ClasificadorFalso(tmp_path / "c.csv"),
                                  mundo.extraer, mundo.reloj)
    mundo.correr(mundo.clasificar)
    mundo.sacar(c.EXTRAER)
    return mundo


def _doc(mundo, ruta):
    return next(r for r in mundo.estado.listar(P, estados.DOCUMENTO) if r.datos["ruta_origen"] == ruta)


def _resolver(mundo, id_tarea, asignaciones, quien="evaluadora.juridica"):
    return resolver_clasificacion(mundo.estado, mundo.reloj, mundo.extraer, P, id_tarea, asignaciones, quien)


# --- Tarea de un segmento ---


def test_asignar_el_tipo_de_un_segmento_lo_manda_a_extraer(mundo):
    seg = f"{_doc(mundo, 'borroso.pdf').id}-p1-1"
    tarea = _resolver(mundo, f"clasificacion-{seg}", [Asignacion(1, 1, "TD-25")])
    assert tarea.datos["estado"] == estados.RESUELTA
    assert tarea.datos["resolucion"]["quien"] == "evaluadora.juridica"

    segmento = mundo.estado.leer(P, estados.SEGMENTO, seg).datos
    assert (segmento["estado"], segmento["tipo_documental"], segmento["asignado_por"]) == (
        estados.PENDIENTE, "TD-25", "evaluadora.juridica")
    assert (segmento["confianza"], segmento["tipo_sugerido"]) == (None, "TD-24")

    [solicitud] = mundo.sacar(c.EXTRAER)
    contratos.validar(contratos.EXTRACCION_ENTRADA, solicitud)
    assert (solicitud["id_segmento"], solicitud["tipo_documental"]) == (seg, "TD-25")
    assert (solicitud["confianza_clasificacion"], solicitud["clasificacion_dudosa"]) == (None, False)


def test_en_un_archivo_compuesto_solo_espera_el_segmento_dudoso(mundo):
    doc = _doc(mundo, "mixto.pdf")
    assert doc.datos["estado"] == estados.CLASIFICADO
    seg = f"{doc.id}-p2-2"
    _resolver(mundo, f"clasificacion-{seg}", [Asignacion(2, 2, "TD-99")])
    assert mundo.estado.leer(P, estados.SEGMENTO, seg).datos["estado"] == estados.SIN_EXTRACCION
    assert mundo.sacar(c.EXTRAER) == []


def test_resolver_dos_veces_no_repite_nada(mundo):
    seg = f"{_doc(mundo, 'borroso.pdf').id}-p1-1"
    _resolver(mundo, f"clasificacion-{seg}", [Asignacion(1, 1, "TD-25")])
    mundo.sacar(c.EXTRAER)
    otra = _resolver(mundo, f"clasificacion-{seg}", [Asignacion(1, 1, "TD-03")], quien="otra.persona")
    assert otra.datos["resolucion"]["quien"] == "evaluadora.juridica"
    assert mundo.sacar(c.EXTRAER) == []
    assert mundo.estado.leer(P, estados.SEGMENTO, seg).datos["tipo_documental"] == "TD-25"


@pytest.mark.parametrize("asignaciones,quien,mensaje", [
    ([Asignacion(1, 1, "TD-77")], "x", "TD desconocido"),
    ([Asignacion(1, 2, "TD-03")], "x", "va un solo tipo"),
    ([Asignacion(1, 1, "TD-03"), Asignacion(1, 1, "TD-07")], "x", "va un solo tipo"),
    ([Asignacion(1, 1, "TD-03")], "", "Falta quién"),
])
def test_asignacion_invalida_de_un_segmento(mundo, asignaciones, quien, mensaje):
    seg = f"{_doc(mundo, 'borroso.pdf').id}-p1-1"
    with pytest.raises(ResolucionInvalida, match=mensaje):
        _resolver(mundo, f"clasificacion-{seg}", asignaciones, quien)
    assert mundo.estado.leer(P, estados.TAREA, f"clasificacion-{seg}").datos["estado"] == estados.ABIERTA


# --- Tarea de un documento entero ---


def test_partir_un_documento_entero(mundo):
    doc = _doc(mundo, "hueco.pdf")
    assert doc.datos["estado"] == estados.ESPERANDO_CLASIFICACION_HUMANA
    _resolver(mundo, f"clasificacion-{doc.id}",
              [Asignacion(3, 3, "TD-14"), Asignacion(1, 2, "TD-03")])
    datos_doc = _doc(mundo, "hueco.pdf").datos
    assert (datos_doc["estado"], datos_doc["segmentos"]) == (estados.CLASIFICADO, [f"{doc.id}-p1-2", f"{doc.id}-p3-3"])
    pedidas = sorted((s["paginas"]["desde"], s["tipo_documental"]) for s in mundo.sacar(c.EXTRAER))
    assert pedidas == [(1, "TD-03"), (3, "TD-14")]


def test_partir_un_documento_revisa_las_paginas(mundo):
    doc = _doc(mundo, "hueco.pdf")
    with pytest.raises(ResolucionInvalida, match="faltan las páginas 3-3"):
        _resolver(mundo, f"clasificacion-{doc.id}", [Asignacion(1, 2, "TD-03")])
    assert _doc(mundo, "hueco.pdf").datos["estado"] == estados.ESPERANDO_CLASIFICACION_HUMANA


def test_solo_tareas_de_clasificacion(mundo):
    estados.crear(mundo.estado, mundo.reloj, P, estados.TAREA, "documento_con_error-X", estados.ABIERTA, "m",
                  {"clase": "documento_con_error"}, entrega="OF-001")
    with pytest.raises(ResolucionInvalida, match="no es de clasificación"):
        _resolver(mundo, "documento_con_error-X", [Asignacion(1, 1, "TD-03")])
    with pytest.raises(estados.NoExiste):
        _resolver(mundo, "clasificacion-no-hay", [Asignacion(1, 1, "TD-03")])


# --- Escalar fallas a las 24 horas ---


@pytest.fixture
def mundo_con_falla(mundo):
    # Los datos de un documento clasificado traen campos de más; se limpian para crear uno nuevo.
    doc = _doc(mundo, "borroso.pdf").datos
    limpio = {k: v for k, v in doc.items() if k not in ("estado", "entrega", "historial", "segmentos",
                                                         "version_ontologia", "error")}
    estados.crear(mundo.estado, mundo.reloj, P, estados.DOCUMENTO, "OF-001-nuevo", estados.NORMALIZADO, "prueba",
                  {**limpio, "ruta_origen": "nuevo.pdf"}, entrega="OF-001")

    class Caido:
        def clasificar(self, solicitud):
            raise ErrorTransitorio()

    bueno = mundo.clasificar._clasificador
    mundo.clasificar._clasificador = Caido()
    mundo.cola.publicar(c.CLASIFICAR, {"id_proceso": P, "entrega": "OF-001", "id_documento": "OF-001-nuevo"})
    while not any(r.desenlace == "a_errores" for r in mundo.correr(mundo.clasificar)):
        mundo.reloj.adelantar(3600)
    mundo.clasificar._clasificador = bueno
    assert mundo.estado.leer(P, estados.DOCUMENTO, "OF-001-nuevo").datos["estado"] == estados.ERROR_PROCESO
    return mundo


def test_no_escala_antes_de_24_horas(mundo_con_falla):
    mundo_con_falla.reloj.adelantar(23 * 3600)
    assert escalar_fallas(mundo_con_falla.estado, mundo_con_falla.reloj) == []


def test_escala_a_las_24_horas_una_sola_vez(mundo_con_falla):
    mundo = mundo_con_falla
    mundo.reloj.adelantar(24 * 3600)
    [tarea] = escalar_fallas(mundo.estado, mundo.reloj)
    assert tarea.id == "falla_tecnica-OF-001-nuevo"
    assert (tarea.datos["clase"], tarea.datos["motivo"], tarea.datos["entrega"]) == (
        "falla_tecnica", "FALLA_TECNICA", "OF-001")
    assert tarea.datos["referencia"] == {"tipo": "documento", "id": "OF-001-nuevo"}
    assert "falla técnica" in tarea.datos["detalle"]
    assert escalar_fallas(mundo.estado, mundo.reloj) == []


def test_horas_configurables(mundo_con_falla):
    mundo_con_falla.reloj.adelantar(2 * 3600)
    assert len(escalar_fallas(mundo_con_falla.estado, mundo_con_falla.reloj, Parametros(horas_escalamiento=1))) == 1


def test_escala_tambien_una_entrega_que_no_se_normalizo(mundo):
    estados.crear(mundo.estado, mundo.reloj, P, estados.OFERENTE, "OF-009", estados.RECIBIDO, "aviso",
                  {"archivos": []}, entrega="OF-009")
    estados.cambiar(mundo.estado, mundo.reloj, P, estados.OFERENTE, "OF-009", estados.RECIBIDO,
                    estados.ERROR_PROCESO, "falla", {"error": "Bug: X", "error_desde": mundo.reloj.ahora().isoformat()})
    mundo.reloj.adelantar(25 * 3600)
    [tarea] = escalar_fallas(mundo.estado, mundo.reloj)
    assert tarea.datos["referencia"] == {"tipo": "oferente", "id": "OF-009"}
    assert tarea.datos["detalle"].startswith("La entrega completa")
