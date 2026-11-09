"""Documentos inventados, normalizados de verdad, y solicitudes como las del orquestador.

Nada de documentos reales (principio 6): los PDF se fabrican aquí. Se pasan por
`normalizar_entrega` para que la lectura sea la que produce la normalización.
"""

import io
import json
from pathlib import Path

from normalizacion.almacen import CARPETA_ALMACEN, AlmacenLocal
from normalizacion.entrega import normalizar_entrega
import pikepdf
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PROCESO = "SR0000000001"


def pdf(paginas: int, texto: str = "Documento inventado") -> bytes:
    salida = io.BytesIO()
    lienzo = canvas.Canvas(salida)
    for n in range(paginas):
        lienzo.drawString(72, 720, f"{texto}, página {n + 1}. Documento inventado para pruebas.")
        lienzo.showPage()
    lienzo.save()
    return salida.getvalue()


ANCHO, ALTO = letter
PARRAFO = (
    "El suscrito representante legal certifica que la sociedad OFERENTE INVENTADO S.A.S. "
    "se encuentra al día en el pago de aportes al sistema de seguridad social."
)


def _escaneo() -> Image.Image:
    """Una "hoja escaneada": fondo de papel con renglones dibujados, sin texto."""
    imagen = Image.new("RGB", (850, 1100), "#f2efe6")
    dibujo = ImageDraw.Draw(imagen)
    for y in range(150, 950, 40):
        dibujo.line((100, y, 750 - (y * 7) % 200, y), fill="#555555", width=6)
    return imagen


def _parrafo(lienzo: canvas.Canvas, y: float = 700, render: int = 0) -> None:
    texto = lienzo.beginText(72, y)
    texto.setFont("Helvetica", 11)
    texto.setTextRenderMode(render)
    texto.textLine(PARRAFO[:90])
    texto.textLine(PARRAFO[90:])
    lienzo.drawText(texto)


def _firma(lienzo: canvas.Canvas) -> None:
    lienzo.drawString(72, 200, "________________________________")
    lienzo.drawString(72, 186, "Firma del representante legal")


def pdf_mixto() -> bytes:
    """Seis páginas, una de cada caso:

    1. texto sin anclas; 2. texto con línea de firma; 3. escaneo sin texto;
    4. escaneo con la capa de texto del escáner y una línea de firma;
    5. en blanco; 6. texto con línea de firma, girada 90 grados.
    """
    salida = io.BytesIO()
    lienzo = canvas.Canvas(salida, pagesize=letter, invariant=1)
    _parrafo(lienzo)
    lienzo.showPage()
    _parrafo(lienzo)
    _firma(lienzo)
    lienzo.showPage()
    lienzo.drawImage(ImageReader(_escaneo()), 0, 0, width=ANCHO, height=ALTO)
    lienzo.showPage()
    lienzo.drawImage(ImageReader(_escaneo()), 0, 0, width=ANCHO, height=ALTO)
    _parrafo(lienzo, render=3)
    texto = lienzo.beginText(72, 200)
    texto.setTextRenderMode(3)
    texto.textLine("________________________________")
    lienzo.drawText(texto)
    texto = lienzo.beginText(72, 186)
    texto.setTextRenderMode(3)
    texto.textLine("Firma del representante legal")
    lienzo.drawText(texto)
    lienzo.showPage()
    lienzo.showPage()
    _parrafo(lienzo)
    _firma(lienzo)
    lienzo.showPage()
    lienzo.save()
    girado = io.BytesIO()
    with pikepdf.open(io.BytesIO(salida.getvalue())) as documento:
        documento.pages[5].obj.Rotate = 90
        documento.save(girado, deterministic_id=True)
    return girado.getvalue()


def xlsx(filas: int = 3, texto: str = "Contrato") -> bytes:
    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Experiencia"
    hoja.append(["Consecutivo", "Contratante", "Valor", None])
    for n in range(1, filas + 1):
        hoja.append([n, f"{texto} {n}", n * 1000.0, None])
    hoja.append([None, None, None])
    otra = libro.create_sheet("Totales")
    otra["A1"] = "Total"
    otra["B1"] = "=SUM(Experiencia!C2:C4)"
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


class Corrida:
    """Una corrida local: `<raiz>/almacen/` con las entregas normalizadas."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz
        self.almacen = AlmacenLocal(raiz / CARPETA_ALMACEN)

    def normalizar(self, archivos: dict[str, bytes], id_oferente: str | None = "OF-001") -> list[dict]:
        """Normaliza una entrega con esos archivos y devuelve las entradas normalizadas del manifiesto."""
        carpeta = self.raiz / "entregas" / (id_oferente or "PROCESO")
        for nombre, contenido in archivos.items():
            (carpeta / nombre).parent.mkdir(parents=True, exist_ok=True)
            (carpeta / nombre).write_bytes(contenido)
        manifiesto = normalizar_entrega(carpeta, PROCESO, id_oferente, self.almacen).manifiesto
        return [a for a in manifiesto["archivos"] if a["estado"] == "normalizado"]

    def lectura(self, documento: dict) -> dict:
        return json.loads(self.almacen.leer(documento["lectura"]))

    def solicitud(self, documento: dict, desde: int, hasta: int, tipo_documental: str = "TD-16", **extra) -> dict:
        """La solicitud que armaría el orquestador (`orquestador.extraer.solicitud`) para un segmento.

        Como el orquestador, toma la huella del PDF de la lectura.
        """
        return solicitud(documento, self.lectura(documento)["hash_pdf"], desde, hasta, tipo_documental, **extra)


def solicitud(documento: dict, hash_pdf: str, desde: int, hasta: int, tipo_documental: str = "TD-16", **extra) -> dict:
    id_documento = documento["id_documento"]
    entrega = id_documento.split("-")[0] if id_documento.startswith("PROCESO") else "-".join(id_documento.split("-")[:2])
    base = {
        "contrato": "modulo3-extraccion/0.2",
        "id_proceso": PROCESO,
        "id_oferente": None if entrega == "PROCESO" else entrega,
        "id_segmento": f"{id_documento}-p{desde}-{hasta}",
        "id_documento": id_documento,
        "archivo": {"uri": documento["pdf"], "sha256": hash_pdf},
        "paginas": {"desde": desde, "hasta": hasta},
        "tipo_documental": tipo_documental,
        "lectura": documento["lectura"],
        "anexos": [documento["anexo_nativo"]] if documento["anexo_nativo"] else [],
        "clasificacion_dudosa": False,
        "version_modelo": 21,
        "confianza_clasificacion": 0.97,
    }
    base.update(extra)
    return base
