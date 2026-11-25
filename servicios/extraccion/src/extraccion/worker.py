"""Comando `extraer-worker`: la extracción como Container Apps Job (T06 de
`specs/005-orquestador/tasks-workers.md`, decisiones 3, 4 y 12).

    extraer-worker [--hilos 3] [--tomar-mensajes-s 1500]

Toma solicitudes de la cola `extraer`, extrae cada segmento con `extraer_segmento`
y publica el sobre en la cola `resultados`. Usa la mensajería compartida, no el
orquestador.

- `ok`, `no_corresponde`, `error_entrada` y un `error_proceso` que no se arregla
  repitiendo se publican y el mensaje se completa.
- Un `error_proceso` reintentable (el LLM o el MCP no respondieron, un 429, el
  almacén no disponible) lo reintenta el bucle de la cola, con la espera que pidió
  el servicio. `Llamador` solo repite por dentro las respuestas mal formadas.
- Si se agotan los reintentos, se publica el sobre `error_proceso` del último error.
- Una solicitud que no cumple el contrato va a errores sin reintento.
- Los resultados se guardan en el almacén: si un mensaje se vuelve a entregar, se
  publica lo guardado sin llamar otra vez al LLM. Quien consuma `resultados`
  deduplica por la clave de la solicitud.

Un solo job a la vez, con `--hilos 3` que comparten el `Llamador`: así el tope de
3 llamadas al LLM vale para todo el proceso.

Entorno: `SERVICEBUS_NAMESPACE`, `ALMACEN_BLOB_CUENTA`, `EXTRACCION_MODELO`
(`mcp` o `archivo:<ficha.json>`) y las variables del LLM de `llm_azure.py` (y de
`ficha_mcp.py` con `mcp`). Código de salida: 0 normal, 2 configuración, 1 otra falla.
"""

import argparse
import logging
import os
import sys
import threading
from contextlib import ExitStack
from dataclasses import dataclass

from mensajeria.cola import EXTRAER, RESULTADOS, Cola
from mensajeria.cola_servicebus import cola_desde_entorno
from mensajeria.errores import ErrorDeConfiguracion, ErrorTransitorio, MensajeRechazado
from mensajeria.registros import contexto_de
from mensajeria.worker import SALIDA_CONFIGURACION, Limites, atender_senales, informar, vaciar
from normalizacion.almacen import AlmacenSinPermiso

from .entrada import ERROR_PROCESO, ErrorDeSolicitud, SolicitudInvalida, validar
from .llamada import Llamador
from .parametros import parametros
from .registros import configurar, registro
from .reloj import RelojSistema
from .resultados import ResultadosEnAlmacen
from .servicio import Servicio, extraer_segmento, resultado_de_error

VARIABLES = ("SERVICEBUS_NAMESPACE", "ALMACEN_BLOB_CUENTA", "EXTRACCION_MODELO")
VARIABLES_MCP = ("MCP_URL", "MCP_API_KEY")
"""Con `EXTRACCION_MODELO=mcp`. El job usa la clave del MCP (`servicios/workers/README.md`)."""
CONCURRENCIA = 3

FALLA_INTERNA = ErrorDeSolicitud(ERROR_PROCESO, "FALLA_INTERNA",
                                 "La extracción falló por una causa técnica sin resolver.", reintentable=True)


def ajustes_del_worker() -> dict:
    """Los de la llamada, sin los reintentos que ahora hace el bucle de la cola."""
    return {**parametros()["llamada"], "concurrencia": CONCURRENCIA,
            "reintentos_falla_pasajera": 0, "espera_limite_uso_total_s": 0}


class ManejadorExtraer:
    cola = EXTRAER

    def __init__(self, publicar: Cola, servicio: Servicio) -> None:
        if not servicio.relanzar_reintentables:
            raise ValueError("El worker necesita un Servicio con relanzar_reintentables")
        self._publicar = publicar
        self._servicio = servicio
        self._ultimo = threading.local()
        """El último error reintentable y el último resultado de cada hilo, para `al_fallar`."""

    def procesar(self, solicitud: dict) -> None:
        self._ultimo.error = self._ultimo.resultado = None
        try:
            resultado = extraer_segmento(solicitud, self._servicio)
        except SolicitudInvalida as invalida:
            raise MensajeRechazado(f"La solicitud no cumple el contrato ({len(invalida.errores)} problemas)") from None
        except ErrorDeSolicitud as error:
            self._ultimo.error = error
            raise ErrorTransitorio(error.codigo, espera_s=getattr(error, "espera_s", None)) from None
        self._ultimo.resultado = resultado
        self._publicar.publicar(RESULTADOS, resultado)

    def al_fallar(self, solicitud: dict, motivo: str) -> None:
        try:
            validar(solicitud)
        except SolicitudInvalida:
            return
        with contexto_de(solicitud):
            if (resultado := getattr(self._ultimo, "resultado", None)) is not None:
                # El segmento se extrajo y lo que falló fue publicarlo: se publica ese resultado.
                self._publicar.publicar(RESULTADOS, resultado)
                registro.warning("Segmento extraído que no se pudo publicar en los reintentos: se publica de nuevo")
                return
        error = getattr(self._ultimo, "error", None) or FALLA_INTERNA
        with contexto_de(solicitud):
            self._publicar.publicar(RESULTADOS, resultado_de_error(solicitud, self._servicio, error))
            registro.warning("Segmento sin extraer tras los reintentos: %s", error.codigo)


