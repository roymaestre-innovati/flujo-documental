"""Las versiones locales de las interfaces se portan como sus equivalentes de Azure
en lo que el orquestador necesita."""

import pytest

from orquestador import cola as c
from orquestador import datos
from orquestador.clasificador import ClasificadorFalso, ErrorClasificadorFalso
from orquestador.estado import Conflicto, ErrorEstado, EstadoEnMemoria
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


def test_cola_entrega_en_orden_y_bloquea(cola):
    cola.publicar(c.NORMALIZAR, {"n": 1})
    cola.publicar(c.NORMALIZAR, {"n": 2})
    primero = cola.recibir(c.NORMALIZAR)
    segundo = cola.recibir(c.NORMALIZAR)
    assert (primero.cuerpo, segundo.cuerpo) == ({"n": 1}, {"n": 2})
    assert cola.recibir(c.NORMALIZAR) is None
    assert cola.pendientes(c.NORMALIZAR) == 2
    cola.completar(primero)
    cola.completar(segundo)
    assert cola.pendientes(c.NORMALIZAR) == 0


def test_cola_abandonar_vuelve_a_entregar(cola):
    cola.publicar(c.CLASIFICAR, {"n": 1})
    m = cola.recibir(c.CLASIFICAR)
    cola.abandonar(m)
    otra_vez = cola.recibir(c.CLASIFICAR)
    assert otra_vez.id == m.id
    assert otra_vez.entregas == 2


def test_cola_demora(cola, reloj):
    cola.publicar(c.CLASIFICAR, {"n": 1}, demora_s=120)
    assert cola.recibir(c.CLASIFICAR) is None
    assert (cola.proxima_visible() - reloj.ahora()).total_seconds() == 120
    reloj.adelantar(119)
    assert cola.recibir(c.CLASIFICAR) is None
    reloj.adelantar(1)
    assert cola.recibir(c.CLASIFICAR).cuerpo == {"n": 1}


def test_cola_errores_y_reenvio(cola):
    cola.publicar(c.EXTRAER, {"n": 1})
    m = cola.recibir(c.EXTRAER)
    cola.a_errores(m, "bug")
    assert cola.pendientes(c.EXTRAER) == 0
    [en_errores] = cola.errores(c.EXTRAER)
    assert (en_errores.mensaje.cuerpo, en_errores.motivo) == ({"n": 1}, "bug")
    assert [e.mensaje.id for e in cola.sacar_de_errores(c.EXTRAER)] == [m.id]
    assert cola.errores(c.EXTRAER) == []


def test_cola_no_deja_completar_dos_veces(cola):
    cola.publicar(c.EXTRAER, {})
    m = cola.recibir(c.EXTRAER)
    cola.completar(m)
    with pytest.raises(c.ErrorCola):
        cola.completar(m)


def test_cola_copia_el_cuerpo_y_exige_json(cola):
    cuerpo = {"lista": [1]}
    cola.publicar(c.EXTRAER, cuerpo)
    cuerpo["lista"].append(2)
    assert cola.recibir(c.EXTRAER).cuerpo == {"lista": [1]}
    with pytest.raises(TypeError):
        cola.publicar(c.EXTRAER, {"no_json": object()})
    with pytest.raises(c.ErrorCola):
        cola.publicar("otra", {})


# --- Estado ---


def test_estado_crear_si_no_existe_gana_el_primero():
    estado = EstadoEnMemoria()
    primero, creado = estado.crear_si_no_existe("SR1", "proceso", "SR1", {"v": 1})
    segundo, creado_otra_vez = estado.crear_si_no_existe("SR1", "proceso", "SR1", {"v": 2})
    assert creado and not creado_otra_vez
    assert segundo.datos == {"v": 1}
    assert primero.version == segundo.version == 1


def test_estado_reemplazo_condicional():
    estado = EstadoEnMemoria()
    leido, _ = estado.crear_si_no_existe("SR1", "documento", "D1", {"estado": "pendiente"})
    nuevo = estado.reemplazar(leido, {"estado": "normalizado"})
    assert nuevo.version == 2
    with pytest.raises(Conflicto):
        estado.reemplazar(leido, {"estado": "error_entrada"})
    assert estado.leer("SR1", "documento", "D1").datos == {"estado": "normalizado"}


def test_estado_lista_por_proceso_y_tipo(tmp_path):
    estado = EstadoEnMemoria()
    estado.crear_si_no_existe("SR1", "documento", "D2", {})
    estado.crear_si_no_existe("SR1", "proceso", "SR1", {})
    estado.crear_si_no_existe("SR1", "documento", "D1", {})
    estado.crear_si_no_existe("SR2", "documento", "D9", {})
    assert [(r.tipo, r.id) for r in estado.listar("SR1")] == [("proceso", "SR1"), ("documento", "D1"), ("documento", "D2")]
    assert [r.id for r in estado.listar("SR1", "documento")] == ["D1", "D2"]
    estado.guardar(tmp_path / "estado.json")
    assert (tmp_path / "estado.json").read_text(encoding="utf-8").count('"tipo"') == 4


def test_estado_rechaza_tipos_desconocidos_y_lo_que_no_es_json():
    estado = EstadoEnMemoria()
    with pytest.raises(ErrorEstado):
        estado.crear_si_no_existe("SR1", "otro", "X", {})
    with pytest.raises(TypeError):
        estado.crear_si_no_existe("SR1", "proceso", "SR1", {"x": object()})


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
