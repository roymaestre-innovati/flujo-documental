"""El comando `extraer`, y la prueba de punta a punta (criterio A8).

Un proceso inventado se normaliza, las solicitudes se arman con
`orquestador.extraer.solicitud` (como las publicaría el orquestador) y se corre el
comando dos veces: la segunda no llama al LLM.
"""

import json

import pytest
from orquestador.estado import Registro
from orquestador.extraer import solicitud as solicitud_del_orquestador

from conftest import AQUI, FICHA_V21, respuesta_falsa
from extraccion import cli, contratos
from extraccion.llm import FallaPasajera, LLMFalso
from extraccion.reloj import RelojManual
from fabrica import PROCESO, Corrida, pdf

RESPUESTAS = AQUI / "respuestas"


def _registro(tipo: str, id: str, datos: dict) -> Registro:
    return Registro(id_proceso=PROCESO, tipo=tipo, id=id, version=1, datos=datos)


def _solicitudes(corrida: Corrida, documento: dict, entrega: str, segmentos) -> list[dict]:
    proceso = _registro("proceso", PROCESO, {"versiones": {"modelo_extraccion": 21}})
    doc = _registro("documento", documento["id_documento"], {
        "pdf": documento["pdf"], "lectura": documento["lectura"], "anexo_nativo": documento["anexo_nativo"],
    })
    hash_pdf = corrida.lectura(documento)["hash_pdf"]
    salida = []
    for desde, hasta, td in segmentos:
        segmento = _registro("segmento", f"{documento['id_documento']}-p{desde}-{hasta}", {
            "entrega": entrega, "pagina_inicio": desde, "pagina_fin": hasta, "tipo_documental": td,
            "clasificacion_dudosa": False, "confianza": 0.95,
        })
        salida.append(solicitud_del_orquestador(proceso, doc, segmento, hash_pdf))
    return salida


@pytest.fixture
def proceso(tmp_path):
    """Una corrida con un documento del proceso y uno de un oferente, y su jsonl."""
    corrida = Corrida(tmp_path / "corrida")
    (del_proceso,) = corrida.normalizar({"pliego.pdf": pdf(2, "Pliego inventado")}, id_oferente=None)
    (del_oferente,) = corrida.normalizar({"carpeta.pdf": pdf(5, "Carpeta inventada")}, id_oferente="OF-001")
    solicitudes = [
        *_solicitudes(corrida, del_proceso, "PROCESO", [(1, 2, "TD-16")]),
        *_solicitudes(corrida, del_oferente, "OF-001", [(1, 2, "TD-16"), (3, 5, "TD-29"), (4, 9, "TD-16")]),
    ]
    for s in solicitudes:
        assert contratos.errores(contratos.ENTRADA, s) == []
    jsonl = corrida.raiz / "solicitudes-extraccion.jsonl"
    jsonl.write_text("".join(json.dumps(s) + "\n" for s in solicitudes), encoding="utf-8")
    return corrida, jsonl, solicitudes


def _argumentos(corrida, jsonl, *extra):
    return [str(jsonl), "--corrida", str(corrida.raiz), "--modelo", f"archivo:{FICHA_V21}", *extra]


