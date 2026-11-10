"""Visor local de las corridas del orquestador: el estado de cada proceso, sus
documentos, segmentos, tareas y solicitudes, con el PDF normalizado al lado.
Si la corrida tiene `extraccion/` (comando `extraer`), también los resultados de
la extracción de cada segmento.

    uv run visor --corridas <carpeta>        # abre http://127.0.0.1:8766

`<carpeta>` es la salida de una corrida (`orquestar --salida` o
`correr_muestra.py --salida`) o una carpeta que tiene varias, una por
subcarpeta. Se vuelve a leer en cada pedido: una corrida nueva aparece al
recargar la página.

Las corridas traen datos personales: el servidor solo escucha en 127.0.0.1 y
solo sirve archivos que estén dentro del almacén de la corrida.
"""

import argparse
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from normalizacion.almacen import en_el_almacen

from .. import datos

AQUI = Path(__file__).resolve().parent
PUERTO = 8766
PROFUNDIDAD = 3
"""Hasta cuántas carpetas por debajo de `--corridas` se buscan corridas."""
EXTRACCION = "extraccion"
FICHAS = "fichas"


def _leer_json(ruta: Path, defecto=None):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defecto


def buscar_corridas(raiz: Path) -> dict[str, Path]:
    """Las carpetas con `estado.json` bajo `raiz`, por su ruta relativa ("." si es la raíz)."""
    raiz = raiz.resolve()
    encontradas = {}
    for estado in sorted(raiz.glob("estado.json")) + sorted(
            p for n in range(1, PROFUNDIDAD + 1) for p in raiz.glob("/".join(["*"] * n) + "/estado.json")):
        carpeta = estado.parent
        if "almacen" in carpeta.relative_to(raiz).parts:
            continue
        encontradas[carpeta.relative_to(raiz).as_posix()] = carpeta
    return encontradas


def resumen_de(id_corrida: str, carpeta: Path) -> dict:
    registros = _leer_json(carpeta / "estado.json", [])
    procesos = [r for r in registros if r["tipo"] == "proceso"]
    return {
        "id": id_corrida,
        "procesos": [p["id"] for p in procesos],
        "fecha": procesos[0]["datos"].get("fecha_aviso") if procesos else None,
        "modificada": (carpeta / "estado.json").stat().st_mtime,
        "conteos": _leer_json(carpeta / "conteos.json"),
    }


def _datos_de_version(versiones: dict) -> dict:
    """Nombres de los TD y umbrales, de las versiones fijadas en el proceso."""
    salida = {}
    try:
        salida["tipos"] = datos.tipos_documentales(versiones["tipos_documentales"]).tipos
    except (datos.ErrorDatos, KeyError, OSError):
        salida["tipos"] = {}
    try:
        u = datos.umbrales(versiones["umbrales"])
        salida["umbrales"] = {"piso": u.piso, "por_td": u.por_td}
    except (datos.ErrorDatos, KeyError, OSError):
        salida["umbrales"] = None
    return salida


def _resultados_de_extraccion(carpeta: Path) -> dict[tuple[str, str, int], Path]:
    """Los resultados vigentes en `extraccion/<id_proceso>/<entrega>/`, por (segmento, TD, versión).

    El visor lee los archivos del contrato `modulo3-extraccion/0.2`; no importa el
    servicio de extracción. Los reemplazados (`.anterior-…`) no se muestran.
    """
    raiz = carpeta / EXTRACCION
    encontrados = {}
    for ruta in sorted(raiz.glob("*/*/*.json")):
        if ruta.relative_to(raiz).parts[0] == FICHAS or ".anterior-" in ruta.name:
            continue
        resultado = _leer_json(ruta)
        if not isinstance(resultado, dict) or "id_segmento" not in resultado:
            continue
        encontrados[(resultado["id_segmento"], resultado["tipo_documental"], resultado["version_modelo"])] = ruta
    return encontrados


