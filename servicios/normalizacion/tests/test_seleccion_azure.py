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
    return []

@contextmanager
def almacen_blob_desde_entorno():
    assert os.environ["ALMACEN_BLOB_CUENTA"] == "cuentafalsa"
    blobs = {}
    operaciones = []

    def escribir(uri, datos):
        assert uri.startswith("pruebas/") and uri.endswith("/acceso.json")
        if os.environ.get("ACCESO_AZURE_DE_PRUEBA") == "solo-lectura":
            raise AlmacenSinPermiso("sin permiso de escritura de prueba")
        blobs[uri] = datos
        operaciones.append("escribir")

    def leer(uri):
        operaciones.append("leer")
        return blobs[uri]

    def borrar(nombre, *, delete_snapshots):
        operaciones.append("borrar")
        del blobs[nombre]

    cliente = SimpleNamespace(delete_blob=borrar)
    yield SimpleNamespace(uri=str, listar=_listar, escribir=escribir, leer=leer,
                          cliente_contenedor=lambda: cliente, blobs=blobs, operaciones=operaciones)
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
            assert almacen_blob_azure_sesion.operaciones == ["escribir", "leer", "borrar"]
            assert almacen_blob_azure_sesion.blobs == {}
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


def test_el_acceso_de_solo_lectura_detiene_la_corrida_con_una_linea(suite_azure, monkeypatch):
    monkeypatch.setenv("ALMACEN_BLOB_CUENTA", "cuentafalsa")
    monkeypatch.setenv("ACCESO_AZURE_DE_PRUEBA", "solo-lectura")
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
    assert sum("Sin acceso a Azure: sin permiso de escritura de prueba" in linea
               for linea in resultado.stdout.lines) == 1
    resultado.assert_outcomes()


def test_la_limpieza_del_uuid_sigue_si_falla_un_borrado_y_solo_informa_conteos(suite_azure):
    suite_azure.makepyfile("""
        from types import SimpleNamespace

        import pytest
        from azure.core.exceptions import AzureError

        from test_almacen_contrato import uris_ajenas_blob_azure


        @pytest.fixture
        def cliente_contenedor_blob_azure(prefijo_blob_azure):
            blobs = [f"{prefijo_blob_azure}/{ruta}/nombre-reservado.json"
                     for ruta in ("interno", "otra", "internod")]
            fuera = "pruebas/otro-uuid/nombre-reservado.json"
            blobs.append(fuera)

            def listar(*, name_starts_with):
                assert name_starts_with == prefijo_blob_azure + "/"
                return (SimpleNamespace(name=nombre) for nombre in blobs if nombre.startswith(name_starts_with))

            def borrar(nombre, *, delete_snapshots):
                if nombre == blobs[0]:
                    raise AzureError(nombre)
                blobs.remove(nombre)

            yield SimpleNamespace(account_name="cuentafalsa", container_name="contenedor-falso",
                                  list_blobs=listar, delete_blob=borrar)
            assert blobs == [f"{prefijo_blob_azure}/interno/nombre-reservado.json", fuera]


        def test_azure(almacen_blob_de_prueba, prefijo_blob_azure, uris_ajenas_blob_azure):
            from urllib.parse import urlsplit

            assert urlsplit(almacen_blob_de_prueba.uri("a.json")).path.endswith(f"/{prefijo_blob_azure}/interno/a.json")
            assert [urlsplit(uri).path for uri in uris_ajenas_blob_azure[-2:]] == [
                f"/contenedor-falso/{prefijo_blob_azure}/otra/a.json",
                f"/contenedor-falso/{prefijo_blob_azure}/internod/a.json",
            ]
    """)

    resultado = suite_azure.runpytest("-q")

    resultado.assert_outcomes(passed=1, errors=1)
    assert "Blobs de prueba restantes (1). Fallos de borrado (1)." in resultado.stdout.str()
    assert "nombre-reservado.json" not in resultado.stdout.str()
