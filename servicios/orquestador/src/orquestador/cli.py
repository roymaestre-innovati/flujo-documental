"""Comando `orquestar`: corre un proceso desde una carpeta local o OneLake.

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
from .entrada_modulo1 import EventoRechazado, Tablas, TablasOneLake, armar_entrada
from .local import Corrida, aviso, conteos, guardar_salida
from .origen import OrigenLocal
from .origen_onelake import OrigenOneLake
from .parametros import PARAMETROS
from .registros import configurar


def dentro_de_un_repositorio(ruta: Path) -> bool:
    return any((carpeta / ".git").exists() for carpeta in (ruta, *ruta.parents))


def _argumentos(argv):
    p = argparse.ArgumentParser(prog="orquestar", description="Corre un proceso del aviso a las solicitudes de extracción.")
    local = p.add_argument_group("Entrada local")
    local.add_argument("--origen", type=Path, help="carpeta del proceso, con PROCESO/ y una por oferente")
    local.add_argument("--proceso", help="id_proceso, por ejemplo SR0000000001")
    onelake = p.add_argument_group("Entrada OneLake")
    onelake.add_argument("--onelake-workspace", help="workspace del módulo 1")
    onelake.add_argument("--onelake-lakehouse", help="lakehouse del módulo 1")
    onelake.add_argument("--evento", help="event_id del módulo 1")
    p.add_argument("--clasificacion", type=Path, help="CSV del clasificador falso (si falta, todo sale TD-99)")
    p.add_argument("--salida", type=Path, required=True, help="carpeta de salida, fuera de cualquier repositorio")
    p.add_argument("--paralelo", type=int, default=PARAMETROS.paralelo_normalizar,
                   help=f"entregas que se normalizan a la vez (por defecto {PARAMETROS.paralelo_normalizar})")
    p.add_argument("--paralelo-bajar", type=int, default=PARAMETROS.paralelo_bajar,
                   help=f"archivos que se bajan a la vez por entrega (por defecto {PARAMETROS.paralelo_bajar})")
    p.add_argument("--soffice", help="ruta de LibreOffice, si no está en el PATH")
    p.add_argument("--registros", type=Path, help="archivo para los registros en JSON (sin él, solo advertencias por pantalla)")
    p.add_argument("--version", action="version", version=f"orquestar {VERSION}")
    return p.parse_args(argv)


def main(argv: list[str] | None = None, *, tablas: Tablas | None = None, origen: OrigenOneLake | None = None) -> int:
    args = _argumentos(argv)
    opciones_locales = (args.origen, args.proceso)
    opciones_onelake = (args.onelake_workspace, args.onelake_lakehouse, args.evento)
    es_onelake = any(valor is not None for valor in opciones_onelake)
    if es_onelake and any(valor is not None for valor in opciones_locales):
        print("Elija un solo modo de entrada: local o OneLake.", file=sys.stderr)
        return 2
    if es_onelake and not all(opciones_onelake):
        print("La entrada OneLake requiere --onelake-workspace, --onelake-lakehouse y --evento.", file=sys.stderr)
        return 2
    if not es_onelake and None in opciones_locales:
        print("La entrada local requiere --origen y --proceso. También puede elegir la entrada OneLake.",
              file=sys.stderr)
        return 2

    carpeta = args.origen.resolve() if args.origen is not None else None
    salida = args.salida.resolve()
    if carpeta is not None and not carpeta.is_dir():
        print("La carpeta del proceso no existe.", file=sys.stderr)
        return 2
    if dentro_de_un_repositorio(salida):
        print("La salida trae datos personales: elija una carpeta fuera de cualquier repositorio git.", file=sys.stderr)
        return 2
    if args.paralelo < 1:
        print("--paralelo debe ser 1 o más.", file=sys.stderr)
        return 2
    if args.paralelo_bajar < 1:
        print("--paralelo-bajar debe ser 1 o más.", file=sys.stderr)
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
        if es_onelake:
            try:
                if tablas is None:
                    tablas = TablasOneLake(args.onelake_workspace, args.onelake_lakehouse)
                entrada = armar_entrada(args.evento, tablas)
            except EventoRechazado as error:
                print(error, file=sys.stderr)
                return 2
            if origen is None:
                origen = OrigenOneLake(args.onelake_workspace, args.onelake_lakehouse)

        corrida = Corrida(
            origen=origen if es_onelake else OrigenLocal(carpeta.parent),
            almacen=AlmacenLocal(salida / "almacen"),
            clasificador=ClasificadorFalso(args.clasificacion),
            parametros=dataclasses.replace(PARAMETROS, paralelo_normalizar=args.paralelo,
                                           paralelo_bajar=args.paralelo_bajar),
            soffice=args.soffice,
        )
        cuerpo = entrada.aviso if es_onelake else aviso(args.proceso, carpeta.name, corrida.reloj)
        corrida.publicar_aviso(cuerpo)
        corrida.correr()
        resumen = {**conteos(corrida, cuerpo["id_proceso"]), "tiempo_s": round(time.perf_counter() - inicio, 1)}
        if es_onelake:
            resumen.update(
                archivos_del_aviso=len(cuerpo["archivos"]),
                excluidos_por_motivo=dict(entrada.excluidos),
                comprimidos_sin_contenido=len(cuerpo.get("comprimidos_sin_contenido", [])),
                **origen.conteos_descarga(),
            )
    finally:
        if archivo_registros:
            archivo_registros.close()

    guardar_salida(corrida, salida, resumen)

    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 1 if resumen["mensajes_en_errores"] else 0


if __name__ == "__main__":
    sys.exit(main())
