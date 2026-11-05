"""Conversión a PDF de Word, hojas de cálculo e imágenes (R7 a R10).

- Word y hojas de cálculo: LibreOffice sin interfaz, con un perfil temporal propio
  por conversión y las macros bloqueadas. Tiempo máximo y un reintento.
- Imágenes: img2pdf, una página por imagen o por cuadro del TIFF, sin volver a
  comprimir. Antes se valida con Pillow que la imagen abre.
- Hojas de cálculo: además del PDF, se conserva el original como anexo (R9). A un
  `xlsx` se le quitan antes los vínculos a otros libros, solo en la copia que va a
  LibreOffice (T16).

El original nunca se modifica (R10): todo se hace sobre copias en carpetas
temporales. El PDF que sale se deja sin fechas ni identificadores aleatorios,
para que convertir dos veces el mismo archivo dé los mismos bytes (R25).
"""

import io
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import img2pdf
import pikepdf
from PIL import Image

from .errores import CONTRASENA, CONVERSION_FALLIDA, DANADO, NO_SOPORTADO, ErrorDocumento, error_documento
from .parametros import PARAMETROS
from .tipos import HOJAS_DE_CALCULO, IMAGEN, NO_SOPORTADO as TIPO_NO_SOPORTADO, PDF, WORD, XLSX, TipoReal

registro = logging.getLogger(__name__)

