"""Contrato que comparten las implementaciones de Estado."""

from copy import deepcopy
from dataclasses import replace

import mongomock
import pytest

from orquestador.estado import Conflicto, ErrorEstado, EstadoEnMemoria, Registro
from orquestador.estado_mongo import EstadoMongo


@pytest.fixture
def estado_mongomock():
    return EstadoMongo(mongomock.MongoClient().evaluacion_ofertas.estado)


@pytest.fixture
def estado_en_memoria():
    return EstadoEnMemoria()


@pytest.fixture
def estado_mongo_azure(coleccion_mongo_de_prueba):
    return EstadoMongo(coleccion_mongo_de_prueba)


# Cada implementación agrega su fixture como un parámetro de este fixture.
@pytest.fixture(params=[
    pytest.param("estado_en_memoria", id="memoria"),
    pytest.param("estado_mongomock", id="mongomock"),
    pytest.param("estado_mongo_azure", id="azure", marks=pytest.mark.azure),
])
def estado(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def id_proceso(procesos_de_prueba):
    return procesos_de_prueba[0]


def test_estado_crear_si_no_existe_gana_el_primero(estado, id_proceso):
    primero, creado = estado.crear_si_no_existe(id_proceso, "proceso", id_proceso, {"v": 1})
    segundo, creado_otra_vez = estado.crear_si_no_existe(id_proceso, "proceso", id_proceso, {"v": 2})

    esperado = Registro(id_proceso, "proceso", id_proceso, 1, {"v": 1})
    assert creado is True
    assert creado_otra_vez is False
    assert primero == segundo == esperado
    segundo.datos["v"] = 3
    assert estado.leer(id_proceso, "proceso", id_proceso) == esperado


def test_estado_reemplazo_condicional(estado, id_proceso):
    leido, _ = estado.crear_si_no_existe(id_proceso, "documento", "D1", {"estado": "pendiente"})
    nuevo = estado.reemplazar(leido, {"estado": "normalizado"})

    assert nuevo == Registro(id_proceso, "documento", "D1", 2, {"estado": "normalizado"})
    with pytest.raises(Conflicto):
        estado.reemplazar(leido, {"estado": "error_entrada"})
    assert estado.leer(id_proceso, "documento", "D1") == nuevo


def test_estado_reemplazar_un_registro_inexistente(estado, id_proceso):
    registro = Registro(id_proceso, "documento", "D1", 1, {})
    with pytest.raises(ErrorEstado):
        estado.reemplazar(registro, {"estado": "normalizado"})


def test_estado_leer_un_registro_inexistente(estado, id_proceso):
    assert estado.leer(id_proceso, "documento", "D1") is None


def test_estado_lista_por_proceso_y_tipo(estado, procesos_de_prueba):
    primero, segundo = procesos_de_prueba
    estado.crear_si_no_existe(primero, "documento", "D2", {})
    estado.crear_si_no_existe(primero, "tarea", "T1", {})
    estado.crear_si_no_existe(primero, "proceso", primero, {})
    estado.crear_si_no_existe(primero, "segmento", "S1", {})
    estado.crear_si_no_existe(primero, "documento", "D1", {})
    estado.crear_si_no_existe(primero, "oferente", "PROCESO", {})
    estado.crear_si_no_existe(segundo, "documento", "D9", {})

    assert [(r.tipo, r.id) for r in estado.listar(primero)] == [
        ("proceso", primero), ("oferente", "PROCESO"), ("documento", "D1"),
        ("documento", "D2"), ("segmento", "S1"), ("tarea", "T1"),
    ]
    assert [(r.tipo, r.id) for r in estado.listar(primero, "documento")] == [
        ("documento", "D1"), ("documento", "D2"),
    ]


def test_estado_listar_rechaza_tipo_desconocido(estado, id_proceso):
    with pytest.raises(ErrorEstado):
        estado.listar(id_proceso, "otro")


def test_estado_procesos_ordenados_y_sin_repetidos(estado, procesos_de_prueba):
    primero, segundo = sorted(procesos_de_prueba)
    estado.crear_si_no_existe(segundo, "proceso", segundo, {})
    estado.crear_si_no_existe(primero, "proceso", primero, {})
    estado.crear_si_no_existe(primero, "oferente", "PROCESO", {})

    assert [p for p in estado.procesos() if p in procesos_de_prueba] == [primero, segundo]


def test_estado_crear_rechaza_tipos_desconocidos_y_lo_que_no_es_json(estado, id_proceso):
    with pytest.raises(ErrorEstado):
        estado.crear_si_no_existe(id_proceso, "otro", "X", {})
    with pytest.raises(TypeError):
        estado.crear_si_no_existe(id_proceso, "proceso", id_proceso, {"x": object()})


def test_estado_reemplazar_rechaza_tipos_desconocidos_y_lo_que_no_es_json(estado, id_proceso):
    registro, _ = estado.crear_si_no_existe(id_proceso, "proceso", id_proceso, {})
    with pytest.raises(ErrorEstado):
        estado.reemplazar(replace(registro, tipo="otro"), {})
    with pytest.raises(TypeError):
        estado.reemplazar(registro, {"x": object()})


def test_estado_crear_copia_los_datos(estado, id_proceso):
    datos = {"lista": [1]}
    creado, _ = estado.crear_si_no_existe(id_proceso, "documento", "D1", datos)
    datos["lista"].append(2)
    assert estado.leer(id_proceso, "documento", "D1").datos == {"lista": [1]}
    creado.datos["lista"].append(3)
    assert estado.leer(id_proceso, "documento", "D1").datos == {"lista": [1]}


def test_estado_leer_copia_los_datos(estado, id_proceso):
    estado.crear_si_no_existe(id_proceso, "documento", "D1", {"lista": [1]})
    leido = estado.leer(id_proceso, "documento", "D1")
    leido.datos["lista"].append(2)
    assert estado.leer(id_proceso, "documento", "D1").datos == {"lista": [1]}


def test_estado_reemplazar_copia_los_datos(estado, id_proceso):
    registro, _ = estado.crear_si_no_existe(id_proceso, "documento", "D1", {})
    datos = {"lista": [1]}
    nuevo = estado.reemplazar(registro, datos)
    datos["lista"].append(2)
    assert estado.leer(id_proceso, "documento", "D1").datos == {"lista": [1]}
    nuevo.datos["lista"].append(3)
    assert estado.leer(id_proceso, "documento", "D1").datos == {"lista": [1]}


def test_estado_listar_copia_los_datos(estado, id_proceso):
    estado.crear_si_no_existe(id_proceso, "documento", "D1", {"lista": [1]})
    [listado] = estado.listar(id_proceso)
    listado.datos["lista"].append(2)
    assert estado.leer(id_proceso, "documento", "D1").datos == {"lista": [1]}


def test_estado_mismo_tipo_e_id_en_procesos_distintos(estado, procesos_de_prueba):
    primero, segundo = procesos_de_prueba
    otro, creado_en_segundo = estado.crear_si_no_existe(segundo, "oferente", "PROCESO", {"v": "SR2"})
    original, creado_en_primero = estado.crear_si_no_existe(primero, "oferente", "PROCESO", {"v": "SR1"})

    esperado_segundo = Registro(segundo, "oferente", "PROCESO", 1, {"v": "SR2"})
    assert creado_en_primero and creado_en_segundo
    assert original == Registro(primero, "oferente", "PROCESO", 1, {"v": "SR1"})
    assert otro == estado.leer(segundo, "oferente", "PROCESO") == esperado_segundo

    nuevo = estado.reemplazar(original, {"v": "SR1 actualizado"})
    esperado_primero = Registro(primero, "oferente", "PROCESO", 2, {"v": "SR1 actualizado"})
    assert nuevo == estado.leer(primero, "oferente", "PROCESO") == esperado_primero
    assert estado.leer(segundo, "oferente", "PROCESO") == esperado_segundo


def test_estado_conserva_las_claves_de_esperados(estado, id_proceso):
    datos = {"esperados": {"sub/a.pdf": {"n": 1}, "$carta.pdf": {"n": 2}, "año.pdf": {"n": 3}}}
    creado, _ = estado.crear_si_no_existe(id_proceso, "oferente", "PROCESO", deepcopy(datos))
    leido = estado.leer(id_proceso, "oferente", "PROCESO")
    for registro in (creado, leido):
        assert registro.datos == datos
        assert list(registro.datos["esperados"]) == list(datos["esperados"])

    datos_nuevos = {"esperados": {"año.pdf": {"n": 4}, "otra/b.pdf": {"n": 5}, "$oferta.pdf": {"n": 6}}}
    nuevo = estado.reemplazar(leido, deepcopy(datos_nuevos))
    for registro in (nuevo, estado.leer(id_proceso, "oferente", "PROCESO")):
        assert registro.datos == datos_nuevos
        assert list(registro.datos["esperados"]) == list(datos_nuevos["esperados"])
