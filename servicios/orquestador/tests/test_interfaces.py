"""Las versiones locales de las interfaces se portan como sus equivalentes de Azure
en lo que el orquestador necesita."""

import pytest

from orquestador import cola as c
from orquestador import datos
from orquestador.clasificador import ClasificadorFalso, ErrorClasificadorFalso
from orquestador.estado import EstadoEnMemoria
from orquestador.origen import ErrorOrigen, OrigenLocal
from orquestador.reloj import RelojManual

# --- Reloj ---


def test_reloj_manual_solo_avanza():
    reloj = RelojManual()
    inicio = reloj.ahora()
    reloj.adelantar(60)
    assert (reloj.ahora() - inicio).total_seconds() == 60
    with pytest.raises(ValueError):
        reloj.adelantar(-1)


# --- Cola ---


@pytest.fixture
def reloj():
    return RelojManual()


@pytest.fixture
def cola(reloj):
    return c.ColaEnMemoria(reloj)


def test_cola_demora(cola, reloj):
    cola.publicar(c.CLASIFICAR, {"n": 1}, demora_s=120)
    assert cola.recibir(c.CLASIFICAR) is None
    assert (cola.proxima_visible() - reloj.ahora()).total_seconds() == 120
    reloj.adelantar(119)
    assert cola.recibir(c.CLASIFICAR) is None
    reloj.adelantar(1)
    assert cola.recibir(c.CLASIFICAR).cuerpo == {"n": 1}


# --- Estado ---


def test_estado_en_memoria_guarda_en_json(tmp_path):
    estado = EstadoEnMemoria()
    estado.crear_si_no_existe("SR1", "documento", "D2", {})
    estado.crear_si_no_existe("SR1", "proceso", "SR1", {})
    estado.crear_si_no_existe("SR1", "documento", "D1", {})
    estado.crear_si_no_existe("SR2", "documento", "D9", {})
    estado.guardar(tmp_path / "estado.json")
    assert (tmp_path / "estado.json").read_text(encoding="utf-8").count('"tipo"') == 4


# --- Origen ---


def test_origen_local_lista_y_baja(tmp_path):
    raiz = tmp_path / "datalake"
    (raiz / "procesos/SR1/OF-001/sub").mkdir(parents=True)
    (raiz / "procesos/SR1/OF-001/sub/b.pdf").write_bytes(b"b")
    (raiz / "procesos/SR1/OF-001/a.pdf").write_bytes(b"a")
    origen = OrigenLocal(raiz)
    assert origen.listar("procesos/SR1") == ["OF-001/a.pdf", "OF-001/sub/b.pdf"]
    origen.bajar("procesos/SR1/OF-001/sub/b.pdf", tmp_path / "tmp/b.pdf")
    assert (tmp_path / "tmp/b.pdf").read_bytes() == b"b"


@pytest.mark.parametrize("ruta", ["../fuera", "/etc", "procesos/../../fuera", ""])
def test_origen_local_no_sale_de_la_raiz(tmp_path, ruta):
    with pytest.raises(ErrorOrigen):
        OrigenLocal(tmp_path).listar(ruta)


def test_origen_local_avisa_lo_que_no_existe(tmp_path):
    origen = OrigenLocal(tmp_path)
    with pytest.raises(ErrorOrigen):
        origen.listar("no_hay")
    with pytest.raises(ErrorOrigen):
        origen.bajar("no_hay.pdf", tmp_path / "x.pdf")


# --- Clasificador falso ---


def _solicitud(ruta_origen, id_oferente="OF-001", paginas=5):
    return {"id_documento": "D1", "id_oferente": id_oferente, "ruta_origen": ruta_origen,
            "paginas": paginas, "version_ontologia": "1"}


def test_clasificador_falso(tmp_path):
    csv = tmp_path / "clasificacion.csv"
    csv.write_text(
        "id_oferente,ruta_origen,pagina_inicio,pagina_fin,tipo_documental,confianza,subtipo\n"
        "OF-001,carta.pdf,3,5,TD-07,0.95,\n"
        "OF-001,carta.pdf,1,2,TD-03,0.97,\n"
        "OF-001,desempate/mujeres.pdf,,,TD-98,0.9,emprendimiento_mujeres\n"
        ",CPC.pdf,,,TD-01,0.99,\n",
        encoding="utf-8")
    falso = ClasificadorFalso(csv)
    compuesta = falso.clasificar(_solicitud("carta.pdf"))
    assert [(s["pagina_inicio"], s["pagina_fin"], s["tipo_documental"]) for s in compuesta["segmentos"]] == [
        (1, 2, "TD-03"), (3, 5, "TD-07")]
    [desempate] = falso.clasificar(_solicitud("desempate/mujeres.pdf"))["segmentos"]
    assert (desempate["pagina_fin"], desempate["subtipo"]) == (5, "emprendimiento_mujeres")
    [cpc] = falso.clasificar(_solicitud("CPC.pdf", id_oferente=None))["segmentos"]
    assert cpc["tipo_documental"] == "TD-01"
    [desconocido] = falso.clasificar(_solicitud("otro.pdf"))["segmentos"]
    assert (desconocido["tipo_documental"], desconocido["confianza"]) == ("TD-99", 1.0)


def test_clasificador_falso_responde_segun_el_contrato(tmp_path):
    from orquestador import contratos

    csv = tmp_path / "c.csv"
    csv.write_text("id_oferente,ruta_origen,pagina_inicio,pagina_fin,tipo_documental,confianza\n", encoding="utf-8")
    respuesta = ClasificadorFalso(csv).clasificar(_solicitud("x.pdf"))
    contratos.validar(contratos.CLASIFICACION_RESPUESTA, respuesta)


def test_clasificador_falso_rechaza_csv_mal_hecho(tmp_path):
    csv = tmp_path / "c.csv"
    csv.write_text("ruta_origen,tipo_documental\n", encoding="utf-8")
    with pytest.raises(ErrorClasificadorFalso):
        ClasificadorFalso(csv)
    csv.write_text("id_oferente,ruta_origen,pagina_inicio,pagina_fin,tipo_documental,confianza\nOF-1,a.pdf,x,,TD-01,1\n",
                   encoding="utf-8")
    with pytest.raises(ErrorClasificadorFalso):
        ClasificadorFalso(csv)


# --- Datos ---


def test_datos_vigentes_existen_y_cuadran():
    v = datos.vigentes()
    umbrales = datos.umbrales(v.umbrales)
    tipos = datos.tipos_documentales(v.tipos_documentales)
    extraibles = {t for t in tipos.tipos if t not in ("TD-98", "TD-99")}
    assert extraibles == set(umbrales.por_td), "Cada TD que se extrae necesita su umbral"
    assert all(umbrales.piso < u <= 1 for u in umbrales.por_td.values())
    assert tipos.existe("TD-98") and tipos.existe("TD-99")
    assert umbrales.de("TD-16") == 0.90


def test_datos_version_inexistente():
    with pytest.raises(datos.ErrorDatos):
        datos.umbrales("no-existe")
