"""El visor local de las corridas."""

import json
from pathlib import Path
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


# --- Resultados de la extracción (T09 de la extracción, R57) ---

EJEMPLOS = Path(__file__).resolve().parents[3] / "contracts" / "modulo3-extraccion" / "v0.2" / "ejemplos"


def _ejemplo(nombre: str, segmento: dict, **cambios) -> dict:
    """Un resultado de ejemplo del contrato, puesto sobre un segmento de la corrida."""
    resultado = json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))
    resultado.update(id_segmento=segmento["id"], id_documento=segmento["id_documento"],
                     paginas={"desde": segmento["pagina_inicio"], "hasta": segmento["pagina_fin"]}, **cambios)
    return resultado


def _escribir(ruta: Path, contenido) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(scope="module")
def con_extraccion(corridas):
    """La segunda corrida con resultados en `extraccion/`, como los deja `extraer`."""
    carpeta = corridas / "segunda"
    segmentos = [s for s in v.corrida(carpeta)["segmentos"] if s["estado"] == "pendiente"]
    primero, segundo = segmentos[:2]
    base = carpeta / "extraccion" / P
    nombre = lambda s, td: f"{s['id']}.{td}.v21.json"
    ok = _ejemplo("salida_td16.json", primero, tipo_documental="TD-16")
    _escribir(base / primero["entrega"] / nombre(primero, "TD-16"), ok)
    _escribir(base / primero["entrega"] / f"{primero['id']}.TD-16.v21.anterior-ej-1.json", {**ok, "estado": "no_corresponde"})
    error = _ejemplo("salida_error.json", segundo, tipo_documental="TD-07")
    _escribir(base / segundo["entrega"] / nombre(segundo, "TD-07"), error)
    ficha = {"modelo": "extraccion_documental", "version": 21, "seccion": {"id": "TD-16"},
             "elementos": [{"id_tecnico": "td16.subtipo", "nombre": "Persona jurídica o natural", "seccion": "TD-16",
                            "obligatoriedad": "Si", "atributos": {"umbral_confianza": 0.9}}]}
    _escribir(carpeta / "extraccion" / "fichas" / "v21" / "TD-16.json", ficha)
    return carpeta, primero, segundo


def test_la_corrida_trae_el_resumen_de_cada_extraccion(con_extraccion):
    carpeta, primero, segundo = con_extraccion
    por_segmento = {x["id_segmento"]: x for x in v.corrida(carpeta)["extracciones"]}
    assert set(por_segmento) == {primero["id"], segundo["id"]}, "sin los anteriores ni las fichas"
    ok = por_segmento[primero["id"]]
    assert ok["estado"] == "ok" and ok["requiere_revision"] is True
    assert ok["campos"] == 6 and ok["campos_en_revision"] == 1
    assert sum(ok["motivos"].values()) >= 1
    assert por_segmento[segundo["id"]]["codigo_error"] == "PAGINAS_FUERA_DE_RANGO"


def test_el_resumen_no_trae_valores_ni_citas(con_extraccion):
    carpeta, primero, _ = con_extraccion
    texto = json.dumps(v.corrida(carpeta)["extracciones"])
    resultado = v.extraccion(carpeta, primero["id"], "TD-16", 21)["resultado"]
    for r in resultado["resultados"]:
        for cita in r["evidencia"]:
            if cita["cita"]:
                assert cita["cita"] not in texto


def test_una_extraccion_con_los_datos_de_la_ficha(con_extraccion):
    carpeta, primero, segundo = con_extraccion
    datos = v.extraccion(carpeta, primero["id"], "TD-16", 21)
    assert datos["resultado"]["estado"] == "ok"
    assert datos["campos"]["td16.subtipo"] == {"nombre": "Persona jurídica o natural", "obligatoriedad": "Si", "umbral": 0.9}
    sin_ficha = v.extraccion(carpeta, segundo["id"], "TD-07", 21)
    assert sin_ficha["resultado"]["estado"] == "error_entrada" and sin_ficha["campos"] is None


def test_una_corrida_sin_extraccion(corridas):
    assert v.corrida(corridas / "primera")["extracciones"] == []


def test_el_servidor_da_la_extraccion(url, con_extraccion):
    _, primero, _ = con_extraccion
    estado, tipo, cuerpo = _get(f"{url}/api/extraccion?corrida=segunda&segmento={primero['id']}&td=TD-16&version=21")
    assert estado == 200 and "application/json" in tipo
    assert json.loads(cuerpo)["resultado"]["id_segmento"] == primero["id"]
    assert b"pintarExtracciones" in _get(url + "/")[2]


@pytest.mark.parametrize("consulta", [
    "segmento=no-existe&td=TD-16&version=21",
    "segmento=../../estado&td=TD-16&version=21",
    "td=TD-16&version=21",
    "segmento=x&td=TD-16&version=veintiuno",
])
def test_extraccion_que_no_existe_da_404(url, con_extraccion, consulta):
    with pytest.raises(urllib.error.HTTPError) as error:
        _get(f"{url}/api/extraccion?corrida=segunda&{consulta}")
    assert error.value.code == 404
