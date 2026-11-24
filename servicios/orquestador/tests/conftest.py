import os
import shutil
from uuid import uuid4

import pytest
from limpiar_estado_prueba import limpiar_procesos

from orquestador.estado_mongo import coleccion_desde_entorno


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
                raise pytest.UsageError(f"{item.nodeid}: la marca azure requiere indicar variable= con el nombre de la variable de entorno")
            if not config.getoption("--azure"):
                item.add_marker(pytest.mark.skip(reason="usa recursos de Azure; correr con --azure"))
            elif not os.environ.get(variable):
                item.add_marker(pytest.mark.skip(reason=f"Falta {variable} para correr contra Azure"))


@pytest.fixture
def procesos_de_prueba():
    return f"PRUEBA-{uuid4()}", f"PRUEBA-{uuid4()}"


@pytest.fixture(scope="session")
def coleccion_mongo_azure(pytestconfig):
    if not pytestconfig.getoption("--azure"):
        pytest.skip("usa recursos de Azure; correr con --azure")
    coleccion = coleccion_desde_entorno()
    with coleccion.database.client:
        yield coleccion


@pytest.fixture
def coleccion_mongo_de_prueba(coleccion_mongo_azure, procesos_de_prueba):
    try:
        yield coleccion_mongo_azure
    finally:
        limpiar_procesos(coleccion_mongo_azure, procesos_de_prueba)
