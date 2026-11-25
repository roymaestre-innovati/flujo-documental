import os
import shutil
from uuid import uuid4

import pytest
from azure.core.exceptions import AzureError
from azure.storage.blob import ContainerClient

from normalizacion.almacen import AlmacenSinPermiso
from normalizacion.almacen_blob import AlmacenBlob, almacen_blob_desde_entorno


@pytest.fixture(autouse=True)
def _sin_almacen_blob(monkeypatch, request):
    if request.node.get_closest_marker("azure") is None:
        monkeypatch.delenv("ALMACEN_BLOB_CUENTA", raising=False)
        monkeypatch.delenv("ALMACEN_BLOB_CONTENEDOR", raising=False)


def _detener_si_falta_acceso(probar):
    """Corta la corrida en la primera falla de acceso a Azure."""
    try:
        return probar()
    except AlmacenSinPermiso as error:
        pytest.exit(f"Sin acceso a Azure: {error}", returncode=1)


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
        prefijo = almacen.uri(f"pruebas/{uuid4()}")
        _detener_si_falta_acceso(lambda: almacen.listar(prefijo))
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
def almacen_blob_de_prueba(cliente_contenedor_blob_azure, prefijo_blob_azure):
    cliente = cliente_contenedor_blob_azure
    prefijo = prefijo_blob_azure
    with AlmacenBlob(cliente.account_name, cliente.container_name, prefijo, cliente=cliente) as almacen:
        try:
            yield almacen
        finally:
            carpeta = f"{prefijo}/"
            try:
                for blob in list(cliente.list_blobs(name_starts_with=carpeta)):
                    cliente.delete_blob(blob.name, delete_snapshots="include")
                quedan_blobs = next(iter(cliente.list_blobs(name_starts_with=carpeta)), None) is not None
            except AzureError:
                pytest.fail("Falló la limpieza de los blobs de prueba.", pytrace=False)
            if quedan_blobs:
                pytest.fail("Quedaron blobs bajo el prefijo de prueba.", pytrace=False)


@pytest.fixture(autouse=True)
def _registros_limpios():
    """Deja el registro del paquete como estaba: `registros.configurar()` lo cambia."""
    import logging

    paquete = logging.getLogger("normalizacion")
    antes = (list(paquete.handlers), paquete.level, paquete.propagate)
    yield
    paquete.handlers[:] = antes[0]
    paquete.setLevel(antes[1])
    paquete.propagate = antes[2]
