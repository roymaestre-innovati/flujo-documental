"""Fábrica de documentos sintéticos para las pruebas (plan, tabla "Pruebas").

Cada caso es una función que recibe una carpeta, fabrica ahí uno o más archivos y
devuelve sus rutas. Todo es ficticio: el proceso SR0000000001, el oferente
OFERENTE EJEMPLO LTDA y nombres de persona inventados. Ningún archivo de aquí se
sube al repositorio: se fabrican en una carpeta temporal en cada prueba.

`CASOS` reúne todos los casos por nombre, para que la prueba de punta a punta
(T11) arme con ellos una entrega completa.
"""

import datetime
import io
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pikepdf
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ANCHO, ALTO = letter

OFERENTE = "OFERENTE EJEMPLO LTDA"
PROCESO = "SR0000000001"
REPRESENTANTE = "MARTA LUCÍA PEREIRA GÓMEZ"
FIRMANTE_DIGITAL = "ANDRÉS FELIPE ROJAS MEJÍA"

CONTRASENA_USUARIO = "clave-de-apertura"
CONTRASENA_DUENO = "clave-del-dueno"

PARRAFO = (
    f"{OFERENTE} presenta su oferta para el proceso {PROCESO} y declara que conoce "
    "y acepta las condiciones del proceso de selección."
)

# Cabecera AppleDouble: número mágico, versión 2, 16 bytes de relleno y 0 entradas.
CABECERA_APPLEDOUBLE = bytes.fromhex("00051607") + bytes.fromhex("00020000") + bytes(16) + struct.pack(">H", 0)


def _guardar(ruta: Path, datos: bytes) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos)
    return ruta


# ---------------------------------------------------------------------------
# PDF base


def _lienzo() -> tuple[io.BytesIO, canvas.Canvas]:
    salida = io.BytesIO()
    # invariant=1: sin fecha ni identificador aleatorio, para que el mismo caso dé
    # siempre los mismos bytes.
    return salida, canvas.Canvas(salida, pagesize=letter, invariant=1)


def _escribir_parrafo(lienzo: canvas.Canvas, y: float = 700, render: int = 0) -> None:
    texto = lienzo.beginText(72, y)
    texto.setFont("Helvetica", 11)
    texto.setTextRenderMode(render)
    palabras, linea = PARRAFO.split(), ""
    for palabra in palabras:
        if len(linea) + len(palabra) > 80:
            texto.textLine(linea)
            linea = ""
        linea = f"{linea} {palabra}".strip()
    texto.textLine(linea)
    lienzo.drawText(texto)


def _imagen_escaneo(ancho: int = 850, alto: int = 1100, color: str = "#f2efe6") -> Image.Image:
    """Una "hoja escaneada": fondo de papel con renglones dibujados, sin texto."""
    imagen = Image.new("RGB", (ancho, alto), color)
    dibujo = ImageDraw.Draw(imagen)
    for y in range(150, alto - 150, 40):
        dibujo.line((100, y, ancho - 100 - (y * 7) % 200, y), fill="#555555", width=6)
    return imagen


def pdf_texto_bytes(paginas: int = 1) -> bytes:
    salida, lienzo = _lienzo()
    for numero in range(1, paginas + 1):
        lienzo.setFont("Helvetica-Bold", 14)
        lienzo.drawString(72, 740, f"CARTA DE PRESENTACIÓN DE LA OFERTA - página {numero}")
        _escribir_parrafo(lienzo)
        lienzo.showPage()
    lienzo.save()
    return salida.getvalue()


def _pdf_escaneo_bytes(con_texto: bool) -> bytes:
    salida, lienzo = _lienzo()
    lienzo.drawImage(ImageReader(_imagen_escaneo()), 0, 0, width=ANCHO, height=ALTO)
    if con_texto:
        # Modo de render 3: texto invisible, como la capa que pone el escáner.
        _escribir_parrafo(lienzo, render=3)
    lienzo.showPage()
    lienzo.save()
    return salida.getvalue()


# ---------------------------------------------------------------------------
# Casos de PDF


def pdf_texto(carpeta: Path) -> list[Path]:
    return [_guardar(carpeta / "carta_presentacion.pdf", pdf_texto_bytes())]


def pdf_escaneo_sin_texto(carpeta: Path) -> list[Path]:
    return [_guardar(carpeta / "certificado_escaneado.pdf", _pdf_escaneo_bytes(con_texto=False))]


def pdf_escaneo_con_ocr(carpeta: Path) -> list[Path]:
    return [_guardar(carpeta / "certificado_escaneado_ocr.pdf", _pdf_escaneo_bytes(con_texto=True))]


