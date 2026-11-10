"""Qué ve el LLM de cada página del segmento (R31 a R34, R36).

Se decide con la lectura de la normalización, sin volver a leer el texto del PDF.
El PDF solo se abre para dibujar las imágenes que hacen falta:

| Tipo de página    | Texto                     | Imagen de la página     | Firma ampliada          |
|-------------------|---------------------------|-------------------------|-------------------------|
| `texto`           | Sí                        | Solo si tiene anclas    | Una por `linea_firma`   |
| `escaneo_con_ocr` | Sí, marcado como escáner  | Sí, `detail: original`  | Una por `linea_firma`   |
| `imagen`          | No                        | Sí, `detail: original`  | No (no tiene anclas)    |
| `vacia`           | No                        | No                      | No                      |

Las páginas escaneadas llevan imagen siempre, también en documentos largos: sin
ella no hay nada que leer (aceptado por el usuario el 2026-11-09, para estudio
posterior). Los números (dpi, márgenes, topes) son parámetros con versión.
"""

import io
import threading
from dataclasses import dataclass, field

import pypdfium2
from PIL import Image

from .entrada import Entrada
from .parametros import parametros

TEXTO = "texto"
ESCANEO_CON_OCR = "escaneo_con_ocr"
IMAGEN = "imagen"
VACIA = "vacia"
LINEA_FIRMA = "linea_firma"

PDFIUM = threading.Lock()
"""pdfium no admite dos hilos a la vez en el mismo proceso: todo lo que lo toca pasa por aquí."""

DETALLE_ALTO = "high"
DETALLE_ORIGINAL = "original"


@dataclass(frozen=True)
class Imagen:
    jpeg: bytes
    detalle: str
    ancho: int
    alto: int


@dataclass(frozen=True)
class Pagina:
    numero: int
    """Número sobre el documento completo."""
    tipo: str
    texto: str | None
    """El texto que se le manda, o None si no se le manda texto."""
    texto_de_escaner: bool
    """El texto es la capa del escáner: puede estar incompleto."""
    imagen: Imagen | None
    firmas: tuple[Imagen, ...]


@dataclass(frozen=True)
class Anexo:
    numero: int
    """Posición del anexo en la solicitud, desde 1."""
    texto: str | None
    """Los valores de cada hoja, o None si no se pudo leer."""
    recortado: bool


@dataclass(frozen=True)
class Contenido:
    paginas: tuple[Pagina, ...]
    anexos: tuple[Anexo, ...]
    alertas: tuple[dict, ...] = field(default=())

    def lectura(self) -> dict:
        """El campo `lectura` de la salida: qué se le mandó al LLM de cada página (R36)."""
        return {
            "paginas_con_texto": [p.numero for p in self.paginas if p.texto],
            "paginas_solo_imagen": [p.numero for p in self.paginas if p.imagen and not p.texto],
            "ampliaciones_firma": [p.numero for p in self.paginas if p.firmas],
        }


def _jpeg(imagen: Image.Image, detalle: str) -> Imagen:
    salida = io.BytesIO()
    imagen.convert("RGB").save(salida, format="JPEG", quality=parametros()["pagina"]["calidad_jpeg"])
    return Imagen(jpeg=salida.getvalue(), detalle=detalle, ancho=imagen.width, alto=imagen.height)


def _dibujado(pagina: pypdfium2.PdfPage, **opciones) -> Image.Image:
    """La página dibujada, copiada fuera de pdfium. El bitmap se cierra aquí, no al recolectar basura."""
    bitmap = pagina.render(**opciones)
    try:
        return bitmap.to_pil().copy()
    finally:
        bitmap.close()


def _dibujar_pagina(pagina: pypdfium2.PdfPage, detalle: str) -> Imagen:
    escala = parametros()["pagina"]["dpi"] / 72
    # pdfium aplica la rotación de la página: la imagen sale como se ve.
    return _jpeg(_dibujado(pagina, scale=escala), detalle)


def zona_de_firma(caja: list[float], ancho: float, alto: float) -> tuple[float, float, float, float]:
    """La zona que se amplía alrededor de un ancla de firma (D20).

    La caja del ancla (puntos, origen arriba a la izquierda, página sin rotar) se
    agranda hacia arriba, para tomar el trazo que cruza la línea, y a los lados.
    Queda dentro de la página.
    """
    p = parametros()["firma"]
    x0, y0, x1, y1 = caja
    return (
        max(0.0, x0 - p["margen_lateral_pt"]),
        max(0.0, y0 - p["renglones_arriba"] * p["alto_renglon_pt"]),
        min(ancho, x1 + p["margen_lateral_pt"]),
        min(alto, y1 + p["renglones_abajo"] * p["alto_renglon_pt"]),
    )


