"""Revisión de un PDF: si abre, si pide contraseña, si trae restricciones y cuántas
páginas tiene (R11 a R13 y R16).

Se usa con el PDF del oferente y con el PDF que sale de una conversión.
"""

import io
import logging
from dataclasses import dataclass

import pikepdf

from .errores import CONTRASENA, DANADO, SIN_PAGINAS, ErrorDocumento, error_documento

registro = logging.getLogger(__name__)

SUJETO = "El PDF"


@dataclass(frozen=True)
class RevisionPdf:
    datos: bytes | None
    """El PDF normalizado: el original tal cual o, si estaba dañado, la copia
    reparada. None si el documento queda con error."""
    paginas: int | None
    restricciones: bool | None
    """True si trae restricciones de copia o impresión. None si no se pudo abrir."""
    reparado: bool
    error: ErrorDocumento | None

    @property
    def ok(self) -> bool:
        return self.error is None


def _con_error(codigo: str) -> RevisionPdf:
    return RevisionPdf(
        datos=None,
        paginas=None,
        restricciones=None,
        reparado=False,
        error=error_documento(codigo, SUJETO),
    )


def _restricciones(pdf: pikepdf.Pdf) -> bool:
    """Solo cuentan las de copia e impresión, que son las que pide R13."""
    if not pdf.is_encrypted:
        return False
    permisos = pdf.allow
    return not (permisos.extract and permisos.print_lowres and permisos.print_highres)


def _inspeccionar(datos: bytes, recuperar: bool) -> tuple[int, bool]:
    """Abre el PDF y devuelve (páginas, restricciones). Lanza la excepción de pikepdf."""
    with pikepdf.open(io.BytesIO(datos), attempt_recovery=recuperar) as pdf:
        return len(pdf.pages), _restricciones(pdf)


def _reparar(datos: bytes) -> bytes:
    """Una sola copia reparada. qpdf reconstruye lo que puede al abrir con recuperación.

    La copia se guarda sin cifrado y con identificador derivado del contenido, para
    que reparar dos veces el mismo PDF dé los mismos bytes (R25).
    """
    with pikepdf.open(io.BytesIO(datos), attempt_recovery=True) as pdf:
        salida = io.BytesIO()
        pdf.save(salida, encryption=False, deterministic_id=True)
    return salida.getvalue()


def revisar(datos: bytes) -> RevisionPdf:
    """Revisa un PDF. Un problema del documento queda en `error`, nunca como excepción."""
    try:
        paginas, restricciones = _inspeccionar(datos, recuperar=False)
    except pikepdf.PasswordError:
        return _con_error(CONTRASENA)
    except pikepdf.PdfError:
        return _revisar_danado(datos)
    if paginas == 0:
        return _con_error(SIN_PAGINAS)
    # R11: un PDF que ya viene bien se usa tal cual, sin reescribirlo.
    return RevisionPdf(datos=datos, paginas=paginas, restricciones=restricciones, reparado=False, error=None)


def _revisar_danado(datos: bytes) -> RevisionPdf:
    try:
        # Las restricciones se leen del original: la copia reparada va sin cifrado.
        _, restricciones = _inspeccionar(datos, recuperar=True)
        reparado = _reparar(datos)
        paginas, _ = _inspeccionar(reparado, recuperar=False)
    except pikepdf.PasswordError:
        return _con_error(CONTRASENA)
    except pikepdf.PdfError:
        registro.info("PDF dañado que no se pudo reparar")
        return _con_error(DANADO)
    if paginas == 0:
        return _con_error(SIN_PAGINAS)
    registro.info("PDF dañado reparado; el normalizado es la copia reparada")
    return RevisionPdf(datos=reparado, paginas=paginas, restricciones=restricciones, reparado=True, error=None)
