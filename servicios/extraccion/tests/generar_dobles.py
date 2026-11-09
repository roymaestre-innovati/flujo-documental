"""Genera los dobles de prueba de `tests/fichas/` y `tests/respuestas/`.

No es una prueba: se corre a mano cuando cambian sus fuentes, y su salida se
guarda en el repositorio.

    uv run python tests/generar_dobles.py ~/GEB/modelo-semantico

- **Ficha** (`fichas/extraccion_documental.v21.json`): las secciones TD-01, TD-16 y
  TD-29 de `modelos/extraccion_documental/tipos_documentales.json`, con la forma de
  `obtener_seccion` del MCP (se usa `modelo_semantico.formato` de ese repositorio) y
  la guía de interpretación. Son metadatos del modelo, sin datos de documentos.
  Agrega lo que v21 todavía no trae, solo para reproducir los ejemplos del contrato:
  `td_probado: true` en TD-16 y TD-29, y los validadores (`atributos.validador`) de
  los campos cuyo ejemplo los cita.
- **Respuestas** (`respuestas/TD-16.json`, `respuestas/TD-29.json`): lo que tendría
  que responder el LLM para que la posvalidación dé `salida_td16.json` y
  `salida_td29.json` del contrato. Se sacan de esos ejemplos: sin `revision`, sin
  `id_regla`, sin `datos_personales` y solo con los motivos que propone el LLM.
"""

import json
import sys
from pathlib import Path

AQUI = Path(__file__).parent
EJEMPLOS = Path(__file__).resolve().parents[3] / "contracts" / "modulo3-extraccion" / "v0.2" / "ejemplos"
SECCIONES = ("TD-01", "TD-16", "TD-29")
PROBADOS = {"TD-16", "TD-29"}
VALIDADORES = {
    "td16.sociedad": [{"tipo": "nit_dv", "propiedad": "nit"}],
    "td29.contratos": [{"tipo": "fecha_orden", "desde": "fecha_inicio", "hasta": "fecha_fin"}],
    "td29.totales_declarados": [
        {"tipo": "suma_igual", "total": "total_valor", "campo": "td29.contratos", "columna": "valor_total", "tolerancia": 0},
        {"tipo": "suma_igual", "total": "total_smmlv", "campo": "td29.contratos", "columna": "valor_smmlv", "tolerancia": 0},
    ],
}
MOTIVOS_DEL_LLM = {"REQUIERE_IMAGEN", "PLANTILLA_SIN_LLENAR", "NOTA_ELEMENTO", "CONTRADICCION"}


def ficha(repo_modelo: Path) -> dict:
    sys.path.insert(0, str(repo_modelo / "src"))
    from modelo_semantico.formato import catalogos_usados, elemento_para_agente

    carpeta = repo_modelo / "modelos" / "extraccion_documental"
    modelo = json.loads((carpeta / "tipos_documentales.json").read_text(encoding="utf-8"))
    catalogos = json.loads((carpeta / "catalogos.json").read_text(encoding="utf-8"))["catalogos"]
    guia = (carpeta / modelo["guia_interpretacion_archivo"]).read_text(encoding="utf-8").strip()

    elementos = [e for e in modelo["elementos"] if e["seccion"] in SECCIONES]
    usados = {n: catalogos.get(n, []) for n in catalogos_usados(elementos)}
    salida = []
    for e in elementos:
        limpio = elemento_para_agente(e, usados)
        if e["id_tecnico"] in VALIDADORES:
            limpio["atributos"]["validador"] = VALIDADORES[e["id_tecnico"]]
        salida.append(limpio)
    secciones = []
    for s in modelo["secciones"]:
        if s["id"] in SECCIONES:
            secciones.append({**s, **({"td_probado": True} if s["id"] in PROBADOS else {})})
    return {
        "modelo": "extraccion_documental",
        "nombre": modelo["nombre"],
        "tipo_tarea": modelo["tipo_tarea"],
        "version": 21,
        "guia_interpretacion": guia,
        "diccionario": modelo["diccionario"],
        "secciones": secciones,
        "elementos": salida,
    }


def respuesta(salida: dict) -> dict:
    resultados = []
    for r in salida["resultados"]:
        resultados.append({
            "id_tecnico": r["id_tecnico"],
            "evidencia": r["evidencia"],
            "valor": r["valor"],
            "confianza": r["confianza"],
            "cumple": r["cumple"],
            "reglas_pendientes": [{"texto": p["texto"], "requiere": p["requiere"]} for p in r["reglas_pendientes"]],
            "motivos": [m for m in r["motivos"] if m in MOTIVOS_DEL_LLM],
            "observacion": r["observacion"],
        })
    alertas = [{"codigo": a["codigo"], "mensaje": a["mensaje"], "id_tecnico": a.get("id_tecnico")} for a in salida["alertas"]]
    return {"corresponde": True, "motivo_no_corresponde": None, "resultados": resultados, "alertas": alertas}


def escribir(ruta: Path, contenido: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(ruta.relative_to(AQUI))


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    escribir(AQUI / "fichas" / "extraccion_documental.v21.json", ficha(Path(sys.argv[1]).expanduser()))
    for td in ("16", "29"):
        salida = json.loads((EJEMPLOS / f"salida_td{td}.json").read_text(encoding="utf-8"))
        escribir(AQUI / "respuestas" / f"TD-{td}.json", respuesta(salida))


if __name__ == "__main__":
    main()
