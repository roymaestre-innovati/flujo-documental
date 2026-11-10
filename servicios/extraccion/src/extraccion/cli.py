"""Comando `extraer`: extrae los segmentos de una corrida local del orquestador.

    extraer <solicitudes.jsonl> --corrida <carpeta> --modelo archivo:<ficha.json>
            [--llm falso --respuestas <carpeta> | --llm azure] [--solo <id_segmento>]…
            [--concurrencia 3] [--forzar] [--si-mando-documentos] [--registros <archivo>]

Las URI de las solicitudes se resuelven contra `<corrida>/almacen/` y los
resultados van a `<corrida>/extraccion/`, donde los encuentra el visor. Una
segunda corrida devuelve los resultados guardados sin llamar al LLM, salvo con
`--forzar`.

- `--llm falso` responde sin red con `<respuestas>/TD-NN.json`, uno por TD.
- `--llm azure` usa gpt-5.4 con `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` y
  `AZURE_OPENAI_DEPLOYMENT` del entorno o del `.env` de la carpeta actual, sin
  imprimirlos. Antes de mandar nada pregunta si seguir, salvo con
  `--si-mando-documentos`: manda el contenido de los documentos a la nube.

Los resultados traen datos personales: la corrida no puede estar dentro de un
repositorio git (principio 6). Por pantalla salen solo conteos.
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import dotenv_values
from normalizacion.almacen import CARPETA_ALMACEN, AlmacenLocal
from normalizacion.registros import lugar_de_la_excepcion

from . import VERSION
from .entrada import SolicitudInvalida
from .ficha import FuenteModeloArchivo
from .llamada import Llamador
from .llm import ClienteLLM, LLMFalso
from .llm_azure import ConfiguracionIncompleta, DeploymentNoPermitido, LLMAzureOpenAI
from .parametros import parametros
from .registros import configurar, registro
from .reloj import Reloj, RelojSistema
from .resultados import ResultadosEnCarpeta
from .servicio import Servicio, extraer_segmento

CARPETA_RESULTADOS = "extraccion"
PREGUNTA = "Esto manda documentos al modelo de lenguaje en la nube. ¿Seguir? (s/N) "


def dentro_de_un_repositorio(ruta: Path) -> bool:
    return any((carpeta / ".git").exists() for carpeta in (ruta, *ruta.parents))


def _argumentos(argv):
    p = argparse.ArgumentParser(prog="extraer", description="Extrae los segmentos de una corrida del orquestador.")
    p.add_argument("solicitudes", type=Path, help="solicitudes-extraccion.jsonl de la corrida")
    p.add_argument("--corrida", type=Path, required=True, help="carpeta de la corrida, con almacen/")
    p.add_argument("--modelo", required=True, help="archivo:<ficha.json> (el MCP llega en T08)")
    p.add_argument("--llm", choices=("falso", "azure"), default="falso")
    p.add_argument("--respuestas", type=Path, help="con --llm falso: carpeta con TD-NN.json")
    p.add_argument("--solo", action="append", default=[], metavar="ID_SEGMENTO", help="extrae solo esos segmentos")
    p.add_argument("--concurrencia", type=int, default=parametros()["llamada"]["concurrencia"],
                   help="llamadas al LLM a la vez")
    p.add_argument("--forzar", action="store_true", help="extrae otra vez aunque haya un resultado guardado")
    p.add_argument("--si-mando-documentos", action="store_true", help="no pregunta antes de usar el LLM en la nube")
    p.add_argument("--registros", type=Path, help="archivo para los registros en JSON")
    p.add_argument("--version", action="version", version=f"extraer {VERSION}")
    return p.parse_args(argv)


class ErrorDeUso(Exception):
    """Un argumento o la configuración no sirven. Se informa y el comando sale con 2."""


def _fuente(modelo: str) -> FuenteModeloArchivo:
    tipo, _, ruta = modelo.partition(":")
    if tipo == "mcp":
        raise ErrorDeUso("--modelo mcp todavía no está disponible: use archivo:<ficha.json>.")
    if tipo != "archivo" or not ruta:
        raise ErrorDeUso("--modelo debe ser archivo:<ficha.json>.")
    if not Path(ruta).is_file():
        raise ErrorDeUso("No existe el archivo de la ficha.")
    return FuenteModeloArchivo(ruta)


def _respuestas_falsas(carpeta: Path | None) -> LLMFalso:
    if carpeta is None or not carpeta.is_dir():
        raise ErrorDeUso("--llm falso necesita --respuestas con una carpeta de TD-NN.json.")
    return LLMFalso(por_tipo={a.stem: a.read_text(encoding="utf-8") for a in sorted(carpeta.glob("TD-*.json"))})


def _llm_azure() -> LLMAzureOpenAI:
    entorno = {**dotenv_values(Path.cwd() / ".env"), **os.environ}
    try:
        return LLMAzureOpenAI.desde_entorno(entorno)
    except (ConfiguracionIncompleta, DeploymentNoPermitido) as error:
        raise ErrorDeUso(str(error)) from None


def leer_solicitudes(ruta: Path, solo: list[str]) -> tuple[list[dict], int]:
    """Las solicitudes del archivo, en orden, y cuántas líneas no eran JSON."""
    solicitudes, ilegibles = [], 0
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            solicitud = json.loads(linea)
        except json.JSONDecodeError:
            ilegibles += 1
            continue
        if not solo or (isinstance(solicitud, dict) and solicitud.get("id_segmento") in solo):
            solicitudes.append(solicitud)
    return solicitudes, ilegibles


def _confirmar(entrada=input) -> bool:
    try:
        return entrada(PREGUNTA).strip().lower() in ("s", "si", "sí")
    except EOFError:
        return False


def correr(solicitudes: list[dict], servicio: Servicio, hilos: int, forzar: bool) -> dict:
    """Extrae todas las solicitudes y devuelve los conteos. Nada de valores ni texto."""
    estados, motivos, errores = Counter(), Counter(), Counter()
    cuenta = Counter()

    def una(solicitud):
        if forzar and isinstance(solicitud, dict):
            solicitud = {**solicitud, "forzar_reproceso": True}
        try:
            return extraer_segmento(solicitud, servicio)
        except SolicitudInvalida:
            registro.error("Solicitud que no cumple el contrato")
            return "invalida"
        except Exception as error:  # un bug en un segmento no frena los demás
            registro.error("Falla interna: %s", lugar_de_la_excepcion(error))
            return "falla"

    with ThreadPoolExecutor(max_workers=hilos) as grupo:
        for resultado in grupo.map(una, solicitudes):
            if resultado == "invalida":
                cuenta["solicitudes_invalidas"] += 1
                continue
            if resultado == "falla":
                cuenta["fallas_internas"] += 1
                continue
            ejecucion = resultado["ejecucion"]
            estados[resultado["estado"]] += 1
            cuenta["repetidos"] += ejecucion.get("desde_cache", False)
            cuenta["campos"] += len(resultado["resultados"])
            cuenta["campos_en_revision"] += len(resultado["campos_en_revision"])
            motivos.update(m for r in resultado["resultados"] for m in r["motivos"])
            if "error" in resultado:
                errores[resultado["error"]["codigo"]] += 1
            if not ejecucion.get("desde_cache"):
                cuenta["tokens_entrada"] += ejecucion.get("tokens_entrada", 0)
                cuenta["tokens_salida"] += ejecucion.get("tokens_salida", 0)
                cuenta["reintentos"] += ejecucion.get("reintentos", 0)
    return {
        "solicitudes": len(solicitudes),
        "por_estado": dict(sorted(estados.items())),
        "repetidos": cuenta["repetidos"],
        "campos": cuenta["campos"],
        "campos_en_revision": cuenta["campos_en_revision"],
        "motivos": dict(sorted(motivos.items())),
        "errores": dict(sorted(errores.items())),
        "tokens_entrada": cuenta["tokens_entrada"],
        "tokens_salida": cuenta["tokens_salida"],
        "reintentos": cuenta["reintentos"],
        "solicitudes_invalidas": cuenta["solicitudes_invalidas"],
        "fallas_internas": cuenta["fallas_internas"],
    }


def main(argv: list[str] | None = None, cliente: ClienteLLM | None = None, entrada=input,
         reloj: Reloj | None = None) -> int:
    """`cliente`, `entrada` y `reloj` son solo para las pruebas."""
    args = _argumentos(argv)
    corrida = args.corrida.resolve()
    try:
        if not (corrida / CARPETA_ALMACEN).is_dir():
            raise ErrorDeUso("La corrida no tiene almacen/.")
        if dentro_de_un_repositorio(corrida):
            raise ErrorDeUso("Los resultados traen datos personales: la corrida debe estar fuera de cualquier repositorio git.")
        if not args.solicitudes.is_file():
            raise ErrorDeUso("No existe el archivo de solicitudes.")
        if args.concurrencia < 1:
            raise ErrorDeUso("--concurrencia debe ser 1 o más.")
        fuente = _fuente(args.modelo)
        if cliente is None:
            cliente = _llm_azure() if args.llm == "azure" else _respuestas_falsas(args.respuestas)
        if args.llm == "azure" and not args.si_mando_documentos and not _confirmar(entrada):
            print("No se mandó nada.", file=sys.stderr)
            return 2
    except ErrorDeUso as error:
        print(error, file=sys.stderr)
        return 2

    solicitudes, ilegibles = leer_solicitudes(args.solicitudes, args.solo)
    archivo_registros = open(args.registros, "a", encoding="utf-8") if args.registros else None
    try:
        # Los registros llevan solo identificadores y conteos. Sin archivo, por pantalla
        # salen solo las advertencias y los errores.
        if archivo_registros:
            configurar(logging.INFO, archivo_registros)
        else:
            configurar(logging.WARNING, sys.stderr)
        reloj = reloj or RelojSistema()
        ajustes = {**parametros()["llamada"], "concurrencia": args.concurrencia}
        servicio = Servicio(
            almacen=AlmacenLocal(corrida / CARPETA_ALMACEN),
            fuente=fuente,
            llamador=Llamador(cliente, reloj, ajustes),
            resultados=ResultadosEnCarpeta(corrida / CARPETA_RESULTADOS),
            reloj=reloj,
        )
        inicio = time.perf_counter()
        # Más hilos que llamadas a la vez: el preprocesamiento de unos avanza mientras otros esperan al LLM.
        resumen = correr(solicitudes, servicio, hilos=args.concurrencia * 2, forzar=args.forzar)
        resumen["lineas_ilegibles"] = ilegibles
        resumen["tiempo_s"] = round(time.perf_counter() - inicio, 1)
    finally:
        if archivo_registros:
            archivo_registros.close()

    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    con_problemas = (resumen["solicitudes_invalidas"] or resumen["fallas_internas"] or ilegibles
                     or resumen["por_estado"].get("error_proceso"))
    return 1 if con_problemas else 0


if __name__ == "__main__":
    sys.exit(main())