def pdf_vacio(carpeta: Path) -> list[Path]:
    salida, lienzo = _lienzo()
    lienzo.showPage()
    lienzo.save()
    return [_guardar(carpeta / "pagina_en_blanco.pdf", salida.getvalue())]


def _con_pikepdf(datos: bytes, cambio, **guardar) -> bytes:
    # Sin cifrado, el identificador sale del contenido y el resultado es siempre
    # igual. Con cifrado no se puede: cada fabricación da bytes distintos.
    if "encryption" not in guardar:
        guardar["deterministic_id"] = True
    with pikepdf.open(io.BytesIO(datos)) as pdf:
        cambio(pdf)
        salida = io.BytesIO()
        pdf.save(salida, **guardar)
    return salida.getvalue()


def pdf_rotado(carpeta: Path) -> list[Path]:
    def rotar(pdf):
        pdf.pages[0].obj.Rotate = 90

    return [_guardar(carpeta / "anexo_rotado.pdf", _con_pikepdf(pdf_texto_bytes(), rotar))]


def pdf_con_contrasena(carpeta: Path) -> list[Path]:
    cifrado = pikepdf.Encryption(user=CONTRASENA_USUARIO, owner=CONTRASENA_DUENO, R=6)
    datos = _con_pikepdf(pdf_texto_bytes(), lambda pdf: None, encryption=cifrado)
    return [_guardar(carpeta / "estados_financieros.pdf", datos)]


def pdf_solo_restricciones(carpeta: Path) -> list[Path]:
    permisos = pikepdf.Permissions(
        extract=False,
        accessibility=False,
        modify_annotation=False,
        modify_assembly=False,
        modify_form=False,
        modify_other=False,
        print_lowres=False,
        print_highres=False,
    )
    cifrado = pikepdf.Encryption(user="", owner=CONTRASENA_DUENO, allow=permisos, R=6)
    datos = _con_pikepdf(pdf_texto_bytes(), lambda pdf: None, encryption=cifrado)
    return [_guardar(carpeta / "certificado_restringido.pdf", datos)]


def pdf_danado_reparable(carpeta: Path) -> list[Path]:
    """PDF con la tabla de referencias (xref) apuntando mal: qpdf la reconstruye."""
    datos = pdf_texto_bytes()
    inicio = datos.rindex(b"startxref") + len(b"startxref")
    fin = datos.index(b"%%EOF", inicio)
    datos = datos[:inicio] + b"\n999999\n" + datos[fin:]
    return [_guardar(carpeta / "acta_danada_reparable.pdf", datos)]


def pdf_danado_irreparable(carpeta: Path) -> list[Path]:
    """Empieza como PDF pero después solo trae bytes sin estructura."""
    datos = b"%PDF-1.7\n" + bytes(range(256)) * 8
    return [_guardar(carpeta / "acta_danada_irreparable.pdf", datos)]


# ---------------------------------------------------------------------------
# Firma digital


