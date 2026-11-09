"""Documentos inventados y un mundo local completo para las pruebas.

Nada de documentos reales (principio 6): los PDF se fabrican aquí.
"""

import io

import pikepdf
from normalizacion.almacen import AlmacenLocal
from reportlab.pdfgen import canvas

from orquestador import cola as c
from orquestador.apertura import Apertura
from orquestador.errores import procesar_uno
from orquestador.estado import EstadoEnMemoria
from orquestador.normalizar import Normalizar
from orquestador.origen import OrigenLocal
from orquestador.reloj import RelojManual

P = "SR0000000001"
RUTA = "procesos/SR0000000001"
AVISO = {"contrato": "modulo5-orquestador/0.1", "id_proceso": P, "ruta": RUTA, "fecha": "2026-11-06T09:00:00-05:00"}


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


def escribir(raiz, ruta, contenido):
    """Deja un archivo en el datalake de prueba, dentro de la carpeta del proceso."""
    archivo = raiz / "datalake" / RUTA / ruta
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_bytes(contenido)


class Mundo:
    """Cola, estado, origen y almacén locales, con la apertura y la normalización."""

    def __init__(self, raiz):
        self.raiz = raiz
        self.reloj = RelojManual()
        self.cola = c.ColaEnMemoria(self.reloj)
        self.estado = EstadoEnMemoria()
        self.origen = OrigenLocal(raiz / "datalake")
        self.salida = raiz / "salida"
        self.almacen = AlmacenLocal(self.salida)
        self.apertura = Apertura(self.cola, self.estado, self.origen, self.reloj)
        self.normalizar = Normalizar(self.cola, self.estado, self.origen, self.almacen, self.reloj)

    def abrir(self):
        self.cola.publicar(c.PROCESOS_LISTOS, AVISO)
        assert procesar_uno(self.cola, self.apertura).desenlace == "ok"

    def correr(self, manejador):
        resultados = []
        while (r := procesar_uno(self.cola, manejador)) is not None:
            resultados.append(r)
        return resultados

    def sacar(self, nombre_cola):
        mensajes = []
        while (m := self.cola.recibir(nombre_cola)) is not None:
            mensajes.append(m.cuerpo)
            self.cola.completar(m)
        return mensajes