@dataclass
class Fabricas:
    """Cómo se crea cada pieza. Las pruebas pasan versiones falsas."""

    cola: object = cola_desde_entorno
    almacen: object = None
    fuente: object = None
    cliente: object = None


def _fabricas_reales() -> Fabricas:
    from normalizacion.almacen_blob import almacen_blob_desde_entorno

    from .cli import ErrorDeUso, _fuente
    from .ficha_mcp import FuenteModeloMCP
    from .llm_azure import ConfiguracionIncompleta, DeploymentNoPermitido, LLMAzureOpenAI

    # Solo el entorno del job: el worker no lee el `.env` de la carpeta actual, como la CLI.
    def fuente():
        modelo = os.environ["EXTRACCION_MODELO"].strip()
        if modelo != "mcp":
            try:
                return _fuente(modelo)
            except ErrorDeUso:
                raise ErrorDeConfiguracion("EXTRACCION_MODELO debe ser mcp o archivo:<ficha.json> legible") from None
        if faltan := [v for v in VARIABLES_MCP if not os.environ.get(v, "").strip()]:
            raise ErrorDeConfiguracion("Faltan variables de entorno: " + ", ".join(faltan))
        return FuenteModeloMCP.desde_entorno(os.environ)

    def cliente():
        try:
            return LLMAzureOpenAI.desde_entorno(os.environ)
        except ConfiguracionIncompleta as error:
            raise ErrorDeConfiguracion(str(error)) from None
        except DeploymentNoPermitido:
            raise ErrorDeConfiguracion("AZURE_OPENAI_DEPLOYMENT parece gpt-5.4-mini: la extracción usa gpt-5.4") from None

    return Fabricas(cola_desde_entorno, almacen_blob_desde_entorno, fuente, cliente)


def _argumentos(argv):
    p = argparse.ArgumentParser(prog="extraer-worker", description="Extrae las solicitudes de la cola y termina.")
    p.add_argument("--hilos", type=int, default=CONCURRENCIA, help="solicitudes a la vez, cada una con su cola (3)")
    p.add_argument("--tomar-mensajes-s", type=float, default=Limites().tomar_mensajes_s,
                   help="no toma mensajes nuevos pasado este tiempo (1500 s)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None, *, fabricas: Fabricas | None = None,
         detener: threading.Event | None = None) -> int:
    """`fabricas` y `detener` son solo para las pruebas."""
    args = _argumentos(argv)
    configurar(logging.INFO, sys.stderr)
    try:
        limites = Limites(tomar_mensajes_s=args.tomar_mensajes_s)
        if args.hilos < 1:
            raise ValueError("--hilos debe ser 1 o más")
    except ValueError as error:
        print(error, file=sys.stderr)
        return SALIDA_CONFIGURACION
    if faltan := [v for v in VARIABLES if not os.environ.get(v, "").strip()]:
        print("Configuración: Faltan variables de entorno: " + ", ".join(faltan), file=sys.stderr)
        return SALIDA_CONFIGURACION

    fabricas = fabricas or _fabricas_reales()
    with ExitStack() as recursos:
        try:
            almacen = recursos.enter_context(fabricas.almacen())
            reloj = RelojSistema()
            fuente = fabricas.fuente()
            cliente = fabricas.cliente()
            if hasattr(cliente, "cerrar"):
                recursos.callback(cliente.cerrar)
            servicio = Servicio(almacen=almacen, fuente=fuente,
                                llamador=Llamador(cliente, reloj, ajustes_del_worker()),
                                resultados=ResultadosEnAlmacen(almacen), reloj=reloj, relanzar_reintentables=True)
            colas = [_cola(fabricas, recursos) for _ in range(args.hilos)]
            manejador = ManejadorExtraer(_cola(fabricas, recursos), servicio)
        except (ErrorDeConfiguracion, AlmacenSinPermiso) as error:
            print(f"Configuración: {error}", file=sys.stderr)
            return SALIDA_CONFIGURACION
        detener = detener or threading.Event()
        if threading.current_thread() is threading.main_thread():
            with atender_senales(detener):
                resumen = vaciar(colas, manejador, limites=limites, detener=detener)
        else:
            resumen = vaciar(colas, manejador, limites=limites, detener=detener)
        return informar(resumen)


def _cola(fabricas: Fabricas, recursos: ExitStack) -> Cola:
    cola = fabricas.cola()
    if hasattr(cola, "cerrar"):
        recursos.callback(cola.cerrar)
    return cola


if __name__ == "__main__":
    sys.exit(main())
