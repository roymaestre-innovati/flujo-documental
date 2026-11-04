"""Tipo real de un archivo, por su contenido y no por la extensión (R6).

Sigue la tabla del plan: mira los primeros bytes y, en los ZIP y OLE, qué traen
adentro. Son pocas reglas y así no hace falta otra dependencia.
"""

import struct
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
    cifrado: bool = False
    """Word o Excel protegido con contraseña: el documento queda con error CONTRASENA.

    Un DOCX o XLSX cifrado es un OLE con un flujo `EncryptedPackage`, y no se
    sabe si era Word o Excel: queda `no_soportado` con `cifrado` en True. Los DOC,
    XLS, ODT y ODS cifrados conservan su tipo. Los PDF no se marcan aquí: su
    contraseña la revisa `revision_pdf`.
    """


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
        return _tipo_zip(ruta)
    if cabecera.startswith(MAGICO_OLE):
        return _tipo_ole(ruta)
    return TipoReal(NO_SOPORTADO)


def _tipo_zip(ruta: Path) -> TipoReal:
    """DOCX, XLSX, ODT u ODS según lo que trae el ZIP. Un ZIP cualquiera no se soporta."""
    try:
        with zipfile.ZipFile(ruta) as zip_:
            nombres = set(zip_.namelist())
            if "mimetype" in nombres:
                tipo = _MIMETYPES_ODF.get(zip_.read("mimetype").strip())
                if tipo:
                    return TipoReal(tipo, cifrado=_odf_cifrado(zip_, nombres))
    except (zipfile.BadZipFile, OSError, KeyError, ValueError, NotImplementedError):
        return TipoReal(NO_SOPORTADO)
    # Se pide la pieza principal, no solo la carpeta, para no confundir un ZIP
    # que el oferente armó con una carpeta llamada word/ o xl/.
    if "[Content_Types].xml" in nombres:
        if "word/document.xml" in nombres:
            return TipoReal(DOCX)
        if "xl/workbook.xml" in nombres:
            return TipoReal(XLSX)
    return TipoReal(NO_SOPORTADO)


def _odf_cifrado(zip_: zipfile.ZipFile, nombres: set[str]) -> bool:
    """Un ODT u ODS con contraseña declara sus datos de cifrado en el manifiesto."""
    if "META-INF/manifest.xml" not in nombres:
        return False
    return b"encryption-data" in zip_.read("META-INF/manifest.xml")


# Registro FILEPASS de Excel 97: va justo después del BOF cuando el libro está cifrado.
_XLS_BOF = 0x0809
_XLS_FILEPASS = 0x002F
# Bit fEncrypted en las banderas del encabezado (FIB) del flujo WordDocument.
_DOC_FENCRYPTED = 0x0100


def _tipo_ole(ruta: Path) -> TipoReal:
    """DOC o XLS según los flujos del archivo OLE. Los demás OLE no se soportan."""
    try:
        with olefile.OleFileIO(str(ruta)) as ole:
            if ole.exists("EncryptedPackage"):
                return TipoReal(NO_SOPORTADO, cifrado=True)
            if ole.exists("WordDocument"):
                return TipoReal(DOC, cifrado=_doc_cifrado(ole))
            for flujo in ("Workbook", "Book"):
                if ole.exists(flujo):
                    return TipoReal(XLS, cifrado=_xls_cifrado(ole, flujo))
    except (OSError, ValueError, IndexError, TypeError, struct.error):
        pass
    return TipoReal(NO_SOPORTADO)


def _doc_cifrado(ole: olefile.OleFileIO) -> bool:
    encabezado = ole.openstream("WordDocument").read(12)
    if len(encabezado) < 12:
        return False
    (banderas,) = struct.unpack_from("<H", encabezado, 10)
    return bool(banderas & _DOC_FENCRYPTED)


def _xls_cifrado(ole: olefile.OleFileIO, flujo: str) -> bool:
    datos = ole.openstream(flujo).read(4096)
    if len(datos) < 4:
        return False
    tipo, largo = struct.unpack_from("<HH", datos, 0)
    if tipo != _XLS_BOF or len(datos) < 4 + largo + 2:
        return False
    (siguiente,) = struct.unpack_from("<H", datos, 4 + largo)
    return siguiente == _XLS_FILEPASS
