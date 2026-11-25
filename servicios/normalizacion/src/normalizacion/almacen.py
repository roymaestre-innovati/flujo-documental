"""Dónde se guardan los resultados de la normalización.

La interfaz `Almacen` permite usar una carpeta con URI `file://` (`AlmacenLocal`)
o Azure Blob Storage (`normalizacion.almacen_blob`).
"""

import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from typing import Self
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
    """URI inválida, fuera del almacén o inexistente. Se lanza una de sus dos subclases."""


class UriInvalida(ErrorAlmacen):
    """La URI o la ruta no son de este almacén, o no sirven. Repetir no cambia nada."""


class NoEncontrado(ErrorAlmacen):
    """La URI es de este almacén, pero ahí no hay ningún archivo."""


class AlmacenNoDisponible(Exception):
    """Una falla transitoria del almacén, con la espera que pidió el servicio."""

    def __init__(self, descripcion: str = "", espera_s: float | None = None) -> None:
        super().__init__(descripcion)
        self.espera_s = espera_s


class AlmacenSinPermiso(Exception):
    """Acceso denegado o configuración del almacén inválida."""


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

    def cerrar(self) -> None:
        """Libera los recursos propios del almacén, si tiene."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.cerrar()


class AlmacenLocal(Almacen):
    def __init__(self, raiz: str | os.PathLike[str]) -> None:
        self.raiz = Path(raiz).resolve()

    def uri(self, ruta: str) -> str:
        relativa = PurePosixPath(ruta)
        if relativa.is_absolute() or ".." in relativa.parts or not relativa.parts:
            raise UriInvalida("La ruta debe ser relativa y no puede salir del almacén.")
        return self.raiz.joinpath(*relativa.parts).as_uri()

    def _ruta(self, uri: str) -> Path:
        try:
            partes = urlparse(uri)
            if partes.scheme != "file" or partes.netloc not in ("", "localhost"):
                raise UriInvalida("El almacén local solo acepta URI file:// locales.")
            ruta = Path(unquote(partes.path)).resolve()
        except ValueError:  # una autoridad mal formada o un carácter nulo
            raise UriInvalida("La URI no es válida.") from None
        if ruta != self.raiz and self.raiz not in ruta.parents:
            raise UriInvalida("La URI está fuera del almacén.")
        return ruta

    def leer(self, uri: str) -> bytes:
        ruta = self._ruta(uri)
        if not ruta.is_file():
            raise NoEncontrado("No existe el archivo pedido en el almacén.")
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


def almacen_desde_entorno(raiz_local: str | os.PathLike[str]) -> Almacen:
    """El almacén configurado en el entorno o el local si falta la cuenta Blob."""
    if "ALMACEN_BLOB_CUENTA" not in os.environ:
        return AlmacenLocal(raiz_local)

    from .almacen_blob import almacen_blob_desde_entorno

    return almacen_blob_desde_entorno()