def resumen_extraccion(resultado: dict) -> dict:
    """Lo que muestra la lista de segmentos: estado y conteos, sin valores."""
    motivos: dict[str, int] = {}
    for r in resultado.get("resultados", []):
        for m in r.get("motivos", []):
            motivos[m] = motivos.get(m, 0) + 1
    ejecucion = resultado.get("ejecucion", {})
    return {
        "id_segmento": resultado["id_segmento"],
        "tipo_documental": resultado["tipo_documental"],
        "version_modelo": resultado["version_modelo"],
        "estado": resultado["estado"],
        "requiere_revision": resultado.get("requiere_revision", False),
        "campos": len(resultado.get("resultados", [])),
        "campos_en_revision": len(resultado.get("campos_en_revision", [])),
        "motivos": motivos,
        "codigo_error": (resultado.get("error") or {}).get("codigo"),
        "tokens_entrada": ejecucion.get("tokens_entrada", 0),
        "tokens_salida": ejecucion.get("tokens_salida", 0),
    }


def extracciones(carpeta: Path) -> list[dict]:
    salida = []
    for ruta in _resultados_de_extraccion(carpeta).values():
        resultado = _leer_json(ruta)
        if resultado:
            salida.append(resumen_extraccion(resultado))
    return salida


def _campos_de_la_ficha(carpeta: Path, version: int, tipo_documental: str) -> dict | None:
    """Nombre, umbral y obligatoriedad de cada campo, si el comando guardó la ficha."""
    ficha = _leer_json(carpeta / EXTRACCION / FICHAS / f"v{version}" / f"{tipo_documental}.json")
    if not isinstance(ficha, dict):
        return None
    return {e["id_tecnico"]: {"nombre": e.get("nombre"), "obligatoriedad": e.get("obligatoriedad"),
                              "umbral": (e.get("atributos") or {}).get("umbral_confianza")}
            for e in ficha.get("elementos", []) if "id_tecnico" in e}


def extraccion(carpeta: Path, id_segmento: str, tipo_documental: str, version: int) -> dict | None:
    """El resultado completo de un segmento, con los datos de la ficha si están.

    El archivo se busca entre los resultados encontrados, nunca armando la ruta
    con lo que llega en el pedido.
    """
    ruta = _resultados_de_extraccion(carpeta).get((id_segmento, tipo_documental, version))
    resultado = _leer_json(ruta) if ruta else None
    if not resultado:
        return None
    return {"resultado": resultado, "campos": _campos_de_la_ficha(carpeta, version, tipo_documental)}


def corrida(carpeta: Path) -> dict:
    """Todo lo que muestra la página de una corrida."""
    registros = _leer_json(carpeta / "estado.json", [])
    por_tipo: dict[str, list] = {}
    for r in registros:
        por_tipo.setdefault(r["tipo"], []).append({"id": r["id"], "id_proceso": r["id_proceso"], **r["datos"]})
    solicitudes = []
    archivo = carpeta / "solicitudes-extraccion.jsonl"
    if archivo.is_file():
        solicitudes = [json.loads(linea) for linea in archivo.read_text(encoding="utf-8").splitlines() if linea.strip()]
    proceso = (por_tipo.get("proceso") or [{}])[0]
    return {
        "proceso": proceso,
        "oferentes": por_tipo.get("oferente", []),
        "documentos": por_tipo.get("documento", []),
        "segmentos": por_tipo.get("segmento", []),
        "tareas": por_tipo.get("tarea", []),
        "solicitudes": solicitudes,
        "errores": _leer_json(carpeta / "errores.json", []),
        "conteos": _leer_json(carpeta / "conteos.json"),
        "datos": _datos_de_version(proceso.get("versiones", {})),
        "extracciones": extracciones(carpeta),
    }


def _documento(carpeta: Path, id_documento: str) -> dict | None:
    for r in _leer_json(carpeta / "estado.json", []):
        if r["tipo"] == "documento" and r["id"] == id_documento:
            return r["datos"]
    return None


