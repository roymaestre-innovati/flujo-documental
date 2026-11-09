"""Estados, transiciones, historial y consulta (R24 a R26, R28)."""

import pytest

from orquestador import estados as e
from orquestador.estado import Conflicto, EstadoEnMemoria
from orquestador.reloj import RelojManual

P = "SR0000000001"


@pytest.fixture
def reloj():
    return RelojManual()


@pytest.fixture
def estado():
    return EstadoEnMemoria()


def _documento(estado, reloj, id="OF-001-aaa", inicial=e.NORMALIZADO, entrega="OF-001"):
    return e.crear(estado, reloj, P, e.DOCUMENTO, id, inicial, "normalizacion", {"hash": "h"}, entrega=entrega)


# --- Creación ---


def test_crear_guarda_estado_entrega_e_historial(estado, reloj):
    cambio = _documento(estado, reloj)
    assert cambio.aplicado
    datos = cambio.registro.datos
    assert (datos["estado"], datos["entrega"], datos["hash"]) == (e.NORMALIZADO, "OF-001", "h")
    assert datos["historial"] == [{"de": None, "a": e.NORMALIZADO, "cuando": reloj.ahora().isoformat(),
                                   "motivo": "normalizacion"}]


def test_crear_dos_veces_no_cambia_nada(estado, reloj):
    _documento(estado, reloj)
    reloj.adelantar(10)
    otra_vez = _documento(estado, reloj, inicial=e.DUPLICADO)
    assert not otra_vez.aplicado
    assert otra_vez.registro.datos["estado"] == e.NORMALIZADO
    assert len(otra_vez.registro.datos["historial"]) == 1


@pytest.mark.parametrize("tipo,inicial", [
    (e.DOCUMENTO, e.CLASIFICADO),
    (e.SEGMENTO, e.CLASIFICADO),
    (e.TAREA, e.RESUELTA),
    (e.OFERENTE, e.PROCESANDO),
    ("otro", e.ABIERTO),
])
def test_crear_con_estado_inicial_no_permitido(estado, reloj, tipo, inicial):
    with pytest.raises(e.TransicionNoPermitida):
        e.crear(estado, reloj, P, tipo, "X", inicial, "m", entrega="OF-001")


def test_crear_exige_entrega_salvo_en_el_proceso(estado, reloj):
    with pytest.raises(e.TransicionNoPermitida):
        e.crear(estado, reloj, P, e.DOCUMENTO, "X", e.NORMALIZADO, "m")
    with pytest.raises(e.TransicionNoPermitida):
        e.crear(estado, reloj, P, e.PROCESO, P, e.ABIERTO, "aviso", entrega="OF-001")
    assert e.crear(estado, reloj, P, e.PROCESO, P, e.ABIERTO, "aviso").aplicado


def test_crear_no_acepta_campos_reservados(estado, reloj):
    with pytest.raises(e.TransicionNoPermitida):
        e.crear(estado, reloj, P, e.TAREA, "T", e.ABIERTA, "m", {"estado": "otro"}, entrega="OF-001")


# --- Cambios ---


def test_cambiar_agrega_al_historial_y_suma_datos(estado, reloj):
    _documento(estado, reloj)
    reloj.adelantar(30)
    cambio = e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-aaa", e.NORMALIZADO, e.CLASIFICADO, "clasificador",
                       {"segmentos": ["s1"]})
    assert cambio.aplicado
    datos = cambio.registro.datos
    assert (datos["estado"], datos["segmentos"], datos["hash"]) == (e.CLASIFICADO, ["s1"], "h")
    assert datos["historial"][-1] == {"de": e.NORMALIZADO, "a": e.CLASIFICADO, "cuando": reloj.ahora().isoformat(),
                                      "motivo": "clasificador"}


