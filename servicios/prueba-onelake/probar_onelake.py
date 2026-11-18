# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "azure-identity>=1.19",
#     "azure-storage-file-datalake>=12.18",
# ]
# ///
"""Prueba de acceso a OneLake: ¿podemos listar y leer la carpeta de un proceso?

    uv run servicios/prueba-onelake/probar_onelake.py \\
        --workspace <workspace> --lakehouse <lakehouse> --ruta <carpeta dentro de Files>
        [--leer 3]

Los tres datos también se pueden dar con ONELAKE_WORKSPACE, ONELAKE_LAKEHOUSE y
ONELAKE_RUTA. Sirven el nombre o el GUID del workspace y del lakehouse.

La identidad sale de DefaultAzureCredential, en este orden de uso habitual:

- Service principal, si están AZURE_TENANT_ID, AZURE_CLIENT_ID y AZURE_CLIENT_SECRET.
- Identidad administrada, si corre dentro de Azure.
- El usuario de `az login`, en local.

Pasos, y se detiene en el primero que falle con una pista de la causa:

1. Pide el token para Azure Storage.
2. Lista la carpeta en OneLake (recursivo).
3. Lee completos los primeros `--leer` archivos, en memoria, y compara los bytes
   con el tamaño listado. Nada se escribe a disco ni a OneLake.

Por pantalla salen solo conteos, extensiones y tamaños: nunca nombres de carpetas
ni de archivos (principio 6).
"""

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import PurePosixPath

from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

ENDPOINT = "https://onelake.dfs.fabric.microsoft.com"
ALCANCE = "https://storage.azure.com/.default"

PISTAS = {
    401: "El token no sirve para OneLake: revisa el tenant de la identidad.",
    403: (
        "La identidad entra pero no tiene permiso sobre los datos. Revisa: (a) que esté "
        "en el workspace con permiso de lectura de datos de OneLake (ReadAll o un rol "
        "de acceso a datos de OneLake sobre la carpeta; el rol Viewer solo puede no "
        "bastar), (b) en el tenant, 'Users can access data stored in OneLake with apps "
        "external to Fabric', y (c) si es service principal o identidad administrada, "
        "'Service principals can use Fabric APIs'. También puede ser Conditional Access."
    ),
    404: (
        "No existe el workspace, el lakehouse o la ruta. Revisa los nombres "
        "(mayúsculas incluidas) y que la ruta sea relativa a Files/."
    ),
}


def _config():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--workspace", default=os.environ.get("ONELAKE_WORKSPACE"))
    p.add_argument("--lakehouse", default=os.environ.get("ONELAKE_LAKEHOUSE"))
    p.add_argument("--ruta", default=os.environ.get("ONELAKE_RUTA", ""),
                   help="Carpeta dentro de Files/ (vacía: todo Files/)")
    p.add_argument("--leer", type=int, default=3,
                   help="Cuántos archivos leer completos (0: solo listar)")
    a = p.parse_args()
    faltan = [n for n in ("workspace", "lakehouse") if not getattr(a, n)]
    if faltan:
        p.error("falta " + " y ".join(f"--{n}" for n in faltan))
    return a


def ruta_en_onelake(lakehouse, ruta):
    """Ruta dentro del workspace: '<lakehouse>.Lakehouse/Files/<ruta>'."""
    item = lakehouse if lakehouse.endswith(".Lakehouse") else f"{lakehouse}.Lakehouse"
    return "/".join(x for x in (item, "Files", ruta.strip("/")) if x)


def _falla(paso, error):
    codigo = getattr(error, "status_code", None)
    print(f"FALLA en {paso}: {type(error).__name__}"
          + (f" HTTP {codigo}" if codigo else ""))
    error_code = getattr(error, "error_code", None)
    if error_code:
        print(f"  código del servicio: {error_code}")
    if codigo in PISTAS:
        print(f"  pista: {PISTAS[codigo]}")
    sys.exit(1)


def main():
    a = _config()
    credencial = DefaultAzureCredential(exclude_interactive_browser_credential=True)

    # 1. Token
    try:
        token = credencial.get_token(ALCANCE)
    except ClientAuthenticationError as e:
        print("FALLA en token: ninguna identidad disponible.")
        print("  pista: en local corre `az login` (con el tenant de Fabric), o define "
              "AZURE_TENANT_ID, AZURE_CLIENT_ID y AZURE_CLIENT_SECRET.")
        print(f"  detalle: {str(e).splitlines()[0]}")
        # La línea de Azure CLI dice por qué falló `az login` (MFA vencida, otro tenant…)
        cli = [x.strip() for x in str(e).splitlines() if x.strip().startswith("AzureCliCredential")]
        if cli:
            print(f"  {cli[0][:300]}")
        sys.exit(1)
    minutos = (token.expires_on - time.time()) / 60
    print(f"1. Token OK (vence en {minutos:.0f} min)")

    servicio = DataLakeServiceClient(ENDPOINT, credential=credencial)
    workspace = servicio.get_file_system_client(a.workspace)
    base = ruta_en_onelake(a.lakehouse, a.ruta)

    # 2. Listar
    try:
        inicio = time.monotonic()
        rutas = list(workspace.get_paths(path=base, recursive=True))
    except HttpResponseError as e:
        _falla("listar", e)
    archivos = [r for r in rutas if not r.is_directory]
    carpetas = len(rutas) - len(archivos)
    total = sum(r.content_length or 0 for r in archivos)
    print(f"2. Listado OK en {time.monotonic() - inicio:.1f} s: {len(archivos)} archivos, "
          f"{carpetas} carpetas, {total / 1e6:.1f} MB")
    extensiones = Counter(PurePosixPath(r.name).suffix.lower() or "(sin)" for r in archivos)
    for ext, n in extensiones.most_common():
        print(f"   {ext}: {n}")

    # 3. Leer
    a_leer = archivos[: max(a.leer, 0)]
    for i, r in enumerate(a_leer, 1):
        try:
            inicio = time.monotonic()
            datos = workspace.get_file_client(r.name).download_file().readall()
        except HttpResponseError as e:
            _falla(f"leer archivo {i}", e)
        igual = "OK" if len(datos) == r.content_length else "DISTINTO al listado"
        print(f"3. Archivo {i}/{len(a_leer)} ({PurePosixPath(r.name).suffix.lower()}): "
              f"{len(datos) / 1e6:.2f} MB en {time.monotonic() - inicio:.1f} s, tamaño {igual}")

    print("Prueba completa: la identidad lista y lee la carpeta en OneLake.")


if __name__ == "__main__":
    main()
