"""Comando `normalizar`.

    normalizar <carpeta_entrega> --proceso SR0000000001 [--oferente OF-002] --salida <carpeta> [--forzar]

Por ahora (T02) solo recorre la entrega e imprime cuántos archivos trae. No
imprime nombres de archivo, porque pueden traer nombres de personas (principio 6).
"""

import argparse
import sys
from pathlib import Path

from . import VERSION
from .inventario import recorrer
from .parametros import VERSION_PARAMETROS


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="normalizar",
        description="Normaliza y lee los documentos de una entrega.",
    )
    parser.add_argument("carpeta_entrega", type=Path, help="Carpeta con los archivos de la entrega.")
    parser.add_argument("--proceso", required=True, help="Identificador del proceso de selección.")
    parser.add_argument("--oferente", help="Identificador del oferente. Sin él, es una entrega del proceso.")
    parser.add_argument("--salida", required=True, type=Path, help="Carpeta del almacén de salida.")
    parser.add_argument("--forzar", action="store_true", help="Vuelve a procesar aunque ya exista la lectura.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION} (parámetros {VERSION_PARAMETROS})")
    argumentos = parser.parse_args(argv)
    if not argumentos.carpeta_entrega.is_dir():
        parser.error("la carpeta de la entrega no existe o no es una carpeta")
    return argumentos


def main(argv: list[str] | None = None) -> int:
    argumentos = _argumentos(argv)
    rutas = recorrer(argumentos.carpeta_entrega)
    entrega = argumentos.oferente or "PROCESO"
    print(f"Entrega {argumentos.proceso}/{entrega}: {len(rutas)} archivos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
