"""La ficha pedida al servidor MCP del modelo semántico (T08, R30).

El servicio llama al MCP como cliente, con código, antes de armar el mensaje: el
LLM no ve las tools. El MCP solo da metadatos del modelo, nunca recibe contenido
de los documentos.

- `describir_modelo` da la guía, el diccionario y las secciones.
- `obtener_seccion` da los elementos del TD, en la versión pedida.

**La versión.** `obtener_seccion` recibe la versión, pero `describir_modelo` (en
el servidor de hoy) no: siempre da la vigente. Si la tool declara `version`, se
le pasa. Siempre se comprueba que la versión que llegó sea la fijada: si no, la
guía no es la de esa versión y la ficha no se usa (principio 7).

Las versiones publicadas no cambian, así que lo pedido se guarda en memoria por
versión (guía) y por (versión, TD) (ficha) mientras vive el proceso.

Errores:

- La versión, la sección o el modelo no existen: `FichaNoEncontrada`.
- No se pudo hablar con el servidor (caído, tiempo agotado, red): `FuenteNoDisponible`,
  que la extracción da como `error_proceso` reintentable.
- Cualquier otro error de la tool (proyecto no habilitado, falta el header): `ErrorDelMCP`,
  un problema de configuración que no se reintenta.
"""

import json
import threading
from collections.abc import Callable, Mapping
from typing import Any

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from .ficha import Ficha, FichaNoEncontrada, FuenteModelo, ficha_desde

MODELO = "extraccion_documental"
PROYECTO = "extraccion_documental"
"""El header `X-Proyecto`: la colección del modelo en el servidor."""
TIEMPO_LIMITE_S = 60
NO_EXISTE = ("no existe", "no tiene la versión")
"""Lo que dicen los errores del servidor cuando lo pedido no está (`servidor.py` del modelo semántico)."""


class FuenteNoDisponible(Exception):
    """El servidor MCP no respondió. Puede pasar solo: se reintenta después."""


class ErrorDelMCP(Exception):
    """El servidor rechazó el pedido por algo que no es la ficha: configuración."""


class _ErrorDeTool(Exception):
    def __init__(self, texto: str) -> None:
        self.texto = texto
        super().__init__(texto)


def _hoja(error: BaseException) -> BaseException:
    """La excepción de adentro, si anyio la envolvió en un grupo de una sola."""
    while isinstance(error, BaseExceptionGroup) and len(error.exceptions) == 1:
        error = error.exceptions[0]
    return error


def _texto(resultado) -> str:
    return "".join(getattr(c, "text", "") for c in resultado.content)


async def _llamar(cliente: Client, tool: str, argumentos: dict) -> dict:
    resultado = await cliente.call_tool(tool, argumentos)
    if resultado.is_error:
        raise _ErrorDeTool(_texto(resultado))
    return json.loads(_texto(resultado))


