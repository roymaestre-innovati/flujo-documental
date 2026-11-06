"""Dónde están los originales. En producción, el datalake de Fabric (OneLake,
decisión 35, entrega 2); aquí, una carpeta local.

Los originales no se copian a nuestro almacenamiento (decisión 32): se bajan a
una carpeta temporal solo mientras se normalizan.

Las rutas son siempre relativas a la raíz del origen, con `/` y sin `..`.
"""

import shutil
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath


class ErrorOrigen(Exception):
    """La ruta no existe o no es válida."""


def _ruta_segura(ruta: str) -> PurePosixPath:
    partes = PurePosixPath(ruta)
    if partes.is_absolute() or ".." in partes.parts or not partes.parts:
        raise ErrorOrigen(f"Ruta no válida en el origen: {ruta!r}")
    return partes


class Origen(ABC):
    @abstractmethod
    def listar(self, carpeta: str) -> list[str]:
        """Todos los archivos bajo `carpeta`, recursivo, como rutas relativas a
        `carpeta` y ordenadas. No incluye carpetas."""

    @abstractmethod
    def bajar(self, archivo: str, destino: Path) -> None:
        """Copia el archivo a `destino` (una ruta de archivo local)."""


class OrigenLocal(Origen):
    def __init__(self, raiz: str | Path) -> None:
        self._raiz = Path(raiz).resolve()

    def _local(self, ruta: str) -> Path:
        local = (self._raiz / _ruta_segura(ruta)).resolve()
        if not local.is_relative_to(self._raiz):
            raise ErrorOrigen(f"Ruta fuera del origen: {ruta!r}")
        return local

    def listar(self, carpeta: str) -> list[str]:
        base = self._local(carpeta)
        if not base.is_dir():
            raise ErrorOrigen(f"No existe la carpeta {carpeta!r} en el origen")
        return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())

    def bajar(self, archivo: str, destino: Path) -> None:
        local = self._local(archivo)
        if not local.is_file():
            raise ErrorOrigen(f"No existe el archivo {archivo!r} en el origen")
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, destino)
