"""Formato, filtros y traducción de fallas de EstadoMongo, con colecciones falsas."""

from unittest.mock import Mock, call

import bson
import mongomock
import pytest
from bson.errors import InvalidDocument
from bson.int64 import Int64
from pymongo.collection import Collection
from pymongo.errors import (
    AutoReconnect,
    ConfigurationError,
    ConnectionFailure,
    DuplicateKeyError,
    ExecutionTimeout,
    NetworkTimeout,
    OperationFailure,
    ServerSelectionTimeoutError,
    WriteError,
    WTimeoutError,
)
from pymongo.write_concern import WriteConcern

from orquestador.cola import CLASIFICAR, ColaEnMemoria
from orquestador.errores import ErrorDeConfiguracion, ErrorTransitorio, procesar_uno
from orquestador.estado import Conflicto, ErrorEstado, Registro
from orquestador.estado_mongo import ErrorMongo, EstadoMongo, coleccion_desde_entorno
from orquestador.parametros import Parametros
from orquestador.reloj import RelojManual


@pytest.fixture
def coleccion():
    return mongomock.MongoClient().evaluacion_ofertas.estado


def test_rechaza_escrituras_sin_confirmar(coleccion):
    sin_confirmar = coleccion.with_options(write_concern=WriteConcern(w=0))
    assert not sin_confirmar.write_concern.acknowledged

    with pytest.raises(ErrorDeConfiguracion, match="Revisa la opción w de ESTADO_MONGO_URL"):
        EstadoMongo(sin_confirmar)


def test_documento_guardado(coleccion):
    estado = EstadoMongo(coleccion)
    datos = {"_id": "del flujo", "version": 17, "estado": "abierto"}
    estado.crear_si_no_existe("P1", "documento", "D:1", datos)

    documento = coleccion.find_one({"id_proceso": "P1"})
    assert documento == {
        "_id": {"p": "P1", "t": "documento", "i": "D:1"},
        "id_proceso": "P1",
        "tipo": "documento",
        "id": "D:1",
        "version": 1,
        "datos": datos,
    }
    assert list(documento["_id"]) == ["p", "t", "i"]


def test_operaciones_usan_la_clave_de_particion(coleccion):
    espia = Mock(wraps=coleccion)
    estado = EstadoMongo(espia)
    filtro = {"_id": {"p": "P1", "t": "documento", "i": "D1"}, "id_proceso": "P1"}
    registro, _ = estado.crear_si_no_existe("P1", "documento", "D1", {})
    estado.leer("P1", "documento", "D1")
    estado.listar("P1")
    estado.listar("P1", "documento")
    estado.reemplazar(registro, {"v": 2})
    with pytest.raises(Conflicto):
        estado.reemplazar(registro, {})
    estado.procesos()

    documento = {**filtro, "tipo": "documento", "id": "D1", "version": 1, "datos": {}}
    espia.insert_one.assert_called_once_with(documento)
    assert espia.find_one.call_args_list == [call(filtro), call(filtro)]
    assert espia.find.call_args_list == [call({"id_proceso": "P1"}), call({"id_proceso": "P1", "tipo": "documento"})]
    assert espia.replace_one.call_args_list == [
        call({**filtro, "version": 1}, {**documento, "version": 2, "datos": {"v": 2}}),
        call({**filtro, "version": 1}, {**documento, "version": 2}),
    ]
    espia.distinct.assert_called_once_with("id_proceso")


