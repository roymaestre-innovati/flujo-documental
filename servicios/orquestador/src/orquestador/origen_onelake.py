"""Los originales en OneLake (T02 de `specs/005-orquestador/tasks-entrada-onelake.md`).

Lee la sección `Files/` de un lakehouse de Fabric con la API de Azure Data Lake
Storage Gen2, que es la que acepta OneLake. Los archivos del módulo 1 están en
una cuenta de ADLS propia y llegan por el shortcut `Files/informacion-adjuntos`
(paso 0 del diseño), así que se leen con permisos de Fabric.

La identidad sale de `DefaultAzureCredential`: en Azure, la identidad
administrada del job; en local, el `az login` del equipo. No hay contraseñas.

Cómo se traducen las fallas a las clases de error del orquestador:

| Falla de OneLake                              | Excepción          | Qué pasa                     |
|-----------------------------------------------|--------------------|------------------------------|
| 404: no existe                                | `ErrorOrigen`      | Como en `OrigenLocal`        |
| Bajado de otro tamaño o con otro MD5          | `ArchivoDistinto`  | Como en `OrigenLocal`        |
| 401, 403 o sin identidad                      | `ErrorDeAcceso`    | Configuración: sin reintento, |
|                                               |                    | a operación                  |
| 408, 429, 5xx, sin conexión o sin respuesta   | `ErrorTransitorio` | Reintento; con `Retry-After`, |
|                                               |                    | espera sin contar intento    |
| Cualquier otra respuesta                      | la del SDK         | Un bug: sin reintento        |

El SDK ya reintenta por su cuenta las fallas de red y los 5xx antes de que llegue
aquí la excepción.

Los mensajes de error no llevan rutas ni nombres, solo la operación y el código
(principio 6).
"""

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path, PurePosixPath
from threading import Lock, local
from time import perf_counter
from typing import Any

from .errores import ErrorDeConfiguracion, ErrorTransitorio
from .origen import ArchivoDistinto, ErrorOrigen, Esperado, Origen, _ruta_segura, revisar_bajado

registro = logging.getLogger("orquestador.origen")

ENDPOINT = "https://onelake.dfs.fabric.microsoft.com"
CONCURRENCIA_POR_ARCHIVO = 4
"""Partes de un mismo archivo que se bajan a la vez. El SDK solo parte los
archivos de más de 32 MB, y en la muestra el más grande sin comprimir pesa 11 MB:
casi nunca aplica. Lo que pesa es la latencia por archivo (~1,8 s, nota de T02),
y eso se ataca bajando varios archivos a la vez (T04)."""
TIMEOUT_S = 120
CODIGOS_TRANSITORIOS = {408, 429, 500, 502, 503, 504}


class ErrorDeAcceso(ErrorDeConfiguracion):
    """OneLake no deja entrar a la identidad del job (401 o 403), o no hay
    identidad. Causas típicas: `az login` vencido en local, la identidad
    administrada sin acceso al workspace, la conexión del shortcut del módulo 1
    rota (por ejemplo, tras rotar la llave de su cuenta), un permiso o una opción
    del tenant que cambió, o Conditional Access. Lo revisa operación."""


_CODIGOS = re.compile(r"\b(AADSTS\d+)\b")


def _codigos(error: Any) -> str:
    """Los códigos del servicio que traiga el error, sin el resto del texto (que
    puede traer rutas o nombres de usuario)."""
    codigos = []
    codigo_servicio = getattr(error, "error_code", None)
    if codigo_servicio:
        codigos.append(str(codigo_servicio))
    codigos += sorted(set(_CODIGOS.findall(str(error))))
    return f" [{', '.join(codigos)}]" if codigos else ""


def _espera_pedida(error: Any) -> float | None:
    respuesta = getattr(error, "response", None)
    valor = getattr(respuesta, "headers", {}).get("Retry-After") if respuesta is not None else None
    try:
        return float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


@contextmanager
def traducir_fallas(operacion: str) -> Iterator[None]:
    from azure.core.exceptions import (
        ClientAuthenticationError,
        HttpResponseError,
        ResourceNotFoundError,
        ServiceRequestError,
        ServiceResponseError,
    )

    try:
        yield
    except ResourceNotFoundError:
        raise ErrorOrigen(f"No existe en OneLake ({operacion})") from None
    except ClientAuthenticationError as error:
        raise ErrorDeAcceso(f"OneLake no dejó {operacion}: sin identidad o sin permiso "
                            f"({getattr(error, 'status_code', None) or type(error).__name__})"
                            f"{_codigos(error)}") from None
    except HttpResponseError as error:
        codigo = error.status_code
        if codigo == 404:
            raise ErrorOrigen(f"No existe en OneLake ({operacion})") from None
        if codigo in (401, 403):
            raise ErrorDeAcceso(f"OneLake no dejó {operacion}: HTTP {codigo}{_codigos(error)}") from None
        if codigo in CODIGOS_TRANSITORIOS:
            raise ErrorTransitorio(f"OneLake respondió HTTP {codigo} al {operacion}",
                                   espera_s=_espera_pedida(error)) from None
        raise
    except (ServiceRequestError, ServiceResponseError) as error:
        raise ErrorTransitorio(f"OneLake no respondió al {operacion}: {type(error).__name__}") from None


