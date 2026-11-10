"""El borrador de clasificación con un proceso inventado, y su uso en `orquestar`."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest
from orquestador import cli as orquestar
from orquestador.clasificador import ClasificadorFalso

from extraccion.llm import LLMFalso, Respuesta
from fabrica import pdf

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "proponer_clasificacion.py"
spec = importlib.util.spec_from_file_location("proponer_clasificacion", SCRIPT)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


def _respuesta(mensajes):
    """Clasifica por el texto: cada PDF inventado dice qué es en su primera línea."""
    texto = " ".join(p.get("text", "") for p in mensajes[1]["content"] if p.get("type") == "text")
    if "Compilado" in texto:
        r = {"tipo_documental": "TD-03", "confianza": 0.97, "varios_documentos": True,
             "tramos": [{"desde": 1, "hasta": 1, "tipo_documental": "TD-03"}, {"desde": 2, "hasta": 3, "tipo_documental": "TD-16"}],
             "nota": "carta y certificado"}
    elif "Condiciones" in texto:
        r = {"tipo_documental": "TD-01", "confianza": 0.99, "varios_documentos": False, "tramos": [], "nota": "CPC"}
    elif "Certificado" in texto:
        r = {"tipo_documental": "TD-16", "confianza": 0.80, "varios_documentos": False, "tramos": [], "nota": "aportes"}
    else:
        r = {"tipo_documental": "TD-99", "confianza": 0.4, "varios_documentos": False, "tramos": [], "nota": "no se sabe"}
    return Respuesta(json.dumps(r), 1000, 50, "gpt-5.4")


@pytest.fixture
def proceso(tmp_path):
    raiz = tmp_path / "09. PCA SR0000000077 PRUEBA"
    (raiz / "Pliego de condiciones").mkdir(parents=True)
    (raiz / "Pliego de condiciones" / "cpc.pdf").write_bytes(pdf(2, "Condiciones del proceso"))
    (raiz / "Empresa Uno" / "sub").mkdir(parents=True)
    (raiz / "Empresa Uno" / "sub" / "aportes.pdf").write_bytes(pdf(1, "Certificado de aportes"))
    (raiz / "Empresa Uno" / "todo.pdf").write_bytes(pdf(3, "Compilado de la oferta"))
    (raiz / "Empresa Dos").mkdir()
    (raiz / "Empresa Dos" / "largo.pdf").write_bytes(pdf(12, "Anexo largo"))
    (raiz / "Empresa Uno" / "copia.pdf").write_bytes((raiz / "Empresa Uno" / "sub" / "aportes.pdf").read_bytes())
    (raiz / "suelto.pdf").write_bytes(pdf(1, "Otra cosa"))
    return raiz, tmp_path / "trabajo"


def test_propone_y_el_orquestador_la_usa(proceso, capsys):
    raiz, trabajo = proceso
    llm = LLMFalso(responder_con=_respuesta)
    assert pc.main([str(raiz), "--trabajo", str(trabajo), "--max-paginas", "10", "--si-mando-documentos"], cliente=llm) == 0
    salida = capsys.readouterr().out
    for privado in ("Empresa", "Pliego", "aportes", "todo.pdf", "suelto"):
        assert privado not in salida

    assert len(llm.llamadas) == 4, "ni el largo ni la copia exacta se mandan"
    origen = trabajo / "origen" / "SR0000000077"
    assert sorted(p.name for p in origen.iterdir()) == ["OF-001", "OF-002", "PROCESO"]
    assert (origen / "PROCESO" / "suelto.pdf").exists() and (origen / "OF-002" / "sub" / "aportes.pdf").exists()
    with open(trabajo / "oferentes.csv", encoding="utf-8") as f:
        assert [r["carpeta_original"] for r in csv.DictReader(f)] == ["Pliego de condiciones", "Empresa Dos", "Empresa Uno"]

    with open(trabajo / "clasificacion-propuesta.csv", encoding="utf-8") as f:
        filas = {(r["id_oferente"], r["ruta_origen"], r["pagina_inicio"]): r for r in csv.DictReader(f)}
    assert filas[("", "cpc.pdf", "")]["tipo_documental"] == "TD-01" and filas[("", "cpc.pdf", "")]["revisar"] == ""
    assert filas[("OF-002", "copia.pdf", "")]["revisar"] == "SI", "0.80 está bajo el umbral de TD-16"
    assert [filas[("OF-002", "todo.pdf", d)]["tipo_documental"] for d in ("1", "2")] == ["TD-03", "TD-16"]
    assert filas[("OF-002", "todo.pdf", "2")]["pagina_fin"] == "3"
    largo = filas[("OF-001", "largo.pdf", "")]
    assert largo["tipo_documental"] == "TD-99" and largo["revisar"] == "SI" and "10 páginas" in largo["nota"]
    assert not any(k[1] == "sub/aportes.pdf" for k in filas), "la copia exacta (la segunda por ruta) toma lo del original"

    ClasificadorFalso(trabajo / "clasificacion-propuesta.csv")  # el CSV tiene la forma que espera
    corrida = trabajo / "corrida"
    assert orquestar.main(["--origen", str(origen), "--proceso", "SR0000000077", "--clasificacion",
                           str(trabajo / "clasificacion-propuesta.csv"), "--salida", str(corrida)]) == 0
    solicitudes = [json.loads(l) for l in (corrida / "solicitudes-extraccion.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted((s["tipo_documental"], s["paginas"]["desde"], s["paginas"]["hasta"]) for s in solicitudes) == [
        ("TD-01", 1, 2), ("TD-03", 1, 1), ("TD-16", 1, 1), ("TD-16", 2, 3)], "ni TD-99 ni la copia exacta van a extracción"


def test_la_segunda_vez_no_vuelve_a_llamar(proceso, capsys):
    raiz, trabajo = proceso
    argumentos = [str(raiz), "--trabajo", str(trabajo), "--si-mando-documentos"]
    pc.main(argumentos, cliente=LLMFalso(responder_con=_respuesta))
    otro = LLMFalso(responder_con=_respuesta)
    assert pc.main(argumentos, cliente=otro) == 0
    assert otro.llamadas == []
    capsys.readouterr()


def test_tramos_que_no_cubren_el_documento_se_descartan():
    tipos = {"TD-03", "TD-16"}
    r = {"varios_documentos": True, "tramos": [{"desde": 1, "hasta": 1, "tipo_documental": "TD-03"},
                                               {"desde": 2, "hasta": 2, "tipo_documental": "TD-16"}]}
    assert pc.tramos_validos(r, 2, tipos) is not None
    assert pc.tramos_validos(r, 5, tipos) is None
    con_hueco = {**r, "tramos": [r["tramos"][0], {"desde": 3, "hasta": 5, "tipo_documental": "TD-16"}]}
    assert pc.tramos_validos(con_hueco, 5, tipos) is None


def test_sin_carpeta_del_proceso_clara(tmp_path, capsys):
    raiz = tmp_path / "SR0000000001 x"
    for nombre in ("A", "B"):
        (raiz / nombre).mkdir(parents=True)
    with pytest.raises(SystemExit, match="--carpeta-proceso"):
        pc.main([str(raiz), "--trabajo", str(tmp_path / "t"), "--solo-armar"])
