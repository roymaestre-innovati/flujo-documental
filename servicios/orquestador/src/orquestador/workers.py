"""Comando `orquestar-worker`: un manejador del orquestador como Container Apps Job
(T05 de `specs/005-orquestador/tasks-workers.md`).

    orquestar-worker apertura|normalizar|clasificar [--tomar-mensajes-s 1500] [--soffice <ruta>]

Arma las piezas de Azure desde el entorno (`entorno.py`), vacía la cola del
manejador con `mensajeria.worker.vaciar` y termina. Los registros van en JSON
por stderr, solo con identificadores y conteos.

- `apertura` lee `procesos-listos` y publica en `normalizar`. Usa OneLake cuando
  el aviso no trae la lista de archivos.
- `normalizar` lee `normalizar` y publica en `clasificar`. Usa OneLake y, para
  los documentos de Office, LibreOffice (`--soffice` o `soffice` en el `PATH`),
  que se busca al arrancar.
- `clasificar` lee `clasificar` y publica en `extraer`. En esta entrega solo hay
  clasificador falso, para desarrollo: `CLASIFICADOR=falso` y `CLASIFICADOR_CSV`
  con la ruta del CSV dentro del almacén (decisión 2).

Un solo mensaje a la vez por ejecución (decisión 4): la concurrencia de
`normalizar` la dan las ejecuciones del job, no hilos.

Código de salida: 0 normal, 2 configuración inválida, 1 otra falla que cortó la
ejecución (ver `mensajeria.worker`).
"""

import argparse
import logging
import os
import shutil
import sys
import threading

from mensajeria.worker import SALIDA_CONFIGURACION, Limites, atender_senales, informar, vaciar
from normalizacion.almacen import AlmacenNoDisponible, AlmacenSinPermiso, ErrorAlmacen

from .apertura import Apertura
from .clasificador import ClasificadorFalso, ErrorClasificadorFalso
from .clasificar import Clasificar
from .entorno import Fabricas, Piezas, piezas_desde_entorno
from .errores import ErrorDeConfiguracion, Manejador
from .extraer import Extraer
from .normalizar import Normalizar
from .parametros import PARAMETROS
from .registros import configurar
from .reloj import RelojSistema

registro = logging.getLogger("orquestador.workers")

APERTURA, NORMALIZAR, CLASIFICAR = "apertura", "normalizar", "clasificar"
WORKERS = (APERTURA, NORMALIZAR, CLASIFICAR)
CON_ORIGEN = {APERTURA, NORMALIZAR}


def _argumentos(argv):
    p = argparse.ArgumentParser(prog="orquestar-worker", description="Vacía la cola de un manejador y termina.")
    p.add_argument("worker", choices=WORKERS)
    p.add_argument("--tomar-mensajes-s", type=float, default=Limites().tomar_mensajes_s,
                   help="no toma mensajes nuevos pasado este tiempo (1500 s)")
    p.add_argument("--soffice", help="con normalizar: la ruta de LibreOffice, si no está en el PATH")
    return p.parse_args(argv)


def _soffice(ruta: str | None) -> str:
    """LibreOffice, revisado antes de recibir: sin él, el primer documento de Office fallaría."""
    encontrado = shutil.which(ruta or "soffice")
    if encontrado is None:
        raise ValueError("No se encontró LibreOffice: --soffice o soffice en el PATH")
    return encontrado


def clasificador_desde_entorno(piezas: Piezas) -> ClasificadorFalso:
    """El clasificador falso con su CSV del almacén, revisado antes de recibir mensajes."""
    if os.environ.get("CLASIFICADOR", "").strip() != "falso":
        raise ErrorDeConfiguracion("CLASIFICADOR debe ser 'falso': el clasificador real todavía no existe (A-5)")
    ruta = os.environ.get("CLASIFICADOR_CSV", "").strip()
    if not ruta:
        raise ErrorDeConfiguracion("Falta CLASIFICADOR_CSV, la ruta del CSV dentro del almacén")
    try:
        clasificador = ClasificadorFalso(texto=piezas.almacen.leer(piezas.almacen.uri(ruta)).decode("utf-8"))
    except (ErrorAlmacen, AlmacenSinPermiso):
        raise ErrorDeConfiguracion("No se encontró el CSV de CLASIFICADOR_CSV en el almacén") from None
    except (UnicodeDecodeError, ErrorClasificadorFalso):
        raise ErrorDeConfiguracion("El CSV de CLASIFICADOR_CSV no es válido") from None
    if not clasificador.filas:
        raise ErrorDeConfiguracion("El CSV de CLASIFICADOR_CSV no tiene filas: todo saldría TD-99")
    return clasificador


def armar_manejador(worker: str, piezas: Piezas, *, soffice: str | None = None) -> Manejador:
    """El manejador con una cola propia para publicar, aparte de las que reciben."""
    reloj = RelojSistema()
    publicar = piezas.cola()
    if worker == APERTURA:
        return Apertura(publicar, piezas.estado, piezas.origen, reloj)
    if worker == NORMALIZAR:
        return Normalizar(publicar, piezas.estado, piezas.origen, piezas.almacen, reloj,
                          soffice=soffice, parametros=PARAMETROS)
    clasificador = clasificador_desde_entorno(piezas)
    return Clasificar(piezas.estado, piezas.almacen, clasificador, Extraer(publicar, piezas.almacen), reloj)


def main(argv: list[str] | None = None, *, fabricas: Fabricas | None = None,
         detener: threading.Event | None = None) -> int:
    """`fabricas` y `detener` son solo para las pruebas."""
    args = _argumentos(argv)
    configurar(logging.INFO, sys.stderr)
    try:
        limites = Limites(tomar_mensajes_s=args.tomar_mensajes_s)
        if args.worker == NORMALIZAR:
            args.soffice = _soffice(args.soffice)
    except ValueError as error:
        print(error, file=sys.stderr)
        return SALIDA_CONFIGURACION

    try:
        piezas = piezas_desde_entorno(con_origen=args.worker in CON_ORIGEN, fabricas=fabricas)
    except ErrorDeConfiguracion as error:
        print(f"Configuración: {error}", file=sys.stderr)
        return SALIDA_CONFIGURACION

    with piezas:
        try:
            manejador = armar_manejador(args.worker, piezas, soffice=args.soffice)
            colas = piezas.colas(1)
        except ErrorDeConfiguracion as error:
            print(f"Configuración: {error}", file=sys.stderr)
            return SALIDA_CONFIGURACION
        except AlmacenNoDisponible as error:
            print(f"El almacén no respondió: {error}", file=sys.stderr)
            return 1
        detener = detener or threading.Event()
        if threading.current_thread() is threading.main_thread():
            with atender_senales(detener):
                resumen = vaciar(colas, manejador, parametros=PARAMETROS, limites=limites, detener=detener)
        else:
            resumen = vaciar(colas, manejador, parametros=PARAMETROS, limites=limites, detener=detener)
        return informar(resumen)


if __name__ == "__main__":
    sys.exit(main())
