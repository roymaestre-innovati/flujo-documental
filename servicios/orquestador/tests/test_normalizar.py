"""Normalizar cada entrega (T06; R3, R6 a R8)."""

import io

import pikepdf
import pytest
from normalizacion.almacen import AlmacenLocal
from reportlab.pdfgen import canvas

from orquestador import cola as c
from orquestador import estados
from orquestador.apertura import Apertura
from orquestador.errores import procesar_uno, reenviar_errores
from orquestador.estado import EstadoEnMemoria
from orquestador.normalizar import Normalizar, ruta_en_la_entrega
from orquestador.origen import OrigenLocal
from orquestador.reloj import RelojManual

P = "SR0000000001"
RUTA = "procesos/SR0000000001"


def pdf(paginas: int, texto: str) -> bytes:
    salida = io.BytesIO()
    lienzo = canvas.Canvas(salida)
    for n in range(paginas):
        lienzo.drawString(72, 720, f"{texto}, página {n + 1}. Documento inventado para pruebas.")
        lienzo.showPage()
    lienzo.save()
    return salida.getvalue()


def pdf_con_contrasena() -> bytes:
    salida = io.BytesIO()
    with pikepdf.open(io.BytesIO(pdf(1, "secreto"))) as documento:
        documento.save(salida, encryption=pikepdf.Encryption(user="clave", owner="clave"))
    return salida.getvalue()


def _escribir(raiz, ruta, contenido):
    archivo = raiz / "datalake" / RUTA / ruta
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_bytes(contenido)


class Mundo:
    def __init__(self, raiz):
        self.reloj = RelojManual()
        self.cola = c.ColaEnMemoria(self.reloj)
        self.estado = EstadoEnMemoria()
        self.origen = OrigenLocal(raiz / "datalake")
        self.almacen = AlmacenLocal(raiz / "salida")
        self.salida = raiz / "salida"
        self.apertura = Apertura(self.cola, self.estado, self.origen, self.reloj)
        self.normalizar = Normalizar(self.cola, self.estado, self.origen, self.almacen, self.reloj)

    def abrir(self):
        self.cola.publicar(c.PROCESOS_LISTOS, {"contrato": "modulo5-orquestador/0.1", "id_proceso": P, "ruta": RUTA,
                                                "fecha": "2026-11-06T09:00:00-05:00"})
        assert procesar_uno(self.cola, self.apertura).desenlace == "ok"

    def correr(self):
        resultados = []
        while (r := procesar_uno(self.cola, self.normalizar)) is not None:
            resultados.append(r)
        return resultados

    def clasificar(self):
        mensajes = []
        while (m := self.cola.recibir(c.CLASIFICAR)) is not None:
            mensajes.append(m.cuerpo)
            self.cola.completar(m)
        return mensajes

    def documentos(self, entrega):
        return {r.id: r.datos for r in self.estado.listar(P, estados.DOCUMENTO) if r.datos["entrega"] == entrega}


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
