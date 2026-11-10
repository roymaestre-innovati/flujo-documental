"""`extraer_segmento` con documentos inventados, el LLM falso y el reloj manual."""

import io
import json
import logging

import pytest

from conftest import respuesta_falsa
from extraccion import CONTRATO, VERSION, contratos
from extraccion.entrada import SolicitudInvalida
from extraccion.llamada import Llamador
from extraccion.llm import FallaPasajera, LLMFalso, Respuesta
from extraccion.mensaje import VERSION_PROMPT
from extraccion.registros import configurar
from extraccion.reloj import RelojManual
from extraccion.resultados import Clave, ResultadosEnCarpeta
from extraccion.servicio import Servicio, extraer_segmento
from fabrica import Corrida, pdf


@pytest.fixture
def corrida(tmp_path):
    return Corrida(tmp_path / "corrida")


@pytest.fixture
def documento(corrida):
    (documento,) = corrida.normalizar({"certificado.pdf": pdf(3, "Certificado de aportes")})
    return documento


@pytest.fixture
def llm():
    return LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16"), "TD-29": respuesta_falsa("TD-29")},
                    modelo="gpt-5.4")


@pytest.fixture
def servicio(corrida, fuente_modelo, llm, tmp_path):
    reloj = RelojManual()
    ids = iter(f"ej-{n:012d}" for n in range(1, 100))
    return Servicio(almacen=corrida.almacen, fuente=fuente_modelo, llamador=Llamador(llm, reloj),
                    resultados=ResultadosEnCarpeta(tmp_path / "extraccion"), reloj=reloj,
                    nuevo_id=lambda: next(ids))


def test_extrae_un_segmento(corrida, documento, servicio, llm):
    resultado = extraer_segmento(corrida.solicitud(documento, 1, 3), servicio)

    assert contratos.errores(contratos.SALIDA, resultado) == []
    assert resultado["contrato"] == CONTRATO
    assert resultado["estado"] == "ok"
    assert resultado["resultados"]
    assert resultado["ejecucion"] == {
        "id": "ej-000000000001", "inicio": "2026-01-01T00:00:00+00:00", "duracion_ms": 0,
        "tokens_entrada": resultado["ejecucion"]["tokens_entrada"],
        "tokens_salida": resultado["ejecucion"]["tokens_salida"],
        "modelo_llm": "gpt-5.4", "version_prompt": VERSION_PROMPT, "version_unidad": VERSION,
        "reintentos": 0, "desde_cache": False,
    }
    assert resultado["ejecucion"]["tokens_entrada"] > 0
    assert len(llm.llamadas) == 1


def test_la_misma_solicitud_no_vuelve_a_llamar(corrida, documento, servicio, llm):
    solicitud = corrida.solicitud(documento, 1, 3)
    primero = extraer_segmento(solicitud, servicio)
    segundo = extraer_segmento(solicitud, servicio)

    assert len(llm.llamadas) == 1
    assert segundo["ejecucion"]["desde_cache"] is True
    assert segundo["ejecucion"]["id"] == primero["ejecucion"]["id"]
    assert {**segundo, "ejecucion": None} == {**primero, "ejecucion": None}
    guardado = servicio.resultados.buscar(Clave.de(solicitud))
    assert guardado["ejecucion"]["desde_cache"] is False, "lo guardado no cambia"


def test_otro_segmento_u_otra_version_son_otra_clave(corrida, documento, servicio, llm):
    extraer_segmento(corrida.solicitud(documento, 1, 3), servicio)
    extraer_segmento(corrida.solicitud(documento, 1, 2), servicio)
    extraer_segmento(corrida.solicitud(documento, 1, 3, tipo_documental="TD-29"), servicio)
    assert len(llm.llamadas) == 3


def test_forzar_reproceso_extrae_otra_vez_y_guarda_el_anterior(corrida, documento, servicio, llm):
    solicitud = corrida.solicitud(documento, 1, 3)
    primero = extraer_segmento(solicitud, servicio)
    segundo = extraer_segmento({**solicitud, "forzar_reproceso": True}, servicio)

    assert len(llm.llamadas) == 2
    assert segundo["ejecucion"]["desde_cache"] is False
    assert segundo["ejecucion"]["id"] != primero["ejecucion"]["id"]
    ruta = servicio.resultados.ruta(Clave.de(solicitud))
    anterior = ruta.with_name(f"{Clave.de(solicitud).nombre}.anterior-{primero['ejecucion']['id']}.json")
    assert json.loads(anterior.read_text(encoding="utf-8")) == primero
    assert servicio.resultados.buscar(Clave.de(solicitud)) == segundo