def test_limite_incluye_el_documento_bson_completo(coleccion):
    espia = Mock(wraps=coleccion)
    estado = EstadoMongo(espia)
    registro, _ = estado.crear_si_no_existe("P1", "documento", "D1", {"texto": ""})
    cabecera = espia.insert_one.call_args.args[0]
    limite = 2 * 1024 * 1024
    bytes_disponibles = limite - len(bson.encode(cabecera))
    texto = "contenido privado".ljust(bytes_disponibles, "a")
    nuevo = estado.reemplazar(registro, {"texto": texto})
    espia.reset_mock()

    # Esta letra ocupa dos bytes y se agrega al documento que ya llegó al límite.
    datos = {"texto": texto + "ñ"}
    for escribir in (lambda: estado.crear_si_no_existe("P1", "documento", "D2", datos),
                     lambda: estado.reemplazar(nuevo, datos)):
        with pytest.raises(ErrorEstado, match=f"{limite + 2} bytes") as error:
            escribir()
        assert "contenido privado" not in str(error.value)
    assert espia.mock_calls == []


@pytest.mark.parametrize(("datos", "falla"), [
    ({"contenido privado": 2**63}, OverflowError),
    ({"contenido privado\x00": 1}, InvalidDocument),
    ({"texto": "contenido privado\ud800"}, UnicodeEncodeError),
])
def test_rechaza_datos_que_bson_no_acepta_sin_tocar_mongo(datos, falla):
    falsa = Mock(spec=Collection)
    estado = EstadoMongo(falsa)
    registro = Registro("P1", "documento", "D1", 1, {})

    for escribir in (lambda: estado.crear_si_no_existe("P1", "documento", "D1", datos),
                     lambda: estado.reemplazar(registro, datos)):
        with pytest.raises(ErrorEstado, match=falla.__name__) as error:
            escribir()
        assert "contenido privado" not in str(error.value)
        assert error.value.__suppress_context__
    assert falsa.mock_calls == []


def test_escribir_rechaza_tipo_desconocido_sin_tocar_mongo():
    falsa = Mock(spec=Collection)
    estado = EstadoMongo(falsa)

    with pytest.raises(ErrorEstado, match="Tipo desconocido"):
        estado.crear_si_no_existe("P1", "otro", "D1", {})
    with pytest.raises(ErrorEstado, match="Tipo desconocido"):
        estado.reemplazar(Registro("P1", "otro", "D1", 1, {}), {})

    assert falsa.mock_calls == []


def test_crear_devuelve_el_registro_del_trabajador_que_gano(coleccion):
    espia = Mock(wraps=coleccion)
    estado = EstadoMongo(espia)

    def insertar_el_del_otro(documento):
        coleccion.insert_one({**documento, "datos": {"v": "ganador"}})
        raise DuplicateKeyError("detalle del servidor", 11000)

    espia.insert_one.side_effect = insertar_el_del_otro
    registro, creado = estado.crear_si_no_existe("P1", "documento", "D1", {"v": "perdedor"})

    assert creado is False
    assert registro == Registro("P1", "documento", "D1", 1, {"v": "ganador"})
    espia.find_one.assert_called_once_with({
        "_id": {"p": "P1", "t": "documento", "i": "D1"}, "id_proceso": "P1",
    })


def test_crear_avisa_si_el_duplicado_ya_no_esta(coleccion):
    espia = Mock(wraps=coleccion)
    espia.insert_one.side_effect = DuplicateKeyError("detalle del servidor", 11000)

    with pytest.raises(ErrorEstado, match="duplicado.*no se encontró"):
        EstadoMongo(espia).crear_si_no_existe("P1", "documento", "D1", {})


@pytest.mark.parametrize(("mensaje", "detalles", "espera"), [
    ("detalle interno RetryAfterMs=250", None, 0.25),
    ("detalle interno RetryAfterMs=250", {"errmsg": "x", "op": {"RetryAfterMs": 3600000}}, 0.25),
    ("detalle interno RetryAfterMs=0", None, 0),
    ("detalle interno", {"errmsg": "RetryAfterMs=625"}, 0.625),
    ("detalle interno", {"RetryAfterMs": 1500}, 1.5),
    ("detalle interno", {"RetryAfterMs": Int64(1500)}, 1.5),
    ("detalle interno", None, 1),
])
def test_limite_de_ru_pide_esperar(mensaje, detalles, espera):
    falsa = Mock(spec=Collection)
    falsa.insert_one.side_effect = OperationFailure(mensaje, 16500, detalles)

    with pytest.raises(ErrorTransitorio) as error:
        EstadoMongo(falsa).crear_si_no_existe("P1", "documento", "D1", {})

    assert error.value.espera_s == espera
    assert str(error.value) == "MongoDB insert_one (OperationFailure, código 16500)"
    assert error.value.__suppress_context__


