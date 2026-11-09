"""Comando `orquestar`: corre un proceso completo en local (T10).

    orquestar --origen <carpeta del proceso> --proceso SR... --clasificacion <csv> --salida <carpeta>

La carpeta del proceso trae `PROCESO/` y una subcarpeta por oferente, como la
dejará el módulo 1 en OneLake. El CSV es el del clasificador falso
(`clasificador.py`).

En `<salida>` quedan el almacén (PDF normalizados y lecturas), `estado.json`,
`solicitudes-extraccion.jsonl`, `errores.json` y `conteos.json`. Todo eso trae
datos personales: el comando no escribe dentro de un repositorio git
(principio 6). Por pantalla salen solo conteos.
"""

import argparse
import dataclasses
import json
import logging
import sys
import time
from pathlib import Path

from normalizacion.almacen import AlmacenLocal

from . import VERSION
from .clasificador import ClasificadorFalso
from .cola import COLAS
from .local import Corrida, aviso, conteos
from .origen import OrigenLocal
from .parametros import PARAMETROS
from .registros import configurar


def dentro_de_un_repositorio(ruta: Path) -> bool:
    return any((carpeta / ".git").exists() for carpeta in (ruta, *ruta.parents))


def _argumentos(argv):
    p = argparse.ArgumentParser(prog="orquestar", description="Corre un proceso del aviso a las solicitudes de extracción.")
    p.add_argument("--origen", type=Path, required=True, help="carpeta del proceso, con PROCESO/ y una por oferente")
    p.add_argument("--proceso", required=True, help="id_proceso, por ejemplo SR0000000001")
    p.add_argument("--clasificacion", type=Path, required=True, help="CSV del clasificador falso")
    p.add_argument("--salida", type=Path, required=True, help="carpeta de salida, fuera de cualquier repositorio")
    p.add_argument("--paralelo", type=int, default=PARAMETROS.paralelo_normalizar,
                   help=f"entregas que se normalizan a la vez (por defecto {PARAMETROS.paralelo_normalizar})")
    p.add_argument("--soffice", help="ruta de LibreOffice, si no está en el PATH")
    p.add_argument("--registros", type=Path, help="archivo para los registros en JSON (sin él, solo advertencias por pantalla)")
    p.add_argument("--version", action="version", version=f"orquestar {VERSION}")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    origen, salida = args.origen.resolve(), args.salida.resolve()
    if not origen.is_dir():
        print("La carpeta del proceso no existe.", file=sys.stderr)
        return 2
    if dentro_de_un_repositorio(salida):
        print("La salida trae datos personales: elija una carpeta fuera de cualquier repositorio git.", file=sys.stderr)
        return 2
    if args.paralelo < 1:
        print("--paralelo debe ser 1 o más.", file=sys.stderr)
        return 2
    salida.mkdir(parents=True, exist_ok=True)

    archivo_registros = open(args.registros, "a", encoding="utf-8") if args.registros else None
    try:
        # Los registros llevan solo identificadores. Sin archivo, por pantalla
        # salen solo las advertencias y los errores.
        if archivo_registros:
            configurar(logging.INFO, archivo_registros)
        else:
            configurar(logging.WARNING, sys.stderr)
        inicio = time.perf_counter()
        corrida = Corrida(
            origen=OrigenLocal(origen.parent),
            almacen=AlmacenLocal(salida / "almacen"),
            clasificador=ClasificadorFalso(args.clasificacion),
            parametros=dataclasses.replace(PARAMETROS, paralelo_normalizar=args.paralelo),
            soffice=args.soffice,
        )
        corrida.publicar_aviso(aviso(args.proceso, origen.name, corrida.reloj))
        corrida.correr()
        resumen = {**conteos(corrida, args.proceso), "tiempo_s": round(time.perf_counter() - inicio, 1)}
    finally:
        if archivo_registros:
            archivo_registros.close()

    corrida.estado.guardar(salida / "estado.json")
    with open(salida / "solicitudes-extraccion.jsonl", "w", encoding="utf-8") as f:
        for solicitud in corrida.solicitudes:
            f.write(json.dumps(solicitud, ensure_ascii=False) + "\n")
    errores = [{"cola": c, "motivo": e.motivo, "cuerpo": e.mensaje.cuerpo} for c in COLAS for e in corrida.cola.errores(c)]
    (salida / "errores.json").write_text(json.dumps(errores, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (salida / "conteos.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 1 if resumen["mensajes_en_errores"] else 0


if __name__ == "__main__":
    sys.exit(main())
