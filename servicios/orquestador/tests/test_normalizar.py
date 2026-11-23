"""Normalizar cada entrega (T06; R3, R6 a R8)."""

import hashlib
from threading import Barrier, Lock, current_thread
from unittest.mock import Mock

import pytest
from normalizacion.almacen import AlmacenLocal

from fabrica import AVISO, P, RUTA, escribir, pdf, pdf_con_contrasena
from fabrica import Mundo as MundoBase
from orquestador import cola as c
from orquestador import estados, normalizar
from orquestador.clasificador import COLUMNAS, ClasificadorFalso
from orquestador.errores import procesar_uno, reenviar_errores
from orquestador.local import Corrida
from orquestador.normalizar import ruta_en_la_entrega
from orquestador.origen import ArchivoDistinto, ErrorOrigen, Esperado, Origen, revisar_bajado
from orquestador.parametros import Parametros
from orquestador.reloj import RelojManual


def _escribir(raiz, ruta, contenido):
    escribir(raiz, ruta, contenido)


class Mundo(MundoBase):
    def correr(self):
        return super().correr(self.normalizar)

    def clasificar(self):
        return self.sacar(c.CLASIFICAR)

    def documentos(self, entrega):
        return {r.id: r.datos for r in self.estado.listar(P, estados.DOCUMENTO) if r.datos["entrega"] == entrega}


class _OrigenEnMemoria(Origen):
    def __init__(self, archivos, durante_descarga):
        self.archivos = archivos
        self.durante_descarga = durante_descarga
        self.descargas = []
        self.activas = self.maximo = 0
        self.candado = Lock()

    def listar(self, carpeta):
        pytest.fail("El aviso ya trae los archivos")

    def bajar(self, archivo, destino, esperado=None):
        with self.candado:
            self.descargas.append((archivo, destino, esperado, current_thread()))
            self.activas += 1
            self.maximo = max(self.maximo, self.activas)
        try:
            self.durante_descarga(archivo)
            destino.write_bytes(self.archivos[archivo])
            revisar_bajado(destino, esperado)
        finally:
            with self.candado:
                self.activas -= 1


def _entrega_con_descargas(tmp_path, paralelo, durante_descarga=lambda _: None):
    archivos = {f"{RUTA}/OF-001/{letra}.pdf": pdf(1, letra) for letra in "abcdef"}
    origen = _OrigenEnMemoria(archivos, durante_descarga)
    csv = tmp_path / "clasificacion.csv"
    csv.write_text(",".join(COLUMNAS) + "\n", encoding="utf-8")
    corrida = Corrida(origen, AlmacenLocal(tmp_path / "salida"), ClasificadorFalso(csv),
                      reloj=RelojManual(), parametros=Parametros(paralelo_bajar=paralelo))
    corrida.publicar_aviso({**AVISO, "archivos": [
        {"ruta": ruta.removeprefix(f"{RUTA}/"), "id_oferente": "OF-001",
         "tamano": len(datos), "md5": hashlib.md5(datos).hexdigest()}
        for ruta, datos in archivos.items()
    ]})
    assert procesar_uno(corrida.cola, corrida.apertura).desenlace == "ok"
    return corrida, origen


@pytest.fixture
def mundo(tmp_path):
    carta = pdf(2, "Carta de presentación")
    _escribir(tmp_path, "PROCESO/CPC.pdf", pdf(3, "Condiciones del proceso"))
    _escribir(tmp_path, "OF-001/carta.pdf", carta)
    _escribir(tmp_path, "OF-001/copias/carta.pdf", carta)
    _escribir(tmp_path, "OF-001/clave.pdf", pdf_con_contrasena())
    _escribir(tmp_path, "OF-002/parafiscales/formulario3.pdf", pdf(1, "Parafiscales"))
    mundo = Mundo(tmp_path)
    mundo.abrir()
    return mundo


