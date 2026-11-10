"""Propone la clasificación de un proceso real para probar el flujo completo.

    uv run --project <extraccion> python <extraccion>/scripts/proponer_clasificacion.py \\
        <carpeta del proceso> --trabajo <carpeta> [--carpeta-proceso N] [--proceso SR…]
        [--max-paginas 100] [--solo-armar] [--si-mando-documentos]

No es el clasificador del flujo (ese es de otro equipo, C1 a C3): arma el borrador
del CSV del clasificador falso del orquestador, para que una persona lo revise
antes de correr `orquestar`. Se puede borrar cuando exista el clasificador real.

1. **Arma el origen** en `<trabajo>/origen/<SR…>/`: la carpeta de los documentos
   del proceso como `PROCESO/` y las demás como `OF-001`, `OF-002`… en orden
   alfabético. Los originales no se tocan. Los archivos sueltos en la raíz van a
   `PROCESO/`. La correspondencia queda en `<trabajo>/oferentes.csv`.
2. **Normaliza** cada entrega en local, en `<trabajo>/clasificacion/almacen/`.
3. **Clasifica** cada documento con gpt-5.4: las fichas de clasificación
   (`contexto/Conocimiento_Clasificacion.txt`) y una muestra del documento (el
   texto de las primeras páginas, el comienzo de las demás hasta la 40 y la
   imagen de las primeras si no tienen texto). Los documentos de más de
   `--max-paginas` no se mandan: salen TD-99 para revisar. Cada respuesta se
   guarda: una segunda corrida no vuelve a llamar.
4. **Escribe** `<trabajo>/clasificacion-propuesta.csv` con las columnas del
   clasificador falso más `revisar`, `paginas_documento` y `nota`.

Por pantalla salen solo conteos: nunca nombres de carpetas, de archivos ni de
oferentes.
"""

import argparse
import csv
import json
import re
import shutil
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from normalizacion.almacen import CARPETA_ALMACEN, AlmacenLocal
from normalizacion.entrega import normalizar_entrega
from orquestador import datos

from extraccion.cli import _confirmar, _llm_azure, dentro_de_un_repositorio
from extraccion.entrada import Entrada
from extraccion.llamada import LlamadaFallida, Llamador
from extraccion.llm import ClienteLLM, PedidoRechazado
from extraccion.mensaje import _imagen, _texto
from extraccion.parametros import parametros
from extraccion.posvalidacion import RespuestaInvalida
from extraccion.preproceso import preparar_contenido
from extraccion.reloj import RelojSistema

REPO = Path(__file__).resolve().parents[3]
FICHAS = REPO / "contexto" / "Conocimiento_Clasificacion.txt"
PISTA_PROCESO = re.compile(r"pliego|condici|adenda|proceso|cpc|invitaci|evaluaci|informe", re.I)
SIN_CLASIFICAR = "TD-99"
PAGINAS_LARGAS = 3        # páginas con todo su texto (hasta 3.000 caracteres)
PAGINAS_MUESTRA = 40      # de ahí en adelante, nada
CARACTERES_LARGA, CARACTERES_CORTA = 3000, 300
COLUMNAS = ("id_oferente", "ruta_origen", "pagina_inicio", "pagina_fin", "tipo_documental", "confianza", "subtipo",
            "revisar", "paginas_documento", "nota")

INSTRUCCIONES = """Clasificas documentos de las ofertas y de los procesos de contratación del Grupo Energía Bogotá.

Te doy una muestra de un documento: el texto de sus primeras páginas, el comienzo de las siguientes y, si no tienen texto, su imagen. Elige el tipo documental con las fichas de abajo, según el propósito principal del documento. Si ninguno encaja, TD-99.

Un mismo PDF puede traer varios documentos seguidos (por ejemplo, una carta, un certificado y un RUT escaneados juntos). Si es así, di `varios_documentos: true` y da los tramos de páginas con su tipo, sin huecos ni cruces, cubriendo las páginas que viste.

Responde solo con un objeto JSON, sin texto antes ni después:
{"tipo_documental": "TD-NN", "subtipo": null, "confianza": 0.0, "varios_documentos": false, "tramos": [{"desde": 1, "hasta": 3, "tipo_documental": "TD-NN"}], "nota": "…"}

- `tipo_documental`: el del documento entero o, si trae varios, el del primero.
- `confianza`: de 0 a 1, qué tan seguro estás.
- `tramos`: solo si `varios_documentos` es true; si no, lista vacía.
- `nota`: hasta 200 caracteres, por qué. Sin nombres de personas, números de documento ni otros datos personales.

# Fichas de clasificación

"""


