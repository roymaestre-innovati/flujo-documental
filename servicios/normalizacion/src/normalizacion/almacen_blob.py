"""Almacén de resultados en Azure Blob Storage, con el extra `azure`."""

import mimetypes
import os
import re
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager, nullcontext
from enum import Enum
from math import isfinite
from pathlib import PurePosixPath
from threading import Lock, local
from typing import Self
from urllib.parse import quote, unquote, urlsplit

from azure.core.credentials import TokenCredential
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    IncompleteReadError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.core.utils import CaseInsensitiveDict
from azure.identity import DefaultAzureCredential
from azure.storage.blob import ContainerClient, ContentSettings

from .almacen import Almacen, AlmacenNoDisponible, AlmacenSinPermiso, ErrorAlmacen

_CONTENEDOR_PREDETERMINADO = "evaluacion-ofertas"
_ESTADOS_TRANSITORIOS = {408, 429, 500, 502, 503, 504}


class _BlobNoEncontrado(ErrorAlmacen):
    """El contenedor respondió que falta el blob pedido."""


def _codigo_servicio(error: HttpResponseError, cabeceras: Mapping[str, str]) -> str | None:
    codigo = getattr(error, "error_code", None) or cabeceras.get("x-ms-error-code")
    if isinstance(codigo, Enum):
        codigo = codigo.value
    if isinstance(codigo, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", codigo):
        return codigo
    return None


def _espera_pedida(cabeceras: Mapping[str, str]) -> float | None:
    for nombre, divisor in (("Retry-After", 1), ("x-ms-retry-after-ms", 1000)):
        valor = cabeceras.get(nombre)
        if valor is None:
            continue
        try:
            segundos = float(valor) / divisor
        except (ValueError, TypeError, OverflowError):
            continue
        if isfinite(segundos) and segundos >= 0:
            return segundos
    return None


@contextmanager
def _traducir_fallas(operacion: str) -> Iterator[None]:
    """Conserva solo la operación, el estado HTTP y el código del servicio."""
    try:
        yield
    except (ServiceRequestError, ServiceResponseError):
        raise AlmacenNoDisponible(f"Blob {operacion}") from None
    except HttpResponseError as error:
        estado = error.status_code
        cabeceras = CaseInsensitiveDict(getattr(error.response, "headers", None) or {})
        codigo = _codigo_servicio(error, cabeceras)
        mensaje = f"Blob {operacion}"
        if estado is not None:
            mensaje += f" HTTP {estado}"
        if codigo is not None:
            mensaje += f" [{codigo}]"

        if isinstance(error, ClientAuthenticationError) or estado in (401, 403) or codigo == "ContainerNotFound":
            raise AlmacenSinPermiso(mensaje) from None
        if estado == 404 and codigo != "BlobNotFound":
            raise AlmacenSinPermiso(mensaje) from None
        if estado in (404, None) and codigo == "BlobNotFound" and operacion in ("leer", "existe"):
            raise _BlobNoEncontrado(mensaje) from None
        # El SDK de Blob puede envolver el corte de descarga en un HttpResponseError sin estado.
        descarga_interrumpida = estado is None and (operacion == "leer" or isinstance(error, IncompleteReadError))
        if estado in _ESTADOS_TRANSITORIOS or descarga_interrumpida:
            raise AlmacenNoDisponible(mensaje, espera_s=_espera_pedida(cabeceras)) from None
        raise RuntimeError(mensaje) from None


def _cerrar(recurso, operacion: str) -> None:
    with _traducir_fallas(operacion):
        recurso.close()


def _validar_configuracion(cuenta: str, contenedor: str) -> None:
    if not re.fullmatch(r"[a-z0-9]{3,24}", cuenta):
        raise AlmacenSinPermiso("ALMACEN_BLOB_CUENTA falta o es inválida.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", contenedor) or "--" in contenedor:
        raise AlmacenSinPermiso("ALMACEN_BLOB_CONTENEDOR es inválida.")


def _ruta_relativa(ruta: str) -> PurePosixPath:
    relativa = PurePosixPath(ruta)
    if relativa.is_absolute() or ".." in relativa.parts or not relativa.parts:
        raise ErrorAlmacen("La ruta debe ser relativa y no puede salir del almacén.")
    return relativa


class AlmacenBlob(Almacen):
    """Contenedor con un prefijo opcional que delimita el almacén.

    Un cliente inyectado se usa bajo un candado. Con una credencial se crea un
    cliente por hilo. El cliente o la credencial inyectados son del llamador.
    """

    def __init__(
        self,
        cuenta: str,
        contenedor: str,
        prefijo: str = "",
        *,
        cliente: ContainerClient | None = None,
        credencial: TokenCredential | None = None,
    ) -> None:
        _validar_configuracion(cuenta, contenedor)
        if (cliente is None) == (credencial is None):
            raise TypeError("Se requiere un cliente de contenedor o una credencial.")
        self._host = f"{cuenta}.blob.core.windows.net"
        self._url_cuenta = f"https://{self._host}"
        self._contenedor = contenedor
        self._prefijo = _ruta_relativa(prefijo).as_posix() if prefijo else ""
        self._credencial = credencial
        self._cliente_inyectado = cliente
        self._proteger_cliente = Lock() if cliente is not None else nullcontext()
        self._clientes = local()
        self._candado_clientes = Lock()
        self._recursos = ExitStack()
        self._cerrado = False

    def _cliente_del_hilo(self) -> ContainerClient:
        with self._candado_clientes:
            if self._cerrado:
                raise RuntimeError("El almacén Blob está cerrado.")
            if self._cliente_inyectado is not None:
                return self._cliente_inyectado
            cliente = getattr(self._clientes, "cliente", None)
            if cliente is None:
                cliente = ContainerClient(
                    self._url_cuenta, self._contenedor, credential=self._credencial,
                    connection_timeout=20, read_timeout=60,
                )
                self._recursos.callback(_cerrar, cliente, "cerrar cliente")
                self._clientes.cliente = cliente
            return cliente

    def cerrar(self) -> None:
        """Cierra los recursos propios al terminar las operaciones."""
        with self._proteger_cliente, self._candado_clientes:
            self._cerrado = True
            self._recursos.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.cerrar()

    def _uri_blob(self, nombre: str) -> str:
        return f"{self._url_cuenta}/{self._contenedor}/{quote(nombre)}"

    def uri(self, ruta: str) -> str:
        nombre = PurePosixPath(self._prefijo, _ruta_relativa(ruta)).as_posix()
        return self._uri_blob(nombre)

    def _nombre_blob(self, uri: str, *, listar: bool = False) -> str:
        if not uri or ord(uri[0]) <= 32 or any(caracter in uri for caracter in "?#\r\n\t"):
            raise ErrorAlmacen("La URI del almacén Blob es inválida.")
        try:
            partes = urlsplit(uri)
            ruta = unquote(partes.path, errors="strict")
        except ValueError:
            raise ErrorAlmacen("La URI del almacén Blob es inválida.") from None
        if partes.scheme != "https" or partes.netloc.lower() != self._host:
            raise ErrorAlmacen("La URI está fuera del almacén Blob.")

        contenedor, _, nombre = ruta.removeprefix("/").partition("/")
        if listar:
            nombre = nombre.rstrip("/")
        if contenedor != self._contenedor or ".." in nombre.split("/"):
            raise ErrorAlmacen("La URI está fuera del almacén Blob.")
        if self._prefijo and nombre != self._prefijo and not nombre.startswith(self._prefijo + "/"):
            raise ErrorAlmacen("La URI está fuera del almacén Blob.")
        if not nombre and not listar:
            raise ErrorAlmacen("La URI del almacén Blob debe indicar un archivo.")
        return nombre

    def leer(self, uri: str) -> bytes:
        nombre = self._nombre_blob(uri)
        with _traducir_fallas("leer"), self._proteger_cliente:
            cliente = self._cliente_del_hilo().get_blob_client(nombre)
            return cliente.download_blob().readall()

    def escribir(self, uri: str, datos: bytes) -> None:
        nombre = self._nombre_blob(uri)
        tipo, _ = mimetypes.guess_type(f"/{nombre}")
        opciones = ContentSettings(content_type=tipo or "application/octet-stream")
        with _traducir_fallas("escribir"), self._proteger_cliente:
            cliente = self._cliente_del_hilo().get_blob_client(nombre)
            cliente.upload_blob(datos, overwrite=True, content_settings=opciones)

    def existe(self, uri: str) -> bool:
        nombre = self._nombre_blob(uri)
        try:
            with _traducir_fallas("existe"), self._proteger_cliente:
                self._cliente_del_hilo().get_blob_client(nombre).get_blob_properties()
        except _BlobNoEncontrado:
            return False
        return True

    def listar(self, prefijo: str) -> list[str]:
        base = self._nombre_blob(prefijo, listar=True)
        carpeta = base + "/" if base else ""
        with _traducir_fallas("listar"), self._proteger_cliente:
            cliente = self._cliente_del_hilo()
            nombres = [blob.name for blob in cliente.list_blobs(name_starts_with=base)
                       if blob.name == base or blob.name.startswith(carpeta)]
        if base and base in nombres:
            return [self._uri_blob(base)]
        return sorted(self._uri_blob(nombre) for nombre in nombres)


def almacen_blob_desde_entorno() -> AlmacenBlob:
    """Arma el almacén con la identidad del entorno y le transfiere sus recursos."""
    cuenta = os.environ.get("ALMACEN_BLOB_CUENTA", "")
    contenedor = os.environ.get("ALMACEN_BLOB_CONTENEDOR", _CONTENEDOR_PREDETERMINADO)
    _validar_configuracion(cuenta, contenedor)

    with ExitStack() as recursos:
        with _traducir_fallas("crear credencial"):
            try:
                credencial = DefaultAzureCredential(exclude_interactive_browser_credential=True)
            except ValueError:
                raise AlmacenSinPermiso("Blob crear credencial") from None
        recursos.callback(_cerrar, credencial, "cerrar credencial")
        almacen = AlmacenBlob(cuenta, contenedor, credencial=credencial)
        almacen._recursos = recursos
        with _traducir_fallas("crear cliente"):
            almacen._cliente_del_hilo()
        almacen._recursos = recursos.pop_all()
        return almacen