def _firmante():
    """Certificado autofirmado, generado en la prueba, y su firmante de pyHanko."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from pyhanko.sign import signers

    clave = ec.generate_private_key(ec.SECP256R1())
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, FIRMANTE_DIGITAL)])
    desde = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(clave.public_key())
        .serial_number(1)
        .not_valid_before(desde)
        .not_valid_after(desde + datetime.timedelta(days=3650))
        .sign(clave, hashes.SHA256())
    )
    with tempfile.TemporaryDirectory() as temporal:
        ruta_clave = Path(temporal) / "clave.pem"
        ruta_certificado = Path(temporal) / "certificado.pem"
        ruta_clave.write_bytes(
            clave.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        ruta_certificado.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
        return signers.SimpleSigner.load(str(ruta_clave), str(ruta_certificado))


def pdf_firmado_bytes() -> bytes:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers

    escritor = IncrementalPdfFileWriter(io.BytesIO(pdf_texto_bytes()))
    metadatos = signers.PdfSignatureMetadata(field_name="Firma1")
    return signers.sign_pdf(escritor, metadatos, signer=_firmante()).getvalue()


def pdf_firmado(carpeta: Path) -> list[Path]:
    return [_guardar(carpeta / "certificacion_experiencia_firmada.pdf", pdf_firmado_bytes())]


def pdf_modificado_despues_de_firmar(carpeta: Path) -> list[Path]:
    """El firmado, más una actualización incremental que dibuja sobre la página."""
    from pyhanko.pdf_utils import generic
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

    escritor = IncrementalPdfFileWriter(io.BytesIO(pdf_firmado_bytes()))
    contenido = escritor.add_object(generic.StreamObject(stream_data=b"0 0 1 rg 72 72 200 50 re f"))
    escritor.add_stream_to_page(0, contenido)
    salida = io.BytesIO()
    escritor.write(salida)
    return [_guardar(carpeta / "certificacion_experiencia_modificada.pdf", salida.getvalue())]


# ---------------------------------------------------------------------------
# Word, Excel e imágenes


def docx_bytes() -> bytes:
    from docx import Document

    documento = Document()
    documento.add_heading("CARTA DE PRESENTACIÓN DE LA OFERTA", level=1)
    documento.add_paragraph(PARRAFO)
    documento.add_paragraph("Firma del representante legal: ____________________")
    documento.add_paragraph(REPRESENTANTE)
    salida = io.BytesIO()
    documento.save(salida)
    return salida.getvalue()


def docx(carpeta: Path) -> list[Path]:
    return [_guardar(carpeta / "carta_presentacion.docx", docx_bytes())]


def convertir_con_libreoffice(origen: Path, formato: str, destino: Path) -> Path:
    """Convierte con LibreOffice, con un perfil temporal propio. Solo para fabricar."""
    soffice = shutil.which("soffice")
    if soffice is None:
        raise RuntimeError("Hace falta LibreOffice (soffice) para fabricar este caso.")
    with tempfile.TemporaryDirectory() as perfil, tempfile.TemporaryDirectory() as salida:
        subprocess.run(
            [
                soffice,
                f"-env:UserInstallation={Path(perfil).as_uri()}",
                "--headless",
                "--norestore",
                "--convert-to",
                formato,
                "--outdir",
                salida,
                str(origen),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        convertido = next(Path(salida).iterdir())
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(convertido, destino)
    return destino


def _desde_docx(carpeta: Path, formato: str, nombre: str) -> list[Path]:
    with tempfile.TemporaryDirectory() as temporal:
        origen = _guardar(Path(temporal) / "carta_presentacion.docx", docx_bytes())
        return [convertir_con_libreoffice(origen, formato, carpeta / nombre)]


def odt(carpeta: Path) -> list[Path]:
    """Necesita LibreOffice."""
    return _desde_docx(carpeta, "odt", "carta_presentacion.odt")


def doc(carpeta: Path) -> list[Path]:
    """Necesita LibreOffice."""
    return _desde_docx(carpeta, "doc:MS Word 97", "carta_presentacion.doc")


def xlsx_ancho(carpeta: Path) -> list[Path]:
    """Hoja de cálculo con 40 columnas: al pasarla a PDF se corta en varias páginas."""
    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Experiencia"
    hoja.append([f"Columna {n}" for n in range(1, 41)])
    for fila in range(1, 31):
        hoja.append([f"{OFERENTE} {fila}-{n}" if n == 1 else fila * n for n in range(1, 41)])
    salida = io.BytesIO()
    libro.save(salida)
    return [_guardar(carpeta / "experiencia.xlsx", salida.getvalue())]


def _imagen_bytes(formato: str, **opciones) -> bytes:
    salida = io.BytesIO()
    _imagen_escaneo(425, 550).save(salida, format=formato, **opciones)
    return salida.getvalue()


def jpg(carpeta: Path) -> list[Path]:
    return [_guardar(carpeta / "cedula_representante.jpg", _imagen_bytes("JPEG", quality=85))]


def png(carpeta: Path) -> list[Path]:
    return [_guardar(carpeta / "rut.png", _imagen_bytes("PNG"))]


def tiff_tres_paginas(carpeta: Path) -> list[Path]:
    hojas = [_imagen_escaneo(425, 550, color) for color in ("#ffffff", "#eeeeee", "#dddddd")]
    salida = io.BytesIO()
    hojas[0].save(salida, format="TIFF", save_all=True, append_images=hojas[1:], compression="tiff_deflate")
    return [_guardar(carpeta / "poliza_escaneada.tiff", salida.getvalue())]


# ---------------------------------------------------------------------------
# Archivos de sistema, tipos falsos y no soportados


def archivos_de_sistema(carpeta: Path) -> list[Path]:
    """Los que hay que descartar: por nombre (R2) y, en los ._*, también por contenido."""
    appledouble = CABECERA_APPLEDOUBLE + bytes(64)
    return [
        _guardar(carpeta / ".DS_Store", b"\x00\x00\x00\x01Bud1" + bytes(64)),
        _guardar(carpeta / "imagenes" / "Thumbs.db", bytes.fromhex("D0CF11E0A1B11AE1") + bytes(504)),
        _guardar(carpeta / "__MACOSX" / "._carta_presentacion.pdf", appledouble),
        _guardar(carpeta / "__MACOSX" / "anexos" / "._experiencia.xlsx", appledouble),
        _guardar(carpeta / "._carta_presentacion.pdf", appledouble),
    ]


def appledouble_sin_prefijo(carpeta: Path) -> list[Path]:
    """Un AppleDouble con nombre normal: solo se reconoce por el contenido (R2, R6)."""
    return [_guardar(carpeta / "anexo_tecnico.pdf", CABECERA_APPLEDOUBLE + bytes(64))]


def extension_falsa(carpeta: Path) -> list[Path]:
    """Un DOCX renombrado a .pdf: el tipo real sale del contenido (R6)."""
    return [_guardar(carpeta / "propuesta_tecnica.pdf", docx_bytes())]


def no_soportados(carpeta: Path) -> list[Path]:
    comprimido = io.BytesIO()
    with zipfile.ZipFile(comprimido, "w") as zip_:
        zip_.writestr("notas.txt", "Notas del oferente.")
    return [
        _guardar(carpeta / "notas.txt", "Notas del oferente.\n".encode("utf-8")),
        _guardar(carpeta / "soportes.zip", comprimido.getvalue()),
    ]


def duplicados(carpeta: Path) -> list[Path]:
    """El mismo PDF en dos carpetas: el original es el primero por orden de ruta (R4)."""
    datos = pdf_texto_bytes(paginas=2)
    return [
        _guardar(carpeta / "anexos" / "certificado_bancario.pdf", datos),
        _guardar(carpeta / "copias" / "certificado_bancario.pdf", datos),
    ]


# ---------------------------------------------------------------------------
# Anclas


def pdf_anclas(carpeta: Path) -> list[Path]:
    """Línea de firma con rótulo, casillas y tablas SI/NO (con y sin tilde)."""
    salida, lienzo = _lienzo()
    lienzo.setFont("Helvetica-Bold", 14)
    lienzo.drawString(72, 740, "FORMULARIO DE DECLARACIONES DEL OFERENTE")
    lienzo.setFont("Helvetica", 11)

    # Tabla SI/NO con casillas de 10 puntos y celdas.
    preguntas = [
        ("¿Acepta las condiciones del proceso?", ("SI", "NO")),
        ("¿Tiene inhabilidades o incompatibilidades?", ("Sí", "No")),
    ]
    y = 660
    lienzo.drawString(380, y + 24, "SI")
    lienzo.drawString(430, y + 24, "NO")
    for pregunta, (si, no) in preguntas:
        lienzo.rect(66, y - 6, 420, 20)
        lienzo.drawString(72, y, pregunta)
        lienzo.drawString(360, y, si)
        lienzo.rect(380, y - 1, 10, 10)
        lienzo.drawString(410, y, no)
        lienzo.rect(430, y - 1, 10, 10)
        y -= 30

    # Línea de firma: guiones bajos, una línea dibujada y su rótulo.
    lienzo.drawString(72, 200, "________________________________")
    lienzo.line(330, 200, 530, 200)
    lienzo.drawString(72, 186, "Firma del representante legal")
    lienzo.drawString(330, 186, "Firma del revisor fiscal")
    lienzo.drawString(72, 172, REPRESENTANTE)
    lienzo.showPage()
    lienzo.save()
    return [_guardar(carpeta / "formulario_declaraciones.pdf", salida.getvalue())]


# ---------------------------------------------------------------------------

CASOS = {
    "pdf_texto": pdf_texto,
    "pdf_escaneo_sin_texto": pdf_escaneo_sin_texto,
    "pdf_escaneo_con_ocr": pdf_escaneo_con_ocr,
    "pdf_vacio": pdf_vacio,
    "pdf_rotado": pdf_rotado,
    "pdf_con_contrasena": pdf_con_contrasena,
    "pdf_solo_restricciones": pdf_solo_restricciones,
    "pdf_danado_reparable": pdf_danado_reparable,
    "pdf_danado_irreparable": pdf_danado_irreparable,
    "pdf_firmado": pdf_firmado,
    "pdf_modificado_despues_de_firmar": pdf_modificado_despues_de_firmar,
    "docx": docx,
    "odt": odt,
    "doc": doc,
    "xlsx_ancho": xlsx_ancho,
    "jpg": jpg,
    "png": png,
    "tiff_tres_paginas": tiff_tres_paginas,
    "archivos_de_sistema": archivos_de_sistema,
    "appledouble_sin_prefijo": appledouble_sin_prefijo,
    "extension_falsa": extension_falsa,
    "no_soportados": no_soportados,
    "duplicados": duplicados,
    "pdf_anclas": pdf_anclas,
}

CASOS_CON_LIBREOFFICE = {"odt", "doc"}
