import shutil

import pytest


def pytest_collection_modifyitems(config, items):
    """Salta las pruebas marcadas `libreoffice` si `soffice` no está instalado."""
    if shutil.which("soffice"):
        return
    saltar = pytest.mark.skip(reason="soffice (LibreOffice) no está instalado")
    for item in items:
        if "libreoffice" in item.keywords:
            item.add_marker(saltar)


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
