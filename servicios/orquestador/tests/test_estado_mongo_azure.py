"""Carreras entre trabajadores y consultas entre particiones en Cosmos DB."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from orquestador.estado import Conflicto, Registro
from orquestador.estado_mongo import EstadoMongo

pytestmark = pytest.mark.azure(variable="ESTADO_MONGO_URL")


@pytest.mark.parametrize("repeticion", range(10))
def test_crear_si_no_existe_con_dos_hilos(coleccion_mongo_de_prueba, procesos_de_prueba, repeticion):
    clave = (procesos_de_prueba[0], "documento", f"D{repeticion}")
    barrera = Barrier(2, timeout=30)
    valores = (1, 2)

    def crear(valor):
        trabajador = EstadoMongo(coleccion_mongo_de_prueba)
        barrera.wait()
        return trabajador.crear_si_no_existe(*clave, {"v": valor})

    with ThreadPoolExecutor(max_workers=2) as hilos:
        resultados = list(hilos.map(crear, valores))

    creaciones = [creado for _, creado in resultados]
    assert any(creado is True for creado in creaciones)
    assert any(creado is False for creado in creaciones)
    esperado = Registro(*clave, 1, {"v": valores[creaciones.index(True)]})
    assert [registro for registro, _ in resultados] == [esperado, esperado]
    assert EstadoMongo(coleccion_mongo_de_prueba).leer(*clave) == esperado


@pytest.mark.parametrize("repeticion", range(10))
def test_reemplazar_con_dos_hilos(coleccion_mongo_de_prueba, procesos_de_prueba, repeticion):
    clave = (procesos_de_prueba[0], "documento", f"D{repeticion}")
    estado = EstadoMongo(coleccion_mongo_de_prueba)
    original, creado = estado.crear_si_no_existe(*clave, {"v": 0})
    assert creado is True
    assert original.version == 1
    barrera = Barrier(2, timeout=30)
    valores = (1, 2)

    def reemplazar(valor):
        trabajador = EstadoMongo(coleccion_mongo_de_prueba)
        leido = trabajador.leer(*clave)
        barrera.wait()
        assert leido == original
        try:
            return trabajador.reemplazar(leido, {"v": valor})
        except Conflicto as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as hilos:
        resultados = list(hilos.map(reemplazar, valores))

    assert sum(isinstance(resultado, Conflicto) for resultado in resultados) == 1
    [(valor, nuevo)] = [
        (valor, resultado)
        for valor, resultado in zip(valores, resultados, strict=True)
        if isinstance(resultado, Registro)
    ]
    esperado = Registro(*clave, 2, {"v": valor})
    assert nuevo == estado.leer(*clave) == esperado


def test_procesos_ordenados_entre_particiones(coleccion_mongo_de_prueba, procesos_de_prueba):
    estado = EstadoMongo(coleccion_mongo_de_prueba)
    primero, segundo = sorted(procesos_de_prueba)
    for id_proceso in (segundo, primero):
        estado.crear_si_no_existe(id_proceso, "oferente", "OF-001", {})

    procesos = estado.procesos()
    assert procesos == sorted(procesos)
    assert [id_proceso for id_proceso in procesos if id_proceso in procesos_de_prueba] == [primero, segundo]
