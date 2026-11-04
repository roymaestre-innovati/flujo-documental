"""Inventario de una entrega.

Por ahora solo recorre la carpeta (R1). El descarte de archivos de sistema, la
huella, los duplicados y el `id_documento` llegan en T04.
"""

from pathlib import Path


def recorrer(carpeta: Path) -> list[str]:
    """Rutas relativas de todos los archivos de la entrega, con `/` y ordenadas.

    Recorre las carpetas anidadas. No sigue enlaces simbólicos, para no salir de
    la entrega.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise NotADirectoryError("La entrega debe ser una carpeta.")
    rutas = []
    for actual, _carpetas, archivos in carpeta.walk(follow_symlinks=False):
        for nombre in archivos:
            ruta = actual / nombre
            if ruta.is_file() and not ruta.is_symlink():
                rutas.append(ruta.relative_to(carpeta).as_posix())
    return sorted(rutas)