class OrigenOneLake(Origen):
    """`Files/` de un lakehouse. Las rutas de `listar` y `bajar` son relativas a
    `Files/`, con `/` y sin `..`, igual que en `OrigenLocal`.

    `cliente` es un `FileSystemClient` del workspace; las pruebas pasan uno falso.
    Si se inyecta, se protege con un candado. Si no se da, se crea uno por hilo,
    todos con la misma credencial: `credencial` o, si falta, un
    `DefaultAzureCredential`, que guarda el token para todos.
    """

    def __init__(
        self,
        workspace: str,
        lakehouse: str,
        *,
        credencial: Any = None,
        cliente: Any = None,
        concurrencia_por_archivo: int = CONCURRENCIA_POR_ARCHIVO,
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        item = lakehouse if lakehouse.endswith(".Lakehouse") else f"{lakehouse}.Lakehouse"
        self._files = PurePosixPath(item, "Files")
        self._concurrencia = concurrencia_por_archivo
        self._workspace = workspace
        if cliente is None and credencial is None:
            from azure.identity import DefaultAzureCredential

            credencial = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self._credencial = credencial
        self._timeout_s = timeout_s
        self._clientes = local()
        self._cliente_inyectado = cliente
        self._proteger_cliente = Lock() if cliente is not None else nullcontext()
        self._candado_conteos = Lock()
        self._archivos_bajados = 0
        self._bytes_bajados = 0
        self._descargas_activas = 0
        self._inicio_descargas = 0.0
        self._tiempo_descarga = 0.0

    @contextmanager
    def _medir_descarga(self) -> Iterator[None]:
        with self._candado_conteos:
            if self._descargas_activas == 0:
                self._inicio_descargas = perf_counter()
            self._descargas_activas += 1
        try:
            yield
        finally:
            with self._candado_conteos:
                self._descargas_activas -= 1
                if self._descargas_activas == 0:
                    self._tiempo_descarga += perf_counter() - self._inicio_descargas

    def conteos_descarga(self) -> dict:
        """Archivos verificados, MB decimales y segundos con descargas en curso.

        Se consulta al terminar la corrida. El tiempo incluye intentos fallidos
        y cuenta una sola vez los intervalos de descargas simultáneas.
        """
        with self._candado_conteos:
            return {
                "archivos_bajados": self._archivos_bajados,
                "mb_bajados": round(self._bytes_bajados / 1_000_000, 3),
                "tiempo_descarga_s": round(self._tiempo_descarga, 3),
            }

    def _cliente_del_hilo(self) -> Any:
        """Cada hilo reutiliza su cliente y su sesión HTTP."""
        if self._cliente_inyectado is not None:
            return self._cliente_inyectado

        cliente = getattr(self._clientes, "cliente", None)
        if cliente is None:
            from azure.storage.filedatalake import FileSystemClient

            cliente = FileSystemClient(ENDPOINT, self._workspace, credential=self._credencial,
                                       connection_timeout=30, read_timeout=self._timeout_s)
            self._clientes.cliente = cliente
        return cliente

    def _ruta(self, ruta: str) -> str:
        return (self._files / _ruta_segura(ruta)).as_posix()

    def listar(self, carpeta: str) -> list[str]:
        base = self._ruta(carpeta)
        with traducir_fallas("listar"), self._proteger_cliente:
            cliente = self._cliente_del_hilo()
            nombres = [p.name for p in cliente.get_paths(path=base, recursive=True) if not p.is_directory]
        prefijo = base + "/"
        relativas = []
        for nombre in nombres:
            if not nombre.startswith(prefijo):
                raise ErrorOrigen("OneLake listó un archivo fuera de la carpeta pedida")
            relativas.append(nombre[len(prefijo):])
        return sorted(relativas)

    def bajar(self, archivo: str, destino: Path, esperado: Esperado | None = None) -> None:
        ruta = self._ruta(archivo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        try:
            with traducir_fallas("bajar"), self._proteger_cliente, self._medir_descarga():
                cliente = self._cliente_del_hilo()
                descarga = cliente.get_file_client(ruta).download_file(max_concurrency=self._concurrencia)
                with open(destino, "wb") as salida:
                    escritos = descarga.readinto(salida)
            if escritos != descarga.size:
                raise ArchivoDistinto(f"La descarga se cortó: {escritos} de {descarga.size} bytes")
        except BaseException:
            destino.unlink(missing_ok=True)
            raise
        revisar_bajado(destino, esperado)
        with self._candado_conteos:
            self._archivos_bajados += 1
            self._bytes_bajados += escritos
