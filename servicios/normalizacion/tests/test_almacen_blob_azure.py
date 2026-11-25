"""Comprobaciones propias del contenedor de desarrollo de Azure Blob Storage."""

from hashlib import sha256
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.azure(variable="ALMACEN_BLOB_CUENTA")


def _estado_http_anonimo(uri):
    try:
        with urlopen(uri, timeout=20) as respuesta:
            return respuesta.status
    except HTTPError as error:
        with error:
            return error.code
    except (URLError, OSError, HTTPException):
        pytest.fail("Falló la petición HTTP anónima.", pytrace=False)


def test_deniega_lectura_y_listado_anonimos(almacen_blob_de_prueba, cliente_contenedor_blob_azure):
    almacen = almacen_blob_de_prueba
    uri = almacen.uri("privado.json")
    almacen.escribir(uri, b'{"prueba": true}')
    existe = almacen.existe(uri)
    assert existe

    estado_lectura = _estado_http_anonimo(uri)
    estado_listado = _estado_http_anonimo(f"{cliente_contenedor_blob_azure.url}?restype=container&comp=list")

    assert estado_lectura == 404
    assert estado_listado == 404


@pytest.mark.parametrize(("extension", "tipo"), [
    ("pdf", "application/pdf"),
    ("json", "application/json"),
    ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
])
def test_guarda_el_tipo_de_contenido(
    almacen_blob_de_prueba, cliente_contenedor_blob_azure, prefijo_blob_azure, extension, tipo,
):
    nombre = f"inventado.{extension}"
    almacen = almacen_blob_de_prueba
    almacen.escribir(almacen.uri(nombre), b"Contenido inventado")

    blob = cliente_contenedor_blob_azure.get_blob_client(f"{prefijo_blob_azure}/{nombre}")
    propiedades = blob.get_blob_properties()
    assert propiedades.content_settings.content_type == tipo


def test_sube_en_bloques_y_recupera_un_blob_de_5_mib(
    almacen_blob_de_prueba, cliente_contenedor_blob_azure, prefijo_blob_azure,
):
    nombre = "bloques.bin"
    datos = bytes(range(256)) * (5 * 1024**2 // 256)
    almacen = almacen_blob_de_prueba
    uri = almacen.uri(nombre)

    almacen.escribir(uri, datos)

    blob = cliente_contenedor_blob_azure.get_blob_client(f"{prefijo_blob_azure}/{nombre}")
    bloques, _ = blob.get_block_list(block_list_type="committed")
    assert len(bloques) > 1
    assert sha256(almacen.leer(uri)).hexdigest() == sha256(datos).hexdigest()
