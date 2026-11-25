"""Selección de pruebas de Azure con un cliente falso."""

from pathlib import Path

import pytest

pytest_plugins = ("pytester",)


@pytest.fixture
def suite_azure(pytester):
    pytester.makeini("[pytest]\nmarkers = azure(variable): prueba de Azure")
    conftest = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    pytester.makeconftest(conftest + """
from contextlib import nullcontext
from types import SimpleNamespace

def coleccion_desde_entorno():
    assert os.environ.get("VARIABLE_AZURE_DE_PRUEBA") == "presente"
    return SimpleNamespace(database=SimpleNamespace(client=nullcontext()), nombre="falsa")

def _sin_rol():
    raise ErrorDeConfiguracion("sin rol de prueba")

_detener_real = _detener_si_falta_acceso

def _detener_si_falta_acceso(probar):
    # La colección falsa no se puede consultar: solo se prueba el corte cuando se pide.
    if os.environ.get("ACCESO_AZURE_DE_PRUEBA") == "negado":
        _detener_real(_sin_rol)
""")
    return pytester


@pytest.mark.parametrize(("opciones", "valor", "motivo"), [
    ([], "presente", "usa recursos de Azure; correr con --azure"),
    (["--azure"], None, "Falta VARIABLE_AZURE_DE_PRUEBA para correr contra Azure"),
    (["--azure"], "presente", None),
])
def test_seleccionar_azure_con_m_respeta_la_opcion_y_la_variable(suite_azure, monkeypatch, opciones, valor, motivo):
    if valor is None:
        monkeypatch.delenv("VARIABLE_AZURE_DE_PRUEBA", raising=False)
    else:
        monkeypatch.setenv("VARIABLE_AZURE_DE_PRUEBA", valor)
    suite_azure.makepyfile("""
        import pytest

        @pytest.mark.azure(variable="VARIABLE_AZURE_DE_PRUEBA")
        def test_azure(coleccion_mongo_azure):
            assert coleccion_mongo_azure.nombre == "falsa"
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
    monkeypatch.setenv("VARIABLE_AZURE_DE_PRUEBA", "presente")
    monkeypatch.setenv("ACCESO_AZURE_DE_PRUEBA", "negado")
    suite_azure.makepyfile("""
        import pytest

        @pytest.mark.azure(variable="VARIABLE_AZURE_DE_PRUEBA")
        def test_uno(coleccion_mongo_azure):
            pass

        @pytest.mark.azure(variable="VARIABLE_AZURE_DE_PRUEBA")
        def test_dos(coleccion_mongo_azure):
            pass
    """)

    resultado = suite_azure.runpytest("-m", "azure", "--azure")

    assert resultado.ret == 1
    resultado.stdout.fnmatch_lines(["*Sin acceso a Azure: sin rol de prueba*"])
    resultado.assert_outcomes()