def test_limite_de_ru_ignora_el_documento_y_otros_detalles_anidados():
    falsa = Mock(spec=Collection)
    falsa.insert_one.side_effect = WriteError("x", 16500, {
        "errmsg": "x", "op": {"datos": {"RetryAfterMs": 3600000}}, "extra": {"RetryAfterMs": 500},
    })

    with pytest.raises(ErrorTransitorio) as error:
        EstadoMongo(falsa).crear_si_no_existe("P1", "documento", "D1", {})

    assert error.value.espera_s == 1


def test_espera_por_limite_de_ru_es_configurable():
    falsa = Mock(spec=Collection)
    falsa.distinct.side_effect = OperationFailure("detalle interno", 16500)
    estado = EstadoMongo(falsa, parametros=Parametros(espera_limite_estado_s=2.5))

    with pytest.raises(ErrorTransitorio) as error:
        estado.procesos()

    assert error.value.espera_s == 2.5
    assert str(error.value) == "MongoDB distinct (OperationFailure, código 16500)"


@pytest.mark.parametrize(("falla", "codigo"), [
    (AutoReconnect("detalle interno"), ""),
    (ConnectionFailure("detalle interno"), ""),
    (NetworkTimeout("detalle interno"), ""),
    (ServerSelectionTimeoutError("detalle interno"), ""),
    (ExecutionTimeout("detalle interno", 50), ", código 50"),
    (WTimeoutError("detalle interno", 64), ", código 64"),
])
def test_fallas_de_red_y_tiempo_se_reintentan_sin_espera(falla, codigo):
    falsa = Mock(spec=Collection)
    falsa.find_one.side_effect = falla

    with pytest.raises(ErrorTransitorio) as error:
        EstadoMongo(falsa).leer("P1", "documento", "D1")

    assert error.value.espera_s is None
    assert str(error.value) == f"MongoDB find_one ({type(falla).__name__}{codigo})"


def test_timeout_de_escritura_se_reintenta_sin_espera():
    falsa = Mock(spec=Collection)
    falsa.replace_one.side_effect = WriteError("x", 50, {"op": {"datos": {"texto": "contenido privado"}}})

    with pytest.raises(ErrorTransitorio) as error:
        EstadoMongo(falsa).reemplazar(Registro("P1", "documento", "D1", 1, {}), {})

    assert error.value.espera_s is None
    assert str(error.value) == "MongoDB replace_one (WriteError, código 50)"


@pytest.mark.parametrize(("falla", "detalle"), [
    (OperationFailure("detalle interno", 13), "OperationFailure, código 13"),
    (OperationFailure("detalle interno", 18), "OperationFailure, código 18"),
    (ConfigurationError("detalle interno"), "ConfigurationError"),
])
def test_fallas_de_acceso_son_de_configuracion(falla, detalle):
    falsa = Mock(spec=Collection)
    falsa.replace_one.side_effect = falla

    with pytest.raises(ErrorDeConfiguracion) as error:
        EstadoMongo(falsa).reemplazar(Registro("P1", "documento", "D1", 1, {}), {})

    assert str(error.value) == f"MongoDB replace_one ({detalle})"


