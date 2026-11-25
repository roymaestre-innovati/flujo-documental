import pytest

from normalizacion.almacen import AlmacenLocal, en_el_almacen, ruta_en_el_almacen


@pytest.fixture
def almacen(tmp_path) -> AlmacenLocal:
    return AlmacenLocal(tmp_path / "salida")


def test_usa_uri_file(almacen):
    assert almacen.uri("a.json").startswith("file://")


def test_no_deja_temporales(almacen):
    uri = almacen.uri("pdf/a.pdf")
    almacen.escribir(uri, b"%PDF-")
    assert [p.name for p in (almacen.raiz / "pdf").iterdir()] == ["a.pdf"]


def test_listar_ignora_temporales(almacen):
    uri = almacen.uri("pdf/a.pdf")
    almacen.escribir(uri, b"%PDF-")
    (almacen.raiz / "pdf" / ".escribiendo-a").write_bytes(b"parcial")
    assert almacen.listar(almacen.uri("pdf")) == [uri]


# Ubicar una URI en el almacén de una corrida movida (lo usan el visor y la extracción)


def test_ruta_en_el_almacen_toma_lo_que_va_despues_del_ultimo_almacen():
    uri = "file:///otra/maquina/almacen/viejo/almacen/SR1/OF-001/pdf/OF-001-abc.pdf"
    assert str(ruta_en_el_almacen(uri)) == "SR1/OF-001/pdf/OF-001-abc.pdf"
    assert str(ruta_en_el_almacen("file:///x/almacen/SR1/a%20b.json")) == "SR1/a b.json"


def test_ruta_en_el_almacen_sin_almacen_o_sin_archivo():
    assert ruta_en_el_almacen(None) is None
    assert ruta_en_el_almacen("file:///x/salida/SR1/a.pdf") is None
    assert ruta_en_el_almacen("file:///x/almacen") is None
    assert ruta_en_el_almacen("https://cuenta.blob.core.windows.net/almacen/SR1/a.pdf") is None


def test_en_el_almacen_no_deja_salir(tmp_path):
    archivo = tmp_path / "almacen" / "SR1" / "a.pdf"
    archivo.parent.mkdir(parents=True)
    archivo.write_bytes(b"%PDF-")
    assert en_el_almacen(tmp_path, "file:///lejos/almacen/SR1/a.pdf") == archivo.resolve()
    assert en_el_almacen(tmp_path, "file:///lejos/almacen/SR1/no.pdf") is None
    assert en_el_almacen(tmp_path, "file:///lejos/almacen/../secreto.txt") is None
