# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "azure-identity>=1.19",
#     "azure-storage-file-datalake>=12.18",
#     "deltalake>=1.0",
#     "pyarrow>=18",
# ]
# ///
"""Revisa los metadatos del módulo 1 contra los archivos en OneLake (T01 de
specs/005-orquestador/tasks-entrada-onelake.md).

    uv run servicios/prueba-onelake/revisar_metadatos.py \\
        [--workspace workspace-evaluacionofertas-dev] [--lakehouse lkh_evaluacionofertas_bronce]

Solo lee. Responde, por evento descargado:

1. Si cada fila de `adjuntos_metadata` existe en la carpeta y coincide en tamaño.
2. Qué archivos de la carpeta no están en la tabla (los JSON del módulo 1 y los
   que quedaron de corridas viejas).
3. Si las filas de oferente cruzan con `oferentes_control` por `event_id` e
   `invitation_id`, y cuántos oferentes no presentaron oferta.
4. Cuántos comprimidos hay y cuántos no tienen ninguna fila hija.
5. El proyecto del evento y su estado en `eventos_control`.
6. Qué forma tienen los JSON del módulo 1: solo llaves y tipos, nunca valores.

Las tablas se leen en su versión vigente con `deltalake`. Por pantalla salen solo
conteos, tipos y la forma de los identificadores (dígitos como 9): nunca nombres
de oferentes, de carpetas ni de archivos (principio 6).
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from posixpath import dirname

from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
from deltalake import DeltaTable

ENDPOINT = "https://onelake.dfs.fabric.microsoft.com"
SHORTCUT = "informacion-adjuntos"
ALCANCE = "https://storage.azure.com/.default"


def forma_id(valor):
    return re.sub(r"\d", "9", valor) if valor else "(vacío)"


def forma_json(valor, nivel=0):
    """Llaves y tipos, sin valores."""
    if isinstance(valor, dict):
        if nivel > 2:
            return "{…}"
        llaves = list(valor.items())[:25]
        resto = ", …" if len(valor) > 25 else ""
        return "{" + ", ".join(f"{k}: {forma_json(v, nivel + 1)}" for k, v in llaves) + resto + "}"
    if isinstance(valor, list):
        return f"[{len(valor)}× {forma_json(valor[0], nivel + 1) if valor else '-'}]"
    return type(valor).__name__


def forma_nombre(nombre):
    return re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "9", nombre))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--workspace", default=os.environ.get("ONELAKE_WORKSPACE", "workspace-evaluacionofertas-dev"))
    p.add_argument("--lakehouse", default=os.environ.get("ONELAKE_LAKEHOUSE", "lkh_evaluacionofertas_bronce"))
    a = p.parse_args()

    credencial = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    token = credencial.get_token(ALCANCE).token
    opciones = {"bearer_token": token, "use_fabric_endpoint": "true"}
    item = f"{a.lakehouse}.Lakehouse"
    raiz_tablas = f"abfss://{a.workspace}@onelake.dfs.fabric.microsoft.com/{item}/Tables"

    def tabla(nombre, columnas):
        dt = DeltaTable(f"{raiz_tablas}/{nombre}", storage_options=opciones)
        filas = dt.to_pyarrow_table(columns=columnas).to_pylist()
        print(f"{nombre}: versión {dt.version()}, {len(filas)} filas")
        return filas

    adjuntos = tabla("bronce/tbl_evaluacionofertas_adjuntos_metadata", [
        "event_id", "doc_category", "invitation_id", "adls_path", "downloaded_bytes", "md5_hex",
        "is_compressed_archive", "idempotency_key", "parent_archive_key", "file_status"])
    oferentes = tabla("bronce/tbl_evaluacionofertas_oferentes_control", [
        "event_id", "invitation_id", "sm_vendor_id", "has_bid"])
    eventos = {e["event_id"]: e for e in tabla("control/tbl_evaluacionofertas_eventos_control", [
        "event_id", "parent_project_id", "event_type_name", "event_state_name", "control_status",
        "total_files_detected", "total_files_succeeded", "total_files_failed"])}
    print(f"control_status de todos los eventos: {dict(Counter(e['control_status'] for e in eventos.values()))}")

    workspace = DataLakeServiceClient(ENDPOINT, credential=credencial).get_file_system_client(a.workspace)
    base = f"{item}/Files/{SHORTCUT}/"
    listado = {}
    for ruta in workspace.get_paths(path=base.rstrip("/"), recursive=True):
        if not ruta.is_directory:
            listado[ruta.name[len(base):]] = ruta.content_length
    print(f"archivos en {SHORTCUT}/: {len(listado)}; primer nivel: "
          f"{dict(Counter(r.split('/')[0] if r.startswith('fase2/') else '(fuera de fase2)' for r in listado))}")

    cruce = {(o["event_id"], o["invitation_id"]): o for o in oferentes}
    por_evento = defaultdict(list)
    for fila in adjuntos:
        por_evento[fila["event_id"]].append(fila)

    for numero, id_evento in enumerate(sorted(por_evento), 1):
        filas = por_evento[id_evento]
        evento = eventos.get(id_evento, {})
        print(f"\n== Evento {numero}: {forma_id(id_evento)}, proyecto {forma_id(evento.get('parent_project_id'))}, "
              f"{evento.get('event_type_name')} {evento.get('event_state_name')}, control {evento.get('control_status')} "
              f"({evento.get('total_files_succeeded')}/{evento.get('total_files_detected')}, "
              f"fallidos {evento.get('total_files_failed')})")

        rutas = Counter(f["adls_path"] for f in filas)
        unicas = {f["adls_path"]: f for f in filas}
        existen = [r for r in unicas if r in listado]
        print(f"   filas {len(filas)} ({sum(1 for v in rutas.values() if v > 1)} rutas repetidas); "
              f"existen {len(existen)} de {len(unicas)}; tamaño igual "
              f"{sum(1 for r in existen if listado[r] == unicas[r]['downloaded_bytes'])}")
        print(f"   doc_category {dict(Counter(f['doc_category'] for f in unicas.values()))}; "
              f"file_status {dict(Counter(f['file_status'] for f in unicas.values()))}")

        carpeta = f"fase2/{id_evento}/"
        sobrantes = [r for r in listado if r.startswith(carpeta) and r not in unicas]
        carpetas_tabla = {dirname(r) for r in unicas}
        print(f"   en la carpeta y no en la tabla: {len(sobrantes)} "
              f"({sum(1 for r in sobrantes if r.lower().endswith('.json'))} JSON; "
              f"{sum(1 for r in sobrantes if not r.lower().endswith('.json') and dirname(r) not in carpetas_tabla)} "
              f"en carpetas sin filas)")

        de_oferente = [f for f in unicas.values() if f["doc_category"] == "OFERENTE"]
        cruzan = [f for f in de_oferente if (id_evento, f["invitation_id"]) in cruce]
        con_archivos = {f["invitation_id"] for f in de_oferente}
        del_evento = [o for o in oferentes if o["event_id"] == id_evento]
        print(f"   filas de oferente que cruzan: {len(cruzan)} de {len(de_oferente)}; oferentes con archivos "
              f"{len(con_archivos)}; en control {len(del_evento)} "
              f"(has_bid {dict(Counter(o['has_bid'] for o in del_evento))}; con archivos y sin oferta "
              f"{sum(1 for o in del_evento if not o['has_bid'] and o['invitation_id'] in con_archivos)})")

        comprimidos = {f["idempotency_key"] for f in unicas.values() if f["is_compressed_archive"]}
        padres = {f["parent_archive_key"] for f in unicas.values() if f["parent_archive_key"]}
        print(f"   comprimidos {len(comprimidos)}; sin filas hijas {len(comprimidos - padres)}; "
              f"filas hijas {sum(1 for f in unicas.values() if f['parent_archive_key'])}")

    print("\n== JSON del módulo 1 (forma del nombre, cuántos, llaves y tipos)")
    grupos = defaultdict(list)
    for ruta in listado:
        if ruta.lower().endswith(".json"):
            grupos[forma_nombre(ruta.rsplit("/", 1)[-1])].append(ruta)
    for forma, rutas in sorted(grupos.items()):
        datos = json.loads(workspace.get_file_client(base + rutas[0]).download_file().readall())
        print(f"   {forma} ({len(rutas)}): {forma_json(datos)[:1200]}")

    sys.stdout.flush()
    # deltalake deja hilos vivos y el proceso no termina solo (2026-11-20).
    os._exit(0)


if __name__ == "__main__":
    main()
