"""De punta a punta: un proceso inventado desde el aviso hasta las solicitudes de
extracción (criterio A2), cada mensaje entregado dos veces (A3) y el comando
`orquestar`. T10."""

import json
import shutil
import threading
import time

import pytest
from normalizacion.almacen import AlmacenLocal

from fabrica import AVISO, P, RUTA, escribir, pdf, pdf_con_contrasena
from orquestador import cli, contratos, estados
from orquestador import cola as c
from orquestador.clasificador import ClasificadorFalso
from orquestador.errores import ErrorTransitorio
from orquestador.local import Corrida, conteos
from orquestador.origen import OrigenLocal
from orquestador.parametros import Parametros
from orquestador.reloj import RelojManual
from orquestador.resolucion import Asignacion, resolver_clasificacion

CSV = """id_oferente,ruta_origen,pagina_inicio,pagina_fin,tipo_documental,confianza,subtipo
,CPC.pdf,,,TD-01,0.97,
OF-001,carta.pdf,,,TD-03,0.97,
OF-001,mixto.pdf,1,1,TD-03,0.97,
OF-001,mixto.pdf,2,2,TD-16,0.80,
OF-002,rut.pdf,,,TD-07,0.96,
OF-002,borroso.pdf,,,TD-24,0.60,
OF-002,foto.pdf,,,TD-99,0.99,
"""


def _proceso(raiz):
    """Documentos del proceso y dos oferentes, con una copia, un documento con
    contraseña, una clasificación dudosa, una de baja confianza y un TD-99."""
    carta = pdf(1, "carta")
    escribir(raiz, "PROCESO/CPC.pdf", pdf(1, "CPC"))
    escribir(raiz, "OF-001/carta.pdf", carta)
    escribir(raiz, "OF-001/copia de carta.pdf", carta)
    escribir(raiz, "OF-001/clave.pdf", pdf_con_contrasena())
    escribir(raiz, "OF-001/mixto.pdf", pdf(2, "mixto"))
    escribir(raiz, "OF-002/rut.pdf", pdf(1, "rut"))
    escribir(raiz, "OF-002/borroso.pdf", pdf(1, "borroso"))
    escribir(raiz, "OF-002/foto.pdf", pdf(1, "foto"))
    (raiz / "clasificacion.csv").write_text(CSV, encoding="utf-8")


def _corrida(raiz, cola=None, paralelo=2, clasificador=None):
    reloj = RelojManual()
    return Corrida(
        origen=OrigenLocal(raiz / "datalake"),
        almacen=AlmacenLocal(raiz / "salida"),
        clasificador=clasificador or ClasificadorFalso(raiz / "clasificacion.csv"),
        reloj=reloj,
        cola=cola(reloj) if cola else None,
        parametros=Parametros(paralelo_normalizar=paralelo),
    )


@pytest.fixture
def corrida(tmp_path):
    _proceso(tmp_path)
    corrida = _corrida(tmp_path)
    corrida.publicar_aviso(AVISO)
    corrida.correr()
    return corrida


# --- A2: punta a punta ---


def test_llega_del_aviso_a_las_solicitudes(corrida):
    assert conteos(corrida, P) == {
        "entregas": {"procesando": 3},
        "documentos": {"clasificado": 6, "duplicado": 1, "error_entrada": 1},
        "segmentos": {"esperando_clasificacion_humana": 1, "pendiente": 5, "sin_extraccion": 1},
        "solicitudes_por_td": {"TD-01": 1, "TD-03": 2, "TD-07": 1, "TD-16": 1},
        "tareas_abiertas_por_clase": {"clasificacion": 1, "documento_con_error": 1},
        "tareas_abiertas_por_motivo": {"CONFIANZA_BAJA": 1, "CONTRASENA": 1},
        "atascados": 0,
        "mensajes_en_errores": {},
        "mensajes_pendientes": {},
    }