def test_error_de_entrada_se_guarda(corrida, documento, servicio, llm):
    solicitud = corrida.solicitud(documento, 2, 9)
    resultado = extraer_segmento(solicitud, servicio)

    assert resultado["estado"] == "error_entrada"
    assert resultado["error"]["codigo"] == "PAGINAS_FUERA_DE_RANGO"
    assert contratos.errores(contratos.SALIDA, resultado) == []
    assert resultado["ejecucion"]["modelo_llm"] == "gpt-5.4"
    assert llm.llamadas == []
    assert extraer_segmento(solicitud, servicio)["ejecucion"]["desde_cache"] is True


def test_error_de_proceso_no_se_guarda(corrida, documento, servicio, llm):
    solicitud = corrida.solicitud(documento, 1, 3)
    llm.programar(*[FallaPasajera()] * 4)
    resultado = extraer_segmento(solicitud, servicio)

    assert resultado["estado"] == "error_proceso"
    assert resultado["error"] == {"codigo": "LLM_NO_DISPONIBLE", "reintentable": True,
                                  "mensaje": resultado["error"]["mensaje"]}
    assert resultado["ejecucion"]["reintentos"] == 3
    assert contratos.errores(contratos.SALIDA, resultado) == []
    assert servicio.resultados.buscar(Clave.de(solicitud)) is None

    otra_vez = extraer_segmento(solicitud, servicio)
    assert otra_vez["estado"] == "ok"
    assert len(llm.llamadas) == 5


def test_respuesta_invalida_agotada_lleva_lo_gastado(corrida, documento, servicio, llm):
    llm.programar(*[Respuesta("no es JSON", 1000, 20, "gpt-5.4-2026")] * 3)
    resultado = extraer_segmento(corrida.solicitud(documento, 1, 3), servicio)

    assert resultado["estado"] == "error_proceso"
    assert resultado["error"]["codigo"] == "RESPUESTA_INVALIDA"
    ejecucion = resultado["ejecucion"]
    assert (ejecucion["tokens_entrada"], ejecucion["tokens_salida"]) == (3000, 60)
    assert ejecucion["reintentos"] == 2
    assert ejecucion["modelo_llm"] == "gpt-5.4-2026"


def test_ficha_que_no_existe(corrida, documento, servicio, llm):
    resultado = extraer_segmento(corrida.solicitud(documento, 1, 3, version_modelo=99), servicio)
    assert resultado["estado"] == "error_proceso"
    assert resultado["error"]["codigo"] == "FICHA_NO_ENCONTRADA"
    assert resultado["error"]["reintentable"] is False
    assert llm.llamadas == []


def test_archivo_que_falta_es_reintentable_y_no_se_guarda(corrida, documento, servicio):
    solicitud = corrida.solicitud(documento, 1, 3)
    solicitud["lectura"] = solicitud["lectura"].rsplit("/", 1)[0] + "/no-existe.json"
    resultado = extraer_segmento(solicitud, servicio)
    assert resultado["estado"] == "error_proceso"
    assert resultado["error"]["codigo"] == "ARCHIVO_NO_ENCONTRADO"
    assert servicio.resultados.buscar(Clave.de(solicitud)) is None


def test_solicitud_invalida_es_un_bug(corrida, documento, servicio):
    with pytest.raises(SolicitudInvalida):
        extraer_segmento(corrida.solicitud(documento, 1, 3, tipo_documental="TD-99"), servicio)


def test_registros_sin_datos_del_documento(corrida, documento, servicio):
    salida = io.StringIO()
    configurar(logging.INFO, salida)
    try:
        solicitud = corrida.solicitud(documento, 1, 3)
        resultado = extraer_segmento(solicitud, servicio)
        extraer_segmento(solicitud, servicio)
    finally:
        configurar(logging.WARNING)

    lineas = [json.loads(l) for l in salida.getvalue().splitlines()]
    extraido, repetido = [l for l in lineas if l["modulo"] == "extraccion"]
    assert extraido["mensaje"] == "Segmento extraído"
    assert extraido["id_segmento"] == solicitud["id_segmento"]
    assert extraido["id_documento"] == solicitud["id_segmento"]
    assert extraido["estado"] == "ok"
    assert extraido["campos"] == len(resultado["resultados"])
    assert extraido["campos_en_revision"] == len(resultado["campos_en_revision"])
    assert sum(extraido["motivos"].values()) == sum(len(r["motivos"]) for r in resultado["resultados"])
    assert repetido["mensaje"] == "Segmento repetido" and repetido["desde_cache"] is True

    texto = salida.getvalue()
    for r in resultado["resultados"]:
        for cita in r["evidencia"]:
            assert cita["cita"] not in texto
    assert "certificado" not in texto.lower()
    assert "Certificado de aportes" not in texto
