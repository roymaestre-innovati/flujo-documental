import os
import shutil
from uuid import uuid4

import pytest
from azure.core.exceptions import AzureError
from azure.storage.blob import ContainerClient
from normalizacion.almacen import AlmacenNoDisponible, AlmacenSinPermiso, ErrorAlmacen
from normalizacion.almacen_blob import (
    AlmacenBlob,
    _traducir_fallas,
    almacen_blob_desde_entorno,
)


@pytest.fixture(autouse=True)
def _sin_almacen_blob(monkeypatch, request):
    if request.node.get_closest_marker("azure") is None:
        monkeypatch.delenv("ALMACEN_BLOB_CUENTA", raising=False)
        monkeypatch.delenv("ALMACEN_BLOB_CONTENEDOR", raising=False)


def _detener_si_falta_acceso(probar):
    """Corta la corrida en la primera falla de acceso a Azure."""
    try:
        return probar()
    except (AlmacenSinPermiso, AlmacenNoDisponible, ErrorAlmacen, RuntimeError) as error:
        pytest.exit(f"Sin acceso a Azure: {error}", returncode=1)


def _comprobar_acceso(almacen):
    prefijo = f"pruebas/{uuid4()}"
    nombre = f"{prefijo}/acceso.json"
    uri = almacen.uri(nombre)
    datos = b'{"prueba": true}'
    almacen.listar(almacen.uri(prefijo))
    almacen.escribir(uri, datos)
    try:
        if almacen.leer(uri) != datos:
            raise AlmacenSinPermiso("La comprobación de lectura devolvió un contenido inesperado.")
    finally:
        with _traducir_fallas("borrar blob de acceso"):
            almacen.cliente_contenedor().delete_blob(nombre, delete_snapshots="include")


def pytest_addoption(parser):
    parser.addoption("--azure", action="store_true", help="corre las pruebas que usan recursos de Azure")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Valida los requisitos de Azure antes de que -m filtre la colección."""
    sin_soffice = not shutil.which("soffice")
    for item in items:
        if sin_soffice and item.get_closest_marker("libreoffice"):
            item.add_marker(pytest.mark.skip(reason="soffice (LibreOffice) no está instalado"))
        marca_azure = item.get_closest_marker("azure")
        if marca_azure:
            variable = marca_azure.kwargs.get("variable")
            if not isinstance(variable, str) or not variable.strip():
                raise pytest.UsageError(
                    f"{item.nodeid}: la marca azure requiere indicar variable= con el nombre de la variable de entorno"
                )
            if not config.getoption("--azure"):
                item.add_marker(pytest.mark.skip(reason="usa recursos de Azure; correr con --azure"))
            elif not os.environ.get(variable):
                item.add_marker(pytest.mark.skip(reason=f"Falta {variable} para correr contra Azure"))


@pytest.fixture(scope="session")
def almacen_blob_azure_sesion(pytestconfig):
    if not pytestconfig.getoption("--azure"):
        pytest.skip("usa recursos de Azure; correr con --azure")
    with _detener_si_falta_acceso(almacen_blob_desde_entorno) as almacen:
        _detener_si_falta_acceso(lambda: _comprobar_acceso(almacen))
        yield almacen


@pytest.fixture(scope="session")
def cliente_contenedor_blob_azure(almacen_blob_azure_sesion):
    cliente = almacen_blob_azure_sesion.cliente_contenedor()
    # Así el blob de 5 MiB se carga en bloques con el SDK.
    with ContainerClient.from_container_url(
        cliente.url, credential=cliente.credential, max_single_put_size=4 * 1024**2,
        connection_timeout=20, read_timeout=60,
    ) as contenedor:
        yield contenedor


@pytest.fixture
def prefijo_blob_azure():
    return f"pruebas/{uuid4()}"


@pytest.fixture
def prefijo_interno_blob_azure(prefijo_blob_azure):
    return f"{prefijo_blob_azure}/interno"


def _limpiar_blobs_de_prueba(cliente, carpeta):
    try:
        blobs = list(cliente.list_blobs(name_starts_with=carpeta))
    except AzureError:
        pytest.fail("Falló el listado de blobs para la limpieza.", pytrace=False)

    fallos = 0
    for blob in blobs:
        try:
            cliente.delete_blob(blob.name, delete_snapshots="include")
        except AzureError:
            fallos += 1

    try:
        restantes = sum(1 for _ in cliente.list_blobs(name_starts_with=carpeta))
    except AzureError:
        pytest.fail(f"Falló la comprobación de la limpieza tras {fallos} fallos de borrado.", pytrace=False)
    if restantes or fallos:
        pytest.fail(f"Blobs de prueba restantes ({restantes}). Fallos de borrado ({fallos}).", pytrace=False)


@pytest.fixture
def almacen_blob_de_prueba(cliente_contenedor_blob_azure, prefijo_blob_azure, prefijo_interno_blob_azure):
    cliente = cliente_contenedor_blob_azure
    with AlmacenBlob(cliente.account_name, cliente.container_name, prefijo_interno_blob_azure, cliente=cliente) as almacen:
        try:
            yield almacen
        finally:
            _limpiar_blobs_de_prueba(cliente, f"{prefijo_blob_azure}/")


@pytest.fixture(autouse=True)
def _registros_limpios():
    """Deja el registro del paquete como estaba: `registros.configurar()` lo cambia."""
    import logging

    paquete = logging.getLogger("normalizacion")
    registro_http = logging.getLogger("azure.core.pipeline.policies.http_logging_policy")
    antes = (list(paquete.handlers), paquete.level, paquete.propagate)
    nivel_http = registro_http.level
    yield
    paquete.handlers[:] = antes[0]
    paquete.setLevel(antes[1])
    paquete.propagate = antes[2]
    registro_http.setLevel(nivel_http)