def test_ruta_en_la_entrega():
    assert ruta_en_la_entrega("OF-001/sub/carta.pdf", "OF-001") == "sub/carta.pdf"
    assert ruta_en_la_entrega("docs/carta.pdf", "OF-001") == "docs/carta.pdf"
    assert ruta_en_la_entrega("OF-001", "OF-001") == "OF-001"


def test_normaliza_cada_entrega_y_registra_sus_documentos(mundo):
    assert [r.desenlace for r in mundo.correr()] == ["ok"] * 3

    docs = mundo.documentos("OF-001")
    por_ruta = {d["ruta_origen"]: d for d in docs.values()}
    assert set(por_ruta) == {"carta.pdf", "copias/carta.pdf", "clave.pdf"}
    assert por_ruta["carta.pdf"]["estado"] == estados.NORMALIZADO
    assert por_ruta["carta.pdf"]["paginas"] == 2
    assert por_ruta["carta.pdf"]["pdf"].startswith("file://")
    assert por_ruta["copias/carta.pdf"]["estado"] == estados.DUPLICADO
    assert por_ruta["clave.pdf"]["estado"] == estados.ERROR_ENTRADA
    assert por_ruta["clave.pdf"]["error"]["codigo"] == "CONTRASENA"
    assert all(d["historial"][0]["motivo"] == "normalización" for d in docs.values())

    oferente = mundo.estado.leer(P, estados.OFERENTE, "OF-001").datos
    assert (oferente["estado"], oferente["documentos"]) == (estados.PROCESANDO, 3)
    assert oferente["manifiesto"].endswith(f"{P}/OF-001/manifiesto.json")
    assert (mundo.salida / P / "OF-001" / "manifiesto.json").exists()


def test_documento_del_proceso_sin_oferente(mundo):
    mundo.correr()
    [cpc] = mundo.documentos("PROCESO").values()
    assert (cpc["ruta_origen"], cpc["estado"]) == ("CPC.pdf", estados.NORMALIZADO)


def test_tarea_para_el_documento_con_error(mundo):
    mundo.correr()
    [tarea] = mundo.estado.listar(P, estados.TAREA)
    clave = next(i for i, d in mundo.documentos("OF-001").items() if d["estado"] == estados.ERROR_ENTRADA)
    assert tarea.id == f"documento_con_error-{clave}"
    assert {k: tarea.datos[k] for k in ("estado", "clase", "motivo", "id_documento", "entrega")} == {
        "estado": estados.ABIERTA, "clase": "documento_con_error", "motivo": "CONTRASENA",
        "id_documento": clave, "entrega": "OF-001"}
    assert "contraseña" in tarea.datos["detalle"]


def test_solo_se_clasifican_los_normalizados(mundo):
    mundo.correr()
    mensajes = mundo.clasificar()
    normalizados = sorted(i for e in ("PROCESO", "OF-001", "OF-002") for i, d in mundo.documentos(e).items()
                          if d["estado"] == estados.NORMALIZADO)
    assert sorted(m["id_documento"] for m in mensajes) == normalizados
    assert len(normalizados) == 3
    assert all(set(m) == {"id_proceso", "entrega", "id_documento"} for m in mensajes)


def test_no_guarda_copia_de_los_originales(mundo):
    mundo.correr()
    guardados = [p.relative_to(mundo.salida).as_posix() for p in mundo.salida.rglob("*") if p.is_file()]
    assert guardados, "algo se produjo"
    assert all("/pdf/" in g or "/lectura/" in g or "/palabras/" in g or g.endswith("manifiesto.json")
               for g in guardados), guardados
    assert not any(g.endswith(("carta.pdf", "clave.pdf", "CPC.pdf")) for g in guardados)


def test_mensaje_repetido_no_duplica_nada(mundo):
    mundo.correr()
    antes = {(r.tipo, r.id): r.version for r in mundo.estado.listar(P)}
    mensajes = len(mundo.clasificar())
    mundo.cola.publicar(c.NORMALIZAR, {"id_proceso": P, "entrega": "OF-001"})
    assert [r.desenlace for r in mundo.correr()] == ["ok"]
    assert {(r.tipo, r.id): r.version for r in mundo.estado.listar(P)} == antes
    assert mundo.clasificar() == []
    assert mensajes == 3