def test_cambiar_dos_veces_es_un_mensaje_repetido(estado, reloj):
    _documento(estado, reloj)
    e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-aaa", e.NORMALIZADO, e.CLASIFICADO, "clasificador")
    otra_vez = e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-aaa", e.NORMALIZADO, e.CLASIFICADO, "clasificador")
    assert not otra_vez.aplicado
    assert len(otra_vez.registro.datos["historial"]) == 2


def test_cambiar_desde_otro_estado_se_rechaza(estado, reloj):
    _documento(estado, reloj, inicial=e.NORMALIZADO)
    e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-aaa", e.NORMALIZADO, e.ESPERANDO_CLASIFICACION_HUMANA, "invalida")
    with pytest.raises(e.EstadoInesperado) as info:
        e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-aaa", e.NORMALIZADO, e.ERROR_PROCESO, "falla")
    assert info.value.registro.datos["estado"] == e.ESPERANDO_CLASIFICACION_HUMANA


def test_cambiar_acepta_varios_origenes(estado, reloj):
    _documento(estado, reloj)
    e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-aaa", e.NORMALIZADO, e.ERROR_PROCESO, "clasificador caido")
    cambio = e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-aaa", (e.NORMALIZADO, e.ERROR_PROCESO), e.CLASIFICADO,
                       "reenviado")
    assert cambio.aplicado


@pytest.mark.parametrize("tipo,de,a", [
    (e.DOCUMENTO, e.DUPLICADO, e.CLASIFICADO),
    (e.DOCUMENTO, e.ERROR_ENTRADA, e.CLASIFICADO),
    (e.DOCUMENTO, e.CLASIFICADO, e.NORMALIZADO),
    (e.TAREA, e.RESUELTA, e.ABIERTA),
    (e.SEGMENTO, e.PENDIENTE, e.SIN_EXTRACCION),
])
def test_transiciones_no_permitidas_son_un_bug(estado, reloj, tipo, de, a):
    with pytest.raises(e.TransicionNoPermitida):
        e.cambiar(estado, reloj, P, tipo, "X", de, a, "m")


def test_cambiar_lo_que_no_existe_es_un_bug(estado, reloj):
    with pytest.raises(e.NoExiste):
        e.cambiar(estado, reloj, P, e.TAREA, "no-hay", e.ABIERTA, e.RESUELTA, "m")


class EstadoConOtroTrabajador(EstadoEnMemoria):
    """Antes de cada escritura, otro trabajador cambia el registro."""

    def __init__(self, veces, cambio_ajeno):
        super().__init__()
        self.veces = veces
        self.cambio_ajeno = cambio_ajeno

    def reemplazar(self, registro, datos):
        if self.veces:
            self.veces -= 1
            actual = super().leer(registro.id_proceso, registro.tipo, registro.id)
            super().reemplazar(actual, self.cambio_ajeno(actual.datos))
        return super().reemplazar(registro, datos)


def test_conflicto_se_relee_y_se_decide_de_nuevo(reloj):
    # El otro trabajador solo toca un dato: al releer, el cambio sigue siendo válido.
    estado = EstadoConOtroTrabajador(1, lambda d: {**d, "otro": 1})
    _documento(estado, reloj)
    cambio = e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-aaa", e.NORMALIZADO, e.CLASIFICADO, "clasificador")
    assert cambio.aplicado
    assert cambio.registro.datos["otro"] == 1


def test_conflicto_que_ya_hizo_el_cambio_es_un_repetido(reloj):
    estado = EstadoConOtroTrabajador(1, lambda d: {**d, "estado": e.CLASIFICADO})
    _documento(estado, reloj)
    cambio = e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-aaa", e.NORMALIZADO, e.CLASIFICADO, "clasificador")
    assert not cambio.aplicado


def test_conflicto_sin_fin(reloj):
    estado = EstadoConOtroTrabajador(99, lambda d: {**d, "otro": d.get("otro", 0) + 1})
    _documento(estado, reloj)
    with pytest.raises(Conflicto):
        e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-aaa", e.NORMALIZADO, e.CLASIFICADO, "m", intentos=3)