class FuenteModeloMCP(FuenteModelo):
    def __init__(self, destino: Callable[[], Any], modelo: str = MODELO) -> None:
        """`destino` da, en cada conexión, lo que recibe `mcp.Client`: un transporte o, en las pruebas, un servidor."""
        self._destino = destino
        self._modelo = modelo
        self._candado = threading.Lock()
        self._descripciones: dict[int, dict] = {}
        self._fichas: dict[tuple[int, str], Ficha] = {}

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> "FuenteModeloMCP":
        """`MCP_URL` y, si el servidor la exige, `MCP_API_KEY`. Nunca se imprimen."""
        url = entorno.get("MCP_URL")
        if not url:
            raise ValueError("Falta la variable de entorno MCP_URL")
        cabeceras = {"X-Proyecto": PROYECTO}
        if entorno.get("MCP_API_KEY"):
            cabeceras["X-Api-Key"] = entorno["MCP_API_KEY"]

        def destino():
            http = httpx2.AsyncClient(headers=cabeceras, timeout=TIEMPO_LIMITE_S)
            return streamable_http_client(url, http_client=http)

        return cls(destino)

    def ficha(self, version: int, tipo_documental: str) -> Ficha:
        # Un pedido a la vez: son pocos (uno por versión y TD) y así no se piden dos veces.
        with self._candado:
            clave = (version, tipo_documental)
            if clave not in self._fichas:
                self._fichas[clave] = self._pedir(version, tipo_documental)
            return self._fichas[clave]

    def _pedir(self, version: int, tipo_documental: str) -> Ficha:
        try:
            descripcion, seccion = anyio.run(self._pedir_async, version, tipo_documental)
        except Exception as envuelta:
            error = _hoja(envuelta)
            if isinstance(error, FichaNoEncontrada):
                raise error from None
            if isinstance(error, _ErrorDeTool):
                if any(frase in error.texto.lower() for frase in NO_EXISTE):
                    raise FichaNoEncontrada(error.texto) from None
                raise ErrorDelMCP(error.texto) from None
            # Caído, tiempo agotado o sin red.
            raise FuenteNoDisponible(f"El servidor MCP no respondió: {type(error).__name__}") from None
        if seccion.get("version") != version:
            raise FichaNoEncontrada(f"El MCP dio la versión {seccion.get('version')} y no la {version}")
        self._descripciones[version] = descripcion
        return ficha_desde({**descripcion, "elementos": seccion["elementos"]}, tipo_documental)

    async def _pedir_async(self, version: int, tipo_documental: str) -> tuple[dict, dict]:
        async with Client(self._destino()) as cliente:
            descripcion = self._descripciones.get(version)
            if descripcion is None:
                herramientas = {t.name: t for t in (await cliente.list_tools()).tools}
                argumentos = {"modelo": self._modelo}
                if "version" in herramientas["describir_modelo"].input_schema.get("properties", {}):
                    argumentos["version"] = version
                descripcion = await _llamar(cliente, "describir_modelo", argumentos)
                if descripcion.get("version") != version:
                    raise FichaNoEncontrada(
                        f"describir_modelo dio la versión {descripcion.get('version')}, no la {version}: "
                        "el servidor solo da la guía de la versión vigente"
                    )
            if not any(s["id"] == tipo_documental for s in descripcion["secciones"]):
                raise FichaNoEncontrada(f"La versión {version} no tiene la sección {tipo_documental}")
            seccion = await _llamar(cliente, "obtener_seccion",
                                    {"modelo": self._modelo, "seccion": tipo_documental, "version": version})
            return descripcion, seccion


def main(argv: list[str] | None = None, fuente: FuenteModelo | None = None) -> int:
    """`probar-ficha-mcp`: pide una ficha al MCP y cuenta sus elementos. No manda documentos.

    `fuente` es solo para las pruebas.
    """
    import argparse
    import os
    import sys
    from pathlib import Path

    from dotenv import dotenv_values

    p = argparse.ArgumentParser(prog="probar-ficha-mcp", description="Pide una ficha al MCP y cuenta sus elementos.")
    p.add_argument("--td", default="TD-16")
    p.add_argument("--version", type=int, default=21)
    args = p.parse_args(argv)
    try:
        if fuente is None:
            fuente = FuenteModeloMCP.desde_entorno({**dotenv_values(Path.cwd() / ".env"), **os.environ})
        ficha = fuente.ficha(args.version, args.td)
    except (ValueError, FichaNoEncontrada, FuenteNoDisponible, ErrorDelMCP) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "modelo": ficha.modelo,
        "version": ficha.version,
        "tipo_documental": ficha.tipo_documental,
        "td_probado": ficha.td_probado,
        "elementos": len(ficha.elementos),
        "a_extraer": len(ficha.a_extraer()),
        "con_valores_permitidos": sum(1 for e in ficha.elementos if "valores_permitidos" in e),
        "caracteres_guia": len(ficha.guia),
    }, ensure_ascii=False, indent=2))
    return 0
