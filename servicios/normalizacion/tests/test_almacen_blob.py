"""Operaciones, errores y recursos de Blob Storage con el SDK simulado."""

import io
import logging
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock, call

import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    IncompleteReadError,
    ResourceNotFoundError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.identity import CredentialUnavailableError
from azure.storage.blob import StorageErrorCode

from blob_falso import ContenedorFalso, error_http
from normalizacion import almacen_blob, registros
from normalizacion.almacen import AlmacenNoDisponible, AlmacenSinPermiso, ErrorAlmacen
from normalizacion.almacen_blob import AlmacenBlob, almacen_blob_desde_entorno

CUENTA = "cuentafalsa"
CONTENEDOR = "evaluacion-ofertas"
URL_CUENTA = f"https://{CUENTA}.blob.core.windows.net"
RAIZ = f"{URL_CUENTA}/{CONTENEDOR}"
RUTA = "carpeta-reservada/archivo-privado.pdf"
VALOR_SENSIBLE = "secreto-inventado"
TEXTO_SERVIDOR = f"{VALOR_SENSIBLE}: error en {RAIZ}/{RUTA}"


@pytest.fixture
def cliente():
    return ContenedorFalso({RUTA: b"datos"})


@pytest.fixture
def almacen(cliente):
    with AlmacenBlob(CUENTA, CONTENEDOR, cliente=cliente) as instancia:
        yield instancia


def test_uri_codifica_los_nombres_y_los_decodifica_una_vez(cliente):
    with AlmacenBlob(CUENTA, CONTENEDOR, "pruebas/abc", cliente=cliente) as almacen:
        ruta = "una carpeta/presentación % # %2E%2E.pdf"
        uri = almacen.uri(ruta)
        assert uri == f"{RAIZ}/pruebas/abc/una%20carpeta/presentaci%C3%B3n%20%25%20%23%20%252E%252E.pdf"
        almacen.escribir(uri, b"pdf")
        assert cliente.blobs[f"pruebas/abc/{ruta}"] == b"pdf"
        assert almacen.leer(uri) == b"pdf"
        assert almacen.listar(almacen.uri("una carpeta")) == [uri]


def test_acepta_el_host_en_mayusculas(almacen):
    uri = f"https://{CUENTA.upper()}.BLOB.CORE.WINDOWS.NET/{CONTENEDOR}/{RUTA}"
    assert almacen.existe(uri)
    assert almacen.leer(uri) == b"datos"
    assert almacen.listar(uri) == [almacen.uri(RUTA)]


@pytest.mark.parametrize(("extension", "tipo"), [
    ("pdf", "application/pdf"),
    ("json", "application/json"),
    ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("desconocida", "application/octet-stream"),
])
def test_escribir_fija_el_tipo_y_sobrescribe(almacen, cliente, extension, tipo):
    nombre = f"archivo.{extension}"
    uri = almacen.uri(nombre)
    almacen.escribir(uri, b"antes")
    almacen.escribir(uri, b"nuevo")
    assert almacen.leer(uri) == b"nuevo"
    assert cliente.cargas == [(nombre, True, tipo), (nombre, True, tipo)]


def test_lista_la_raiz_del_contenedor(almacen, cliente):
    assert almacen.listar(f"{RAIZ}/") == [almacen.uri(RUTA)]
    assert cliente.prefijos_listados == [""]


def test_lista_la_raiz_del_prefijo_por_segmento(cliente):
    cliente.blobs.update({"pruebas/abc/a.pdf": b"", "pruebas/abcd/b.pdf": b""})
    with AlmacenBlob(CUENTA, CONTENEDOR, "pruebas/abc", cliente=cliente) as almacen:
        assert almacen.listar(f"{RAIZ}/pruebas/abc/") == [almacen.uri("a.pdf")]
    assert cliente.prefijos_listados == ["pruebas/abc"]


def test_lista_solo_el_blob_exacto_aunque_tenga_descendientes(almacen, cliente):
    cliente.blobs[f"{RUTA}/descendiente.json"] = b""
    uri = almacen.uri(RUTA)
    assert almacen.listar(uri) == [uri]
    assert cliente.prefijos_listados == [RUTA]


def _comprobar_mensaje(error, mensaje):
    assert str(error) == mensaje
    traza = "".join(traceback.format_exception(error))
    for secreto in (VALOR_SENSIBLE, CUENTA, RAIZ, RUTA, "archivo-privado.pdf"):
        assert secreto not in traza


