"""`medir-gold` con un gold, documentos y una corrida de lote.py inventados. Sin red."""

import datetime
import json

import openpyxl
import pytest

from conftest import FICHA_V21, respuesta_falsa
from extraccion import medicion as m
from extraccion.ficha import FuenteModeloArchivo
from extraccion.llm import LLMFalso
from fabrica import pdf

CABECERA_TD16 = ["Documento", "Campo", "Propiedad", "Prellenado", "Estado", "Valor en el documento", "Comentario", "id_tecnico"]
CABECERA_TD29 = ["Documento", "Campo", "N°", "Propiedad", "Prellenado", "Estado", "Valor en el documento", "Comentario", "id_tecnico"]


def escribir_gold(ruta, cabecera, filas):
    libro = openpyxl.Workbook()
    libro.active.title = "Instrucciones"
    hoja = libro.create_sheet("Valores")
    hoja.append(cabecera)
    for fila in filas:
        hoja.append(fila)
    libro.save(ruta)


def fila16(documento, id_tecnico, propiedad, prellenado, estado=None, corregido=None):
    return [documento, "campo", propiedad, prellenado, estado, corregido, None, id_tecnico]


# --- El gold ---

def test_lee_el_gold_de_td16(tmp_path):
    ruta = tmp_path / "gold.xlsx"
    escribir_gold(ruta, CABECERA_TD16, [
        fila16("A.pdf", "td16.subtipo", "(valor)", "PJ", "Igual al prellenado"),
        fila16("A.pdf", "td16.firmante", "1. rol", "RF"),
        fila16("A.pdf", "td16.firmante", "2. nombre", "X", "Corregido", "Otra Persona"),
        fila16("A.pdf", "td16.sociedad", "nit", "1", "No aparece en el documento"),
        fila16("A.pdf", "td16.sociedad", "razon_social", "?", "Ilegible"),
        fila16("A.pdf", "td16.version_formato", "(valor)", None),
        fila16("A.pdf", "td16.fecha_certificacion", "(valor)", None, "Igual al prellenado"),
    ])
    filas = m.leer_gold(ruta)
    assert [(f.documento, f.id_tecnico, f.registro, f.propiedad, f.esperado) for f in filas] == [
        ("A", "td16.subtipo", None, "(valor)", "PJ"),
        ("A", "td16.firmante", 1, "rol", "RF"),
        ("A", "td16.firmante", 2, "nombre", "Otra Persona"),
        ("A", "td16.sociedad", None, "nit", None),
        ("A", "td16.fecha_certificacion", None, "(valor)", None),
    ], "Ilegible y sin revisar sin prellenado no cuentan"


def test_lee_el_gold_de_td29_con_columna_de_registro(tmp_path):
    ruta = tmp_path / "gold.xlsx"
    escribir_gold(ruta, CABECERA_TD29, [
        ["B.pdf", "Contratos", 2, "valor", "1.234,5", None, None, None, "td29.contratos"],
        ["B.pdf", "Total", None, "(valor)", "10", None, None, None, "td29.total"],
    ])
    assert [(f.registro, f.propiedad, f.esperado) for f in m.leer_gold(ruta)] == [(2, "valor", "1.234,5"), (None, "(valor)", "10")]


def test_gold_sin_columnas_dice_cuales(tmp_path):
    ruta = tmp_path / "gold.xlsx"
    escribir_gold(ruta, ["Documento", "Campo"], [["A.pdf", "x"]])
    with pytest.raises(m.GoldInvalido, match="Propiedad, Prellenado, id_tecnico"):
        m.leer_gold(ruta)


# --- El acierto ---

