"""Tipo real de un archivo, por su contenido y no por la extensión (R6).

Sigue la tabla del plan: mira los primeros bytes y, en los ZIP y OLE, qué traen
adentro. Son pocas reglas y así no hace falta otra dependencia.
"""

import zipfile
from dataclasses import dataclass
from pathlib import Path

import olefile

PDF = "pdf"
DOC = "doc"
DOCX = "docx"
ODT = "odt"
XLS = "xls"
XLSX = "xlsx"
ODS = "ods"
IMAGEN = "imagen"
NO_SOPORTADO = "no_soportado"

TIPOS_ORIGEN = (PDF, DOC, DOCX, ODT, XLS, XLSX, ODS, IMAGEN, NO_SOPORTADO)
"""Los valores de `tipo_origen` del contrato."""

WORD = frozenset({DOC, DOCX, ODT})
HOJAS_DE_CALCULO = frozenset({XLS, XLSX, ODS})
"""Se convierten a PDF y además se conserva el original como anexo (R9)."""

MAGICO_PDF = b"%PDF-"
MAGICO_ZIP = b"PK\x03\x04"
MAGICO_OLE = bytes.fromhex("D0CF11E0A1B11AE1")
MAGICO_APPLEDOUBLE = bytes.fromhex("00051607")
"""Archivo `._*` de Mac. No es un tipo: el inventario lo descarta antes (R2)."""

_IMAGENES = (
    (bytes.fromhex("FFD8FF"), "jpeg"),
    (bytes.fromhex("89504E47"), "png"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
)

_MIMETYPES_ODF = {
    b"application/vnd.oasis.opendocument.text": ODT,
    b"application/vnd.oasis.opendocument.spreadsheet": ODS,
}

_LONGITUD_CABECERA = 8


@dataclass(frozen=True)
class TipoReal:
    tipo_origen: str
    """Uno de TIPOS_ORIGEN: el valor que va al manifiesto."""
    formato: str | None = None
    """En las imágenes: jpeg, png o tiff. None en los demás."""


def leer_cabecera(ruta: Path) -> bytes:
    with Path(ruta).open("rb") as archivo:
        return archivo.read(_LONGITUD_CABECERA)


def es_appledouble(ruta: Path) -> bool:
    return leer_cabecera(ruta).startswith(MAGICO_APPLEDOUBLE)


def detectar(ruta: Path) -> TipoReal:
    """Tipo real del archivo. Lo que no se reconoce es `no_soportado`, nunca un error."""
    cabecera = leer_cabecera(ruta)
    if cabecera.startswith(MAGICO_PDF):
        return TipoReal(PDF)
    for magico, formato in _IMAGENES:
        if cabecera.startswith(magico):
            return TipoReal(IMAGEN, formato)
    if cabecera.startswith(MAGICO_ZIP):
        return TipoReal(_tipo_zip(ruta))
    if cabecera.startswith(MAGICO_OLE):
        return TipoReal(_tipo_ole(ruta))
    return TipoReal(NO_SOPORTADO)


def _tipo_zip(ruta: Path) -> str:
    """DOCX, XLSX, ODT u ODS según lo que trae el ZIP. Un ZIP cualquiera no se soporta."""
    try:
        with zipfile.ZipFile(ruta) as zip_:
            nombres = set(zip_.namelist())
            if "mimetype" in nombres:
                tipo = _MIMETYPES_ODF.get(zip_.read("mimetype").strip())
                if tipo:
                    return tipo
    except (zipfile.BadZipFile, OSError, KeyError, ValueError, NotImplementedError):
        return NO_SOPORTADO
    # Se pide la pieza principal, no solo la carpeta, para no confundir un ZIP
    # que el oferente armó con una carpeta llamada word/ o xl/.
    if "[Content_Types].xml" in nombres:
        if "word/document.xml" in nombres:
            return DOCX
        if "xl/workbook.xml" in nombres:
            return XLSX
    return NO_SOPORTADO


def _tipo_ole(ruta: Path) -> str:
    """DOC o XLS según los flujos del archivo OLE. Los demás OLE no se soportan."""
    try:
        with olefile.OleFileIO(str(ruta)) as ole:
            if ole.exists("WordDocument"):
                return DOC
            if ole.exists("Workbook") or ole.exists("Book"):
                return XLS
    except (OSError, ValueError, IndexError, TypeError):
        pass
    return NO_SOPORTADO