@pytest.mark.parametrize("codigo", ["BlobNotFound", StorageErrorCode.BLOB_NOT_FOUND])
def test_blob_inexistente_da_false_al_consultar_y_error_al_leer(almacen, cliente, codigo):
    uri = almacen.uri(RUTA)
    cliente.fallas["get_blob_properties"] = error_http(404, codigo, texto=TEXTO_SERVIDOR)
    cliente.fallas["download_blob"] = error_http(404, codigo, texto=TEXTO_SERVIDOR, clase=ResourceNotFoundError)
    assert almacen.existe(uri) is False
    with pytest.raises(ErrorAlmacen) as falla:
        almacen.leer(uri)
    _comprobar_mensaje(falla.value, "Blob leer HTTP 404 [BlobNotFound]")


@pytest.fixture(params=[
    pytest.param(("leer", "download_blob"), id="leer"),
    pytest.param(("escribir", "upload_blob"), id="escribir"),
    pytest.param(("existe", "get_blob_properties"), id="existe"),
    pytest.param(("listar", "list_blobs"), id="listar"),
])
def operacion(request, almacen, cliente):
    nombre, etapa = request.param
    uri = almacen.uri(RUTA)
    argumentos = (b"datos",) if nombre == "escribir" else ()

    def ejecutar(falla):
        cliente.fallas[etapa] = falla
        return getattr(almacen, nombre)(uri, *argumentos)

    return nombre, ejecutar


@pytest.mark.parametrize("clase", [ServiceRequestError, ServiceResponseError])
def test_traduce_las_fallas_de_red(operacion, clase):
    nombre, ejecutar = operacion
    with pytest.raises(AlmacenNoDisponible) as falla:
        ejecutar(clase(TEXTO_SERVIDOR))
    assert falla.value.espera_s is None
    assert not isinstance(falla.value, ErrorAlmacen)
    _comprobar_mensaje(falla.value, f"Blob {nombre}")


@pytest.mark.parametrize("estado", [408, 429, 500, 502, 503, 504])
def test_traduce_los_estados_transitorios(operacion, estado):
    nombre, ejecutar = operacion
    with pytest.raises(AlmacenNoDisponible) as falla:
        ejecutar(error_http(estado, texto=TEXTO_SERVIDOR))
    assert falla.value.espera_s is None
    _comprobar_mensaje(falla.value, f"Blob {nombre} HTTP {estado}")


@pytest.mark.parametrize(("cabeceras", "espera"), [
    ({"Retry-After": "7", "x-ms-retry-after-ms": "1700"}, 7.0),
    ({"retry-after": "0"}, 0.0),
    ({"X-MS-Retry-After-MS": "2500"}, 2.5),
    ({"Retry-After": "mal", "x-ms-retry-after-ms": "1800"}, 1.8),
    ({"Retry-After": "-1", "x-ms-retry-after-ms": "-1"}, None),
    ({"Retry-After": "nan", "x-ms-retry-after-ms": "inf"}, None),
    ({"Retry-After": "Wed, 25 Nov 2026 12:00:00 GMT"}, None),
])
def test_traduce_el_429_y_la_espera_pedida(operacion, cabeceras, espera):
    nombre, ejecutar = operacion
    with pytest.raises(AlmacenNoDisponible) as falla:
        ejecutar(error_http(429, "TooManyRequests", cabeceras, TEXTO_SERVIDOR))
    assert falla.value.espera_s == espera
    _comprobar_mensaje(falla.value, f"Blob {nombre} HTTP 429 [TooManyRequests]")


@pytest.mark.parametrize(("estado", "codigo", "clase", "detalle"), [
    (401, None, HttpResponseError, "HTTP 401"),
    (403, "AuthorizationPermissionMismatch", HttpResponseError, "HTTP 403 [AuthorizationPermissionMismatch]"),
    (404, StorageErrorCode.CONTAINER_NOT_FOUND, ResourceNotFoundError, "HTTP 404 [ContainerNotFound]"),
    (404, None, ResourceNotFoundError, "HTTP 404"),
])
def test_traduce_las_fallas_de_acceso(operacion, estado, codigo, clase, detalle):
    nombre, ejecutar = operacion
    with pytest.raises(AlmacenSinPermiso) as falla:
        ejecutar(error_http(estado, codigo, texto=TEXTO_SERVIDOR, clase=clase))
    assert not isinstance(falla.value, ErrorAlmacen)
    _comprobar_mensaje(falla.value, f"Blob {nombre} {detalle}")


@pytest.mark.parametrize("clase", [ClientAuthenticationError, CredentialUnavailableError])
def test_traduce_las_fallas_de_credencial(operacion, clase):
    nombre, ejecutar = operacion
    with pytest.raises(AlmacenSinPermiso) as falla:
        ejecutar(clase(f"AADSTS12345: {TEXTO_SERVIDOR}"))
    _comprobar_mensaje(falla.value, f"Blob {nombre}")


