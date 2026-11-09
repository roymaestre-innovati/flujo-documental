"""Solicitudes de extracción (T08; R16 y R17)."""

import json

import pytest

from fabrica import P, Mundo, escribir, pdf
from orquestador import CONTRATO_EXTRACCION, contratos, estados
from orquestador import cola as c
from orquestador.clasificador import ClasificadorFalso
from orquestador.clasificar import Clasificar
from orquestador.estado import Registro
from orquestador.extraer import Extraer, SolicitudInvalida, solicitud

CSV = """id_oferente,ruta_origen,pagina_inicio,pagina_fin,tipo_documental,confianza,subtipo
OF-001,compuesto.pdf,1,2,TD-03,0.97,
OF-001,compuesto.pdf,3,3,TD-16,0.82,
OF-001,mujeres.pdf,,,TD-98,0.91,mipyme
,CPC.pdf,,,TD-01,0.99,
"""


@pytest.fixture
def mundo(tmp_path):
    escribir(tmp_path, "OF-001/compuesto.pdf", pdf(3, "compuesto"))
    escribir(tmp_path, "OF-001/mujeres.pdf", pdf(1, "desempate"))
    escribir(tmp_path, "PROCESO/CPC.pdf", pdf(2, "CPC"))
    (tmp_path / "c.csv").write_text(CSV, encoding="utf-8")
    mundo = Mundo(tmp_path)
    mundo.abrir()
    mundo.correr(mundo.normalizar)
    mundo.extraer = Extraer(mundo.cola, mundo.almacen)
    mundo.clasificar = Clasificar(mundo.estado, mundo.almacen, ClasificadorFalso(tmp_path / "c.csv"),
                                  mundo.extraer, mundo.reloj)
    assert {r.desenlace for r in mundo.correr(mundo.clasificar)} == {"ok"}
    return mundo


def test_una_solicitud_por_segmento_que_se_extrae(mundo):
    solicitudes = mundo.sacar(c.EXTRAER)
    vistas = sorted(((s["id_oferente"], s["tipo_documental"], s["paginas"]["desde"]) for s in solicitudes), key=str)
    assert vistas == sorted([("OF-001", "TD-03", 1), ("OF-001", "TD-16", 3), (None, "TD-01", 1)], key=str)


def test_cada_solicitud_cumple_el_contrato_0_2(mundo):
    for s in mundo.sacar(c.EXTRAER):
        contratos.validar(contratos.EXTRACCION_ENTRADA, s)
        assert s["contrato"] == CONTRATO_EXTRACCION


def test_campos_de_la_solicitud(mundo):
    proceso = mundo.estado.leer(P, estados.PROCESO, P).datos
    por_td = {s["tipo_documental"]: s for s in mundo.sacar(c.EXTRAER)}
    dudosa = por_td["TD-16"]
    documento = mundo.estado.leer(P, estados.DOCUMENTO, dudosa["id_documento"]).datos
    lectura = json.loads(mundo.almacen.leer(documento["lectura"]))
    assert dudosa["id_segmento"] == f"{dudosa['id_documento']}-p3-3"
    assert dudosa["paginas"] == {"desde": 3, "hasta": 3}
    assert dudosa["archivo"] == {"uri": documento["pdf"], "sha256": lectura["hash_pdf"]}
    assert dudosa["lectura"] == documento["lectura"]
    assert dudosa["anexos"] == []
    assert (dudosa["clasificacion_dudosa"], dudosa["confianza_clasificacion"]) == (True, 0.82)
    assert dudosa["version_modelo"] == proceso["versiones"]["modelo_extraccion"]
    assert por_td["TD-03"]["clasificacion_dudosa"] is False


def test_documento_del_proceso_va_sin_oferente(mundo):
    [cpc] = [s for s in mundo.sacar(c.EXTRAER) if s["tipo_documental"] == "TD-01"]
    assert cpc["id_oferente"] is None
    assert cpc["id_segmento"].startswith("PROCESO-")


def test_desempate_no_se_pide(mundo):
    assert all(s["tipo_documental"] != "TD-98" for s in mundo.sacar(c.EXTRAER))


def _registro(tipo, id, **datos):
    return Registro(P, tipo, id, 1, datos)


PROCESO = _registro(estados.PROCESO, P, versiones={"modelo_extraccion": 21})
DOCUMENTO = _registro(estados.DOCUMENTO, "OF-001-abc", pdf="file:///s/OF-001-abc.pdf",
                      lectura="file:///s/lectura/OF-001-abc.json", anexo_nativo="file:///s/anexos/OF-001-abc.xlsx")
SEGMENTO = _registro(estados.SEGMENTO, "OF-001-abc-p1-2", entrega="OF-001", pagina_inicio=1, pagina_fin=2,
                     tipo_documental="TD-35", clasificacion_dudosa=False, confianza=None)


def test_excel_lleva_su_anexo_y_tipo_asignado_por_una_persona_va_sin_confianza():
    s = solicitud(PROCESO, DOCUMENTO, SEGMENTO, "0" * 64)
    assert s["anexos"] == ["file:///s/anexos/OF-001-abc.xlsx"]
    assert s["confianza_clasificacion"] is None
    contratos.validar(contratos.EXTRACCION_ENTRADA, s)


def test_solicitud_que_no_cumple_el_contrato_es_un_bug(tmp_path):
    class Almacen:
        def leer(self, uri):
            return json.dumps({"hash_pdf": "0" * 64}).encode()

    malo = Registro(P, estados.SEGMENTO, "x", 1, {**SEGMENTO.datos, "tipo_documental": "TD-99"})
    extraer = Extraer(c.ColaEnMemoria(), Almacen())
    with pytest.raises(SolicitudInvalida, match="tipo_documental: no cumple 'not'"):
        extraer.pedir(PROCESO, DOCUMENTO, malo)


@pytest.mark.libreoffice
def test_excel_real_de_punta_a_punta_lleva_su_anexo(tmp_path):
    """Un Excel entregado por el oferente se normaliza (PDF + original como anexo),
    se clasifica y su solicitud de extracción lleva el Excel original."""
    import io

    import openpyxl

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Ítem", "Descripción", "Valor"])
    for n in range(1, 6):
        hoja.append([n, f"Servicio inventado {n}", n * 1000])
    contenido = io.BytesIO()
    libro.save(contenido)
    escribir(tmp_path, "OF-001/oferta_economica.xlsx", contenido.getvalue())
    (tmp_path / "c.csv").write_text(
        "id_oferente,ruta_origen,pagina_inicio,pagina_fin,tipo_documental,confianza\n"
        "OF-001,oferta_economica.xlsx,,,TD-35,0.97\n", encoding="utf-8")

    mundo = Mundo(tmp_path)
    mundo.abrir()
    assert {r.desenlace for r in mundo.correr(mundo.normalizar)} == {"ok"}
    extraer = Extraer(mundo.cola, mundo.almacen)
    clasificar = Clasificar(mundo.estado, mundo.almacen, ClasificadorFalso(tmp_path / "c.csv"), extraer, mundo.reloj)
    assert {r.desenlace for r in mundo.correr(clasificar)} == {"ok"}

    [s] = mundo.sacar(c.EXTRAER)
    contratos.validar(contratos.EXTRACCION_ENTRADA, s)
    assert s["tipo_documental"] == "TD-35"
    [anexo] = s["anexos"]
    assert anexo.endswith(".xlsx")
    assert mundo.almacen.leer(anexo) == contenido.getvalue(), "el anexo es el Excel original, byte a byte"
    assert s["archivo"]["uri"].endswith(".pdf")
