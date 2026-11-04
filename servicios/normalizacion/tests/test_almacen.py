import pytest

from normalizacion.almacen import Almacen, AlmacenLocal, ErrorAlmacen


@pytest.fixture
def almacen(tmp_path) -> AlmacenLocal:
    return AlmacenLocal(tmp_path / "salida")


def test_cumple_la_interfaz(almacen):
    assert isinstance(almacen, Almacen)


def test_escribe_y_lee(almacen):
    uri = almacen.uri("SR0000000001/OF-002/lectura/OF-002-723c293af12b.json")
    assert uri.startswith("file://")
    assert not almacen.existe(uri)
    almacen.escribir(uri, b"{}")
    assert almacen.existe(uri)
    assert almacen.leer(uri) == b"{}"


def test_sobrescribe(almacen):
    uri = almacen.uri("a.json")
    almacen.escribir(uri, b"uno")
    almacen.escribir(uri, b"dos")
    assert almacen.leer(uri) == b"dos"


def test_no_deja_temporales(almacen):
    uri = almacen.uri("pdf/a.pdf")
    almacen.escribir(uri, b"%PDF-")
    assert [p.name for p in (almacen.raiz / "pdf").iterdir()] == ["a.pdf"]


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


def test_lista_vacio_si_no_existe(almacen):
    assert almacen.listar(almacen.uri("nada")) == []


def test_leer_lo_que_no_existe(almacen):
    with pytest.raises(ErrorAlmacen):
        almacen.leer(almacen.uri("nada.json"))


@pytest.mark.parametrize("ruta", ["../fuera.json", "/absoluta.json", "a/../../fuera.json", ""])
def test_no_arma_uri_fuera_del_almacen(almacen, ruta):
    with pytest.raises(ErrorAlmacen):
        almacen.uri(ruta)


def test_no_acepta_uri_fuera_del_almacen(almacen, tmp_path):
    with pytest.raises(ErrorAlmacen):
        almacen.escribir((tmp_path / "fuera.json").as_uri(), b"x")


@pytest.mark.parametrize("uri", ["https://servidor/a.json", "file://otro-equipo/a.json", "a.json"])
def test_solo_acepta_file_local(almacen, uri):
    with pytest.raises(ErrorAlmacen):
        almacen.existe(uri)
