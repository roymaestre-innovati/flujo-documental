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