def test_caida_antes_de_terminar_se_repite_sin_duplicar(mundo, monkeypatch):
    # El trabajador se cae justo antes de pasar la entrega a procesando.
    original = estados.cambiar
    caidas = {"n": 0}

    def cambiar_y_caer(*args, **kwargs):
        if caidas["n"] == 0 and args[3] == estados.OFERENTE:
            caidas["n"] += 1
            raise RuntimeError("se cayó")
        return original(*args, **kwargs)

    monkeypatch.setattr(estados, "cambiar", cambiar_y_caer)
    primera = mundo.correr()
    assert [r.desenlace for r in primera].count("a_errores") == 1
    monkeypatch.setattr(estados, "cambiar", original)
    assert reenviar_errores(mundo.cola, c.NORMALIZAR) == 1
    assert [r.desenlace for r in mundo.correr()] == ["ok"]
    assert all(mundo.estado.leer(P, estados.OFERENTE, e).datos["estado"] == estados.PROCESANDO
               for e in ("PROCESO", "OF-001", "OF-002"))
    assert len(mundo.estado.listar(P, estados.TAREA)) == 1
    # Los clasificar de la entrega que se repitió salen dos veces; T07 los absorbe.
    ids = [m["id_documento"] for m in mundo.clasificar()]
    assert len(set(ids)) == 3


def test_falla_de_la_normalizacion_deja_la_entrega_en_error_y_no_frena_a_las_demas(mundo, monkeypatch):
    from normalizacion.entrega import ErrorEntrega

    import orquestador.normalizar as modulo
    original = modulo.normalizar_entrega

    def fallar_en_of002(carpeta, id_proceso, id_oferente, almacen, **kwargs):
        if id_oferente == "OF-002":
            raise ErrorEntrega(["OF-002-abc"])
        return original(carpeta, id_proceso, id_oferente, almacen, **kwargs)

    monkeypatch.setattr(modulo, "normalizar_entrega", fallar_en_of002)
    desenlaces = [r.desenlace for r in mundo.correr()]
    assert sorted(desenlaces) == ["a_errores", "ok", "ok"]
    of2 = mundo.estado.leer(P, estados.OFERENTE, "OF-002").datos
    assert of2["estado"] == estados.ERROR_PROCESO
    assert of2["error"].startswith("Bug: ErrorEntrega")
    assert of2["error_desde"] == mundo.reloj.ahora().isoformat()
    assert mundo.estado.leer(P, estados.OFERENTE, "OF-001").datos["estado"] == estados.PROCESANDO
    assert e_consultar_en_curso(mundo, "OF-002") == 1

    # Corregida la causa, operación reenvía y la entrega sale de error.
    monkeypatch.setattr(modulo, "normalizar_entrega", original)
    reenviar_errores(mundo.cola, c.NORMALIZAR)
    assert [r.desenlace for r in mundo.correr()] == ["ok"]
    of2 = mundo.estado.leer(P, estados.OFERENTE, "OF-002").datos
    assert (of2["estado"], of2["error"]) == (estados.PROCESANDO, None)


def e_consultar_en_curso(mundo, entrega):
    return estados.consultar(mundo.estado, P)["entregas"][entrega]["en_curso"]


def test_archivo_que_falta_en_el_origen_es_transitorio(mundo, tmp_path):
    (tmp_path / "datalake" / RUTA / "OF-002/parafiscales/formulario3.pdf").unlink()
    desenlaces = [r.desenlace for r in mundo.correr()]
    assert desenlaces.count("reintento") == 1
    assert mundo.estado.leer(P, estados.OFERENTE, "OF-002").datos["estado"] == estados.RECIBIDO


