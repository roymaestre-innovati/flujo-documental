"""`medir-gold`: exactitud de la extracción contra el gold de un tipo documental (T10, criterio A9).

    medir-gold <carpeta TD-NN> --trabajo <carpeta fuera del repo>
               [--documentos <carpeta de los PDF>] [--modelo mcp|archivo:<ficha.json>] [--version 21]
               [--lote <carpeta de una corrida de lote.py>] [--solo-comparar] [--si-mando-documentos]

Normaliza cada PDF del TD, lo extrae con el servicio (gpt-5.4, un segmento por
documento) y compara campo a campo con `gold_TD-NN.xlsx`. Al lado pone la misma
medida sobre la última corrida de `lote.py` de esa carpeta, con los mismos
documentos. **Manda los documentos a gpt-5.4:** solo con autorización, y lo corre
el usuario. Una segunda corrida usa los resultados guardados en `--trabajo` y no
vuelve a llamar al LLM.

Por pantalla salen solo conteos por campo, tokens y tiempo: nunca valores, citas
ni nombres de documentos (principio 6).

**El gold** (hoja `Valores`): una fila por documento, campo y propiedad. El valor
esperado sale de `Estado`:

| Estado                       | Valor esperado                          |
|------------------------------|-----------------------------------------|
| Corregido                    | `Valor en el documento`                 |
| Igual al prellenado, o vacío | `Prellenado` (vacío y sin prellenado: la fila no cuenta) |
| No aparece en el documento   | ninguno (acierta si el LLM da `null`)   |
| Ilegible                     | la fila no cuenta                       |

Los registros de una lista van en una columna numérica aparte (TD-29) o al
principio de `Propiedad` ("1. rol", TD-16). Una propiedad `(valor)` es el valor
entero del campo.

**El acierto** es por propiedad, con los registros por posición, como
`comparar_con_gold.py` de TD-29: se comparan sin tildes, sin mayúsculas, con los
espacios juntos y los números leídos: `1.234.567,8` (con puntos de miles),
`1,234,567.8` y `1234,8` se leen como números. Un número con un solo punto y tres
decimales (`1.234`) se lee como mil doscientos treinta y cuatro. Dos textos de más de
15 caracteres aciertan si uno contiene al otro.
"""

import argparse
import datetime
import json
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from normalizacion.almacen import CARPETA_ALMACEN, AlmacenLocal
from normalizacion.entrega import normalizar_entrega

from . import CONTRATO
from .cli import CARPETA_FICHAS, CARPETA_RESULTADOS, ErrorDeUso, _confirmar, _fuente, _llm_azure, correr, dentro_de_un_repositorio
from .ficha import FuenteModelo, FuenteQueGuarda
from .llamada import Llamador
from .llm import ClienteLLM
from .parametros import parametros
from .reloj import RelojSistema
from .resultados import Clave, ResultadosEnCarpeta
from .servicio import Servicio

CONOCIDAS = {"Documento", "Campo", "Propiedad", "Prellenado", "Estado", "Valor en el documento", "Comentario", "id_tecnico"}
VALOR_ENTERO = "(valor)"
CORREGIDO, NO_APARECE, ILEGIBLE = "Corregido", "No aparece en el documento", "Ilegible"
ENTREGA = "OF-001"


class GoldInvalido(ValueError):
    """La hoja no tiene la forma esperada. El mensaje nombra columnas, nunca valores."""


@dataclass(frozen=True)
class Fila:
    documento: str
    """El nombre del PDF sin `.pdf`."""
    id_tecnico: str
    registro: int | None
    propiedad: str
    esperado: object


# --- El gold ---

def _documento(nombre: str) -> str:
    return nombre[:-4] if nombre.lower().endswith(".pdf") else nombre


