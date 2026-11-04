"""Comando `normalizar`.

    normalizar <carpeta_entrega> --proceso SR0000000001 [--oferente OF-002] --salida <carpeta> [--forzar]

Normaliza y lee la entrega y escribe el resultado en la carpeta de salida. Imprime
un resumen sin datos personales: conteos por estado y por tipo de página.

Sale con 0 aunque haya documentos con error, porque un error del documento es un
resultado. Solo sale distinto de 0 ante un bug (clase 4 del diseño).
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import VERSION, registros
from .almacen import AlmacenLocal
from .entrega import ErrorEntrega, normalizar_entrega
from .inventario import ENTREGA_DEL_PROCESO
from .parametros import VERSION_PARAMETROS

ESTADOS = ("normalizado", "duplicado", "error_entrada")
TIPOS_DE_PAGINA = ("texto", "escaneo_con_ocr", "imagen", "vacia")


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


def resumen(resultado, proceso: str, entrega: str) -> str:
    manifiesto = resultado.manifiesto
    estados = Counter(archivo["estado"] for archivo in manifiesto["archivos"])
    errores = Counter(a["error"]["codigo"] for a in manifiesto["archivos"] if a["error"])
    lineas = [
        f"Entrega {proceso}/{entrega}: {len(manifiesto['archivos'])} archivos, "
        f"{len(manifiesto['descartados'])} descartados, {resultado.reusados} reusados.",
        "Estados: " + ", ".join(f"{estado} {estados.get(estado, 0)}" for estado in ESTADOS) + ".",
        "Páginas: " + ", ".join(f"{tipo} {resultado.tipos_de_pagina.get(tipo, 0)}" for tipo in TIPOS_DE_PAGINA) + ".",
    ]
    if errores:
        lineas.append("Errores: " + ", ".join(f"{codigo} {n}" for codigo, n in sorted(errores.items())) + ".")
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    argumentos = _argumentos(argv)
    registros.configurar()
    entrega = argumentos.oferente or ENTREGA_DEL_PROCESO
    try:
        resultado = normalizar_entrega(
            argumentos.carpeta_entrega,
            argumentos.proceso,
            argumentos.oferente,
            AlmacenLocal(argumentos.salida),
            forzar=argumentos.forzar,
        )
    except ErrorEntrega as error:
        print(f"Falla inesperada: {error}", file=sys.stderr)
        return 1
    print(resumen(resultado, argumentos.proceso, entrega))
    return 0


if __name__ == "__main__":
    sys.exit(main())
