"""Selección de pruebas de Azure con un almacén falso."""

from pathlib import Path

import pytest

pytest_plugins = ("pytester",)


@pytest.fixture
def suite_azure(pytester):
    pytester.makeini("[pytest]\nmarkers = azure(variable): prueba de Azure")
    conftest = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    pytester.makeconftest(conftest + """
from contextlib import contextmanager
from types import SimpleNamespace

def _listar(prefijo):
    assert prefijo.startswith("pruebas/")
    if os.environ.get("ACCESO_AZURE_DE_PRUEBA") == "negado":
        raise AlmacenSinPermiso("sin rol de prueba")
    return []

@contextmanager
def almacen_blob_desde_entorno():
    assert os.environ["ALMACEN_BLOB_CUENTA"] == "cuentafalsa"
    yield SimpleNamespace(uri=str, listar=_listar)
""")
    return pytester


@pytest.mark.parametrize(("opciones", "cuenta", "motivo"), [
    ([], "cuentafalsa", "usa recursos de Azure; correr con --azure"),
    (["--azure"], None, "Falta ALMACEN_BLOB_CUENTA para correr contra Azure"),
    (["--azure"], "cuentafalsa", None),
])
def test_seleccionar_azure_con_m_respeta_la_opcion_y_la_variable(suite_azure, monkeypatch, opciones, cuenta, motivo):
    if cuenta is None:
        monkeypatch.delenv("ALMACEN_BLOB_CUENTA", raising=False)
    else:
        monkeypatch.setenv("ALMACEN_BLOB_CUENTA", cuenta)
    monkeypatch.setenv("ALMACEN_BLOB_CONTENEDOR", "contenedor-falso")
    suite_azure.makepyfile("""
        import os

        import pytest

        @pytest.mark.azure(variable="ALMACEN_BLOB_CUENTA")
        def test_azure(almacen_blob_azure_sesion):
            assert os.environ["ALMACEN_BLOB_CUENTA"] == "cuentafalsa"
            assert os.environ["ALMACEN_BLOB_CONTENEDOR"] == "contenedor-falso"
    """)

    resultado = suite_azure.runpytest("-m", "azure", "-rs", *opciones)

    if motivo:
        resultado.assert_outcomes(skipped=1)
        resultado.stdout.fnmatch_lines([f"*{motivo}*"])
    else:
        resultado.assert_outcomes(passed=1)


def test_marca_azure_sin_variable_es_error_aunque_m_la_deseleccione(suite_azure):
    suite_azure.makepyfile("""
        import pytest

        @pytest.mark.azure
        def test_azure():
            pass
    """)

    resultado = suite_azure.runpytest("-m", "not azure")

    assert resultado.ret == pytest.ExitCode.USAGE_ERROR
    resultado.stderr.fnmatch_lines(["*test_azure: la marca azure requiere indicar variable=*"])


def test_sin_acceso_a_azure_detiene_la_corrida_con_una_linea(suite_azure, monkeypatch):
    monkeypatch.setenv("ALMACEN_BLOB_CUENTA", "cuentafalsa")
    monkeypatch.setenv("ACCESO_AZURE_DE_PRUEBA", "negado")
    suite_azure.makepyfile("""
        import pytest

        pytestmark = pytest.mark.azure(variable="ALMACEN_BLOB_CUENTA")

        def test_uno(almacen_blob_azure_sesion):
            pytest.fail("La prueba se ejecutó sin acceso a Azure")

        def test_dos(almacen_blob_azure_sesion):
            pytest.fail("La corrida siguió después del error de acceso")
    """)

    resultado = suite_azure.runpytest("-m", "azure", "--azure")

    assert resultado.ret == 1
    assert sum("Sin acceso a Azure: sin rol de prueba" in linea for linea in resultado.stdout.lines) == 1
    resultado.assert_outcomes()
