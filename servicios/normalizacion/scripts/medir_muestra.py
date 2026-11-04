"""Mide la normalización sobre una muestra real (criterios A3 a A5 de la spec 003).

    uv run python scripts/medir_muestra.py <carpeta_muestra> [--json] [--salida <carpeta>]

`<carpeta_muestra>` trae una subcarpeta por oferente, con sus archivos tal como los
entregó. Corre la normalización sobre cada una y imprime **solo conteos**: páginas
únicas, duplicados, restricciones, firmas, descartados, proporción de tipos de
página y tiempo por oferente, junto a lo que espera el diseño.

Se corre en la máquina del equipo, nunca en la nube (principio 6):

- Los oferentes salen como OF-001, OF-002…, en el orden de sus carpetas. Nunca se
  imprimen nombres de carpetas ni de archivos, ni texto de los documentos.
- La salida (PDF, lecturas, palabras) trae datos personales. Por defecto va a una
  carpeta temporal que se borra al terminar. Con `--salida` se conserva donde se
  indique, para revisar a mano; esa carpeta no se sube al repositorio.

Sale con 0 si todos los oferentes se procesaron, y con 1 si alguno tuvo una falla
inesperada (clase 4); los demás se procesan igual.
"""

import argparse
import json
import logging
import sys
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from normalizacion import VERSION, registros
from normalizacion.almacen import AlmacenLocal
from normalizacion.entrega import ErrorEntrega, normalizar_entrega
from normalizacion.parametros import PARAMETROS

TIPOS_DE_PAGINA = ("texto", "escaneo_con_ocr", "imagen", "vacia")

# Lo que encontró el diseño con la muestra SR5658940621 (6 oferentes).
DISENO = {
    "paginas_unicas": 415,
    "duplicados": 9,
    "con_restricciones": 15,
    "con_firma_digital": 7,
    "proporcion": {"texto": 0.76, "escaneo_con_ocr": 0.11, "imagen": 0.08, "vacia": 0.05},
    "segundos_por_oferente": 60,
}


@dataclass
class Medida:
    oferente: str
    segundos: float = 0.0
    falla_inesperada: bool = False
    archivos: int = 0
    normalizados: int = 0
    duplicados: int = 0
    con_error: int = 0
    errores: dict = field(default_factory=dict)
    descartados: int = 0
    descartados_por_motivo: dict = field(default_factory=dict)
    paginas_unicas: int = 0
    tipos_de_pagina: dict = field(default_factory=dict)
    con_restricciones: int = 0
    reparados: int = 0
    con_firma_digital: int = 0
    firmas: int = 0
    firmas_leidas: int = 0
    firmas_no_leidas: int = 0
    firmas_no_integras: int = 0
    convertidos: int = 0
    con_anexo: int = 0


def medir(manifiesto: dict, tipos_de_pagina: Counter, medida: Medida) -> Medida:
    """Conteos de un manifiesto. Solo números: nada de rutas ni de texto."""
    archivos = manifiesto["archivos"]
    normalizados = [a for a in archivos if a["estado"] == "normalizado"]
    firmas = [f for a in normalizados for f in a["firma_digital"]]
    medida.archivos = len(archivos)
    medida.normalizados = len(normalizados)
    medida.duplicados = sum(1 for a in archivos if a["estado"] == "duplicado")
    medida.con_error = sum(1 for a in archivos if a["estado"] == "error_entrada")
    medida.errores = dict(sorted(Counter(a["error"]["codigo"] for a in archivos if a["error"]).items()))
    medida.descartados = len(manifiesto["descartados"])
    medida.descartados_por_motivo = dict(sorted(Counter(d["motivo"] for d in manifiesto["descartados"]).items()))
    medida.paginas_unicas = sum(a["paginas"] for a in normalizados)
    medida.tipos_de_pagina = {tipo: tipos_de_pagina.get(tipo, 0) for tipo in TIPOS_DE_PAGINA}
    medida.con_restricciones = sum(1 for a in normalizados if a["restricciones"])
    medida.reparados = sum(1 for a in normalizados if a["reparado"])
    medida.con_firma_digital = sum(1 for a in normalizados if a["firma_digital"])
    medida.firmas = len(firmas)
    medida.firmas_leidas = sum(1 for f in firmas if f["leida"])
    medida.firmas_no_leidas = sum(1 for f in firmas if not f["leida"])
    medida.firmas_no_integras = sum(1 for f in firmas if f["leida"] and not f["integro"])
    medida.convertidos = sum(1 for a in normalizados if a["tipo_origen"] != "pdf")
    medida.con_anexo = sum(1 for a in normalizados if a["anexo_nativo"])
    return medida