def armar_origen(carpeta: Path, trabajo: Path, proceso: str, carpeta_proceso: int | None) -> tuple[Path, dict[str, Path]]:
    """Copia el proceso con la forma que espera el orquestador. Devuelve la raíz y entrega → carpeta."""
    carpetas = sorted(d for d in carpeta.iterdir() if d.is_dir())
    if carpeta_proceso is None:
        candidatas = [i for i, d in enumerate(carpetas, 1) if PISTA_PROCESO.search(d.name)]
        if len(candidatas) != 1:
            raise SystemExit("No se pudo saber cuál carpeta trae los documentos del proceso: use --carpeta-proceso N.")
        carpeta_proceso = candidatas[0]
    if not 1 <= carpeta_proceso <= len(carpetas):
        raise SystemExit(f"--carpeta-proceso debe estar entre 1 y {len(carpetas)}.")
    raiz = trabajo / "origen" / proceso
    entregas: dict[str, Path] = {}
    oferentes = [d for i, d in enumerate(carpetas, 1) if i != carpeta_proceso]
    entregas["PROCESO"] = carpetas[carpeta_proceso - 1]
    for n, d in enumerate(oferentes, 1):
        entregas[f"OF-{n:03d}"] = d
    for entrega, original in entregas.items():
        destino = raiz / entrega
        if not destino.exists():
            shutil.copytree(original, destino)
    for suelto in (f for f in carpeta.iterdir() if f.is_file()):
        if not (raiz / "PROCESO" / suelto.name).exists():
            shutil.copy2(suelto, raiz / "PROCESO" / suelto.name)
    with open(trabajo / "oferentes.csv", "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["entrega", "carpeta_original"])
        for entrega, original in entregas.items():
            escritor.writerow([entrega, original.name])
    return raiz, entregas


def normalizar(raiz: Path, trabajo: Path, proceso: str) -> tuple[AlmacenLocal, list[tuple[str, dict]]]:
    """Normaliza cada entrega. Devuelve (entrega, archivo del manifiesto) de todos los archivos."""
    almacen = AlmacenLocal(trabajo / "clasificacion" / CARPETA_ALMACEN)
    archivos = []
    for entrega in sorted(p.name for p in raiz.iterdir() if p.is_dir()):
        id_oferente = None if entrega == "PROCESO" else entrega
        manifiesto = normalizar_entrega(raiz / entrega, proceso, id_oferente, almacen).manifiesto
        archivos.extend((entrega, a) for a in manifiesto["archivos"])
    return almacen, archivos


def mensajes(entrada: Entrada, total: int) -> list[dict]:
    contenido = preparar_contenido(entrada)
    partes = [_texto(f"Documento de {total} páginas. Se muestran {'todas' if total <= PAGINAS_MUESTRA else f'las primeras {PAGINAS_MUESTRA}'}.")]
    for pagina in contenido.paginas:
        tope = CARACTERES_LARGA if pagina.numero <= PAGINAS_LARGAS else CARACTERES_CORTA
        if pagina.texto:
            texto = pagina.texto[:tope] + (" […]" if len(pagina.texto) > tope else "")
            partes.append(_texto(f"--- Página {pagina.numero} ---\n{texto}"))
        else:
            partes.append(_texto(f"--- Página {pagina.numero} ---\n{'(sin texto: ver la imagen)' if pagina.imagen else '(página en blanco)'}"))
        if pagina.imagen and not pagina.texto and pagina.numero <= PAGINAS_LARGAS:
            partes.append(_imagen(pagina.imagen))
    return [{"role": "system", "content": INSTRUCCIONES + FICHAS.read_text(encoding="utf-8")},
            {"role": "user", "content": partes}]


def interpretar_con(tipos: set[str], total: int):
    def interpretar(texto: str) -> dict:
        try:
            r = json.loads(texto)
        except json.JSONDecodeError as error:
            raise RespuestaInvalida([f"no es JSON ({error.msg})"]) from None
        errores = []
        if not isinstance(r, dict):
            raise RespuestaInvalida(["no es un objeto"])
        if r.get("tipo_documental") not in tipos:
            errores.append("tipo_documental: no es un TD del catálogo")
        if not isinstance(r.get("confianza"), (int, float)) or not 0 <= r["confianza"] <= 1:
            errores.append("confianza: debe ser un número de 0 a 1")
        if not isinstance(r.get("tramos", []), list):
            errores.append("tramos: debe ser una lista")
        if errores:
            raise RespuestaInvalida(errores)
        return r
    return interpretar


def tramos_validos(r: dict, total: int, tipos: set[str]) -> list[dict] | None:
    """Los tramos si están en orden, sin huecos ni cruces y cubren el documento entero; si no, None."""
    tramos = r.get("tramos") or []
    if not r.get("varios_documentos") or len(tramos) < 2:
        return None
    siguiente = 1
    for t in tramos:
        if not (isinstance(t, dict) and t.get("tipo_documental") in tipos and isinstance(t.get("desde"), int)
                and isinstance(t.get("hasta"), int) and t["desde"] == siguiente and t["hasta"] >= t["desde"]):
            return None
        siguiente = t["hasta"] + 1
    if siguiente - 1 != total:
        return None  # el orquestador pide que los tramos cubran el documento entero
    return tramos


def clasificar(almacen: AlmacenLocal, archivos: list[tuple[str, dict]], trabajo: Path, cliente: ClienteLLM | None,
               max_paginas: int, concurrencia: int) -> tuple[list[dict], Counter]:
    tipos = set(datos.tipos_documentales("1").tipos)
    umbrales = datos.umbrales("1").por_td
    guardadas = trabajo / "clasificacion" / "respuestas"
    guardadas.mkdir(parents=True, exist_ok=True)
    llamador = Llamador(cliente, RelojSistema(), {**parametros()["llamada"], "concurrencia": concurrencia}) if cliente else None
    cuenta = Counter()
    por_id = {a["id_documento"]: a for _, a in archivos}

    def uno(par):
        entrega, archivo = par
        if archivo["estado"] != "normalizado":
            return None
        total = archivo["paginas"]
        guardada = guardadas / f"{archivo['id_documento']}.json"
        if guardada.exists():
            return json.loads(guardada.read_text(encoding="utf-8"))
        if total > max_paginas:
            return {"tipo_documental": SIN_CLASIFICAR, "confianza": 0, "nota": f"más de {max_paginas} páginas: no se clasifica",
                    "omitido": True}
        if llamador is None:
            return None
        lectura = json.loads(almacen.leer(archivo["lectura"]))
        hasta = min(total, PAGINAS_MUESTRA)
        entrada = Entrada(solicitud={"paginas": {"desde": 1, "hasta": hasta}}, lectura=lectura,
                          pdf=almacen.leer(archivo["pdf"]), anexos=())
        try:
            llamada = llamador.llamar(mensajes(entrada, total), interpretar_con(tipos, total))
        except (LlamadaFallida, PedidoRechazado) as error:
            return {"tipo_documental": SIN_CLASIFICAR, "confianza": 0, "nota": f"no se pudo clasificar: {type(error).__name__}",
                    "fallo": True}
        r = {**llamada.respuesta, "tokens": [llamada.tokens_entrada, llamada.tokens_salida]}
        guardada.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        return r

    with ThreadPoolExecutor(max_workers=concurrencia * 2) as grupo:
        respuestas = list(grupo.map(uno, archivos))

    filas = []
    for (entrega, archivo), r in zip(archivos, respuestas):
        cuenta[f"estado_{archivo['estado']}"] += 1
        if archivo["estado"] == "duplicado":
            continue  # el orquestador lo resuelve con el original
        if r is None:
            continue  # sin normalizar: el orquestador lo deja con su error
        cuenta["tokens_entrada"] += (r.get("tokens") or [0, 0])[0]
        cuenta["tokens_salida"] += (r.get("tokens") or [0, 0])[1]
        cuenta["omitidos_por_largos"] += bool(r.get("omitido"))
        cuenta["fallidos"] += bool(r.get("fallo"))
        base = {"id_oferente": "" if entrega == "PROCESO" else entrega, "ruta_origen": archivo["ruta_origen"],
                "paginas_documento": archivo["paginas"], "nota": (r.get("nota") or "")[:200]}
        tramos = tramos_validos(r, archivo["paginas"], tipos)
        if r.get("varios_documentos") and tramos is None:
            base["nota"] = ("tramos no válidos; " + base["nota"])[:200]
        partes = tramos or [{"desde": "", "hasta": "", "tipo_documental": r["tipo_documental"]}]
        for t in partes:
            td = t["tipo_documental"]
            revisar = (td == SIN_CLASIFICAR or bool(r.get("varios_documentos")) or r["confianza"] < umbrales.get(td, 1))
            cuenta[f"td_{td}"] += 1
            cuenta["revisar"] += revisar
            filas.append({**base, "pagina_inicio": t["desde"], "pagina_fin": t["hasta"], "tipo_documental": td,
                          "confianza": round(float(r["confianza"]), 2), "subtipo": r.get("subtipo") or "",
                          "revisar": "SI" if revisar else ""})
    cuenta["con_varios_documentos"] = sum(1 for r in respuestas if r and r.get("varios_documentos"))
    return filas, cuenta


def main(argv: list[str] | None = None, cliente: ClienteLLM | None = None, entrada=input) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("carpeta", type=Path, help="carpeta del proceso: una subcarpeta con los documentos del proceso y una por oferente")
    p.add_argument("--trabajo", type=Path, required=True, help="carpeta de trabajo, fuera de cualquier repositorio")
    p.add_argument("--carpeta-proceso", type=int, help="cuál subcarpeta (1, 2…, en orden alfabético) trae los documentos del proceso")
    p.add_argument("--proceso", help="id del proceso (por defecto, el SR… del nombre de la carpeta)")
    p.add_argument("--max-paginas", type=int, default=100, help="los documentos más largos no se mandan (por defecto 100)")
    p.add_argument("--concurrencia", type=int, default=parametros()["llamada"]["concurrencia"])
    p.add_argument("--solo-armar", action="store_true", help="arma el origen y normaliza, sin clasificar")
    p.add_argument("--si-mando-documentos", action="store_true")
    args = p.parse_args(argv)

    carpeta, trabajo = args.carpeta.resolve(), args.trabajo.resolve()
    proceso = args.proceso or (m.group(0) if (m := re.search(r"SR\d+", carpeta.name)) else None)
    if not proceso:
        print("No hay un SR… en el nombre de la carpeta: use --proceso.", file=sys.stderr)
        return 2
    if dentro_de_un_repositorio(trabajo):
        print("--trabajo guarda copias de los documentos: elija una carpeta fuera de cualquier repositorio git.", file=sys.stderr)
        return 2
    trabajo.mkdir(parents=True, exist_ok=True)
    inicio = time.perf_counter()
    raiz, entregas = armar_origen(carpeta, trabajo, proceso, args.carpeta_proceso)
    print(f"Origen armado: PROCESO y {len(entregas) - 1} oferentes (correspondencia en oferentes.csv).")
    almacen, archivos = normalizar(raiz, trabajo, proceso)
    print(f"Normalizados: {sum(a['estado'] == 'normalizado' for _, a in archivos)} de {len(archivos)} archivos.")
    if args.solo_armar:
        return 0
    if cliente is None:
        try:
            cliente = _llm_azure()
        except Exception as error:  # noqa: BLE001 — ErrorDeUso u otra configuración
            print(error, file=sys.stderr)
            return 2
    if not args.si_mando_documentos and not _confirmar(entrada):
        print("No se mandó nada.", file=sys.stderr)
        return 2
    filas, cuenta = clasificar(almacen, archivos, trabajo, cliente, args.max_paginas, args.concurrencia)
    salida = trabajo / "clasificacion-propuesta.csv"
    with open(salida, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)
    resumen = {"filas": len(filas), **dict(sorted(cuenta.items())), "tiempo_s": round(time.perf_counter() - inicio)}
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"Propuesta en {salida.name}: revise las filas con revisar = SI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