@pytest.mark.parametrize(("codigo", "detalle"), [
    ("InvalidHeaderValue", " [InvalidHeaderValue]"),
    (TEXTO_SERVIDOR, ""),
])
def test_otra_respuesta_http_conserva_solo_el_estado_y_el_codigo(operacion, codigo, detalle):
    nombre, ejecutar = operacion
    with pytest.raises(RuntimeError) as falla:
        ejecutar(error_http(400, codigo, texto=TEXTO_SERVIDOR))
    _comprobar_mensaje(falla.value, f"Blob {nombre} HTTP 400{detalle}")


def test_existe_reconoce_el_codigo_en_la_cabecera(almacen, cliente):
    cliente.fallas["get_blob_properties"] = error_http(404, cabeceras={"X-MS-Error-Code": "BlobNotFound"})
    assert almacen.existe(almacen.uri(RUTA)) is False


@pytest.mark.parametrize("clase", [HttpResponseError, IncompleteReadError, ServiceResponseError])
def test_una_descarga_interrumpida_en_readall_es_transitoria(almacen, cliente, clase):
    cliente.fallas["readall"] = clase(TEXTO_SERVIDOR)
    with pytest.raises(AlmacenNoDisponible) as falla:
        almacen.leer(almacen.uri(RUTA))
    assert falla.value.espera_s is None
    _comprobar_mensaje(falla.value, "Blob leer")


def test_listar_traduce_las_fallas_de_la_pagina_siguiente(almacen, cliente):
    cliente.blobs[f"{RUTA}/descendiente.json"] = b""
    cliente.fallas["pagina_siguiente"] = error_http(
        503, StorageErrorCode.SERVER_BUSY, {"Retry-After": "3"}, TEXTO_SERVIDOR,
    )
    with pytest.raises(AlmacenNoDisponible) as falla:
        almacen.listar(almacen.uri(RUTA))
    assert falla.value.espera_s == 3.0
    _comprobar_mensaje(falla.value, "Blob listar HTTP 503 [ServerBusy]")


@pytest.fixture
def recursos_azure(monkeypatch):
    credencial = Mock(spec=["close"])
    crear_credencial = Mock(return_value=credencial)
    clientes = []

    def nuevo_cliente(*args, **kwargs):
        cliente = ContenedorFalso({RUTA: b"datos"})
        clientes.append(cliente)
        return cliente

    crear_cliente = Mock(side_effect=nuevo_cliente)
    monkeypatch.setattr(almacen_blob, "DefaultAzureCredential", crear_credencial)
    monkeypatch.setattr(almacen_blob, "ContainerClient", crear_cliente)
    monkeypatch.setenv("ALMACEN_BLOB_CUENTA", CUENTA)
    monkeypatch.delenv("ALMACEN_BLOB_CONTENEDOR", raising=False)
    return credencial, crear_credencial, crear_cliente, clientes


def test_crea_y_cierra_un_cliente_por_hilo_con_la_misma_credencial(recursos_azure):
    credencial, _, crear_cliente, clientes = recursos_azure
    barrera = Barrier(2, timeout=10)
    with AlmacenBlob(CUENTA, CONTENEDOR, credencial=credencial) as almacen:
        uri = almacen.uri(RUTA)

        def leer_dos_veces():
            barrera.wait()
            assert almacen.leer(uri) == almacen.leer(uri) == b"datos"

        with ThreadPoolExecutor(max_workers=2) as hilos:
            trabajos = [hilos.submit(leer_dos_veces) for _ in range(2)]
            for trabajo in trabajos:
                trabajo.result()
        assert [cliente.cierres for cliente in clientes] == [0, 0]

    assert crear_cliente.call_args_list == [
        call(URL_CUENTA, CONTENEDOR, credential=credencial, connection_timeout=20, read_timeout=60),
    ] * 2
    assert [cliente.cierres for cliente in clientes] == [1, 1]
    credencial.close.assert_not_called()


def test_el_cliente_inyectado_sigue_siendo_del_llamador(almacen, cliente):
    almacen.cerrar()
    assert cliente.cierres == 0


@pytest.mark.parametrize("valor", [None, "", "ab", "a" * 25, "CuentaFalsa", "cuenta-falsa", URL_CUENTA, " abc"])
def test_el_entorno_exige_un_nombre_de_cuenta_valido(monkeypatch, recursos_azure, valor):
    _, crear_credencial, _, _ = recursos_azure
    if valor is None:
        monkeypatch.delenv("ALMACEN_BLOB_CUENTA")
    else:
        monkeypatch.setenv("ALMACEN_BLOB_CUENTA", valor)
    with pytest.raises(AlmacenSinPermiso) as falla:
        almacen_blob_desde_entorno()
    assert str(falla.value) == "ALMACEN_BLOB_CUENTA falta o es inválida."
    crear_credencial.assert_not_called()