@pytest.mark.parametrize("esperado, valor, ok", [
    ("PJ", "pj", True),
    ("Ana María Pérez", "ANA MARIA  PEREZ", True),
    ("1.234,5", 1234.5, True),
    ("$ 1.000.000", "1000000", True),
    ("1,234,567.5", "1.234.567,5", True),
    ("1.234", 1234, True),
    ("12,5", "12.5", True),
    ("10", "10.0", True),
    ("10", "11", False),
    ("900123456-8", "900123456-8", True),
    ("900123456-8", "900123456-9", False),
    (None, None, True),
    (None, "", True),
    (None, "algo", False),
    ("SI", None, False),
    ("al momento de presentar la Oferta", "al momento de presentar la Oferta (si aplica)", True),
    ("corto", "corto y más", False),
    (datetime.datetime(2026, 7, 30), "2026-07-30", True),
])
def test_acierta(esperado, valor, ok):
    assert m.acierta(esperado, valor) is ok


def test_obtenido_por_registro_y_propiedad():
    firmantes = [{"rol": "RF"}, {"rol": "RL"}]
    assert m.obtenido(firmantes, 2, "rol") == "RL"
    assert m.obtenido(firmantes, 3, "rol") is None
    assert m.obtenido({"nit": "1"}, None, "nit") == "1"
    assert m.obtenido("PJ", None, "(valor)") == "PJ"
    assert m.obtenido("PJ", None, "nit") is None


# --- De punta a punta ---

@pytest.fixture
def pruebas(tmp_path):
    """La forma de ~/GEB/Extraccion/Documentos: pruebas/TD-16 con gold y lote, clasificados/TD-16 … con los PDF."""
    documentos = tmp_path / "Documentos"
    carpeta = documentos / "pruebas" / "TD-16"
    pdfs = documentos / "clasificados" / "TD-16 Certificación inventada"
    carpeta.mkdir(parents=True)
    pdfs.mkdir(parents=True)
    for nombre in ("Oferente Uno", "Oferente Dos"):
        (pdfs / f"{nombre}.pdf").write_bytes(pdf(2, nombre))
    (pdfs / "Copia de Uno.pdf").write_bytes((pdfs / "Oferente Uno.pdf").read_bytes())
    escribir_gold(carpeta / "gold_TD-16.xlsx", CABECERA_TD16, [
        # Con la respuesta falsa: PJ acierta, el NIT acierta, el rol acierta y la fecha no.
        *[fila16(d, "td16.subtipo", "(valor)", "PJ") for d in ("Oferente Uno.pdf", "Oferente Dos.pdf", "Copia de Uno.pdf")],
        fila16("Oferente Uno.pdf", "td16.sociedad", "nit", "900123456-8"),
        fila16("Oferente Uno.pdf", "td16.firmante", "1. rol", "RF"),
        fila16("Oferente Uno.pdf", "td16.fecha_certificacion", "(valor)", "2020-01-01", "Corregido", "2026-01-01"),
        fila16("Documento Que No Está.pdf", "td16.subtipo", "(valor)", "PN"),
    ])
    lote = carpeta / "20261029-101208_TD-16_gpt-5.4"
    lote.mkdir()
    for i, (documento, subtipo) in enumerate([("Oferente Uno.pdf", "PJ"), ("Oferente Dos.pdf", "PN"), ("Copia de Uno.pdf", "PJ")]):
        resultados = [{"id_tecnico": "td16.subtipo", "valor": subtipo},
                      {"id_tecnico": "td16.fecha_certificacion", "valor": "2026-01-01"}]
        (lote / f"{i}.json").write_text(json.dumps({
            "documento": documento, "repeticion": 1, "tokens": {"entrada": 20000, "salida": 900}, "segundos": 30.0,
            "error": None, "resultados": resultados,
        }), encoding="utf-8")
    (carpeta / "20261028-150736_TD-16_gpt-5.4").mkdir()  # una corrida más vieja, que no se usa
    return carpeta, tmp_path / "trabajo"


def _llm():
    return LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16")}, modelo="gpt-5.4")