def leer_gold(ruta: Path) -> list[Fila]:
    import openpyxl

    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    if "Valores" not in libro.sheetnames:
        raise GoldInvalido("El gold no tiene la hoja 'Valores'")
    filas = list(libro["Valores"].iter_rows(values_only=True))
    libro.close()
    if not filas:
        raise GoldInvalido("La hoja 'Valores' está vacía")
    cabecera = [str(c).strip() if c is not None else "" for c in filas[0]]
    faltan = [c for c in ("Documento", "Propiedad", "Prellenado", "id_tecnico") if c not in cabecera]
    if faltan:
        raise GoldInvalido(f"Faltan columnas en 'Valores': {', '.join(faltan)}")
    columna = {c: i for i, c in enumerate(cabecera) if c}
    otras = [i for i, c in enumerate(cabecera) if c not in CONOCIDAS
             and all(f[i] is None or isinstance(f[i], int) for f in filas[1:] if i < len(f))
             and any(i < len(f) and f[i] is not None for f in filas[1:])]
    if len(otras) > 1:
        raise GoldInvalido("Hay más de una columna numérica que podría ser el registro")
    col_registro = otras[0] if otras else None

    def celda(fila, nombre):
        i = columna.get(nombre)
        return fila[i] if i is not None and i < len(fila) else None

    salida = []
    for fila in filas[1:]:
        documento, id_tecnico = celda(fila, "Documento"), celda(fila, "id_tecnico")
        if not documento or not id_tecnico:
            continue
        propiedad = str(celda(fila, "Propiedad") or VALOR_ENTERO).strip()
        registro = fila[col_registro] if col_registro is not None and col_registro < len(fila) else None
        if registro is None and (numerada := re.fullmatch(r"(\d+)\.\s*(.+)", propiedad)):
            registro, propiedad = int(numerada.group(1)), numerada.group(2).strip()
        estado = str(celda(fila, "Estado") or "").strip()
        if estado == ILEGIBLE:
            continue
        if estado == CORREGIDO:
            esperado = celda(fila, "Valor en el documento")
        elif estado == NO_APARECE:
            esperado = None
        else:
            esperado = celda(fila, "Prellenado")
            if esperado is None and not estado:
                continue  # sin revisar y sin prellenado: no hay con qué comparar
        salida.append(Fila(_documento(str(documento)), str(id_tecnico), registro, propiedad, esperado))
    return salida


# --- El acierto ---

def normalizar(valor):
    if valor is None:
        return None
    if isinstance(valor, (datetime.datetime, datetime.date)):
        # Una fecha que Excel guardó como fecha se compara como la escribe el LLM.
        valor = valor.date().isoformat() if isinstance(valor, datetime.datetime) else valor.isoformat()
    texto = unicodedata.normalize("NFKD", str(valor).strip()).encode("ascii", "ignore").decode().upper()
    texto = re.sub(r"\s+", " ", texto)
    if not texto:
        return None
    numero = re.sub(r"[$\s]", "", texto)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", numero):     # 1.234.567,89 (Colombia)
        numero = numero.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", numero):   # 1,234,567.89
        numero = numero.replace(",", "")
    elif re.fullmatch(r"\d+,\d+", numero):                    # 1234,5
        numero = numero.replace(",", ".")
    if re.fullmatch(r"\d+(\.\d+)?", numero):
        return float(numero)
    return texto.rstrip(".")


def obtenido(valor_campo, registro: int | None, propiedad: str):
    valor = valor_campo
    if registro:
        valor = (valor[registro - 1] if isinstance(valor, list) and len(valor) >= registro else None) or {}
    if propiedad == VALOR_ENTERO:
        return valor
    return valor.get(propiedad) if isinstance(valor, dict) else None


def acierta(esperado, valor) -> bool:
    a, b = normalizar(esperado), normalizar(valor)
    if a == b:
        return True
    return isinstance(a, str) and isinstance(b, str) and min(len(a), len(b)) > 15 and (a in b or b in a)


Corrida = dict[str, list[dict]]
"""Por documento (nombre sin `.pdf`), los valores por `id_tecnico` de cada repetición."""


def comparar(filas: list[Fila], corrida: Corrida, documentos: set[str]) -> dict[str, list[int]]:
    """Aciertos y total por `id_tecnico`, solo en esos documentos."""
    cuenta: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for fila in filas:
        if fila.documento not in documentos:
            continue
        for valores in corrida.get(fila.documento, []):
            ok = acierta(fila.esperado, obtenido(valores.get(fila.id_tecnico), fila.registro, fila.propiedad))
            cuenta[fila.id_tecnico][0] += ok
            cuenta[fila.id_tecnico][1] += 1
    return dict(cuenta)


# --- Las corridas ---

def ultima_corrida_de_lote(carpeta_td: Path, td: str) -> Path | None:
    candidatas = sorted(p for p in carpeta_td.glob(f"*_{td}_*") if p.is_dir())
    return candidatas[-1] if candidatas else None


