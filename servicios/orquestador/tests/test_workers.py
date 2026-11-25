"""Los workers del orquestador con piezas en memoria (T05 de tasks-workers.md)."""

import json

import pytest
from normalizacion.almacen import AlmacenLocal

from fabrica import AVISO, P, escribir, pdf
from orquestador import cola as c
from orquestador import estados, workers
from orquestador.clasificador import COLUMNAS
from orquestador.entorno import VARIABLES_COMUNES, VARIABLES_ORIGEN, Fabricas
from orquestador.estado import EstadoEnMemoria
from orquestador.origen import OrigenLocal
from orquestador.reloj import RelojSistema


class Mundo:
    def __init__(self, raiz):
        self.cola = c.ColaEnMemoria(RelojSistema())
        self.estado = EstadoEnMemoria()
        self.almacen = AlmacenLocal(raiz / "almacen")
        self.origen = OrigenLocal(raiz / "datalake")
        self.fabricas = Fabricas(cola=lambda: self.cola, estado=lambda: (self.estado, None),
                                 almacen=lambda: self.almacen, origen=lambda: self.origen)

    def correr(self, *argumentos):
        return workers.main(list(argumentos), fabricas=self.fabricas)

    def sacar(self, nombre):
        mensajes = []
        while (m := self.cola.recibir(nombre)) is not None:
            mensajes.append(m.cuerpo)
            self.cola.completar(m)
        return mensajes


@pytest.fixture
def entorno(monkeypatch):
    for nombre in VARIABLES_COMUNES + VARIABLES_ORIGEN:
        monkeypatch.setenv(nombre, "valor-inventado")


@pytest.fixture
def mundo(tmp_path, entorno):
    escribir(tmp_path, "OF-001/carta.pdf", pdf(2, "Carta de presentación"))
    mundo = Mundo(tmp_path)
    mundo.cola.publicar(c.PROCESOS_LISTOS, AVISO)
    return mundo


def _csv(mundo, filas):
    texto = ",".join(COLUMNAS) + "\n" + "".join(",".join(f) + "\n" for f in filas)
    mundo.almacen.escribir(mundo.almacen.uri("config/clasificacion.csv"), texto.encode("utf-8"))


def test_los_tres_workers_llevan_el_aviso_hasta_las_solicitudes(mundo, monkeypatch, capsys):
    monkeypatch.setenv("CLASIFICADOR", "falso")
    monkeypatch.setenv("CLASIFICADOR_CSV", "config/clasificacion.csv")
    _csv(mundo, [["OF-001", "carta.pdf", "", "", "TD-16", "0.97", ""]])

    assert mundo.correr("apertura") == 0
    assert mundo.correr("normalizar") == 0
    assert mundo.correr("clasificar") == 0

    assert estados.consultar(mundo.estado, P)["entregas"]["OF-001"]["estado"] == estados.PROCESANDO
    [solicitud] = mundo.sacar(c.EXTRAER)
    assert solicitud["tipo_documental"] == "TD-16"
    lineas = [json.loads(l) for l in capsys.readouterr().err.splitlines()]
    resumenes = [l["mensaje"] for l in lineas if l["modulo"] == "mensajeria.worker"]
    assert resumenes[0].startswith("Worker procesos-listos: 1 mensajes {'ok': 1}, terminó por vacia")
    assert len(resumenes) == 3


def test_sin_variables_sale_con_2_sin_tocar_la_cola(mundo, monkeypatch, capsys):
    monkeypatch.delenv("ESTADO_MONGO_URL")
    assert mundo.correr("apertura") == 2
    assert "Faltan variables de entorno: ESTADO_MONGO_URL" in capsys.readouterr().err
    assert mundo.cola.pendientes(c.PROCESOS_LISTOS) == 1


def test_clasificar_no_necesita_onelake(mundo, monkeypatch):
    monkeypatch.delenv("ONELAKE_WORKSPACE")
    monkeypatch.setenv("CLASIFICADOR", "falso")
    monkeypatch.setenv("CLASIFICADOR_CSV", "config/clasificacion.csv")
    _csv(mundo, [["OF-001", "carta.pdf", "", "", "TD-16", "0.97", ""]])
    assert mundo.correr("clasificar") == 0


@pytest.mark.parametrize(("variables", "csv", "mensaje"), [
    ({}, None, "CLASIFICADOR debe ser 'falso'"),
    ({"CLASIFICADOR": "falso"}, None, "Falta CLASIFICADOR_CSV"),
    ({"CLASIFICADOR": "falso", "CLASIFICADOR_CSV": "config/clasificacion.csv"}, None, "No se encontró el CSV"),
    ({"CLASIFICADOR": "falso", "CLASIFICADOR_CSV": "config/clasificacion.csv"}, [], "no tiene filas"),
])
def test_clasificar_revisa_el_clasificador_antes_de_recibir(mundo, monkeypatch, capsys, variables, csv, mensaje):
    monkeypatch.delenv("CLASIFICADOR", raising=False)
    for nombre, valor in variables.items():
        monkeypatch.setenv(nombre, valor)
    if csv is not None:
        _csv(mundo, csv)
    mundo.cola.publicar(c.CLASIFICAR, {"id_proceso": P, "entrega": "OF-001", "id_documento": "x"})
    assert mundo.correr("clasificar") == 2
    assert mensaje in capsys.readouterr().err
    assert mundo.cola.pendientes(c.CLASIFICAR) == 1


def test_un_mensaje_a_errores_sale_con_0(mundo, capsys):
    mundo.cola.publicar(c.NORMALIZAR, {"id_proceso": "SR-NO-EXISTE", "entrega": "OF-001"})
    assert mundo.correr("normalizar") == 0
    assert len(mundo.cola.errores(c.NORMALIZAR)) == 1


@pytest.mark.parametrize("argumentos", [["apertura", "--hilos", "0"], ["apertura", "--tomar-mensajes-s", "0"]])
def test_argumentos_invalidos_salen_con_2(mundo, argumentos):
    assert mundo.correr(*argumentos) == 2


def test_varios_hilos_comparten_el_manejador(mundo):
    assert mundo.correr("apertura", "--hilos", "3") == 0
    assert mundo.cola.pendientes(c.NORMALIZAR) == 1