def test_cada_estado_de_las_maquinas_es_alcanzable():
    for tipo, maquina in e.MAQUINAS.items():
        alcanzables = set(maquina.iniciales)
        while True:
            nuevos = {a for de in alcanzables for a in maquina.transiciones.get(de, ())} - alcanzables
            if not nuevos:
                break
            alcanzables |= nuevos
        assert alcanzables == maquina.estados(), tipo
        assert maquina.intermedios <= maquina.estados(), tipo


# --- Consulta ---


def test_consultar(estado, reloj):
    assert e.consultar(estado, P) is None
    e.crear(estado, reloj, P, e.PROCESO, P, e.ABIERTO, "aviso")
    for entrega in ("PROCESO", "OF-001", "OF-002"):
        e.crear(estado, reloj, P, e.OFERENTE, entrega, e.RECIBIDO, "aviso", entrega=entrega)
    e.cambiar(estado, reloj, P, e.OFERENTE, "OF-001", e.RECIBIDO, e.PROCESANDO, "normalizado")
    _documento(estado, reloj, "OF-001-a")
    _documento(estado, reloj, "OF-001-b", inicial=e.DUPLICADO)
    _documento(estado, reloj, "OF-001-c", inicial=e.ERROR_ENTRADA)
    e.cambiar(estado, reloj, P, e.DOCUMENTO, "OF-001-a", e.NORMALIZADO, e.CLASIFICADO, "clasificador")
    e.crear(estado, reloj, P, e.SEGMENTO, "OF-001-a-p1-2", e.PENDIENTE, "umbral", entrega="OF-001")
    e.crear(estado, reloj, P, e.SEGMENTO, "OF-001-a-p3-3", e.ESPERANDO_CLASIFICACION_HUMANA, "confianza baja",
            entrega="OF-001")
    e.crear(estado, reloj, P, e.TAREA, "documento_con_error-OF-001-c", e.ABIERTA, "error_entrada",
            {"clase": "documento_con_error", "motivo": "CONTRASENA"}, entrega="OF-001")
    e.crear(estado, reloj, P, e.TAREA, "clasificacion-OF-001-a-p3-3", e.ABIERTA, "confianza baja",
            {"clase": "clasificacion", "motivo": "CONFIANZA_BAJA"}, entrega="OF-001")
    e.cambiar(estado, reloj, P, e.TAREA, "clasificacion-OF-001-a-p3-3", e.ABIERTA, e.RESUELTA, "asignado")

    resumen = e.consultar(estado, P)
    assert resumen["estado"] == e.ABIERTO
    assert list(resumen["entregas"]) == ["OF-001", "OF-002", "PROCESO"]
    of1 = resumen["entregas"]["OF-001"]
    assert of1 == {
        "estado": e.PROCESANDO,
        "documentos": {"clasificado": 1, "duplicado": 1, "error_entrada": 1},
        "segmentos": {"esperando_clasificacion_humana": 1, "pendiente": 1},
        "tareas_abiertas": 1,
        "en_curso": 1,
    }
    assert resumen["entregas"]["OF-002"]["en_curso"] == 1  # recibido, sin normalizar
    assert resumen["tareas_abiertas"] == [{"id": "documento_con_error-OF-001-c", "entrega": "OF-001",
                                           "clase": "documento_con_error", "motivo": "CONTRASENA"}]


def test_anotar_suma_datos_sin_cambiar_estado_ni_historial(estado, reloj):
    _documento(estado, reloj)
    registro = e.anotar(estado, P, e.DOCUMENTO, "OF-001-aaa", {"marca": True})
    assert (registro.datos["estado"], registro.datos["marca"], len(registro.datos["historial"])) == (
        e.NORMALIZADO, True, 1)
    with pytest.raises(e.TransicionNoPermitida):
        e.anotar(estado, P, e.DOCUMENTO, "OF-001-aaa", {"estado": "otro"})
    with pytest.raises(e.NoExiste):
        e.anotar(estado, P, e.DOCUMENTO, "no-hay", {})
