import os
import shutil
from contextlib import ExitStack
from uuid import uuid4

import pytest

from orquestador.estado_mongo import coleccion_desde_entorno


def pytest_collection_modifyitems(config, items):
    """Salta las pruebas si faltan sus comandos o variables de entorno."""
    sin_soffice = not shutil.which("soffice")
    for item in items:
        if sin_soffice and item.get_closest_marker("libreoffice"):
            item.add_marker(pytest.mark.skip(reason="soffice (LibreOffice) no está instalado"))
        marca_azure = item.get_closest_marker("azure")
        if marca_azure:
            variable = marca_azure.kwargs.get("variable", "ESTADO_MONGO_URL")
            if not os.environ.get(variable):
                item.add_marker(pytest.mark.skip(reason=f"Falta {variable} para correr contra Azure"))


@pytest.fixture
def procesos_de_prueba():
    return f"PRUEBA-{uuid4()}", f"PRUEBA-{uuid4()}"


@pytest.fixture(scope="session")
def coleccion_mongo_azure():
    coleccion = coleccion_desde_entorno()
    with coleccion.database.client:
        yield coleccion


@pytest.fixture
def coleccion_mongo_de_prueba(coleccion_mongo_azure, procesos_de_prueba):
    # Cada borrado va a una partición. Se intentan todos aunque alguno falle.
    with ExitStack() as limpieza:
        for id_proceso in procesos_de_prueba:
            limpieza.callback(coleccion_mongo_azure.delete_many, {"id_proceso": id_proceso})
        yield coleccion_mongo_azure
