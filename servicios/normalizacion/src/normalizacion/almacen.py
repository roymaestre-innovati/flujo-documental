"""Dónde se guardan los resultados de la normalización.

El almacenamiento queda detrás de la interfaz `Almacen` para cambiarlo cuando se
responda A-1 (por ejemplo, por Blob Storage). En esta entrega solo existe
`AlmacenLocal`, sobre una carpeta, con URI `file://`.
"""

import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse


CARPETA_ALMACEN = "almacen"
"""Nombre de la carpeta del almacén dentro de una corrida local."""


def ruta_en_el_almacen(uri: str | None) -> PurePosixPath | None:
    """La ruta relativa al almacén de una URI `file://`, o None.

    Se toma lo que va después de la última carpeta `almacen/`, para que una
    corrida se pueda mover de carpeta y sus URI absolutas sigan sirviendo. Lo usan
    el visor del orquestador y la extracción.
    """
    if not uri:
        return None
    partes_uri = urlparse(uri)
    if partes_uri.scheme != "file":
        return None
    partes = PurePosixPath(unquote(partes_uri.path)).parts
    if CARPETA_ALMACEN not in partes:
        return None
    resto = partes[len(partes) - partes[::-1].index(CARPETA_ALMACEN):]
    if not resto or ".." in resto:
        return None
    return PurePosixPath(*resto)


def en_el_almacen(carpeta: Path, uri: str | None) -> Path | None:
    """El archivo de una URI dentro del almacén de la corrida `carpeta`, o None.

    No deja salir del almacén y devuelve None si el archivo no existe.
    """
    relativa = ruta_en_el_almacen(uri)
    if relativa is None:
        return None
    base = (carpeta / CARPETA_ALMACEN).resolve()
    ruta = base.joinpath(*relativa.parts).resolve()
    return ruta if ruta.is_file() and ruta.is_relative_to(base) else None


class ErrorAlmacen(Exception):
    """URI inválida, fuera del almacén o inexistente."""


class Almacen(ABC):
    @abstractmethod
    def uri(self, ruta: str) -> str:
        """URI de una ruta relativa al almacén, separada con `/`."""

    @abstractmethod
    def leer(self, uri: str) -> bytes: ...

    @abstractmethod
    def escribir(self, uri: str, datos: bytes) -> None:
        """Escribe completo o no escribe: nunca deja un archivo a medias."""

    @abstractmethod
    def existe(self, uri: str) -> bool: ...

    @abstractmethod
    def listar(self, prefijo: str) -> list[str]:
        """URI de todos los archivos bajo `prefijo`, ordenadas."""


class AlmacenLocal(Almacen):
    def __init__(self, raiz: str | os.PathLike[str]) -> None:
        self.raiz = Path(raiz).resolve()

    def uri(self, ruta: str) -> str:
        relativa = PurePosixPath(ruta)
        if relativa.is_absolute() or ".." in relativa.parts or not relativa.parts:
            raise ErrorAlmacen("La ruta debe ser relativa y no puede salir del almacén.")
        return self.raiz.joinpath(*relativa.parts).as_uri()

    def _ruta(self, uri: str) -> Path:
        partes = urlparse(uri)
        if partes.scheme != "file" or partes.netloc not in ("", "localhost"):
            raise ErrorAlmacen("El almacén local solo acepta URI file:// locales.")
        ruta = Path(unquote(partes.path)).resolve()
        if ruta != self.raiz and self.raiz not in ruta.parents:
            raise ErrorAlmacen("La URI está fuera del almacén.")
        return ruta

    def leer(self, uri: str) -> bytes:
        ruta = self._ruta(uri)
        if not ruta.is_file():
            raise ErrorAlmacen("No existe el archivo pedido en el almacén.")
        return ruta.read_bytes()

    def escribir(self, uri: str, datos: bytes) -> None:
        ruta = self._ruta(uri)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=".escribiendo-")
        try:
            with os.fdopen(descriptor, "wb") as archivo:
                archivo.write(datos)
            os.replace(temporal, ruta)
        except BaseException:
            Path(temporal).unlink(missing_ok=True)
            raise

    def existe(self, uri: str) -> bool:
        return self._ruta(uri).is_file()

    def listar(self, prefijo: str) -> list[str]:
        base = self._ruta(prefijo)
        if base.is_file():
            return [base.as_uri()]
        if not base.is_dir():
            return []
        return sorted(
            ruta.as_uri()
            for ruta in base.rglob("*")
            if ruta.is_file() and not ruta.name.startswith(".escribiendo-")
        )
