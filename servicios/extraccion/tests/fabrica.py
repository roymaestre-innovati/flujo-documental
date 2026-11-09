"""Documentos inventados, normalizados de verdad, y solicitudes como las del orquestador.

Nada de documentos reales (principio 6): los PDF se fabrican aquí. Se pasan por
`normalizar_entrega` para que la lectura sea la que produce la normalización.
"""

import io
import json
from pathlib import Path

from normalizacion.almacen import CARPETA_ALMACEN, AlmacenLocal
from normalizacion.entrega import normalizar_entrega
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