def test_cada_solicitud_cumple_el_contrato_0_2(corrida):
    for solicitud in corrida.solicitudes:
        contratos.validar(contratos.EXTRACCION_ENTRADA, solicitud)
    por_td = {s["tipo_documental"]: s for s in corrida.solicitudes}
    assert por_td["TD-01"]["id_oferente"] is None
    assert [s["tipo_documental"] for s in corrida.solicitudes if s["clasificacion_dudosa"]] == ["TD-16"]
    assert len({s["id_segmento"] for s in corrida.solicitudes}) == len(corrida.solicitudes)


def test_la_tarea_de_baja_confianza_se_resuelve_y_sigue_a_extraccion(corrida):
    [tarea] = [t for t in corrida.estado.listar(P, estados.TAREA) if t.datos["clase"] == "clasificacion"]
    resolver_clasificacion(corrida.estado, corrida.reloj, corrida.extraer, P, tarea.id,
                           [Asignacion(1, 1, "TD-25")], "evaluadora.juridica")
    corrida.correr()
    assert corrida.solicitudes[-1]["tipo_documental"] == "TD-25"
    assert conteos(corrida, P)["segmentos"] == {"pendiente": 6, "sin_extraccion": 1}


def test_un_clasificador_caido_se_reintenta_sin_esperar(tmp_path):
    _proceso(tmp_path)

    class CaeDosVeces:
        def __init__(self):
            self.real, self.caidas = ClasificadorFalso(tmp_path / "clasificacion.csv"), 0

        def clasificar(self, solicitud):
            if self.caidas < 2:
                self.caidas += 1
                raise ErrorTransitorio("caído")
            return self.real.clasificar(solicitud)

    corrida = _corrida(tmp_path, clasificador=CaeDosVeces())
    corrida.publicar_aviso(AVISO)
    corrida.correr()
    assert len(corrida.solicitudes) == 5
    assert conteos(corrida, P)["mensajes_en_errores"] == {}
    assert corrida.reloj.ahora() > RelojManual().ahora()


def test_normaliza_como_maximo_dos_entregas_a_la_vez(tmp_path):
    class Lento:
        cola = c.NORMALIZAR

        def __init__(self):
            self.a_la_vez = self.maximo = self.hechos = 0
            self.candado = threading.Lock()

        def procesar(self, cuerpo):
            with self.candado:
                self.a_la_vez += 1
                self.maximo = max(self.maximo, self.a_la_vez)
            time.sleep(0.05)
            with self.candado:
                self.a_la_vez -= 1
                self.hechos += 1

        def al_fallar(self, cuerpo, motivo):
            pass

    (tmp_path / "clasificacion.csv").write_text(CSV, encoding="utf-8")
    corrida = _corrida(tmp_path)
    corrida.normalizar = lento = Lento()
    for n in range(5):
        corrida.cola.publicar(c.NORMALIZAR, {"id_proceso": P, "entrega": f"OF-{n:03d}"})
    corrida.correr()
    assert (lento.maximo, lento.hechos) == (2, 5)


# --- A3: cada mensaje entregado dos veces ---


class ColaQueRepite(c.ColaEnMemoria):
    """Publica dos veces cada aviso y cada pedido de trabajo, como puede pasar en
    Service Bus (entrega al menos una vez)."""

    def publicar(self, cola, cuerpo, demora_s=0, propiedades=None):
        if cola != c.EXTRAER:
            super().publicar(cola, cuerpo, demora_s, propiedades)
        return super().publicar(cola, cuerpo, demora_s, propiedades)


def _foto(corrida, raiz):
    """El estado y las solicitudes, sin la carpeta de la corrida."""
    ruta = raiz / "estado.json"
    corrida.estado.guardar(ruta)
    estado = ruta.read_text(encoding="utf-8").replace((raiz / "salida").resolve().as_uri(), "SALIDA")
    solicitudes = sorted(json.dumps(s, sort_keys=True).replace((raiz / "salida").resolve().as_uri(), "SALIDA")
                         for s in corrida.solicitudes)
    return estado, solicitudes


