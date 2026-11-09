"""Apertura del proceso (T05; R1 a R5)."""

import dataclasses

import normalizacion
import pytest

from orquestador import cola as c
from orquestador import datos, estados
from orquestador.apertura import Apertura
from orquestador.errores import procesar_uno, reenviar_errores
from orquestador.estado import EstadoEnMemoria
from orquestador.origen import OrigenLocal
from orquestador.reloj import RelojManual

P = "SR0000000001"
RUTA = "procesos/SR0000000001"


def _aviso(**extra):
    return {"contrato": "modulo5-orquestador/0.1", "id_proceso": P, "ruta": RUTA,
            "fecha": "2026-11-06T09:00:00-05:00", **extra}


def _carpeta(raiz, *rutas):
    for ruta in rutas:
        archivo = raiz / RUTA / ruta
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(b"%PDF-1.4 inventado")


class Mundo:
    def __init__(self, raiz, vigentes=datos.vigentes):
        self.reloj = RelojManual()
        self.cola = c.ColaEnMemoria(self.reloj)
        self.estado = EstadoEnMemoria()
        self.origen = OrigenLocal(raiz)
        self.apertura = Apertura(self.cola, self.estado, self.origen, self.reloj, vigentes)

    def avisar(self, aviso):
        self.cola.publicar(c.PROCESOS_LISTOS, aviso)
        return procesar_uno(self.cola, self.apertura)

    def normalizar(self):
        mensajes = []
        while (m := self.cola.recibir(c.NORMALIZAR)) is not None:
            mensajes.append(m.cuerpo)
            self.cola.completar(m)
        return mensajes


@pytest.fixture
def mundo(tmp_path):
    _carpeta(tmp_path, "PROCESO/CPC.pdf", "PROCESO/Adenda 1.pdf", "OF-001/carta.pdf",
             "OF-001/parafiscales/formulario3.pdf", "OF-002/oferta.xlsx")
    return Mundo(tmp_path)


def test_abre_el_proceso_y_publica_una_entrega_por_carpeta(mundo):
    assert mundo.avisar(_aviso()).desenlace == "ok"
    proceso = mundo.estado.leer(P, estados.PROCESO, P).datos
    assert proceso["estado"] == estados.ABIERTO
    assert proceso["entregas"] == ["OF-001", "OF-002", "PROCESO"]
    assert proceso["entregas_publicadas"] is True
    assert mundo.estado.leer(P, estados.OFERENTE, "OF-001").datos["archivos"] == [
        "OF-001/carta.pdf", "OF-001/parafiscales/formulario3.pdf"]
    assert mundo.estado.leer(P, estados.OFERENTE, "PROCESO").datos["estado"] == estados.RECIBIDO
    assert mundo.normalizar() == [{"id_proceso": P, "entrega": e} for e in ("OF-001", "OF-002", "PROCESO")]


def test_fija_las_versiones_vigentes(mundo):
    mundo.avisar(_aviso())
    versiones = mundo.estado.leer(P, estados.PROCESO, P).datos["versiones"]
    vigentes = datos.vigentes()
    assert versiones["modelo_extraccion"] == vigentes.modelo_extraccion
    assert versiones["umbrales"] == vigentes.umbrales
    assert versiones["normalizador"] == normalizacion.VERSION
    assert "parametros_normalizacion" in versiones


def test_con_lista_de_archivos_no_lee_el_origen(tmp_path):
    class SinOrigen(OrigenLocal):
        def listar(self, carpeta):
            raise AssertionError("no debía listar")

    mundo = Mundo(tmp_path)
    mundo.apertura._origen = SinOrigen(tmp_path)
    aviso = _aviso(archivos=[
        {"ruta": "PROCESO/CPC.pdf", "id_oferente": None},
        {"ruta": "OF-001/carta.pdf", "id_oferente": "OF-001"},
        {"ruta": "docs/OF-002 oferta.pdf", "id_oferente": "OF-002"},
    ])
    assert mundo.avisar(aviso).desenlace == "ok"
    assert mundo.estado.leer(P, estados.OFERENTE, "OF-002").datos["archivos"] == ["docs/OF-002 oferta.pdf"]
    assert len(mundo.normalizar()) == 3