def test_baja_varios_archivos_a_la_vez_hasta_el_limite(tmp_path):
    paralelo = 3
    barrera = Barrier(paralelo, timeout=5)
    corrida, origen = _entrega_con_descargas(tmp_path, paralelo, lambda _: barrera.wait())

    assert procesar_uno(corrida.cola, corrida.normalizar).desenlace == "ok"
    assert origen.maximo == paralelo
    assert len({destino.parent for _, destino, _, _ in origen.descargas}) == 1
    assert {ruta: esperado for ruta, _, esperado, _ in origen.descargas} == {
        ruta: Esperado(tamano=len(datos), md5=hashlib.md5(datos).hexdigest())
        for ruta, datos in origen.archivos.items()
    }
    assert len(corrida.estado.listar(P, estados.DOCUMENTO)) == len(origen.archivos)


def test_falla_en_paralelo_corta_las_descargas_y_reintenta_la_entrega(tmp_path, monkeypatch):
    barrera = Barrier(2, timeout=5)

    def fallar(archivo):
        if archivo.endswith("/b.pdf"):
            barrera.wait()
            raise ErrorOrigen("No se encontró el archivo")
        if archivo.endswith("/c.pdf"):
            barrera.wait()
            raise ArchivoDistinto("El archivo bajado no coincide")

    corrida, origen = _entrega_con_descargas(tmp_path, 2, fallar)
    normalizar_entrega = Mock(wraps=normalizar.normalizar_entrega)
    monkeypatch.setattr(normalizar, "normalizar_entrega", normalizar_entrega)

    resultado = procesar_uno(corrida.cola, corrida.normalizar)
    assert resultado.desenlace == "reintento"
    assert resultado.motivo.startswith("ErrorTransitorio en normalizar.py:")
    assert sorted(ruta for ruta, _, _, _ in origen.descargas) == list(origen.archivos)[:3]
    assert origen.activas == 0
    assert all(not hilo.is_alive() and not destino.parent.exists() for _, destino, _, hilo in origen.descargas)
    normalizar_entrega.assert_not_called()
    assert corrida.estado.listar(P, estados.DOCUMENTO) == []
    assert corrida.estado.leer(P, estados.OFERENTE, "OF-001").datos["estado"] == estados.RECIBIDO
    assert corrida.cola.pendientes(c.CLASIFICAR) == 0

    origen.durante_descarga = lambda _: None
    corrida.reloj.adelantar(corrida.parametros.demora_base_s)
    assert procesar_uno(corrida.cola, corrida.normalizar).desenlace == "ok"
    normalizar_entrega.assert_called_once()
    assert len(corrida.estado.listar(P, estados.DOCUMENTO)) == len(origen.archivos)


def test_baja_en_serie_con_un_hilo(tmp_path):
    corrida, origen = _entrega_con_descargas(tmp_path, 1)

    assert procesar_uno(corrida.cola, corrida.normalizar).desenlace == "ok"
    assert origen.maximo == 1
    assert [ruta for ruta, _, _, _ in origen.descargas] == list(origen.archivos)
    assert all(hilo is current_thread() for _, _, _, hilo in origen.descargas)
    documentos = corrida.estado.listar(P, estados.DOCUMENTO)
    assert sorted(d.datos["ruta_origen"] for d in documentos) == [f"{letra}.pdf" for letra in "abcdef"]
    assert all(d.datos["estado"] == estados.NORMALIZADO for d in documentos)


def test_conserva_el_orden_si_dos_rutas_tienen_el_mismo_destino(tmp_path):
    escribir(tmp_path, "OF-001/carta.pdf", pdf(1, "Primera carta"))
    escribir(tmp_path, "carta.pdf", pdf(2, "Segunda carta"))
    mundo = Mundo(tmp_path)
    mundo.abrir({**AVISO, "archivos": [
        {"ruta": ruta, "id_oferente": "OF-001"} for ruta in ("OF-001/carta.pdf", "carta.pdf")
    ]})

    assert [r.desenlace for r in mundo.correr()] == ["ok"]
    [carta] = mundo.documentos("OF-001").values()
    assert (carta["ruta_origen"], carta["paginas"]) == ("carta.pdf", 2)