def test_falla_al_recorrer_el_cursor_tambien_se_traduce():
    def recorrer():
        yield {"id_proceso": "P1", "tipo": "documento", "id": "D1", "version": 1, "datos": {}}
        raise OperationFailure("detalle interno RetryAfterMs=125", 16500)

    falsa = Mock(spec=Collection)
    falsa.find.return_value = recorrer()

    with pytest.raises(ErrorTransitorio) as error:
        EstadoMongo(falsa).listar("P1")

    assert error.value.espera_s == 0.125
    assert str(error.value) == "MongoDB find (OperationFailure, código 16500)"


@pytest.mark.parametrize("falla", [
    OperationFailure("texto del servidor", 2, {"op": {"datos": {"texto": "contenido privado"}}}),
    DuplicateKeyError("texto del servidor", 11000),
])
def test_otras_fallas_de_mongo_se_traducen_sin_texto_del_servidor(falla):
    falsa = Mock(spec=Collection)
    falsa.find.side_effect = falla

    with pytest.raises(ErrorMongo) as error:
        EstadoMongo(falsa).listar("P1")

    assert str(error.value) == f"MongoDB find ({type(falla).__name__}, código {falla.code})"
    assert error.value.__suppress_context__


def test_procesar_uno_manda_error_mongo_a_errores_sin_reintentar():
    falsa = Mock(spec=Collection)
    falsa.find.side_effect = OperationFailure("texto del servidor", 2)
    estado = EstadoMongo(falsa)
    cola = ColaEnMemoria(RelojManual())
    cuerpo = {"id_proceso": "P1"}
    cola.publicar(CLASIFICAR, cuerpo)
    manejador = Mock(cola=CLASIFICAR, procesar=lambda mensaje: estado.listar(mensaje["id_proceso"]))

    resultado = procesar_uno(cola, manejador)

    assert resultado.desenlace == "a_errores"
    assert resultado.motivo.startswith("Bug: ErrorMongo en ")
    assert cola.pendientes(CLASIFICAR) == 0
    assert [mensaje.motivo for mensaje in cola.errores(CLASIFICAR)] == [resultado.motivo]
    manejador.al_fallar.assert_called_once_with(cuerpo, resultado.motivo)


def test_coleccion_desde_entorno_exige_url(monkeypatch):
    monkeypatch.delenv("ESTADO_MONGO_URL", raising=False)
    crear_cliente = Mock()

    with pytest.raises(ErrorDeConfiguracion, match="Falta ESTADO_MONGO_URL"):
        coleccion_desde_entorno(crear_cliente)

    crear_cliente.assert_not_called()


@pytest.mark.parametrize(("base", "nombre"), [(None, None), ("base_de_prueba", "coleccion_de_prueba")])
def test_coleccion_desde_entorno_configura_el_cliente(monkeypatch, base, nombre):
    url = "valor de prueba"
    monkeypatch.setenv("ESTADO_MONGO_URL", url)
    monkeypatch.delenv("ESTADO_MONGO_BASE", raising=False)
    monkeypatch.delenv("ESTADO_MONGO_COLECCION", raising=False)
    if base is not None:
        monkeypatch.setenv("ESTADO_MONGO_BASE", base)
        monkeypatch.setenv("ESTADO_MONGO_COLECCION", nombre)
    crear_cliente = Mock(return_value=mongomock.MongoClient())

    coleccion = coleccion_desde_entorno(crear_cliente)

    crear_cliente.assert_called_once_with(url)
    assert coleccion.database.name == (base or "evaluacion_ofertas")
    assert coleccion.name == (nombre or "estado")


@pytest.mark.parametrize("clase", [ConfigurationError, ValueError])
def test_coleccion_desde_entorno_oculta_el_valor_si_falla_el_cliente(monkeypatch, clase):
    url = "valor de prueba"
    monkeypatch.setenv("ESTADO_MONGO_URL", url)
    crear_cliente = Mock(side_effect=clase(url))

    with pytest.raises(ErrorDeConfiguracion) as error:
        coleccion_desde_entorno(crear_cliente)

    assert url not in str(error.value)
    assert error.value.__suppress_context__