def medir_oferente(carpeta: Path, id_oferente: str, salida: Path, proceso: str) -> Medida:
    medida = Medida(oferente=id_oferente)
    inicio = time.perf_counter()
    try:
        resultado = normalizar_entrega(carpeta, proceso, id_oferente, AlmacenLocal(salida), forzar=True)
    except ErrorEntrega:
        medida.falla_inesperada = True
        medida.segundos = round(time.perf_counter() - inicio, 1)
        return medida
    medida.segundos = round(time.perf_counter() - inicio, 1)
    return medir(resultado.manifiesto, resultado.tipos_de_pagina, medida)


def total(medidas: list[Medida]) -> Medida:
    suma = Medida(oferente="TOTAL")
    for medida in medidas:
        for nombre, valor in asdict(medida).items():
            if nombre == "oferente":
                continue
            if isinstance(valor, bool):
                setattr(suma, nombre, getattr(suma, nombre) or valor)
            elif isinstance(valor, dict):
                acumulado = Counter(getattr(suma, nombre))
                acumulado.update(valor)
                setattr(suma, nombre, dict(sorted(acumulado.items())))
            else:
                setattr(suma, nombre, round(getattr(suma, nombre) + valor, 1))
    suma.tipos_de_pagina = {tipo: suma.tipos_de_pagina.get(tipo, 0) for tipo in TIPOS_DE_PAGINA}
    return suma


def proporcion(tipos: dict) -> dict:
    paginas = sum(tipos.values())
    return {tipo: (tipos.get(tipo, 0) / paginas if paginas else 0.0) for tipo in TIPOS_DE_PAGINA}


# ---------------------------------------------------------------------------
# Salida


def _porcentaje(valor: float) -> str:
    return f"{valor * 100:.0f} %"


def tabla(medidas: list[Medida], suma: Medida) -> str:
    columnas = [
        ("oferente", "Oferente"),
        ("segundos", "Seg."),
        ("archivos", "Archivos"),
        ("normalizados", "Normal."),
        ("duplicados", "Dupl."),
        ("con_error", "Error"),
        ("descartados", "Desc."),
        ("paginas_unicas", "Páginas"),
        ("con_restricciones", "Restr."),
        ("con_firma_digital", "Firma"),
        ("reparados", "Repar."),
    ]
    filas = [[titulo for _, titulo in columnas]]
    for medida in [*medidas, suma]:
        fila = [str(getattr(medida, nombre)) for nombre, _ in columnas]
        if medida.falla_inesperada:
            fila = [medida.oferente, str(medida.segundos), "FALLA INESPERADA"] + [""] * (len(columnas) - 3)
        filas.append(fila)
    anchos = [max(len(fila[i]) for fila in filas) for i in range(len(columnas))]
    lineas = ["  ".join(valor.rjust(ancho) for valor, ancho in zip(fila, anchos)).rstrip() for fila in filas]
    lineas.insert(1, "  ".join("-" * ancho for ancho in anchos))
    lineas.insert(len(lineas) - 1, "  ".join("-" * ancho for ancho in anchos))
    return "\n".join(lineas)


