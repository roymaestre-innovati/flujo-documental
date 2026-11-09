"""Corre el orquestador sobre la muestra real, con la clasificación manual como
clasificador falso (criterio A4 de la spec 005, tarea T11).

    uv run python scripts/correr_muestra.py --manifiesto <manifiesto.csv> \\
        --muestra <carpeta> [--muestra <carpeta> ...] [--salida <carpeta>]

- Cada `--muestra` trae una subcarpeta por oferente, con sus archivos tal como
  los entregó. Los oferentes salen como OF-001, OF-002…, en el orden de las
  carpetas (primero las de la primera `--muestra`), igual que en la medición de
  la normalización.
- `manifiesto.csv` es la clasificación manual (columnas `tipo_documental`,
  `oferente`, `archivo`, `origen` y `nota`). `origen` es la ruta del archivo con
  una carpeta de más al principio y, si la clasificación es de unas páginas, un
  sufijo como ` (p4-33)`. Cada oferente del manifiesto se empareja con la
  carpeta donde están sus archivos.

Se corre en la máquina del equipo, nunca en la nube (principio 6). Por pantalla
salen **solo conteos**: nunca nombres de carpetas, de archivos ni de oferentes.
La salida trae datos personales. Por defecto va a una carpeta temporal que se
borra al terminar; con `--salida` se conserva, fuera de cualquier repositorio.

Sale con 0 si ningún mensaje quedó en errores y ningún registro quedó atascado,
y con 1 si no.
"""

import argparse
import csv
import dataclasses
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pikepdf
from normalizacion.almacen import AlmacenLocal

from orquestador.cli import dentro_de_un_repositorio
from orquestador.clasificador import COLUMNAS, ClasificadorFalso
from orquestador.local import Corrida, aviso, conteos, guardar_salida
from orquestador.origen import OrigenLocal
from orquestador.parametros import PARAMETROS
from orquestador.registros import configurar

PROCESO = "SR5658940621"
SIN_CLASIFICAR = "SIN CLASIFICAR"
"""La persona no le encontró tipo: se trata como TD-99 (no identificado)."""
PAGINAS = re.compile(r" \(p(\d+)(?:-(\d+))?\)$")


def _nfc(texto: str) -> str:
    return unicodedata.normalize("NFC", texto)


@dataclass(frozen=True)
class Fila:
    oferente: str
    ruta: str
    """Relativa a la carpeta del oferente, sin la carpeta de más."""
    paginas: tuple[int, int] | None
    tipo_documental: str


