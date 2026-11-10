"""La ficha pedida al MCP, con un servidor MCP falso en memoria (sin red)."""

import json

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from conftest import FICHA_V21, cargar, respuesta_falsa
from extraccion.ficha import FichaNoEncontrada, FuenteModeloArchivo
from extraccion.ficha_mcp import ErrorDelMCP, FuenteModeloMCP, FuenteNoDisponible, main
from extraccion.llamada import Llamador
from extraccion.llm import LLMFalso
from extraccion.reloj import RelojManual
from extraccion.resultados import Clave, ResultadosEnCarpeta
from extraccion.servicio import Servicio, extraer_segmento
from fabrica import Corrida, pdf

MODELO = cargar(FICHA_V21)


def servidor_falso(vigente: int = 21, describir_con_version: bool = False, error: str | None = None):
    """Un MCP con la forma del modelo semántico: una sola versión publicada (la del doble), con `vigente` como la que
    da `describir_modelo` sin versión. Guarda cada llamada con sus argumentos."""
    llamadas: list[tuple[str, dict]] = []
    servidor = MCPServer(name="modelo-semantico-falso")
    descripcion = {k: v for k, v in MODELO.items() if k != "elementos"}

    def revisar(modelo: str, version: int | None) -> None:
        if error:
            raise ToolError(error)
        if modelo != "extraccion_documental":
            raise ToolError(f"No existe el modelo {modelo!r}. Modelos disponibles: extraccion_documental.")
        if version is not None and version != MODELO["version"]:
            raise ToolError(f"El modelo {modelo!r} no tiene la versión {version}. Versiones publicadas: 21.")

    if describir_con_version:
        @servidor.tool()
        async def describir_modelo(modelo: str, version: int | None = None) -> str:
            llamadas.append(("describir_modelo", {"modelo": modelo, "version": version}))
            revisar(modelo, version)
            return json.dumps({**descripcion, "version": version or vigente})
    else:
        @servidor.tool()
        async def describir_modelo(modelo: str) -> str:
            llamadas.append(("describir_modelo", {"modelo": modelo}))
            revisar(modelo, None)
            return json.dumps({**descripcion, "version": vigente})

    @servidor.tool()
    async def obtener_seccion(modelo: str, seccion: str | None = None, version: int | None = None) -> str:
        llamadas.append(("obtener_seccion", {"modelo": modelo, "seccion": seccion, "version": version}))
        revisar(modelo, version)
        if seccion not in {s["id"] for s in MODELO["secciones"]}:
            raise ToolError(f"La sección {seccion!r} no existe en {modelo!r}.")
        elementos = [e for e in MODELO["elementos"] if e["seccion"] == seccion]
        return json.dumps({"modelo": modelo, "version": version or vigente, "seccion": seccion, "elementos": elementos})

    return servidor, llamadas


def fuente(servidor) -> FuenteModeloMCP:
    return FuenteModeloMCP(lambda: servidor)


def test_da_la_misma_ficha_que_el_archivo():
    servidor, llamadas = servidor_falso()
    del_mcp = fuente(servidor).ficha(21, "TD-16")
    assert del_mcp == FuenteModeloArchivo(FICHA_V21).ficha(21, "TD-16")
    assert del_mcp.td_probado is True
    assert llamadas == [
        ("describir_modelo", {"modelo": "extraccion_documental"}),
        ("obtener_seccion", {"modelo": "extraccion_documental", "seccion": "TD-16", "version": 21}),
    ]


def test_guarda_en_memoria_por_version_y_td():
    servidor, llamadas = servidor_falso()
    sujeto = fuente(servidor)
    sujeto.ficha(21, "TD-16")
    sujeto.ficha(21, "TD-16")
    sujeto.ficha(21, "TD-29")
    assert [nombre for nombre, _ in llamadas] == ["describir_modelo", "obtener_seccion", "obtener_seccion"]


def test_version_que_no_existe():
    servidor, _ = servidor_falso(describir_con_version=True)
    with pytest.raises(FichaNoEncontrada, match="no tiene la versión 99"):
        fuente(servidor).ficha(99, "TD-16")


def test_seccion_que_no_existe():
    servidor, llamadas = servidor_falso()
    with pytest.raises(FichaNoEncontrada, match="TD-77"):
        fuente(servidor).ficha(21, "TD-77")
    assert [nombre for nombre, _ in llamadas] == ["describir_modelo"]