def informe(medidas: list[Medida], proceso: str) -> str:
    suma = total(medidas)
    procesados = [m for m in medidas if not m.falla_inesperada]
    partes = [
        f"Muestra {proceso}: {len(medidas)} oferentes. Normalizador {VERSION}, parámetros {PARAMETROS.version}.",
        "",
        tabla(medidas, suma),
        "",
        "A3. Conteos frente al diseño",
        f"  Páginas únicas:            {suma.paginas_unicas:>5}   (diseño: unas {DISENO['paginas_unicas']})",
        f"  Copias exactas:            {suma.duplicados:>5}   (diseño: {DISENO['duplicados']})",
        f"  PDF con restricciones:     {suma.con_restricciones:>5}   (diseño: {DISENO['con_restricciones']}, todos leídos)",
        f"  PDF con firma digital:     {suma.con_firma_digital:>5}   (diseño: {DISENO['con_firma_digital']})",
        f"    firmas leídas / no leídas / no íntegras: "
        f"{suma.firmas_leidas} / {suma.firmas_no_leidas} / {suma.firmas_no_integras}",
        f"  Descartados:               {suma.descartados:>5}   {suma.descartados_por_motivo or ''}",
        f"  Con error:                 {suma.con_error:>5}   {suma.errores or ''}",
        f"  Reparados:                 {suma.reparados:>5}",
        f"  Convertidos a PDF:         {suma.convertidos:>5}   (con anexo de hoja de cálculo: {suma.con_anexo})",
        "",
        "A4. Proporción de tipos de página frente al diseño",
    ]
    medida = proporcion(suma.tipos_de_pagina)
    for tipo in TIPOS_DE_PAGINA:
        partes.append(
            f"  {tipo:<16} {suma.tipos_de_pagina[tipo]:>5} páginas  {_porcentaje(medida[tipo]):>5}"
            f"   (diseño: {_porcentaje(DISENO['proporcion'][tipo])})"
        )
    segundos = [m.segundos for m in procesados]
    partes += [
        "",
        "A5. Tiempo por oferente",
        f"  Promedio: {sum(segundos) / len(segundos):.1f} s   Máximo: {max(segundos):.1f} s"
        f"   (diseño: del orden de {DISENO['segundos_por_oferente']} s)"
        if segundos
        else "  Sin oferentes procesados.",
    ]
    fallidos = [m.oferente for m in medidas if m.falla_inesperada]
    if fallidos:
        partes += ["", f"Falla inesperada en: {', '.join(fallidos)}. Revisar el registro (stderr)."]
    return "\n".join(partes)


# ---------------------------------------------------------------------------


def oferentes(carpeta: Path) -> list[Path]:
    """Subcarpetas de la muestra, una por oferente, en orden. Ignora las ocultas."""
    return sorted(p for p in carpeta.iterdir() if p.is_dir() and not p.name.startswith("."))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mide la normalización sobre una muestra real (A3 a A5).")
    parser.add_argument("carpeta", type=Path, help="Carpeta con una subcarpeta por oferente.")
    parser.add_argument("--proceso", default="MUESTRA", help="Identificador del proceso para la salida.")
    parser.add_argument("--salida", type=Path, help="Conservar la salida aquí. Sin esto, se borra al terminar.")
    parser.add_argument("--json", action="store_true", help="Imprimir los conteos en JSON en vez de la tabla.")
    parser.add_argument("--detalle", action="store_true", help="Registros de cada documento en stderr (sin nombres).")
    argumentos = parser.parse_args(argv)
    if not argumentos.carpeta.is_dir():
        parser.error("la carpeta de la muestra no existe o no es una carpeta")

    registros.configurar(logging.INFO if argumentos.detalle else logging.WARNING)
    carpetas = oferentes(argumentos.carpeta)
    if not carpetas:
        parser.error("la carpeta de la muestra no tiene subcarpetas de oferentes")

    with tempfile.TemporaryDirectory(prefix="muestra-") as temporal:
        salida = argumentos.salida or Path(temporal)
        medidas = []
        for numero, carpeta in enumerate(carpetas, start=1):
            id_oferente = f"OF-{numero:03d}"
            print(f"Procesando {id_oferente} ({numero} de {len(carpetas)})…", file=sys.stderr)
            medidas.append(medir_oferente(carpeta, id_oferente, salida, argumentos.proceso))

    if argumentos.json:
        suma = total(medidas)
        datos = {
            "proceso": argumentos.proceso,
            "version_normalizador": VERSION,
            "version_parametros": PARAMETROS.version,
            "oferentes": [asdict(m) for m in medidas],
            "total": asdict(suma),
            "proporcion_tipos_de_pagina": proporcion(suma.tipos_de_pagina),
            "diseno": DISENO,
        }
        print(json.dumps(datos, ensure_ascii=False, indent=2))
    else:
        print(informe(medidas, argumentos.proceso))
    return 1 if any(m.falla_inesperada for m in medidas) else 0


if __name__ == "__main__":
    sys.exit(main())
