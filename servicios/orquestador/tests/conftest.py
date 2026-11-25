import os
import shutil
from functools import wraps
from uuid import uuid4

import pytest
from limpiar_estado_prueba import limpiar_procesos
from servicebus_azure import ESPERA_SERVICEBUS_AZURE_S, ids_en_colas, limpiar_colas, nombre_corto

from orquestador.cola_servicebus import cola_desde_entorno
from orquestador.errores import ErrorDeConfiguracion
from orquestador.estado_mongo import EstadoMongo, coleccion_desde_entorno


def _detener_si_falta_acceso(probar) -> None:
    """Corta toda la corrida en la primera falla de permisos, con una sola línea,
    en vez de repetir el mismo error en cada prueba."""
    try:
        probar()
    except ErrorDeConfiguracion as error:
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
        _detener_si_falta_acceso(lambda: EstadoMongo(coleccion).leer("PRUEBA-acceso", "proceso", "PRUEBA-acceso"))
        yield coleccion


@pytest.fixture
def coleccion_mongo_de_prueba(coleccion_mongo_azure, procesos_de_prueba):
    try:
        yield coleccion_mongo_azure
    finally:
        limpiar_procesos(coleccion_mongo_azure, procesos_de_prueba)


@pytest.fixture(scope="session")
def cliente_cola_azure(pytestconfig):
    if not pytestconfig.getoption("--azure"):
        pytest.skip("usa recursos de Azure; correr con --azure")
    with cola_desde_entorno(espera_recibir_s=ESPERA_SERVICEBUS_AZURE_S) as cola:
        _detener_si_falta_acceso(lambda: ids_en_colas(cola))
        yield cola


@pytest.fixture
def cola_servicebus_de_prueba(cliente_cola_azure, monkeypatch):
    cola = cliente_cola_azure
    ocupadas = [f"{nombre_corto(subcola)} tiene {len(ids)} mensaje(s)"
                for subcola, ids in ids_en_colas(cola).items() if ids]
    if ocupadas:
        pytest.fail("Las colas de prueba deben estar vacías. " + ". ".join(ocupadas), pytrace=False)

    publicados = set()
    recibidos = []
    publicar = cola.publicar
    recibir = cola._recibir

    @wraps(publicar)
    def registrar_publicado(*args, **kwargs):
        id_mensaje = publicar(*args, **kwargs)
        publicados.add(id_mensaje)
        return id_mensaje

    def registrar_recibido(nombre, receptor, espera):
        original = recibir(nombre, receptor, espera)
        if original is not None:
            recibidos.append((receptor, original))
        return original

    try:
        with monkeypatch.context() as parche:
            parche.setattr(cola, "publicar", registrar_publicado)
            parche.setattr(cola, "_recibir", registrar_recibido)
            yield cola
    finally:
        restos = limpiar_colas(cola, publicados, recibidos)
        ocupadas = [f"{nombre_corto(subcola)} conserva los ids {', '.join(map(str, ids))}"
                    for subcola, ids in restos.items() if ids]
        if ocupadas:
            pytest.fail("Quedaron mensajes al limpiar. " + ". ".join(ocupadas), pytrace=False)
