"""Dónde están los originales. En producción, el datalake de Fabric (OneLake,
decisión 35): `OrigenOneLake`, en `origen_onelake.py`. En local y en las
pruebas, una carpeta: `OrigenLocal`.

Los originales no se copian a nuestro almacenamiento (decisión 32): se bajan a
una carpeta temporal solo mientras se normalizan.

Las rutas son siempre relativas a la raíz del origen, con `/` y sin `..`.
"""

import hashlib
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class ErrorOrigen(Exception):
    """La ruta no existe o no es válida."""


class ArchivoDistinto(ErrorOrigen):
    """Lo bajado no coincide con lo esperado: otro tamaño u otro MD5. Puede ser una
    descarga cortada, así que se reintenta como cualquier `ErrorOrigen` al bajar."""


@dataclass(frozen=True)
class Esperado:
    """Lo que debe medir el archivo bajado, según quien lo registró (el módulo 1)."""

    tamano: int | None = None
    md5: str | None = None
    """En hexadecimal."""


def revisar_bajado(destino: Path, esperado: Esperado | None) -> None:
    """Compara el archivo bajado con lo esperado. Si no coincide, lo borra y lanza
    `ArchivoDistinto`. El mensaje no lleva la ruta (principio 6)."""
    if esperado is None:
        return
    tamano = destino.stat().st_size
    if esperado.tamano is not None and tamano != esperado.tamano:
        destino.unlink(missing_ok=True)
        raise ArchivoDistinto(f"Se bajaron {tamano} bytes y se esperaban {esperado.tamano}")
    if esperado.md5 is not None:
        md5 = hashlib.md5(usedforsecurity=False)
        with open(destino, "rb") as entrada:
            for bloque in iter(lambda: entrada.read(1 << 20), b""):
                md5.update(bloque)
        if md5.hexdigest() != esperado.md5.lower():
            destino.unlink(missing_ok=True)
            raise ArchivoDistinto("El MD5 del archivo bajado no es el esperado")


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
    def bajar(self, archivo: str, destino: Path, esperado: Esperado | None = None) -> None:
        """Copia el archivo a `destino` (una ruta de archivo local). Con `esperado`,
        revisa el tamaño y el MD5 y lanza `ArchivoDistinto` si no coinciden."""


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

    def bajar(self, archivo: str, destino: Path, esperado: Esperado | None = None) -> None:
        local = self._local(archivo)
        if not local.is_file():
            raise ErrorOrigen(f"No existe el archivo {archivo!r} en el origen")
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, destino)
        revisar_bajado(destino, esperado)