# Perfil de LibreOffice: seguridad de macros "muy alta" (3) y ejecución de macros
# desactivada del todo. Se escribe en cada perfil temporal antes de convertir.
CONFIGURACION_SEGURA = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
</oor:items>
"""


class ErrorConversion(Exception):
    """LibreOffice falló, se pasó del tiempo o no dejó un PDF que abra."""


@dataclass(frozen=True)
class Conversion:
    datos: bytes | None
    """El PDF convertido. None si hubo error."""
    anexo: bytes | None
    """El original, solo en las hojas de cálculo (R9)."""
    error: ErrorDocumento | None

    @property
    def ok(self) -> bool:
        return self.error is None


def _con_error(codigo: str) -> Conversion:
    return Conversion(datos=None, anexo=None, error=error_documento(codigo))


def convertir(
    ruta: Path,
    tipo: TipoReal,
    *,
    soffice: str | None = None,
    tiempo_max_s: float | None = None,
    reintentos: int | None = None,
) -> Conversion:
    """Convierte un archivo que no es PDF. Un problema del documento queda en `error`."""
    if tipo.tipo_origen == PDF:
        raise ValueError("Un PDF no se convierte: se revisa con revision_pdf.")
    if tipo.cifrado:
        return _con_error(CONTRASENA)
    if tipo.tipo_origen == TIPO_NO_SOPORTADO:
        return _con_error(NO_SOPORTADO)
    original = Path(ruta).read_bytes()
    if tipo.tipo_origen == IMAGEN:
        return _convertir_imagen(original)
    if tipo.tipo_origen in WORD | HOJAS_DE_CALCULO:
        para_convertir = sin_vinculos_externos(original) if tipo.tipo_origen == XLSX else original
        try:
            datos = convertir_con_libreoffice(
                para_convertir,
                tipo.tipo_origen,
                soffice=soffice,
                tiempo_max_s=PARAMETROS.tiempo_max_conversion_s if tiempo_max_s is None else tiempo_max_s,
                reintentos=PARAMETROS.reintentos_conversion if reintentos is None else reintentos,
            )
        except ErrorConversion:
            return _con_error(CONVERSION_FALLIDA)
        anexo = original if tipo.tipo_origen in HOJAS_DE_CALCULO else None
        return Conversion(datos=datos, anexo=anexo, error=None)
    raise ValueError(f"Tipo sin conversión: {tipo.tipo_origen}")


# ---------------------------------------------------------------------------
# PDF reproducible


def pdf_reproducible(datos: bytes) -> bytes:
    """Quita lo que cambia en cada conversión: fechas, metadatos XMP, la suma de
    control de LibreOffice y el identificador del archivo, que se vuelve a
    calcular a partir del contenido."""
    with pikepdf.open(io.BytesIO(datos)) as pdf:
        for clave in ("/CreationDate", "/ModDate"):
            if clave in pdf.docinfo:
                del pdf.docinfo[clave]
        if "/Metadata" in pdf.Root:
            del pdf.Root.Metadata
        for clave in ("/DocChecksum", "/ID"):
            if clave in pdf.trailer:
                del pdf.trailer[clave]
        salida = io.BytesIO()
        pdf.save(salida, deterministic_id=True)
    return salida.getvalue()


# ---------------------------------------------------------------------------
# Vínculos a otros libros (T16)

_PARTE_VINCULO = re.compile(r"xl/externalLinks/(_rels/)?externalLink\d+\.xml(\.rels)?$")
_REFERENCIAS = re.compile(
    rb"<(\w+:)?externalReferences\b[^>]*/>|<(\w+:)?externalReferences\b.*?</(\w+:)?externalReferences>", re.S
)
_ENTRADAS = re.compile(rb"<(Relationship|Override)\b[^>]*externalLink[^>]*/>")


def sin_vinculos_externos(datos: bytes) -> bytes:
    """Copia del `xlsx` sin vínculos a otros libros.

    Hay Excel armados copiando hojas de otros archivos que arrastran cientos de
    vínculos, y LibreOffice tarda en procesarlos: uno real, con 201, tardaba 64 s
    en convertirse y sin ellos 1,9 s, con el mismo PDF. El PDF no cambia porque
    cada fórmula guarda su último valor, y eso es lo que se imprime.

    Devuelve los mismos bytes si el archivo no tiene vínculos o no es un ZIP que se
    pueda leer (de ese caso se encarga LibreOffice).
    """
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as entrada:
            partes = entrada.infolist()
            if not any(_PARTE_VINCULO.match(parte.filename) for parte in partes):
                return datos
            salida = io.BytesIO()
            with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as copia:
                for parte in partes:
                    if _PARTE_VINCULO.match(parte.filename):
                        continue
                    contenido = entrada.read(parte.filename)
                    if parte.filename == "xl/workbook.xml":
                        contenido = _REFERENCIAS.sub(b"", contenido)
                    elif parte.filename in ("xl/_rels/workbook.xml.rels", "[Content_Types].xml"):
                        contenido = _ENTRADAS.sub(b"", contenido)
                    copia.writestr(parte, contenido)
            return salida.getvalue()
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        return datos


# ---------------------------------------------------------------------------
# LibreOffice


def _preparar_perfil(carpeta: Path) -> str:
    usuario = carpeta / "user"
    usuario.mkdir(parents=True)
    (usuario / "registrymodifications.xcu").write_text(CONFIGURACION_SEGURA, encoding="utf-8")
    return carpeta.as_uri()


def _correr(argumentos: list[str], tiempo_max_s: float) -> None:
    """Corre LibreOffice en su propio grupo de procesos, para matarlo entero si se
    pasa del tiempo (soffice lanza otros procesos)."""
    proceso = subprocess.Popen(
        argumentos,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        codigo = proceso.wait(timeout=tiempo_max_s)
    except subprocess.TimeoutExpired:
        os.killpg(proceso.pid, signal.SIGKILL)
        proceso.wait()
        raise ErrorConversion("LibreOffice se pasó del tiempo máximo.") from None
    if codigo != 0:
        raise ErrorConversion(f"LibreOffice terminó con código {codigo}.")


def _un_intento(original: bytes, extension: str, soffice: str, tiempo_max_s: float) -> bytes:
    with tempfile.TemporaryDirectory(prefix="normalizacion-") as temporal:
        temporal = Path(temporal)
        # Nombre fijo: el nombre del oferente no aparece en la lista de procesos.
        entrada = temporal / f"entrada.{extension}"
        entrada.write_bytes(original)
        salida = temporal / "salida"
        salida.mkdir()
        perfil = _preparar_perfil(temporal / "perfil")
        _correr(
            [
                soffice,
                f"-env:UserInstallation={perfil}",
                "--headless",
                "--norestore",
                "--nolockcheck",
                "--convert-to",
                "pdf",
                "--outdir",
                str(salida),
                str(entrada),
            ],
            tiempo_max_s,
        )
        convertido = salida / "entrada.pdf"
        if not convertido.is_file():
            raise ErrorConversion("LibreOffice no dejó el PDF.")
        try:
            return pdf_reproducible(convertido.read_bytes())
        except pikepdf.PdfError:
            raise ErrorConversion("LibreOffice dejó un PDF que no abre.") from None


def convertir_con_libreoffice(
    original: bytes,
    extension: str,
    *,
    soffice: str | None = None,
    tiempo_max_s: float,
    reintentos: int,
) -> bytes:
    """PDF del documento. Lanza ErrorConversion si fallan todos los intentos."""
    soffice = soffice or shutil.which("soffice")
    if soffice is None:
        # Falta LibreOffice en la imagen: es un bug de despliegue, no del documento.
        raise RuntimeError("No se encontró LibreOffice (soffice).")
    for intento in range(reintentos + 1):
        try:
            return _un_intento(original, extension, soffice, tiempo_max_s)
        except ErrorConversion as error:
            registro.info("Conversión con LibreOffice fallida (intento %d): %s", intento + 1, error)
    raise ErrorConversion("La conversión falló en todos los intentos.")


# ---------------------------------------------------------------------------
# Imágenes


def _cuadros(original: bytes) -> list[bytes]:
    """Las imágenes que van a img2pdf. Valida con Pillow que abren.

    img2pdf no acepta transparencia: esas imágenes se aplanan sobre blanco y se
    guardan como PNG, sin pérdida. Las demás pasan tal cual, sin recomprimir.
    """
    with Image.open(io.BytesIO(original)) as imagen:
        cuadros = getattr(imagen, "n_frames", 1)
        transparente = any(_tiene_transparencia(imagen, n) for n in range(cuadros))
        if not transparente:
            for numero in range(cuadros):
                imagen.seek(numero)
                imagen.load()
            return [original]
        aplanados = []
        for numero in range(cuadros):
            imagen.seek(numero)
            fondo = Image.new("RGB", imagen.size, "white")
            rgba = imagen.convert("RGBA")
            fondo.paste(rgba, mask=rgba.getchannel("A"))
            salida = io.BytesIO()
            fondo.save(salida, format="PNG")
            aplanados.append(salida.getvalue())
        return aplanados


def _tiene_transparencia(imagen: Image.Image, cuadro: int) -> bool:
    imagen.seek(cuadro)
    return imagen.mode in ("RGBA", "LA", "PA") or (imagen.mode == "P" and "transparency" in imagen.info)


def _convertir_imagen(original: bytes) -> Conversion:
    try:
        cuadros = _cuadros(original)
    except Exception as error:  # noqa: BLE001
        # Pillow lanza excepciones de muchos tipos con una imagen corrupta
        # (OSError, TypeError, SyntaxError, EOFError…). Todas son del documento.
        registro.info("Imagen que no abre: %s", type(error).__name__)
        return Conversion(datos=None, anexo=None, error=error_documento(DANADO))
    try:
        datos = img2pdf.convert(cuadros, rotation=img2pdf.Rotation.ifvalid, nodate=True)
    except (img2pdf.ImageOpenError, img2pdf.PdfTooLargeError, ValueError, OSError) as error:
        registro.info("Conversión de imagen fallida: %s", type(error).__name__)
        return _con_error(CONVERSION_FALLIDA)
    return Conversion(datos=pdf_reproducible(datos), anexo=None, error=None)
