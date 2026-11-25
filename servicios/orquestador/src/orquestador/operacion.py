"""Comando `orquestar-operar`: lo que corre operación, a mano o con horario
(T09 de `specs/005-orquestador/tasks-workers.md`).

    orquestar-operar reenviar-errores <cola>   # después de corregir la causa (R21)
    orquestar-operar escalar-fallas            # cada hora, como job con horario (R22)

- `reenviar-errores` vuelve a publicar todo lo que está en la cola de errores de
  `<cola>`, desde el primer intento. Es seguro porque cada manejador es idempotente
  y el reenvío en Service Bus republica antes de completar. Usa `SERVICEBUS_NAMESPACE`.
- `escalar-fallas` crea una tarea "falla técnica" por cada entrega o documento que
  lleva más de `horas_escalamiento` (24) en `error_proceso`, para que el evaluador
  lo revise a mano. Las que ya existían no se repiten. Usa `ESTADO_MONGO_URL`.

Por pantalla salen solo conteos. Código de salida: 0 bien, 2 configuración, 1 otra falla.
"""

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass

from mensajeria.worker import SALIDA_CONFIGURACION, SALIDA_FALLA, SALIDA_OK

from .cola import COLAS, Cola
from .cola_servicebus import cola_desde_entorno
from .entorno import estado_desde_entorno
from .errores import ErrorDeConfiguracion, reenviar_errores
from .estado import Estado
from .parametros import PARAMETROS
from .registros import configurar, lugar_de_la_excepcion
from .reloj import RelojSistema
from .tareas import escalar_fallas

registro = logging.getLogger("orquestador.operacion")


@dataclass
class Fabricas:
    """Cómo se crean la cola y el estado. Las pruebas pasan versiones falsas."""

    cola: Callable[[], Cola] = cola_desde_entorno
    estado: Callable[[], tuple[Estado, object]] = estado_desde_entorno


def _argumentos(argv):
    p = argparse.ArgumentParser(prog="orquestar-operar", description="Comandos de operación del orquestador.")
    comandos = p.add_subparsers(dest="comando", required=True)
    reenviar = comandos.add_parser("reenviar-errores", help="vuelve a publicar la cola de errores de una cola")
    reenviar.add_argument("cola", choices=COLAS)
    comandos.add_parser("escalar-fallas", help="crea las tareas de las fallas técnicas sin resolver")
    return p.parse_args(argv)


def _reenviar(fabricas: Fabricas, nombre: str) -> dict:
    cola = fabricas.cola()
    try:
        return {"cola": nombre, "reenviados": reenviar_errores(cola, nombre)}
    finally:
        if hasattr(cola, "cerrar"):
            cola.cerrar()


def _escalar(fabricas: Fabricas) -> dict:
    estado, recurso = fabricas.estado()
    try:
        return {"tareas_creadas": len(escalar_fallas(estado, RelojSistema(), PARAMETROS))}
    finally:
        if hasattr(recurso, "close"):
            recurso.close()


def main(argv: list[str] | None = None, *, fabricas: Fabricas | None = None) -> int:
    """`fabricas` es solo para las pruebas."""
    args = _argumentos(argv)
    configurar(logging.INFO, sys.stderr)
    fabricas = fabricas or Fabricas()
    try:
        resumen = _reenviar(fabricas, args.cola) if args.comando == "reenviar-errores" else _escalar(fabricas)
    except ErrorDeConfiguracion as error:
        print(f"Configuración: {error}", file=sys.stderr)
        return SALIDA_CONFIGURACION
    except Exception as error:  # noqa: BLE001 - se informa solo el tipo y el lugar
        registro.error("%s no terminó: %s", args.comando, lugar_de_la_excepcion(error))
        return SALIDA_FALLA
    registro.info("%s: %s", args.comando, resumen)
    print(resumen)
    return SALIDA_OK


if __name__ == "__main__":
    sys.exit(main())
