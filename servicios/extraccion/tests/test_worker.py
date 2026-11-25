"""El worker de extracción con la cola en memoria y el LLM falso (T06 de tasks-workers.md)."""

import datetime
import json

import pytest
from mensajeria.cola import EXTRAER, RESULTADOS, ColaEnMemoria
from mensajeria.cola_servicebus import LIMITE_MENSAJE_BYTES
from mensajeria.errores import ErrorTransitorio
from mensajeria.reloj import RelojManual

from conftest import EJEMPLOS, respuesta_falsa
from extraccion import contratos, worker
from extraccion.llm import FallaPasajera, LimiteDeUso, LLMFalso
from extraccion.resultados import Clave
from fabrica import Corrida, pdf


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    for nombre in worker.VARIABLES:
        monkeypatch.setenv(nombre, "valor-inventado")


@pytest.fixture
def corrida(tmp_path):
    return Corrida(tmp_path / "corrida")


@pytest.fixture
def solicitud(corrida):
    (documento,) = corrida.normalizar({"certificado.pdf": pdf(3, "Certificado de aportes")})
    return corrida.solicitud(documento, 1, 3)


@pytest.fixture
def reloj():
    return RelojManual()


@pytest.fixture
def cola(reloj):
    return ColaEnMemoria(reloj)


@pytest.fixture
def llm():
    return LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16")}, modelo="gpt-5.4")


@pytest.fixture
def fabricas(cola, corrida, fuente_modelo, llm):
    return worker.Fabricas(cola=lambda: cola, almacen=lambda: corrida.almacen,
                           fuente=lambda: fuente_modelo, cliente=lambda: llm)


def _correr(fabricas, *argumentos):
    return worker.main(["--hilos", "1", *argumentos], fabricas=fabricas)


def _resultados(cola):
    sobres = []
    while (m := cola.recibir(RESULTADOS)) is not None:
        sobres.append(m.cuerpo)
        cola.completar(m)
    return sobres


def test_extrae_y_publica_el_resultado(fabricas, cola, solicitud, corrida, llm):
    cola.publicar(EXTRAER, solicitud)
    assert _correr(fabricas) == 0

    [sobre] = _resultados(cola)
    assert contratos.errores(contratos.SALIDA, sobre) == []
    assert (sobre["estado"], sobre["id_segmento"]) == ("ok", solicitud["id_segmento"])
    clave = Clave.de(solicitud)
    guardado = f"extraccion/{clave.id_proceso}/{clave.entrega}/{clave.nombre}.json"
    assert corrida.almacen.existe(corrida.almacen.uri(guardado))
    assert len(llm.llamadas) == 1


def test_un_mensaje_repetido_publica_lo_guardado_sin_llamar_otra_vez(fabricas, cola, solicitud, llm):
    cola.publicar(EXTRAER, solicitud)
    cola.publicar(EXTRAER, solicitud)
    assert _correr(fabricas) == 0

    primero, segundo = _resultados(cola)
    assert len(llm.llamadas) == 1
    assert segundo["ejecucion"]["desde_cache"] is True
    assert segundo["ejecucion"]["id"] == primero["ejecucion"]["id"]


def test_una_falla_pasajera_la_reintenta_la_cola_sin_publicar(fabricas, cola, solicitud, llm):
    llm.programar(FallaPasajera("se cayó"))
    cola.publicar(EXTRAER, solicitud)
    assert _correr(fabricas) == 0

    assert _resultados(cola) == []
    assert len(llm.llamadas) == 1, "Llamador ya no repite las fallas pasajeras"
    assert cola.pendientes(EXTRAER) == 1


def test_un_429_se_reprograma_con_la_espera_pedida(fabricas, cola, solicitud, llm, reloj):
    llm.programar(LimiteDeUso(espera=42))
    cola.publicar(EXTRAER, solicitud)
    assert _correr(fabricas) == 0

    assert cola.proxima_visible() == reloj.ahora() + datetime.timedelta(seconds=42)
    reloj.adelantar(42)
    assert _correr(fabricas) == 0
    [sobre] = _resultados(cola)
    assert sobre["estado"] == "ok"


def test_agotados_los_reintentos_publica_el_error_de_proceso(fabricas, cola, solicitud, llm, reloj):
    llm.programar(*[FallaPasajera("se cayó")] * 4)
    cola.publicar(EXTRAER, solicitud)
    for _ in range(4):
        assert _correr(fabricas) == 0
        reloj.adelantar(10_000)

    [sobre] = _resultados(cola)
    assert contratos.errores(contratos.SALIDA, sobre) == []
    assert sobre["estado"] == "error_proceso"
    assert sobre["error"]["codigo"] == "LLM_NO_DISPONIBLE"
    assert len(cola.errores(EXTRAER)) == 1


def test_un_error_que_no_se_arregla_repitiendo_se_publica_enseguida(fabricas, cola, solicitud):
    cola.publicar(EXTRAER, {**solicitud, "version_modelo": 999})
    assert _correr(fabricas) == 0
    [sobre] = _resultados(cola)
    assert (sobre["estado"], sobre["error"]["codigo"]) == ("error_proceso", "FICHA_NO_ENCONTRADA")
    assert sobre["error"]["reintentable"] is False
    assert cola.errores(EXTRAER) == []