@pytest.mark.parametrize("esperado", [
    {"tamano": 0, "md5": "0" * 32},
    {"tamano": 0},
    {"md5": "0" * 32},
], ids=["ambos", "tamano", "md5"])
def test_archivo_distinto_se_reintenta_y_luego_va_a_errores(tmp_path, esperado):
    ruta = "OF-001/carta.pdf"
    escribir(tmp_path, ruta, pdf(1, "Carta"))
    mundo = Mundo(tmp_path)
    mundo.abrir({**AVISO, "archivos": [{"ruta": ruta, "id_oferente": "OF-001", **esperado}]})

    for demora in (120, 240, 480):
        assert [r.desenlace for r in mundo.correr()] == ["reintento"]
        assert mundo.estado.leer(P, estados.OFERENTE, "OF-001").datos["estado"] == estados.RECIBIDO
        mundo.reloj.adelantar(demora)

    assert [r.desenlace for r in mundo.correr()] == ["a_errores"]
    [error] = mundo.cola.errores(c.NORMALIZAR)
    assert error.mensaje.propiedades["intento"] == 4
    assert mundo.estado.leer(P, estados.OFERENTE, "OF-001").datos["estado"] == estados.ERROR_PROCESO
    assert mundo.documentos("OF-001") == {}
    assert mundo.estado.listar(P, estados.TAREA) == []
    assert mundo.clasificar() == []


@pytest.mark.parametrize("version", ["0.1", "0.2"])
def test_aviso_sin_los_campos_nuevos_se_normaliza(tmp_path, version):
    ruta = "OF-001/carta.pdf"
    escribir(tmp_path, ruta, pdf(1, "Carta"))
    mundo = Mundo(tmp_path)
    mundo.abrir({**AVISO, "contrato": f"modulo5-orquestador/{version}",
                 "archivos": [{"ruta": ruta, "id_oferente": "OF-001"}]})

    assert "id_proyecto" not in mundo.estado.leer(P, estados.PROCESO, P).datos
    assert "esperados" not in mundo.estado.leer(P, estados.OFERENTE, "OF-001").datos
    assert [r.desenlace for r in mundo.correr()] == ["ok"]
    [documento] = mundo.documentos("OF-001").values()
    assert documento["estado"] == estados.NORMALIZADO


def test_normaliza_entrega_con_solo_un_comprimido_anunciado(tmp_path):
    ruta = "OF-001/roto.zip"
    escribir(tmp_path, ruta, b"comprimido ilegible")
    mundo = Mundo(tmp_path)
    mundo.abrir({**AVISO, "comprimidos_sin_contenido": [{"ruta": ruta, "id_oferente": "OF-001"}]})

    assert [r.desenlace for r in mundo.correr()] == ["ok"]
    oferente = mundo.estado.leer(P, estados.OFERENTE, "OF-001").datos
    assert (oferente["archivos"], oferente["documentos"], oferente["estado"]) == ([], 0, estados.PROCESANDO)
    [tarea] = mundo.estado.listar(P, estados.TAREA)
    assert (tarea.datos["entrega"], tarea.datos["motivo"]) == ("OF-001", "COMPRIMIDO_SIN_CONTENIDO")


def test_version_distinta_del_normalizador_no_normaliza(mundo):
    proceso = mundo.estado.leer(P, estados.PROCESO, P)
    datos = dict(proceso.datos)
    datos["versiones"] = {**datos["versiones"], "normalizador": "0.0.1"}
    mundo.estado.reemplazar(proceso, datos)
    desenlaces = [r.desenlace for r in mundo.correr()]
    assert desenlaces == ["a_errores"] * 3
    [primero, *_] = mundo.cola.errores(c.NORMALIZAR)
    assert primero.motivo.startswith("Bug: VersionNoCoincide")
    assert mundo.documentos("OF-001") == {}
