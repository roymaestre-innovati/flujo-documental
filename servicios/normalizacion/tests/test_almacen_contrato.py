"""Contrato que comparten las implementaciones de Almacen."""

import pytest

from normalizacion.almacen import Almacen, AlmacenLocal, ErrorAlmacen


@pytest.fixture
def uris_ajenas_local(tmp_path):
    fuera = tmp_path / "fuera.json"
    fuera.write_bytes(b"{}")
    return (
        "https://servidor/a.json",
        "file://otro-equipo/a.json",
        "a.json",
        fuera.as_uri(),
    )


@pytest.fixture
def almacen_local(tmp_path, uris_ajenas_local):
    return AlmacenLocal(tmp_path / "salida"), uris_ajenas_local


# Cada implementación agrega aquí su fixture con el almacén y sus URI ajenas.
@pytest.fixture(params=[pytest.param("almacen_local", id="local")])
def implementacion_almacen(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def almacen(implementacion_almacen):
    instancia, _ = implementacion_almacen
    return instancia


@pytest.fixture
def uris_ajenas(implementacion_almacen):
    _, uris = implementacion_almacen
    return uris


def test_cumple_la_interfaz(almacen):
    assert isinstance(almacen, Almacen)


def test_escribe_y_lee(almacen):
    uri = almacen.uri("SR0000000001/OF-002/lectura/OF-002-723c293af12b.json")
    assert not almacen.existe(uri)
    almacen.escribir(uri, b"{}")
    assert almacen.existe(uri)
    assert almacen.leer(uri) == b"{}"


def test_sobrescribe(almacen):
    uri = almacen.uri("a.json")
    almacen.escribir(uri, b"uno")
    almacen.escribir(uri, b"dos")
    assert almacen.leer(uri) == b"dos"


def test_escribe_bytes_vacios(almacen):
    uri = almacen.uri("vacio.json")
    almacen.escribir(uri, b"")
    assert almacen.existe(uri)
    assert almacen.leer(uri) == b""


def test_ruta_con_espacios_y_tildes(almacen):
    uri = almacen.uri("carpeta con espacios/presentación.json")
    almacen.escribir(uri, b"x")
    assert almacen.leer(uri) == b"x"
    assert almacen.listar(almacen.uri("carpeta con espacios")) == [uri]


def test_lista_ordenado_bajo_un_prefijo(almacen):
    for ruta in ("p/b.json", "p/a.json", "p/sub/c.json", "otro/d.json"):
        almacen.escribir(almacen.uri(ruta), b"")
    assert almacen.listar(almacen.uri("p")) == [
        almacen.uri("p/a.json"),
        almacen.uri("p/b.json"),
        almacen.uri("p/sub/c.json"),
    ]


def test_lista_solo_la_carpeta_del_prefijo(almacen):
    uri = almacen.uri("p/OF-1/a.json")
    almacen.escribir(uri, b"{}")
    almacen.escribir(almacen.uri("p/OF-10/b.json"), b"{}")
    assert almacen.listar(almacen.uri("p/OF-1")) == [uri]


def test_lista_el_archivo_del_prefijo(almacen):
    uri = almacen.uri("p/a.json")
    almacen.escribir(uri, b"{}")
    almacen.escribir(almacen.uri("p/a.json.bak"), b"{}")
    assert almacen.listar(uri) == [uri]


def test_lista_vacio_si_no_existe(almacen):
    assert almacen.listar(almacen.uri("nada")) == []


def test_leer_lo_que_no_existe(almacen):
    with pytest.raises(ErrorAlmacen):
        almacen.leer(almacen.uri("nada.json"))


@pytest.mark.parametrize("ruta", ["../x", "/abs", "a/../../x", ""])
def test_no_arma_uri_fuera_del_almacen(almacen, ruta):
    with pytest.raises(ErrorAlmacen):
        almacen.uri(ruta)


@pytest.mark.parametrize(("operacion", "argumentos"), [
    ("leer", ()),
    ("escribir", (b"x",)),
    ("existe", ()),
    ("listar", ()),
], ids=["leer", "escribir", "existe", "listar"])
def test_rechaza_uris_ajenas(almacen, uris_ajenas, operacion, argumentos):
    metodo = getattr(almacen, operacion)
    for uri in uris_ajenas:
        with pytest.raises(ErrorAlmacen):
            metodo(uri, *argumentos)