def _dibujar_firma(pagina: pypdfium2.PdfPage, caja: list[float]) -> Imagen:
    rotacion = pagina.get_rotation()
    # Las cajas de la lectura son de la página sin rotar: se dibuja sin rotar y
    # después se gira la imagen, para que la firma se lea derecha.
    pagina.set_rotation(0)
    try:
        ancho, alto = pagina.get_size()
        x0, y0, x1, y1 = zona_de_firma(caja, ancho, alto)
        recorte = (x0, alto - y1, ancho - x1, y0)  # lo que se corta: izquierda, abajo, derecha, arriba
        imagen = _dibujado(pagina, scale=parametros()["firma"]["dpi"] / 72, crop=recorte)
    finally:
        pagina.set_rotation(rotacion)
    if rotacion:
        imagen = imagen.rotate(-rotacion, expand=True)
    return _jpeg(imagen, DETALLE_ALTO)


def _pagina(lectura: dict, pdf: pypdfium2.PdfDocument) -> Pagina:
    numero, tipo = lectura["pagina"], lectura["tipo"]
    if tipo == VACIA:
        return Pagina(numero, tipo, texto=None, texto_de_escaner=False, imagen=None, firmas=())
    pagina = pdf[numero - 1]
    try:
        anclas = lectura["anclas"]
        texto = lectura["texto"] or None if tipo in (TEXTO, ESCANEO_CON_OCR) else None
        if tipo == TEXTO:
            imagen = _dibujar_pagina(pagina, DETALLE_ALTO) if anclas else None
        else:
            imagen = _dibujar_pagina(pagina, DETALLE_ORIGINAL)
        firmas = tuple(_dibujar_firma(pagina, a["caja"]) for a in anclas if a["tipo"] == LINEA_FIRMA)
    finally:
        pagina.close()
    return Pagina(numero, tipo, texto=texto, texto_de_escaner=tipo == ESCANEO_CON_OCR, imagen=imagen, firmas=firmas)


def _texto_de_celda(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).replace("\t", " ").replace("\n", " ").strip()


def valores_de_hoja(datos: bytes) -> str:
    """Los valores guardados de cada hoja, una fila por renglón y separados por tabuladores.

    No ejecuta fórmulas: lee el último valor que guardó Excel. Solo xlsx y xlsm.
    """
    from openpyxl import load_workbook

    libro = load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
    try:
        partes = []
        for hoja in libro.worksheets:
            filas = []
            for fila in hoja.iter_rows(values_only=True):
                celdas = [_texto_de_celda(v) for v in fila]
                while celdas and not celdas[-1]:
                    celdas.pop()
                if celdas:
                    filas.append("\t".join(celdas))
            partes.append(f"Hoja: {hoja.title}\n" + "\n".join(filas))
        return "\n\n".join(partes)
    finally:
        libro.close()


def _anexo(numero: int, datos: bytes) -> tuple[Anexo, list[dict]]:
    tope = parametros()["anexo"]["max_caracteres"]
    try:
        texto = valores_de_hoja(datos)
    except Exception:  # xls, ods o un archivo dañado: el PDF del documento sigue estando
        alerta = {"codigo": "ANEXO_NO_LEIDO", "id_tecnico": None,
                  "mensaje": f"No se pudieron leer los valores de la hoja de cálculo original (anexo {numero}); se usa solo su versión en PDF."}
        return Anexo(numero, texto=None, recortado=False), [alerta]
    if len(texto) <= tope:
        return Anexo(numero, texto=texto, recortado=False), []
    alerta = {"codigo": "ANEXO_RECORTADO", "id_tecnico": None,
              "mensaje": f"La hoja de cálculo original (anexo {numero}) es muy grande: se mandaron sus primeros {tope} caracteres."}
    return Anexo(numero, texto=texto[:tope], recortado=True), [alerta]


def preparar_contenido(entrada: Entrada) -> Contenido:
    """Las páginas del segmento y los anexos, listos para armar el mensaje."""
    with PDFIUM:
        pdf = pypdfium2.PdfDocument(entrada.pdf)
        try:
            paginas = tuple(_pagina(p, pdf) for p in entrada.paginas())
        finally:
            pdf.close()
    anexos, alertas = [], []
    for numero, datos in enumerate(entrada.anexos, start=1):
        anexo, avisos = _anexo(numero, datos)
        anexos.append(anexo)
        alertas.extend(avisos)
    return Contenido(paginas=paginas, anexos=tuple(anexos), alertas=tuple(alertas))