def leer_manifiesto(ruta: Path) -> list[Fila]:
    filas = []
    with open(ruta, encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            origen = _nfc(fila["origen"].strip())
            paginas = None
            if m := PAGINAS.search(origen):
                desde = int(m.group(1))
                paginas = (desde, int(m.group(2) or desde))
                origen = origen[: m.start()]
            partes = PurePosixPath(origen).parts
            ruta_relativa = PurePosixPath(*partes[1:]).as_posix() if len(partes) > 1 else origen
            td = fila["tipo_documental"].strip()
            filas.append(Fila(fila["oferente"].strip(), ruta_relativa, paginas, "TD-99" if td == SIN_CLASIFICAR else td))
    return filas


def archivos_de(carpeta: Path) -> set[str]:
    return {_nfc(p.relative_to(carpeta).as_posix()) for p in carpeta.rglob("*") if p.is_file()}


def emparejar(filas: list[Fila], carpetas: list[set[str]]) -> tuple[dict[str, int], Counter]:
    """A cada oferente del manifiesto, la carpeta con más de sus archivos.

    Devuelve el emparejamiento (oferente → índice de carpeta) y conteos.
    """
    coincidencias: dict[str, Counter] = defaultdict(Counter)
    for fila in filas:
        for i, archivos in enumerate(carpetas):
            if fila.ruta in archivos:
                coincidencias[fila.oferente][i] += 1
    pares: dict[str, int] = {}
    # Primero los oferentes con más coincidencias, para que no les gane la carpeta otro.
    for oferente, cuentas in sorted(coincidencias.items(), key=lambda x: -x[1].most_common(1)[0][1]):
        libres = [(n, i) for i, n in cuentas.items() if i not in pares.values()]
        if libres:
            pares[oferente] = max(libres)[1]
    oferentes = {f.oferente for f in filas}
    return pares, Counter({
        "oferentes_en_el_manifiesto": len(oferentes),
        "oferentes_sin_carpeta": len(oferentes - pares.keys()),
        "carpetas_sin_clasificacion": len(carpetas) - len(pares),
    })


def paginas_del_pdf(ruta: Path) -> int | None:
    try:
        with pikepdf.open(ruta) as pdf:
            return len(pdf.pages)
    except Exception:  # noqa: BLE001 - cifrado o dañado: se clasifica entero
        return None


def filas_del_clasificador(filas: list[Fila], pares: dict[str, int], carpetas: list[Path],
                           ids: list[str]) -> tuple[list[dict], Counter]:
    """Las filas del CSV del clasificador falso, y conteos de lo que se hizo.

    - Un archivo con varias filas sin páginas: se queda la primera.
    - Un archivo clasificado por páginas: los huecos se llenan con TD-99, para
      que el clasificador falso cubra todas las páginas. Si no se puede contar
      las páginas del PDF, se usa el tipo de la primera fila para todo.
    """
    cuentas = Counter()
    por_archivo: dict[tuple[int, str], list[Fila]] = defaultdict(list)
    archivos = [archivos_de(c) for c in carpetas]
    for fila in filas:
        i = pares.get(fila.oferente)
        if i is None or fila.ruta not in archivos[i]:
            cuentas["filas_sin_archivo"] += 1
            continue
        cuentas["filas_usadas"] += 1
        por_archivo[(i, fila.ruta)].append(fila)

    salida = []

    def fila_csv(i, ruta, td, desde="", hasta=""):
        salida.append({"id_oferente": ids[i], "ruta_origen": ruta, "pagina_inicio": desde, "pagina_fin": hasta,
                       "tipo_documental": td, "confianza": "1.0", "subtipo": ""})

    for (i, ruta), grupo in sorted(por_archivo.items()):
        con_paginas = sorted((f for f in grupo if f.paginas), key=lambda f: f.paginas)
        enteras = [f for f in grupo if not f.paginas]
        total = paginas_del_pdf(carpetas[i] / ruta) if con_paginas else None
        if not con_paginas or enteras or total is None:
            if len(grupo) > 1:
                cuentas["archivos_con_filas_de_mas"] += 1
            fila_csv(i, ruta, (enteras or grupo)[0].tipo_documental)
            continue
        cuentas["archivos_por_paginas"] += 1
        siguiente = 1
        for f in con_paginas:
            desde, hasta = f.paginas
            if desde < siguiente or hasta > total:
                cuentas["rangos_descartados"] += 1
                continue
            if desde > siguiente:
                fila_csv(i, ruta, "TD-99", siguiente, desde - 1)
                cuentas["huecos_como_td99"] += 1
            fila_csv(i, ruta, f.tipo_documental, desde, hasta)
            siguiente = hasta + 1
        if siguiente <= total:
            fila_csv(i, ruta, "TD-99", siguiente, total)
            cuentas["huecos_como_td99"] += 1
    return salida, cuentas


def armar_proceso(carpetas: list[Path], ids: list[str], destino: Path) -> None:
    """La carpeta del proceso como la dejará el módulo 1: una subcarpeta por
    oferente, nombrada con su identificador. Enlaces duros si se puede."""
    for carpeta, id_oferente in zip(carpetas, ids):
        for archivo in carpeta.rglob("*"):
            if not archivo.is_file():
                continue
            nuevo = destino / id_oferente / archivo.relative_to(carpeta)
            nuevo.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(archivo, nuevo)
            except OSError:
                shutil.copy2(archivo, nuevo)


def correr(manifiesto: Path, muestras: list[Path], salida: Path, proceso: str, paralelo: int,
           soffice: str | None = None) -> dict:
    carpetas = [c for m in muestras for c in sorted(p for p in m.iterdir() if p.is_dir())]
    ids = [f"OF-{n:03d}" for n in range(1, len(carpetas) + 1)]
    filas = leer_manifiesto(manifiesto)
    pares, emparejamiento = emparejar(filas, [archivos_de(c) for c in carpetas])
    filas_csv, cuentas = filas_del_clasificador(filas, pares, carpetas, ids)
    emparejamiento.update(cuentas)
    emparejamiento["filas_del_manifiesto"] = len(filas)
    emparejamiento["sin_clasificar_como_td99"] = sum(
        1 for f in csv.DictReader(open(manifiesto, encoding="utf-8")) if f["tipo_documental"].strip() == SIN_CLASIFICAR)

    csv_clasificador = salida / "clasificacion.csv"
    with open(csv_clasificador, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=[*COLUMNAS, "subtipo"])
        escritor.writeheader()
        escritor.writerows(filas_csv)
    raiz_origen = salida / "origen"
    armar_proceso(carpetas, ids, raiz_origen / proceso)

    inicio = time.perf_counter()
    corrida = Corrida(
        origen=OrigenLocal(raiz_origen),
        almacen=AlmacenLocal(salida / "almacen"),
        clasificador=ClasificadorFalso(csv_clasificador),
        parametros=dataclasses.replace(PARAMETROS, paralelo_normalizar=paralelo),
        soffice=soffice,
    )
    corrida.publicar_aviso(aviso(proceso, proceso, corrida.reloj))
    corrida.correr()
    resumen = {
        "oferentes": len(carpetas),
        "emparejamiento": dict(sorted(emparejamiento.items())),
        **conteos(corrida, proceso),
        "tiempo_s": round(time.perf_counter() - inicio, 1),
    }
    guardar_salida(corrida, salida, resumen)
    return resumen


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Corre el orquestador sobre la muestra real. Imprime solo conteos.")
    p.add_argument("--manifiesto", type=Path, required=True, help="manifiesto.csv de la clasificación manual")
    p.add_argument("--muestra", type=Path, action="append", required=True,
                   help="carpeta con una subcarpeta por oferente; se puede repetir")
    p.add_argument("--salida", type=Path, help="conservar la salida aquí (fuera de cualquier repositorio)")
    p.add_argument("--proceso", default=PROCESO)
    p.add_argument("--paralelo", type=int, default=PARAMETROS.paralelo_normalizar)
    p.add_argument("--soffice", help="ruta de LibreOffice, si no está en el PATH")
    args = p.parse_args(argv)

    for m in args.muestra:
        if not m.is_dir():
            print("Una de las carpetas de la muestra no existe.", file=sys.stderr)
            return 2
    configurar(30, sys.stderr)  # solo advertencias, y solo con identificadores

    if args.salida:
        salida = args.salida.resolve()
        if dentro_de_un_repositorio(salida):
            print("La salida trae datos personales: elija una carpeta fuera de cualquier repositorio git.",
                  file=sys.stderr)
            return 2
        if salida.exists() and any(salida.iterdir()):
            print("La carpeta de salida debe estar vacía.", file=sys.stderr)
            return 2
        salida.mkdir(parents=True, exist_ok=True)
        resumen = correr(args.manifiesto, args.muestra, salida, args.proceso, args.paralelo, args.soffice)
    else:
        with tempfile.TemporaryDirectory(prefix="muestra-orquestador-") as temporal:
            resumen = correr(args.manifiesto, args.muestra, Path(temporal), args.proceso, args.paralelo, args.soffice)

    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 1 if resumen["mensajes_en_errores"] or resumen["atascados"] else 0


if __name__ == "__main__":
    sys.exit(main())