def lectura(carpeta: Path, id_documento: str) -> dict | None:
    """Lo que dice la lectura de un documento, página por página, sin el texto."""
    documento = _documento(carpeta, id_documento)
    ruta = en_el_almacen(carpeta, documento and documento.get("lectura"))
    contenido = _leer_json(ruta) if ruta else None
    if not contenido:
        return None
    return {
        "firma_digital": contenido.get("firma_digital", []),
        "paginas": [{k: p.get(k) for k in ("pagina", "tipo", "origen_texto", "caracteres", "cobertura_imagen",
                                           "rotacion")} | {"anclas": len(p.get("anclas") or [])}
                    for p in contenido.get("paginas", [])],
    }


class Manejador(BaseHTTPRequestHandler):
    raiz: Path

    def log_message(self, *_):
        pass

    def enviar(self, cuerpo: bytes, tipo: str, estado: int = 200):
        self.send_response(estado)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def json(self, contenido, estado=200):
        self.enviar(json.dumps(contenido, ensure_ascii=False).encode(), "application/json; charset=utf-8", estado)

    def no_existe(self):
        self.json({"error": "no existe"}, 404)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/":
            return self.enviar((AQUI / "index.html").read_bytes(), "text/html; charset=utf-8")
        corridas = buscar_corridas(self.raiz)
        if url.path == "/api/corridas":
            lista = [resumen_de(i, c) for i, c in corridas.items()]
            return self.json(sorted(lista, key=lambda c: c["modificada"], reverse=True))
        carpeta = corridas.get(q.get("corrida", ""))
        if carpeta is None:
            return self.no_existe()
        if url.path == "/api/corrida":
            return self.json(corrida(carpeta))
        if url.path == "/api/lectura":
            contenido = lectura(carpeta, q.get("documento", ""))
            return self.json(contenido) if contenido else self.no_existe()
        if url.path == "/api/extraccion":
            try:
                version = int(q.get("version", ""))
            except ValueError:
                return self.no_existe()
            contenido = extraccion(carpeta, q.get("segmento", ""), q.get("td", ""), version)
            return self.json(contenido) if contenido else self.no_existe()
        if url.path == "/pdf":
            documento = _documento(carpeta, q.get("documento", ""))
            ruta = en_el_almacen(carpeta, documento and documento.get("pdf"))
            if ruta is None:
                return self.enviar("PDF no encontrado en el almacén de la corrida".encode(), "text/plain; charset=utf-8", 404)
            return self.enviar(ruta.read_bytes(), "application/pdf")
        self.no_existe()


def servidor(raiz: Path, puerto: int = PUERTO) -> ThreadingHTTPServer:
    manejador = type("ManejadorDeCorridas", (Manejador,), {"raiz": raiz.resolve()})
    return ThreadingHTTPServer(("127.0.0.1", puerto), manejador)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="visor", description="Visor local de las corridas del orquestador.")
    p.add_argument("--corridas", type=Path, required=True,
                   help="salida de una corrida, o carpeta con varias (una por subcarpeta)")
    p.add_argument("--puerto", type=int, default=PUERTO)
    p.add_argument("--sin-navegador", action="store_true", help="no abrir el navegador")
    args = p.parse_args(argv)
    if not args.corridas.is_dir():
        print("La carpeta de corridas no existe.", file=sys.stderr)
        return 2
    if not buscar_corridas(args.corridas):
        print("No hay corridas (carpetas con estado.json) en esa carpeta. "
              "Corra orquestar o correr_muestra.py con --salida.", file=sys.stderr)
        return 2
    http = servidor(args.corridas, args.puerto)
    url = f"http://127.0.0.1:{args.puerto}"
    print(f"Visor en {url} (Ctrl+C para salir)")
    if not args.sin_navegador:
        webbrowser.open(url)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
