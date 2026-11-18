# Prueba de acceso a OneLake

Prueba de concepto del paso 0 (`contexto/flujo-documental-opcion-a.md`, "Cómo leemos
los archivos de Fabric"): confirma que una identidad lista y lee la carpeta de un
proceso en el lakehouse del módulo 1. Solo lee. Nada se escribe a disco ni a OneLake.

## Qué hace falta

- Nombre (o GUID) del workspace y del lakehouse, y una carpeta de prueba dentro de `Files/`.
- Una identidad con permiso de lectura de datos sobre ese lakehouse:
  - en local, tu usuario con `az login`;
  - un service principal, con `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` y `AZURE_CLIENT_SECRET`;
  - dentro de Azure, la identidad administrada del job.
- `uv`. El script declara sus dependencias (`azure-identity`, `azure-storage-file-datalake`)
  y no necesita un proyecto.

## Cómo correrla

```bash
az login --scope https://storage.azure.com/.default   # solo en local, con usuario

uv run servicios/prueba-onelake/probar_onelake.py \
    --workspace <workspace> --lakehouse <lakehouse> --ruta <carpeta dentro de Files> \
    --leer 3
```

También acepta `ONELAKE_WORKSPACE`, `ONELAKE_LAKEHOUSE` y `ONELAKE_RUTA`.

Pasos: pide el token, lista la carpeta y lee completos los primeros `--leer` archivos.
Se detiene en el primero que falle, con una pista según el código HTTP:

| Código | Causa probable |
|---|---|
| 401 | Token de otro tenant |
| 403 | Falta permiso de datos (ReadAll o rol de OneLake), una opción del tenant o Conditional Access |
| 404 | Workspace, lakehouse o ruta mal escritos |

Por pantalla salen solo conteos, extensiones y tamaños, nunca nombres (principio 6).

Las opciones del tenant y los roles que nombran las pistas se tomaron de memoria y la
prueba los confirma: hay que corregir este README con lo que se encuentre.
