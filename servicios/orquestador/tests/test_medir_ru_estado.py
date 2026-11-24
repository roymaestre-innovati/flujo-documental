"""Medición de RU y limpieza de procesos con colecciones falsas."""

from contextlib import nullcontext
from unittest.mock import Mock, call

import limpiar_estado_prueba
import medir_ru_estado
import mongomock
import pytest
from pymongo.collection import Collection
from pymongo.errors import AutoReconnect, OperationFailure

from orquestador.errores import ErrorTransitorio


@pytest.mark.parametrize(("falla", "espera"), [
    (ErrorTransitorio(), 0.5),
    (AutoReconnect("detalle interno"), 0.5),
    (OperationFailure("detalle interno", 16500, {"RetryAfterMs": 250}), 0.25),
])
def test_limpieza_reintenta_un_borrado_transitorio(monkeypatch, falla, espera):
    coleccion = Mock(spec=Collection)
    coleccion.delete_many.side_effect = [falla, None, None]
    sleep = Mock()
    monkeypatch.setattr(limpiar_estado_prueba, "sleep", sleep)

    limpiar_estado_prueba.limpiar_procesos(coleccion, ("PRUEBA-1", "PRUEBA-2"))

    assert coleccion.delete_many.call_args_list == [call({"id_proceso": "PRUEBA-1"})] * 2 + [
        call({"id_proceso": "PRUEBA-2"}),
    ]
    sleep.assert_called_once_with(espera)


def test_limpieza_agota_cinco_intentos_y_borra_los_demas(monkeypatch):
    coleccion = Mock(spec=Collection)
    coleccion.delete_many.side_effect = [AutoReconnect("detalle interno")] * 5 + [None]
    sleep = Mock()
    monkeypatch.setattr(limpiar_estado_prueba, "sleep", sleep)

    with pytest.raises(limpiar_estado_prueba.ErrorLimpieza) as error:
        limpiar_estado_prueba.limpiar_procesos(coleccion, ("PRUEBA-1", "PRUEBA-2"))

    assert str(error.value) == "No se pudieron borrar los procesos de prueba: PRUEBA-1"
    assert coleccion.delete_many.call_args_list == [call({"id_proceso": "PRUEBA-1"})] * 5 + [
        call({"id_proceso": "PRUEBA-2"}),
    ]
    assert sleep.call_args_list == [call(0.5)] * 4


def test_medir_operaciones_compuestas_suma_las_ru_de_cada_solicitud(capsys):
    coleccion = Mock(wraps=mongomock.MongoClient().evaluacion_ofertas.estado)
    coleccion.database.command.side_effect = [{"RequestCharge": ru} for ru in range(1, 12)]

    medir_ru_estado._medir_operaciones(coleccion, "PRUEBA-1")

    operaciones = [llamada[0] for llamada in coleccion.mock_calls]
    assert operaciones == [
        "find_one", "database.command", "insert_one", "database.command",
        "insert_one", "database.command", "find_one", "database.command",
        "find_one", "database.command", "replace_one", "database.command",
        "replace_one", "database.command", "find_one", "database.command",
        "find", "database.command", "find", "database.command", "distinct", "database.command",
    ]
    assert coleccion.database.command.call_args_list == [call("getLastRequestStatistics")] * 11
    salida = capsys.readouterr().out
    assert "crear repetido\t7 (insert_one: 3 + find_one: 4)\t" in salida
    assert "reemplazar con conflicto\t15 (replace_one: 7 + find_one: 8)\t" in salida


def test_script_intenta_limpiar_y_contar_tras_fallar_la_medicion(monkeypatch, capsys):
    coleccion = Mock(spec=Collection)
    coleccion.database.client = nullcontext()
    coleccion.delete_many.side_effect = OperationFailure("texto del servidor", 2)
    coleccion.count_documents.return_value = 1
    monkeypatch.setenv("ESTADO_MONGO_URL", "valor de prueba")
    monkeypatch.setattr(medir_ru_estado, "coleccion_desde_entorno", Mock(return_value=coleccion))
    monkeypatch.setattr(medir_ru_estado, "_medir_operaciones", Mock(side_effect=RuntimeError("detalle interno")))

    assert medir_ru_estado.main() == 1

    id_proceso = medir_ru_estado._medir_operaciones.call_args.args[1]
    coleccion.delete_many.assert_called_once_with({"id_proceso": id_proceso})
    coleccion.count_documents.assert_called_once_with({"id_proceso": {"$regex": "^PRUEBA-"}})
    salida = capsys.readouterr()
    assert "Documentos con id_proceso PRUEBA- después de la limpieza: 1" in salida.out
    assert f"No se pudieron borrar los procesos de prueba: {id_proceso}" in salida.err
    assert "Falló la medición (RuntimeError)" in salida.err
    assert "texto del servidor" not in salida.err
    assert "detalle interno" not in salida.err