def test_un_bug_publica_una_falla_interna_y_va_a_errores(fabricas, cola, solicitud, llm):
    llm.programar(KeyError("bug"))
    cola.publicar(EXTRAER, solicitud)
    assert _correr(fabricas) == 0
    [sobre] = _resultados(cola)
    assert (sobre["estado"], sobre["error"]["codigo"]) == ("error_proceso", "FALLA_INTERNA")
    assert len(cola.errores(EXTRAER)) == 1


def test_una_solicitud_invalida_va_a_errores_sin_publicar(fabricas, cola, solicitud):
    cola.publicar(EXTRAER, {**solicitud, "paginas": "todas"})
    assert _correr(fabricas) == 0
    assert _resultados(cola) == []
    [error] = cola.errores(EXTRAER)
    assert error.motivo.startswith("Rechazado: La solicitud no cumple el contrato")


def test_sin_variables_sale_con_2_sin_tocar_la_cola(fabricas, cola, solicitud, monkeypatch, capsys):
    monkeypatch.delenv("EXTRACCION_MODELO")
    cola.publicar(EXTRAER, solicitud)
    assert _correr(fabricas) == 2
    assert "EXTRACCION_MODELO" in capsys.readouterr().err
    assert cola.pendientes(EXTRAER) == 1


def test_los_registros_de_la_cola_salen_en_json(fabricas, cola, solicitud, capsys):
    cola.publicar(EXTRAER, solicitud)
    assert _correr(fabricas) == 0
    lineas = [json.loads(l) for l in capsys.readouterr().err.splitlines()]
    assert any(l["modulo"] == "mensajeria.worker" for l in lineas)


def test_un_429_sin_espera_pedida_se_reprograma_con_la_de_por_defecto(fabricas, cola, solicitud, llm, reloj):
    llm.programar(LimiteDeUso(espera=None))
    cola.publicar(EXTRAER, solicitud)
    assert _correr(fabricas) == 0
    espera = worker.parametros()["llamada"]["espera_limite_uso_s"]
    assert cola.proxima_visible() == reloj.ahora() + datetime.timedelta(seconds=espera)


def test_si_publicar_falla_en_todos_los_intentos_se_publica_el_resultado_y_no_una_falla(
        fabricas, cola, solicitud, llm, reloj, monkeypatch):
    original = cola.publicar
    fallas = []

    def publicar(nombre, cuerpo, *args, **kwargs):
        if nombre == RESULTADOS and len(fallas) < 4:
            fallas.append(1)
            raise ErrorTransitorio("Service Bus no respondió")
        return original(nombre, cuerpo, *args, **kwargs)

    monkeypatch.setattr(cola, "publicar", publicar)
    cola.publicar(EXTRAER, solicitud)
    for _ in range(4):
        assert _correr(fabricas) == 0
        reloj.adelantar(10_000)

    [sobre] = _resultados(cola)
    assert sobre["estado"] == "ok"
    assert len(llm.llamadas) == 1, "los reintentos usan lo guardado"


def test_el_sobre_de_error_lleva_lo_que_gasto_el_llm(solicitud):
    from extraccion.llamada import LlamadaFallida
    from extraccion.reloj import RelojManual as RelojExtraccion
    from extraccion.servicio import resultado_de_error

    class Servicio:
        reloj = RelojExtraccion()
        llamador = type("L", (), {"modelo": "gpt-5.4"})()

        @staticmethod
        def nuevo_id():
            return "00000000-0000-4000-8000-000000000000"

    error = LlamadaFallida("RESPUESTA_INVALIDA", "sin forma", 2, 900, 120, "gpt-5.4")
    sobre = resultado_de_error(solicitud, Servicio, error)
    assert contratos.errores(contratos.SALIDA, sobre) == []
    ejecucion = sobre["ejecucion"]
    assert (ejecucion["tokens_entrada"], ejecucion["tokens_salida"], ejecucion["reintentos"]) == (900, 120, 2)


def test_las_fabricas_reales_no_leen_el_env_y_exigen_la_clave_del_mcp(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("MCP_URL=https://mcp.invalido\nMCP_API_KEY=inventada\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXTRACCION_MODELO", "mcp")
    monkeypatch.delenv("MCP_URL", raising=False)
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    with pytest.raises(worker.ErrorDeConfiguracion) as error:
        worker._fabricas_reales().fuente()
    assert str(error.value) == "Faltan variables de entorno: MCP_URL, MCP_API_KEY"


def test_un_deployment_rechazado_no_se_nombra(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://cuentafalsa.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "inventada")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "despliegue-secreto-mini")
    with pytest.raises(worker.ErrorDeConfiguracion) as error:
        worker._fabricas_reales().cliente()
    assert "despliegue-secreto" not in str(error.value)


@pytest.mark.parametrize("ejemplo", sorted(EJEMPLOS.glob("salida_*.json")), ids=lambda r: r.stem)
def test_los_sobres_de_ejemplo_caben_en_un_mensaje(ejemplo):
    tamano = len(json.dumps(json.loads(ejemplo.read_text(encoding="utf-8")), ensure_ascii=False).encode("utf-8"))
    assert tamano < LIMITE_MENSAJE_BYTES / 10


def test_el_worker_no_depende_del_orquestador():
    import subprocess
    import sys

    programa = "import sys\nsys.modules['orquestador'] = None\nimport extraccion.worker\n"
    ejecucion = subprocess.run([sys.executable, "-c", programa], capture_output=True, text=True)
    assert ejecucion.returncode == 0, ejecucion.stderr