def _resumen(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_punta_a_punta_dos_corridas(proceso, capsys):
    corrida, jsonl, solicitudes = proceso
    argumentos = _argumentos(corrida, jsonl, "--llm", "falso", "--respuestas", str(RESPUESTAS))

    assert cli.main(argumentos) == 0
    primera = _resumen(capsys)
    assert primera["solicitudes"] == 4
    assert primera["por_estado"] == {"error_entrada": 1, "ok": 3}
    assert primera["errores"] == {"PAGINAS_FUERA_DE_RANGO": 1}
    assert primera["repetidos"] == 0
    assert primera["tokens_entrada"] > 0

    archivos = sorted((corrida.raiz / "extraccion").rglob("*.json"))
    assert len(archivos) == 4
    for archivo in archivos:
        assert contratos.errores(contratos.SALIDA, json.loads(archivo.read_text(encoding="utf-8"))) == []
    assert {a.parent.name for a in archivos} == {"PROCESO", "OF-001"}
    assert {a.parent.parent.name for a in archivos} == {PROCESO}

    assert cli.main(argumentos) == 0
    segunda = _resumen(capsys)
    assert segunda["repetidos"] == 4
    assert segunda["tokens_entrada"] == 0
    assert segunda["por_estado"] == primera["por_estado"]
    assert sorted((corrida.raiz / "extraccion").rglob("*.json")) == archivos


def test_segunda_corrida_sin_llamadas_al_llm(proceso, capsys):
    corrida, jsonl, _ = proceso
    llm = LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16"), "TD-29": respuesta_falsa("TD-29")})
    cli.main(_argumentos(corrida, jsonl), cliente=llm)
    assert len(llm.llamadas) == 3
    cli.main(_argumentos(corrida, jsonl), cliente=llm)
    assert len(llm.llamadas) == 3
    cli.main(_argumentos(corrida, jsonl, "--forzar"), cliente=llm)
    assert len(llm.llamadas) == 6
    capsys.readouterr()


def test_solo_un_segmento(proceso, capsys):
    corrida, jsonl, solicitudes = proceso
    llm = LLMFalso(por_tipo={"TD-29": respuesta_falsa("TD-29")})
    id_segmento = solicitudes[2]["id_segmento"]
    assert cli.main(_argumentos(corrida, jsonl, "--solo", id_segmento), cliente=llm) == 0
    assert _resumen(capsys)["solicitudes"] == 1
    assert len(llm.llamadas) == 1


def test_una_linea_mala_no_frena_las_demas(proceso, capsys):
    corrida, jsonl, solicitudes = proceso
    mala = {**solicitudes[0], "tipo_documental": "TD-99"}
    jsonl.write_text(jsonl.read_text(encoding="utf-8") + "no es JSON\n" + json.dumps(mala) + "\n", encoding="utf-8")
    llm = LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16"), "TD-29": respuesta_falsa("TD-29")})
    assert cli.main(_argumentos(corrida, jsonl), cliente=llm) == 1
    resumen = _resumen(capsys)
    assert resumen["lineas_ilegibles"] == 1
    assert resumen["solicitudes_invalidas"] == 1
    assert sum(resumen["por_estado"].values()) == 4


def test_falla_tecnica_sale_con_1_y_no_se_guarda(proceso, capsys):
    corrida, jsonl, solicitudes = proceso
    llm = LLMFalso()
    llm.programar(*[FallaPasajera()] * 4)
    argumentos = _argumentos(corrida, jsonl, "--solo", solicitudes[0]["id_segmento"])
    reloj = RelojManual()
    assert cli.main(argumentos, cliente=llm, reloj=reloj) == 1
    assert reloj.esperas == [2, 4, 8]
    resumen = _resumen(capsys)
    assert resumen["por_estado"] == {"error_proceso": 1}
    assert resumen["errores"] == {"LLM_NO_DISPONIBLE": 1}
    assert not list((corrida.raiz / "extraccion").rglob("*.json"))


def test_azure_pregunta_antes_de_mandar(proceso, capsys):
    corrida, jsonl, _ = proceso
    llm = LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16"), "TD-29": respuesta_falsa("TD-29")})
    preguntas = []

    def responde(texto):
        def entrada(pregunta):
            preguntas.append(pregunta)
            return texto
        return entrada

    assert cli.main(_argumentos(corrida, jsonl, "--llm", "azure"), cliente=llm, entrada=responde("")) == 2
    assert preguntas == [cli.PREGUNTA]
    assert llm.llamadas == []
    assert "No se mandó nada" in capsys.readouterr().err

    assert cli.main(_argumentos(corrida, jsonl, "--llm", "azure"), cliente=llm, entrada=responde("s")) == 0
    assert len(llm.llamadas) == 3
    capsys.readouterr()


def test_azure_sin_preguntar_con_la_marca(proceso, capsys):
    corrida, jsonl, _ = proceso
    llm = LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16"), "TD-29": respuesta_falsa("TD-29")})

    def no_preguntar(_):
        raise AssertionError("no debía preguntar")

    argumentos = _argumentos(corrida, jsonl, "--llm", "azure", "--si-mando-documentos")
    assert cli.main(argumentos, cliente=llm, entrada=no_preguntar) == 0
    capsys.readouterr()


def test_azure_sin_configuracion_no_muestra_secretos(proceso, capsys, monkeypatch, tmp_path):
    corrida, jsonl, _ = proceso
    for variable in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secreto-123")
    monkeypatch.chdir(tmp_path)
    assert cli.main(_argumentos(corrida, jsonl, "--llm", "azure", "--si-mando-documentos")) == 2
    error = capsys.readouterr().err
    assert "AZURE_OPENAI_ENDPOINT" in error
    assert "secreto-123" not in error


def test_azure_lee_el_env_y_rechaza_mini(proceso, capsys, monkeypatch, tmp_path):
    corrida, jsonl, _ = proceso
    for variable in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"):
        monkeypatch.delenv(variable, raising=False)
    (tmp_path / ".env").write_text(
        "AZURE_OPENAI_ENDPOINT=https://r.openai.azure.com\nAZURE_OPENAI_API_KEY=k\nAZURE_OPENAI_DEPLOYMENT=gpt-5.4-mini\n",
        encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert cli.main(_argumentos(corrida, jsonl, "--llm", "azure", "--si-mando-documentos")) == 2
    assert "mini" in capsys.readouterr().err


@pytest.mark.parametrize("cambio, mensaje", [
    (lambda a: a[:3] + ["--modelo", "mcp"], "todavía no"),
    (lambda a: a[:3] + ["--modelo", "otra:cosa"], "archivo:<ficha.json>"),
    (lambda a: a[:3] + ["--modelo", "archivo:/no/existe.json"], "No existe"),
    (lambda a: a + ["--concurrencia", "0"], "--concurrencia"),
    (lambda a: a + ["--llm", "falso"], "--respuestas"),
])
def test_errores_de_uso(proceso, capsys, cambio, mensaje):
    corrida, jsonl, _ = proceso
    assert cli.main(cambio(_argumentos(corrida, jsonl))) == 2
    assert mensaje in capsys.readouterr().err


def test_corrida_sin_almacen(tmp_path, capsys):
    jsonl = tmp_path / "s.jsonl"
    jsonl.write_text("", encoding="utf-8")
    assert cli.main([str(jsonl), "--corrida", str(tmp_path), "--modelo", f"archivo:{FICHA_V21}"]) == 2
    assert "almacen" in capsys.readouterr().err


def test_corrida_dentro_de_un_repositorio(proceso, capsys):
    corrida, jsonl, _ = proceso
    (corrida.raiz / ".git").mkdir()
    assert cli.main(_argumentos(corrida, jsonl, "--llm", "falso", "--respuestas", str(RESPUESTAS))) == 2
    assert "repositorio" in capsys.readouterr().err