@pytest.mark.parametrize("valor", ["", "ab", "a" * 64, "Contenedor", "mal_contenedor", "-inicio", "final-", "dos--guiones"])
def test_el_entorno_exige_un_nombre_de_contenedor_valido(monkeypatch, recursos_azure, valor):
    _, crear_credencial, _, _ = recursos_azure
    monkeypatch.setenv("ALMACEN_BLOB_CONTENEDOR", valor)
    with pytest.raises(AlmacenSinPermiso) as falla:
        almacen_blob_desde_entorno()
    assert str(falla.value) == "ALMACEN_BLOB_CONTENEDOR es inválida."
    crear_credencial.assert_not_called()


@pytest.mark.parametrize("contenedor", [None, "a-1", "a" * 63])
def test_el_entorno_configura_y_cierra_sus_recursos(monkeypatch, recursos_azure, contenedor):
    credencial, crear_credencial, crear_cliente, clientes = recursos_azure
    if contenedor is not None:
        monkeypatch.setenv("ALMACEN_BLOB_CONTENEDOR", contenedor)
    esperado = contenedor or CONTENEDOR

    with almacen_blob_desde_entorno() as almacen:
        assert almacen.uri(RUTA) == f"{URL_CUENTA}/{esperado}/{RUTA}"
        assert almacen.leer(almacen.uri(RUTA)) == b"datos"

    almacen.cerrar()
    crear_credencial.assert_called_once_with(exclude_interactive_browser_credential=True)
    crear_cliente.assert_called_once_with(
        URL_CUENTA, esperado, credential=credencial, connection_timeout=20, read_timeout=60,
    )
    credencial.close.assert_called_once_with()
    assert clientes[0].cierres == 1


def test_el_entorno_cierra_su_credencial_si_falla_la_construccion(recursos_azure):
    credencial, _, crear_cliente, _ = recursos_azure
    crear_cliente.side_effect = CredentialUnavailableError(TEXTO_SERVIDOR)
    with pytest.raises(AlmacenSinPermiso) as falla:
        almacen_blob_desde_entorno()
    credencial.close.assert_called_once_with()
    _comprobar_mensaje(falla.value, "Blob crear cliente")


def test_el_entorno_protege_los_datos_de_una_configuracion_de_credencial_invalida(recursos_azure):
    _, crear_credencial, crear_cliente, _ = recursos_azure
    crear_credencial.side_effect = ValueError(TEXTO_SERVIDOR)
    with pytest.raises(AlmacenSinPermiso) as falla:
        almacen_blob_desde_entorno()
    crear_cliente.assert_not_called()
    _comprobar_mensaje(falla.value, "Blob crear credencial")


def test_el_entorno_cierra_la_credencial_aunque_falle_el_cierre_del_cliente(recursos_azure):
    credencial, _, _, clientes = recursos_azure
    almacen = almacen_blob_desde_entorno()
    clientes[0].fallas["close"] = ServiceResponseError(TEXTO_SERVIDOR)
    with pytest.raises(AlmacenNoDisponible) as falla:
        almacen.cerrar()
    credencial.close.assert_called_once_with()
    _comprobar_mensaje(falla.value, "Blob cerrar cliente")


def test_configurar_silencia_los_avisos_de_azure_y_el_error_protege_los_datos(almacen, cliente, caplog):
    caplog.set_level(logging.DEBUG, logger="azure")
    caplog.set_level(logging.DEBUG)
    salida = io.StringIO()
    registros.configurar(salida=salida)
    assert logging.getLogger("azure").level == logging.ERROR
    identidad = logging.getLogger("azure.identity")
    identidad.warning(TEXTO_SERVIDOR)
    identidad.error("Falla simulada de la identidad")
    cliente.fallas["download_blob"] = CredentialUnavailableError(TEXTO_SERVIDOR)
    try:
        almacen.leer(almacen.uri(RUTA))
    except AlmacenSinPermiso as error:
        _comprobar_mensaje(error, "Blob leer")
        logging.getLogger("normalizacion").exception("No se pudo acceder al almacén")

    assert "Falla simulada de la identidad" in caplog.text
    assert "AlmacenSinPermiso" in salida.getvalue()
    assert VALOR_SENSIBLE not in caplog.text + salida.getvalue()


def test_normalizacion_y_almacen_se_importan_sin_el_sdk():
    programa = """
import sys
sys.modules['azure'] = None
import normalizacion
import normalizacion.almacen
assert 'normalizacion.almacen_blob' not in sys.modules
"""
    ejecucion = subprocess.run([sys.executable, "-c", programa], capture_output=True, text=True)
    assert ejecucion.returncode == 0, ejecucion.stderr