def test_mide_y_compara_solo_con_conteos(pruebas, capsys):
    carpeta, trabajo = pruebas
    llm = _llm()
    codigo = m.main([str(carpeta), "--trabajo", str(trabajo), "--si-mando-documentos"],
                    cliente=llm, fuente=FuenteModeloArchivo(FICHA_V21))
    salida = capsys.readouterr().out
    print(salida)

    assert len(llm.llamadas) == 2, "la copia exacta no se extrae dos veces"
    assert "Gold TD-16: 4 documentos, 7 filas que cuentan." in salida
    assert "Se comparan los 3 documentos que están en todas." in salida
    lineas = {l.split()[0]: l for l in salida.splitlines() if l.startswith("td16.")}
    assert "3/3 (100%)" in lineas["td16.subtipo"] and "2/3 (67%)" in lineas["td16.subtipo"]
    assert "0/1 (0%)" in lineas["td16.fecha_certificacion"] and "1/1 (100%)" in lineas["td16.fecha_certificacion"]
    assert lineas["td16.fecha_certificacion"].endswith("baja")
    assert "td16.sociedad" in lineas and "1/1 (100%)" in lineas["td16.sociedad"]
    assert "20261029-101208_TD-16_gpt-5.4" in salida
    assert "A9: la exactitud baja en 1 campo(s) frente a lote.py." in salida
    assert codigo == 1
    gasto = next(l for l in salida.splitlines() if l.startswith("Servicio: 2 respuestas"))
    assert "campos en revisión" in gasto and "ok 2" in gasto

    for privado in ("Oferente", "Copia", "900123456", "PJ", "Ana", "2026-01-01"):
        assert privado not in salida


def test_la_segunda_vez_no_llama_al_llm(pruebas, capsys):
    carpeta, trabajo = pruebas
    argumentos = [str(carpeta), "--trabajo", str(trabajo), "--si-mando-documentos"]
    m.main(argumentos, cliente=_llm(), fuente=FuenteModeloArchivo(FICHA_V21))
    primera = capsys.readouterr().out
    otro = _llm()
    m.main(argumentos, cliente=otro, fuente=FuenteModeloArchivo(FICHA_V21))
    assert otro.llamadas == []
    m.main([str(carpeta), "--trabajo", str(trabajo), "--solo-comparar"])
    solo = capsys.readouterr().out
    quitar_tiempo = lambda t: [l for l in t.splitlines() if not l.startswith("Tiempo")]
    assert quitar_tiempo(solo)[:12] == quitar_tiempo(primera)[:12]


def test_pregunta_antes_de_mandar(pruebas, capsys):
    carpeta, trabajo = pruebas
    llm = _llm()
    assert m.main([str(carpeta), "--trabajo", str(trabajo)], cliente=llm, fuente=FuenteModeloArchivo(FICHA_V21),
                  entrada=lambda _: "n") == 2
    assert llm.llamadas == []
    assert not trabajo.exists()
    assert "No se mandó nada" in capsys.readouterr().err


def test_sin_lote_solo_el_servicio(pruebas, capsys):
    carpeta, trabajo = pruebas
    for corrida in carpeta.glob("*_TD-16_*"):
        for archivo in corrida.iterdir():
            archivo.unlink()
        corrida.rmdir()
    assert m.main([str(carpeta), "--trabajo", str(trabajo), "--si-mando-documentos"],
                  cliente=_llm(), fuente=FuenteModeloArchivo(FICHA_V21)) == 0
    salida = capsys.readouterr().out
    assert "Sin corrida de lote.py." in salida and "A9: sin corrida de lote.py para comparar." in salida


@pytest.mark.parametrize("cambio, mensaje", [
    (lambda c, t: [str(c), "--trabajo", str(t), "--td", "16"], "TD-NN"),
    (lambda c, t: [str(c), "--trabajo", str(t), "--td", "TD-29"], "gold_TD-29.xlsx"),
    (lambda c, t: [str(c), "--trabajo", str(c)], "fuera de cualquier repositorio"),
    (lambda c, t: [str(c), "--trabajo", str(t), "--documentos", str(t)], "no tiene PDF"),
])
def test_errores_de_uso(pruebas, capsys, cambio, mensaje):
    carpeta, trabajo = pruebas
    if "repositorio" in mensaje:
        (carpeta / ".git").mkdir()
    trabajo.mkdir(exist_ok=True)
    assert m.main(cambio(carpeta, trabajo), cliente=_llm(), fuente=FuenteModeloArchivo(FICHA_V21)) == 2
    assert mensaje in capsys.readouterr().err