def test_sin_version_en_describir_y_la_vigente_es_otra():
    # La guía que daría el servidor es la de la v22: no sirve para extraer con la v21 (principio 7).
    servidor, llamadas = servidor_falso(vigente=22)
    with pytest.raises(FichaNoEncontrada, match="solo da la guía de la versión vigente"):
        fuente(servidor).ficha(21, "TD-16")
    assert [nombre for nombre, _ in llamadas] == ["describir_modelo"]


def test_si_describir_acepta_version_se_le_pasa():
    servidor, llamadas = servidor_falso(vigente=22, describir_con_version=True)
    ficha = fuente(servidor).ficha(21, "TD-16")
    assert ficha.version == 21
    assert llamadas[0] == ("describir_modelo", {"modelo": "extraccion_documental", "version": 21})


def test_al_mcp_solo_van_modelo_seccion_y_version():
    servidor, llamadas = servidor_falso()
    fuente(servidor).ficha(21, "TD-29")
    assert {clave for _, argumentos in llamadas for clave in argumentos} <= {"modelo", "seccion", "version"}


def test_otro_error_de_la_tool_es_de_configuracion():
    servidor, _ = servidor_falso(error="El proyecto 'x' no está habilitado en este servidor.")
    with pytest.raises(ErrorDelMCP, match="no está habilitado"):
        fuente(servidor).ficha(21, "TD-16")


def test_servidor_que_no_responde():
    # Un puerto local cerrado: falla al conectar, sin salir a la red.
    sujeto = FuenteModeloMCP.desde_entorno({"MCP_URL": "http://127.0.0.1:9/mcp"})
    with pytest.raises(FuenteNoDisponible):
        sujeto.ficha(21, "TD-16")


def test_desde_entorno_sin_url():
    with pytest.raises(ValueError, match="MCP_URL"):
        FuenteModeloMCP.desde_entorno({"MCP_API_KEY": "secreto-123"})


def test_la_extraccion_con_mcp_caido_es_reintentable_y_no_se_guarda(tmp_path):
    corrida = Corrida(tmp_path / "corrida")
    (documento,) = corrida.normalizar({"certificado.pdf": pdf(3)})
    reloj = RelojManual()
    llm = LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16")})
    servicio = Servicio(almacen=corrida.almacen, fuente=FuenteModeloMCP.desde_entorno({"MCP_URL": "http://127.0.0.1:9/mcp"}),
                        llamador=Llamador(llm, reloj), resultados=ResultadosEnCarpeta(tmp_path / "extraccion"), reloj=reloj)
    solicitud = corrida.solicitud(documento, 1, 3)
    resultado = extraer_segmento(solicitud, servicio)
    assert resultado["estado"] == "error_proceso"
    assert resultado["error"]["codigo"] == "MODELO_NO_DISPONIBLE"
    assert resultado["error"]["reintentable"] is True
    assert llm.llamadas == []
    assert servicio.resultados.buscar(Clave.de(solicitud)) is None


def test_extraccion_con_la_ficha_del_mcp(tmp_path):
    corrida = Corrida(tmp_path / "corrida")
    (documento,) = corrida.normalizar({"certificado.pdf": pdf(3)})
    reloj = RelojManual()
    servidor, _ = servidor_falso()
    servicio = Servicio(almacen=corrida.almacen, fuente=fuente(servidor),
                        llamador=Llamador(LLMFalso(por_tipo={"TD-16": respuesta_falsa("TD-16")}), reloj),
                        resultados=ResultadosEnCarpeta(tmp_path / "extraccion"), reloj=reloj)
    assert extraer_segmento(corrida.solicitud(documento, 1, 3), servicio)["estado"] == "ok"


def test_comando_de_prueba_cuenta_los_elementos(capsys):
    servidor, _ = servidor_falso()
    assert main(["--td", "TD-16", "--version", "21"], fuente=fuente(servidor)) == 0
    salida = json.loads(capsys.readouterr().out)
    esperada = FuenteModeloArchivo(FICHA_V21).ficha(21, "TD-16")
    assert salida["elementos"] == len(esperada.elementos)
    assert salida["a_extraer"] == len(esperada.a_extraer())
    assert salida["version"] == 21 and salida["td_probado"] is True


def test_comando_de_prueba_con_error(capsys):
    servidor, _ = servidor_falso(vigente=22)
    assert main([], fuente=fuente(servidor)) == 1
    assert "FichaNoEncontrada" in capsys.readouterr().err