def leer_lote(carpeta: Path) -> tuple[Corrida, dict]:
    corrida: Corrida = defaultdict(list)
    gasto = Counter()
    for archivo in sorted(carpeta.glob("*.json")):
        try:
            d = json.loads(archivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            gasto["ilegibles"] += 1
            continue
        if d.get("error") or not isinstance(d.get("resultados"), list):
            gasto["con_error"] += 1
            continue
        corrida[_documento(d["documento"])].append({r["id_tecnico"]: r.get("valor") for r in d["resultados"] if "id_tecnico" in r})
        gasto["respuestas"] += 1
        gasto["tokens_entrada"] += (d.get("tokens") or {}).get("entrada", 0)
        gasto["tokens_salida"] += (d.get("tokens") or {}).get("salida", 0)
        gasto["segundos"] += d.get("segundos") or 0
    return dict(corrida), dict(gasto)


def solicitud_de(documento: dict, lectura: dict, td: str, version: int, id_proceso: str) -> dict:
    return {
        "contrato": CONTRATO,
        "id_proceso": id_proceso,
        "id_oferente": ENTREGA,
        "id_segmento": f"{documento['id_documento']}-p1-{len(lectura['paginas'])}",
        "id_documento": documento["id_documento"],
        "archivo": {"uri": documento["pdf"], "sha256": lectura["hash_pdf"]},
        "paginas": {"desde": 1, "hasta": len(lectura["paginas"])},
        "tipo_documental": td,
        "lectura": documento["lectura"],
        "anexos": [documento["anexo_nativo"]] if documento.get("anexo_nativo") else [],
        "clasificacion_dudosa": False,
        "version_modelo": version,
    }


def preparar(pdfs: list[Path], trabajo: Path, td: str, version: int) -> list[tuple[str, dict]]:
    """Normaliza los PDF (local) y arma una solicitud por documento: (nombre sin `.pdf`, solicitud)."""
    import shutil

    id_proceso = f"GOLD-{td}"
    entrega = trabajo / "entregas" / ENTREGA
    entrega.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        destino = entrega / pdf.name
        if not destino.exists():
            shutil.copyfile(pdf, destino)
    almacen = AlmacenLocal(trabajo / CARPETA_ALMACEN)
    manifiesto = normalizar_entrega(entrega, id_proceso, ENTREGA, almacen).manifiesto
    por_id = {a["id_documento"]: a for a in manifiesto["archivos"]}
    nombres = {p.name for p in pdfs}
    salida = []
    for archivo in manifiesto["archivos"]:
        if archivo["ruta_origen"] not in nombres:
            continue
        original = por_id.get(archivo.get("duplicado_de")) if archivo["estado"] == "duplicado" else archivo
        if not original or original["estado"] != "normalizado":
            continue
        lectura = json.loads(almacen.leer(original["lectura"]))
        salida.append((_documento(archivo["ruta_origen"]), solicitud_de(original, lectura, td, version, id_proceso)))
    return salida


def correr_servicio(solicitudes: list[tuple[str, dict]], trabajo: Path, fuente: FuenteModelo, cliente: ClienteLLM | None,
                    concurrencia: int) -> tuple[Corrida, dict]:
    """Extrae (si `cliente`) y lee los resultados guardados. Sin `cliente`, solo lee."""
    resultados = ResultadosEnCarpeta(trabajo / CARPETA_RESULTADOS)
    resumen = {}
    if cliente is not None:
        reloj = RelojSistema()
        servicio = Servicio(
            almacen=AlmacenLocal(trabajo / CARPETA_ALMACEN),
            fuente=FuenteQueGuarda(fuente, trabajo / CARPETA_RESULTADOS / CARPETA_FICHAS),
            llamador=Llamador(cliente, reloj, {**parametros()["llamada"], "concurrencia": concurrencia}),
            resultados=resultados, reloj=reloj,
        )
        # Un documento repetido en el gold se extrae una sola vez.
        unicas = list({s["id_segmento"]: s for _, s in solicitudes}.values())
        resumen = correr(unicas, servicio, hilos=concurrencia * 2, forzar=False)
    corrida: Corrida = {}
    gasto = Counter()
    contados = set()
    for nombre, solicitud in solicitudes:
        resultado = resultados.buscar(Clave.de(solicitud))
        if resultado is not None and resultado["estado"] == "ok":
            corrida[nombre] = [{r["id_tecnico"]: r["valor"] for r in resultado["resultados"]}]
        # El gasto, una vez por documento extraído (una copia exacta usa el resultado del original).
        if solicitud["id_segmento"] in contados:
            continue
        contados.add(solicitud["id_segmento"])
        if resultado is None:
            gasto["sin_resultado"] += 1
            continue
        gasto[f"estado_{resultado['estado']}"] += 1
        if resultado["estado"] != "ok":
            continue
        ejecucion = resultado["ejecucion"]
        gasto["respuestas"] += 1
        gasto["tokens_entrada"] += ejecucion.get("tokens_entrada", 0)
        gasto["tokens_salida"] += ejecucion.get("tokens_salida", 0)
        gasto["segundos"] += ejecucion.get("duracion_ms", 0) / 1000
        gasto["campos_en_revision"] += len(resultado["campos_en_revision"])
        gasto["campos"] += len(resultado["resultados"])
    return corrida, {**dict(gasto), "fallas_internas": resumen.get("fallas_internas", 0)}


# --- El informe ---

def _proporcion(par) -> str:
    if not par or not par[1]:
        return "—"
    return f"{par[0]}/{par[1]} ({par[0] / par[1]:.0%})"


def informe(td: str, filas: list[Fila], servicio: tuple[Corrida, dict], lote: tuple[Corrida, dict] | None,
            nombre_lote: str | None) -> tuple[str, int]:
    """El texto que se imprime, solo con conteos, y cuántos campos bajan frente a lote.py."""
    del_servicio, gasto_servicio = servicio
    documentos_gold = {f.documento for f in filas}
    comunes = documentos_gold & set(del_servicio)
    if lote:
        comunes &= set(lote[0])
    s = comparar(filas, del_servicio, comunes)
    l = comparar(filas, lote[0], comunes) if lote else {}
    total = lambda c: [sum(a for a, _ in c.values()), sum(t for _, t in c.values())]
    lineas = [
        f"Gold {td}: {len(documentos_gold)} documentos, {len(filas)} filas que cuentan.",
        f"Servicio: {len(set(del_servicio) & documentos_gold)} documentos con resultado ok."
        + (f" lote.py ({nombre_lote}): {len(set(lote[0]) & documentos_gold)} documentos." if lote else " Sin corrida de lote.py."),
        f"Se comparan los {len(comunes)} documentos que están en todas.",
        "",
        f"{'Campo':<34} {'Servicio':>16} {'lote.py':>16}  ",
    ]
    bajan = 0
    for id_tecnico in sorted(set(s) | set(l)):
        ps, pl = s.get(id_tecnico), l.get(id_tecnico)
        baja = bool(ps and pl and pl[1] and ps[1] and ps[0] / ps[1] < pl[0] / pl[1])
        bajan += baja
        lineas.append(f"{id_tecnico:<34} {_proporcion(ps):>16} {_proporcion(pl):>16}  {'baja' if baja else ''}")
    lineas += [
        f"{'Total':<34} {_proporcion(total(s)):>16} {_proporcion(total(l)) if lote else '—':>16}",
        "",
        _gasto("Servicio", gasto_servicio),
    ]
    if lote:
        lineas.append(_gasto("lote.py", lote[1]))
    lineas += ["", f"A9: {'la exactitud baja en ' + str(bajan) + ' campo(s)' if bajan else 'ningún campo baja'} frente a lote.py."
               if lote else "A9: sin corrida de lote.py para comparar."]
    return "\n".join(lineas), bajan


def _gasto(nombre: str, g: dict) -> str:
    respuestas = g.get("respuestas", 0)
    por = lambda clave: round(g.get(clave, 0) / respuestas) if respuestas else 0
    partes = [f"{nombre}: {respuestas} respuestas", f"tokens {g.get('tokens_entrada', 0)}+{g.get('tokens_salida', 0)}",
              f"por respuesta {por('tokens_entrada')}+{por('tokens_salida')}", f"{g.get('segundos', 0):.0f} s"]
    if "campos" in g:
        partes.append(f"campos en revisión {g.get('campos_en_revision', 0)}/{g['campos']}")
    otros = {k: v for k, v in g.items()
             if k.startswith("estado_") or (k in ("sin_resultado", "con_error", "ilegibles", "fallas_internas") and v)}
    if otros:
        partes.append(", ".join(f"{k.removeprefix('estado_')} {v}" for k, v in sorted(otros.items())))
    return " · ".join(partes)


# --- El comando ---

def _carpeta_documentos(carpeta_td: Path, td: str) -> Path:
    candidatas = sorted(p for p in (carpeta_td.parent.parent / "clasificados").glob(f"{td} *") if p.is_dir())
    if len(candidatas) != 1:
        raise ErrorDeUso("No se encontró una sola carpeta de documentos en ../../clasificados/: use --documentos.")
    return candidatas[0]


def main(argv: list[str] | None = None, cliente: ClienteLLM | None = None, fuente: FuenteModelo | None = None,
         entrada=input) -> int:
    """`cliente`, `fuente` y `entrada` son solo para las pruebas."""
    p = argparse.ArgumentParser(prog="medir-gold", description="Exactitud de la extracción contra el gold de un TD.")
    p.add_argument("carpeta", type=Path, help="carpeta del TD en pruebas/, con gold_TD-NN.xlsx y las corridas de lote.py")
    p.add_argument("--trabajo", type=Path, required=True, help="carpeta para la normalización y los resultados, fuera del repo")
    p.add_argument("--documentos", type=Path, help="carpeta de los PDF (por defecto ../../clasificados/TD-NN …)")
    p.add_argument("--td", help="tipo documental (por defecto, el nombre de la carpeta)")
    p.add_argument("--version", type=int, default=21, help="versión del modelo semántico (por defecto 21)")
    p.add_argument("--modelo", default="mcp", help="mcp (por defecto) o archivo:<ficha.json>")
    p.add_argument("--lote", type=Path, help="corrida de lote.py para comparar (por defecto, la más reciente de la carpeta)")
    p.add_argument("--concurrencia", type=int, default=parametros()["llamada"]["concurrencia"])
    p.add_argument("--solo-comparar", action="store_true", help="no extrae: compara lo que ya está en --trabajo")
    p.add_argument("--si-mando-documentos", action="store_true", help="no pregunta antes de mandar los documentos a gpt-5.4")
    args = p.parse_args(argv)

    carpeta, trabajo = args.carpeta.resolve(), args.trabajo.resolve()
    td = args.td or carpeta.name
    try:
        if not re.fullmatch(r"TD-\d{2}", td):
            raise ErrorDeUso("El tipo documental debe tener la forma TD-NN (use --td).")
        gold = carpeta / f"gold_{td}.xlsx"
        if not gold.is_file():
            raise ErrorDeUso(f"No existe gold_{td}.xlsx en la carpeta.")
        if dentro_de_un_repositorio(trabajo):
            raise ErrorDeUso("--trabajo guarda datos de los documentos: elija una carpeta fuera de cualquier repositorio git.")
        documentos = args.documentos.resolve() if args.documentos else _carpeta_documentos(carpeta, td)
        pdfs = sorted(documentos.glob("*.pdf"))
        if not pdfs:
            raise ErrorDeUso("La carpeta de documentos no tiene PDF.")
        lote = args.lote.resolve() if args.lote else ultima_corrida_de_lote(carpeta, td)
        filas = leer_gold(gold)
        if not args.solo_comparar:
            fuente = fuente or _fuente(args.modelo)
            if cliente is None:
                cliente = _llm_azure()
            if not args.si_mando_documentos and not _confirmar(entrada):
                print("No se mandó nada.", file=sys.stderr)
                return 2
    except (ErrorDeUso, GoldInvalido) as error:
        print(error, file=sys.stderr)
        return 2

    inicio = time.perf_counter()
    trabajo.mkdir(parents=True, exist_ok=True)
    solicitudes = preparar(pdfs, trabajo, td, args.version)
    del_servicio = correr_servicio(solicitudes, trabajo, fuente, None if args.solo_comparar else cliente, args.concurrencia)
    de_lote = leer_lote(lote) if lote else None
    texto, bajan = informe(td, filas, del_servicio, de_lote, lote.name if lote else None)
    print(texto)
    print(f"\nTiempo de esta corrida: {time.perf_counter() - inicio:.0f} s")
    return 1 if bajan else 0


if __name__ == "__main__":
    sys.exit(main())
