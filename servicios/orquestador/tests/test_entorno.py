"""Las piezas de Azure de un worker, desde el entorno, con fábricas falsas (T03)."""

import pytest
from normalizacion.almacen import AlmacenLocal, AlmacenSinPermiso

from orquestador.cola import ColaEnMemoria
from orquestador.entorno import Fabricas, faltantes, piezas_desde_entorno
from orquestador.errores import ErrorDeConfiguracion
from orquestador.estado import EstadoEnMemoria
from orquestador.reloj import RelojManual

VARIABLES = {
    "SERVICEBUS_NAMESPACE": "espacio.servicebus.windows.net",
    "ESTADO_MONGO_URL": "mongodb://usuario:clave-inventada@servidor/",
    "ALMACEN_BLOB_CUENTA": "cuentafalsa",
    "ONELAKE_WORKSPACE": "espacio-falso",
    "ONELAKE_LAKEHOUSE": "lago-falso",
}


class Recurso:
    def __init__(self, registro, nombre):
        self.registro, self.nombre = registro, nombre

    def close(self):
        self.registro.append(self.nombre)

    cerrar = close

    def get_token(self, *scopes, **kwargs):
        raise AssertionError("las pruebas no piden tokens")


class AlmacenQueCierra(AlmacenLocal):
    def __init__(self, raiz, registro):
        super().__init__(raiz)
        self.registro = registro

    def cerrar(self):
        self.registro.append("almacen")


class ColaQueCierra(ColaEnMemoria):
    def __init__(self, registro, n):
        super().__init__(RelojManual())
        self.registro, self.n = registro, n

    def cerrar(self):
        self.registro.append(f"cola{self.n}")


@pytest.fixture
def entorno(monkeypatch):
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)


@pytest.fixture
def cierres():
    return []


@pytest.fixture
def fabricas(tmp_path, cierres):
    creadas = iter(range(100))
    return Fabricas(
        cola=lambda: ColaQueCierra(cierres, next(creadas)),
        estado=lambda: (EstadoEnMemoria(), Recurso(cierres, "mongo")),
        almacen=lambda: AlmacenQueCierra(tmp_path, cierres),
        origen=lambda: "origen",
    )


def test_arma_las_piezas_y_cierra_todo_en_orden_inverso(entorno, fabricas, cierres):
    with piezas_desde_entorno(con_origen=True, fabricas=fabricas) as piezas:
        colas = piezas.colas(2)
        assert isinstance(piezas.estado, EstadoEnMemoria)
        assert piezas.origen == "origen"
        assert len({id(c) for c in colas}) == 2
    assert cierres == ["cola1", "cola0", "almacen", "mongo"]


def test_sin_origen_no_pide_onelake(entorno, fabricas, monkeypatch):
    monkeypatch.delenv("ONELAKE_WORKSPACE")
    monkeypatch.delenv("ONELAKE_LAKEHOUSE")
    with piezas_desde_entorno(con_origen=False, fabricas=fabricas) as piezas:
        assert piezas.origen is None


def test_nombra_todas_las_variables_que_faltan_sin_sus_valores(monkeypatch, fabricas):
    monkeypatch.setenv("SERVICEBUS_NAMESPACE", VARIABLES["SERVICEBUS_NAMESPACE"])
    monkeypatch.setenv("ESTADO_MONGO_URL", "  ")
    for nombre in ("ALMACEN_BLOB_CUENTA", "ONELAKE_WORKSPACE", "ONELAKE_LAKEHOUSE"):
        monkeypatch.delenv(nombre, raising=False)
    with pytest.raises(ErrorDeConfiguracion) as error:
        piezas_desde_entorno(con_origen=True, fabricas=fabricas)
    assert str(error.value) == ("Faltan variables de entorno: ESTADO_MONGO_URL, ALMACEN_BLOB_CUENTA, "
                                "ONELAKE_WORKSPACE, ONELAKE_LAKEHOUSE")
    assert "espacio" not in str(error.value)


def test_no_cae_al_almacen_local_si_falta_la_cuenta(entorno, monkeypatch):
    monkeypatch.delenv("ALMACEN_BLOB_CUENTA")
    assert faltantes(con_origen=False) == ["ALMACEN_BLOB_CUENTA"]


def test_una_falla_al_armar_cierra_lo_ya_creado(entorno, fabricas, cierres):
    def almacen_sin_permiso():
        raise AlmacenSinPermiso("Blob crear credencial")

    fabricas.almacen = almacen_sin_permiso
    with pytest.raises(ErrorDeConfiguracion, match="Blob crear credencial"):
        piezas_desde_entorno(con_origen=True, fabricas=fabricas)
    assert cierres == ["mongo"]


def test_la_configuracion_invalida_de_la_cola_es_error_de_configuracion(entorno, fabricas):
    def cola_invalida():
        raise ErrorDeConfiguracion("Falta SERVICEBUS_NAMESPACE")

    fabricas.cola = cola_invalida
    with piezas_desde_entorno(con_origen=False, fabricas=fabricas) as piezas:
        with pytest.raises(ErrorDeConfiguracion):
            piezas.cola()


def test_las_fabricas_reales_arman_mongo_y_blob_sin_red(entorno, monkeypatch):
    # pymongo no se conecta hasta la primera operación, y Blob no pide token al armarse.
    from normalizacion import almacen_blob

    from orquestador.estado_mongo import EstadoMongo

    cerrados = []
    monkeypatch.setattr(almacen_blob, "DefaultAzureCredential", lambda **_: Recurso(cerrados, "credencial"))
    with piezas_desde_entorno(con_origen=False) as piezas:
        assert isinstance(piezas.estado, EstadoMongo)
        assert type(piezas.almacen).__name__ == "AlmacenBlob"
    assert cerrados == ["credencial"]
