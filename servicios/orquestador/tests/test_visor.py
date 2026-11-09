"""El visor local de las corridas."""

import json
import threading
import urllib.error
import urllib.request

import pytest
from fabrica import RUTA, P
from test_punta_a_punta import _proceso

from orquestador import cli
from orquestador.visor import servidor as v


@pytest.fixture(scope="module")
def corridas(tmp_path_factory):
    """Una carpeta con dos corridas inventadas, hechas con `orquestar --salida`."""
    raiz = tmp_path_factory.mktemp("corridas")
    for nombre in ("primera", "segunda"):
        trabajo = raiz / "trabajo" / nombre
        _proceso(trabajo)
        assert cli.main(["--origen", str(trabajo / "datalake" / RUTA), "--proceso", P, "--clasificacion",
                         str(trabajo / "clasificacion.csv"), "--salida", str(trabajo / "salida")]) == 0
        # Se mueve la corrida: las URI del estado quedan apuntando a la carpeta vieja.
        (raiz / "corridas").mkdir(exist_ok=True)
        (trabajo / "salida").rename(raiz / "corridas" / nombre)
    return raiz / "corridas"


def test_encuentra_las_corridas(corridas):
    assert sorted(v.buscar_corridas(corridas)) == ["primera", "segunda"]
    assert list(v.buscar_corridas(corridas / "primera")) == ["."]


def test_arma_la_corrida(corridas):
    datos = v.corrida(corridas / "primera")
    assert datos["proceso"]["id"] == P
    assert len(datos["documentos"]) == 8 and len(datos["solicitudes"]) == 5
    assert datos["conteos"]["atascados"] == 0
    assert datos["datos"]["tipos"]["TD-03"] and datos["datos"]["umbrales"]["piso"] == 0.75


def test_el_pdf_se_busca_en_el_almacen_de_la_corrida_aunque_se_haya_movido(corridas):
    carpeta = corridas / "primera"
    documento = next(d for d in v.corrida(carpeta)["documentos"] if d["ruta_origen"] == "carta.pdf")
    ruta = v.en_el_almacen(carpeta, documento["pdf"])
    assert ruta is not None and ruta.read_bytes().startswith(b"%PDF")


@pytest.mark.parametrize("uri", [
    None, "", "file:///etc/passwd", "file:///x/almacen/../../../etc/passwd", "file:///x/almacen/", "https://h/almacen/a.pdf/../..",
])
def test_no_sale_del_almacen(corridas, uri):
    assert v.en_el_almacen(corridas / "primera", uri) is None


def test_la_lectura_no_trae_el_texto(corridas):
    carpeta = corridas / "primera"
    documento = next(d for d in v.corrida(carpeta)["documentos"] if d["ruta_origen"] == "mixto.pdf")
    lectura = v.lectura(carpeta, documento["id"])
    assert [p["pagina"] for p in lectura["paginas"]] == [1, 2]
    assert "mixto" not in json.dumps(lectura)


@pytest.fixture(scope="module")
def url(corridas):
    http = v.servidor(corridas, 0)
    hilo = threading.Thread(target=http.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{http.server_address[1]}"
    http.shutdown()


def _get(url):
    with urllib.request.urlopen(url) as r:
        return r.status, r.headers["Content-Type"], r.read()


def test_el_servidor_responde(url):
    estado, tipo, cuerpo = _get(url + "/")
    assert estado == 200 and "text/html" in tipo and b"Visor del orquestador" in cuerpo
    lista = json.loads(_get(url + "/api/corridas")[2])
    assert {c["id"] for c in lista} == {"primera", "segunda"}
    datos = json.loads(_get(url + "/api/corrida?corrida=primera")[2])
    documento = next(d for d in datos["documentos"] if d["ruta_origen"] == "carta.pdf")
    estado, tipo, cuerpo = _get(f"{url}/pdf?corrida=primera&documento={documento['id']}")
    assert tipo == "application/pdf" and cuerpo.startswith(b"%PDF")


@pytest.mark.parametrize("ruta", ["/api/corrida?corrida=../..", "/api/corrida?corrida=otra",
                                  "/pdf?corrida=primera&documento=no-existe", "/api/lectura?corrida=primera&documento=x"])
def test_lo_que_no_existe_da_404(url, ruta):
    with pytest.raises(urllib.error.HTTPError) as error:
        _get(url + ruta)
    assert error.value.code == 404


def test_solo_escucha_en_localhost(corridas):
    http = v.servidor(corridas, 0)
    assert http.server_address[0] == "127.0.0.1"
    http.server_close()
