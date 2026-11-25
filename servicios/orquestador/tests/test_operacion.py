"""Los comandos de operación con cola y estado en memoria (T09 de tasks-workers.md)."""

import datetime

import pytest

from orquestador import cola as c
from orquestador import estados, operacion
from orquestador.errores import ErrorDeConfiguracion
from orquestador.estado import EstadoEnMemoria
from orquestador.reloj import RelojManual


@pytest.fixture
def cola():
    return c.ColaEnMemoria(RelojManual())


def test_reenviar_errores_republica_y_cuenta(cola, capsys):
    cola.publicar(c.NORMALIZAR, {"id_proceso": "SR1", "entrega": "OF-001"})
    cola.a_errores(cola.recibir(c.NORMALIZAR), "Bug: algo")
    fabricas = operacion.Fabricas(cola=lambda: cola)

    assert operacion.main(["reenviar-errores", "normalizar"], fabricas=fabricas) == 0

    assert cola.errores(c.NORMALIZAR) == []
    assert cola.pendientes(c.NORMALIZAR) == 1
    assert "'reenviados': 1" in capsys.readouterr().out


def test_reenviar_errores_rechaza_una_cola_desconocida():
    with pytest.raises(SystemExit) as salida:
        operacion.main(["reenviar-errores", "otra"])
    assert salida.value.code == 2


def test_escalar_fallas_crea_las_tareas_de_lo_que_lleva_mas_de_24_horas(capsys):
    estado = EstadoEnMemoria()
    reloj = RelojManual()
    estados.crear(estado, reloj, "SR1", estados.PROCESO, "SR1", estados.ABIERTO, "aviso",
                  {"ruta": "r", "fecha_aviso": "f", "versiones": {}, "entregas": ["OF-001"]})
    estados.crear(estado, reloj, "SR1", estados.OFERENTE, "OF-001", estados.RECIBIDO, "aviso", entrega="OF-001")
    hace_dos_dias = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)).isoformat()
    estados.cambiar(estado, reloj, "SR1", estados.OFERENTE, "OF-001", estados.RECIBIDO, estados.ERROR_PROCESO,
                    "falla", {"error": "Bug", "error_desde": hace_dos_dias})
    fabricas = operacion.Fabricas(estado=lambda: (estado, None))

    assert operacion.main(["escalar-fallas"], fabricas=fabricas) == 0
    assert operacion.main(["escalar-fallas"], fabricas=fabricas) == 0

    salida = capsys.readouterr().out.splitlines()
    assert salida == ["{'tareas_creadas': 1}", "{'tareas_creadas': 0}"]
    assert len(estado.listar("SR1", estados.TAREA)) == 1


def test_sin_configuracion_sale_con_2(capsys):
    def sin_namespace():
        raise ErrorDeConfiguracion("Falta SERVICEBUS_NAMESPACE")

    assert operacion.main(["reenviar-errores", "extraer"], fabricas=operacion.Fabricas(cola=sin_namespace)) == 2
    assert "Falta SERVICEBUS_NAMESPACE" in capsys.readouterr().err


def test_otra_falla_sale_con_1_sin_su_mensaje(capsys):
    def roto():
        raise ConnectionError("Juan Pérez")

    assert operacion.main(["escalar-fallas"], fabricas=operacion.Fabricas(estado=roto)) == 1
    assert "Juan" not in capsys.readouterr().err