def test_mensajes_repetidos_dan_el_mismo_estado_y_las_mismas_solicitudes(tmp_path):
    fotos = []
    _proceso(tmp_path / "una")
    # Los mismos archivos en las dos corridas: un PDF hecho de nuevo cambia de huella.
    shutil.copytree(tmp_path / "una", tmp_path / "dos")
    for nombre, cola in (("una", None), ("dos", ColaQueRepite)):
        raiz = tmp_path / nombre
        # Una entrega a la vez: así la comparación no depende del orden de los hilos.
        corrida = _corrida(raiz, cola=cola, paralelo=1)
        corrida.publicar_aviso(AVISO)
        corrida.correr()
        fotos.append(_foto(corrida, raiz))
    (estado_una, solicitudes_una), (estado_dos, solicitudes_dos) = fotos
    assert len(solicitudes_una) == 5
    assert solicitudes_dos == solicitudes_una
    assert estado_dos == estado_una


def test_mensajes_repetidos_con_dos_entregas_a_la_vez(tmp_path):
    """Las dos copias de un `normalizar` pueden correr a la vez sobre la misma
    entrega. El historial puede quedar en otro orden; los conteos y las
    solicitudes, no."""
    _proceso(tmp_path / "una")
    shutil.copytree(tmp_path / "una", tmp_path / "dos")
    resultados = []
    for nombre, cola, paralelo in (("una", None, 1), ("dos", ColaQueRepite, 2)):
        corrida = _corrida(tmp_path / nombre, cola=cola, paralelo=paralelo)
        corrida.publicar_aviso(AVISO)
        corrida.correr()
        resultados.append((conteos(corrida, P), _foto(corrida, tmp_path / nombre)[1]))
    assert resultados[1] == resultados[0]


def test_un_trabajador_que_se_cae_antes_de_completar(tmp_path):
    """Cada mensaje se procesa y se abandona una vez (el trabajador se cayó antes
    de completarlo), así que se entrega de nuevo: mismo resultado."""
    _proceso(tmp_path)

    class ColaQueSeCae(c.ColaEnMemoria):
        def completar(self, mensaje):
            if mensaje.cola != c.EXTRAER and mensaje.entregas == 1:
                return self.abandonar(mensaje)
            return super().completar(mensaje)

    corrida = _corrida(tmp_path, cola=ColaQueSeCae, paralelo=1)
    corrida.publicar_aviso(AVISO)
    corrida.correr()
    assert len(corrida.solicitudes) == 5
    assert conteos(corrida, P)["documentos"] == {"clasificado": 6, "duplicado": 1, "error_entrada": 1}


# --- Comando orquestar ---


def _comando(tmp_path, salida):
    _proceso(tmp_path)
    return cli.main(["--origen", str(tmp_path / "datalake" / RUTA), "--proceso", P,
                     "--clasificacion", str(tmp_path / "clasificacion.csv"), "--salida", str(salida)])


def test_el_comando_imprime_solo_conteos(tmp_path, capsys):
    assert _comando(tmp_path, tmp_path / "salida") == 0
    salida = capsys.readouterr()
    resumen = json.loads(salida.out)
    assert resumen["solicitudes_por_td"] == {"TD-01": 1, "TD-03": 2, "TD-07": 1, "TD-16": 1}
    assert resumen["tiempo_s"] >= 0
    for nombre in ("carta", "mixto", "borroso", "CPC", "datalake"):
        assert nombre not in salida.out + salida.err
    for archivo in ("estado.json", "solicitudes-extraccion.jsonl", "errores.json", "conteos.json"):
        assert (tmp_path / "salida" / archivo).is_file()
    assert len((tmp_path / "salida" / "solicitudes-extraccion.jsonl").read_text().splitlines()) == 5


def test_el_comando_no_escribe_dentro_de_un_repositorio(tmp_path, capsys):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    assert _comando(tmp_path, tmp_path / "repo" / "salida") == 2
    assert "fuera de cualquier repositorio" in capsys.readouterr().err
    assert not (tmp_path / "repo" / "salida").exists()