def test_aviso_repetido_no_repite_trabajo_ni_cambia_versiones(tmp_path):
    _carpeta(tmp_path, "PROCESO/CPC.pdf", "OF-001/carta.pdf")
    vigentes = [datos.vigentes()]
    mundo = Mundo(tmp_path, lambda: vigentes[0])
    mundo.avisar(_aviso())
    mundo.normalizar()
    vigentes[0] = dataclasses.replace(vigentes[0], modelo_extraccion=99)
    assert mundo.avisar(_aviso()).desenlace == "ok"
    assert mundo.normalizar() == []
    assert mundo.estado.leer(P, estados.PROCESO, P).datos["versiones"]["modelo_extraccion"] != 99


def test_aviso_repetido_con_otros_datos_se_ignora(mundo):
    mundo.avisar(_aviso())
    mundo.normalizar()
    assert mundo.avisar(_aviso(ruta="otra/carpeta")).desenlace == "ok"
    assert mundo.normalizar() == []
    assert mundo.estado.leer(P, estados.PROCESO, P).datos["ruta"] == RUTA


@pytest.mark.parametrize("aviso,motivo", [
    ({"contrato": "modulo5-orquestador/0.1", "id_proceso": P, "fecha": "2026-11-06T09:00:00Z"},
     "Rechazado: No cumple modulo5-orquestador/v0/proceso-listo: (raíz): no cumple 'required'"),
    (_aviso(contrato="otro/9"), "Rechazado: No cumple modulo5-orquestador/v0/proceso-listo: contrato: no cumple 'const'"),
    (_aviso(ruta="no/existe"), "Rechazado: La carpeta del proceso no existe en el origen o no es válida"),
    (_aviso(archivos=[{"ruta": "a.pdf", "id_oferente": "PROCESO"}]),
     "Rechazado: 'PROCESO' no puede ser el identificador de un oferente"),
    (_aviso(archivos=[{"ruta": "PROCESO/CPC.pdf", "id_oferente": None}]), "Rechazado: El proceso no trae ningún oferente"),
])
def test_aviso_que_no_se_puede_procesar_va_a_operacion(mundo, aviso, motivo):
    resultado = mundo.avisar(aviso)
    assert (resultado.desenlace, resultado.motivo) == ("a_errores", motivo)
    assert mundo.estado.listar(P) == []
    assert mundo.normalizar() == []
    assert len(mundo.cola.errores(c.PROCESOS_LISTOS)) == 1


def test_archivo_suelto_en_la_raiz_rechaza_el_aviso(mundo, tmp_path):
    _carpeta(tmp_path, "suelto.pdf")
    resultado = mundo.avisar(_aviso())
    assert resultado.desenlace == "a_errores"
    assert resultado.motivo == "Rechazado: 1 archivo(s) sueltos en la raíz de la carpeta del proceso, fuera de una entrega"
    assert mundo.estado.listar(P) == []


def test_carpeta_vacia_rechaza_el_aviso(tmp_path):
    (tmp_path / RUTA).mkdir(parents=True)
    assert Mundo(tmp_path).avisar(_aviso()).motivo == "Rechazado: El proceso no trae ningún archivo"


def test_caida_a_la_mitad_se_completa_al_reenviar(mundo):
    publicar = mundo.cola.publicar
    llamadas = {"n": 0}

    def publicar_y_caer(cola, cuerpo, demora_s=0, propiedades=None):
        if cola == c.NORMALIZAR:
            llamadas["n"] += 1
            if llamadas["n"] == 2:
                raise RuntimeError("se cayó el trabajador")
        return publicar(cola, cuerpo, demora_s, propiedades)

    mundo.cola.publicar = publicar_y_caer
    mundo.cola.publicar(c.PROCESOS_LISTOS, _aviso())
    assert procesar_uno(mundo.cola, mundo.apertura).desenlace == "a_errores"
    assert mundo.estado.leer(P, estados.PROCESO, P).datos["entregas_publicadas"] is False

    assert reenviar_errores(mundo.cola, c.PROCESOS_LISTOS) == 1
    assert procesar_uno(mundo.cola, mundo.apertura).desenlace == "ok"
    publicadas = [m["entrega"] for m in mundo.normalizar()]
    # La primera entrega sale dos veces: la normalización lo absorbe (T06).
    assert sorted(set(publicadas)) == ["OF-001", "OF-002", "PROCESO"]
    assert publicadas.count("OF-001") == 2
    assert mundo.estado.leer(P, estados.PROCESO, P).datos["entregas_publicadas"] is True
    # Y ahora un aviso repetido ya no hace nada.
    mundo.avisar(_aviso())
    assert mundo.normalizar() == []


def test_el_mensaje_normalizar_no_lleva_rutas(mundo):
    mundo.avisar(_aviso())
    for cuerpo in mundo.normalizar():
        assert set(cuerpo) == {"id_proceso", "entrega"}
