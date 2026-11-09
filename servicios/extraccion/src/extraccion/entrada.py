"""Entrada de una solicitud: validarla, ubicar sus archivos y revisar el rango (R26 a R30).

Lo que sale mal aquí no es un bug del servicio, salvo una solicitud que no cumple
el contrato (`SolicitudInvalida`). Lo demás se informa en el resultado con
`error_entrada` (un problema del documento) o `error_proceso` (una falla técnica),
con la excepción `ErrorDeSolicitud`.
"""

import hashlib
import json
from dataclasses import dataclass

from normalizacion.almacen import Almacen, ErrorAlmacen, ruta_en_el_almacen

from . import contratos

ERROR_ENTRADA = "error_entrada"
ERROR_PROCESO = "error_proceso"


class SolicitudInvalida(Exception):
    """La solicitud no cumple el contrato de entrada: un bug de quien la mandó (clase 4)."""

    def __init__(self, errores: list[str]) -> None:
        self.errores = errores
        super().__init__("La solicitud no cumple modulo3-extraccion/0.2: " + "; ".join(errores))


class ErrorDeSolicitud(Exception):
    """El segmento no se puede extraer. Va al resultado como `error` (sin valores del documento)."""

    def __init__(self, estado: str, codigo: str, mensaje: str, reintentable: bool) -> None:
        self.estado = estado
        self.codigo = codigo
        self.mensaje = mensaje
        self.reintentable = reintentable
        super().__init__(f"{estado} {codigo}: {mensaje}")

    def como_error(self) -> dict:
        return {"codigo": self.codigo, "mensaje": self.mensaje, "reintentable": self.reintentable}


def _proceso(codigo: str, mensaje: str, reintentable: bool) -> ErrorDeSolicitud:
    return ErrorDeSolicitud(ERROR_PROCESO, codigo, mensaje, reintentable)


@dataclass(frozen=True)
class Entrada:
    solicitud: dict
    lectura: dict
    pdf: bytes
    anexos: tuple[bytes, ...]

    @property
    def desde(self) -> int:
        return self.solicitud["paginas"]["desde"]

    @property
    def hasta(self) -> int:
        return self.solicitud["paginas"]["hasta"]

    def paginas(self) -> list[dict]:
        """Las páginas del segmento en la lectura, numeradas sobre el documento completo (R31)."""
        return self.lectura["paginas"][self.desde - 1:self.hasta]


def ubicar(almacen: Almacen, uri: str) -> str:
    """La URI dentro del almacén que se usa.

    Una URI `file://` de una corrida local se reubica por lo que va después de
    `almacen/`, para que la corrida se pueda mover de carpeta. Las demás (Blob
    Storage en producción, O2) quedan como vienen.
    """
    relativa = ruta_en_el_almacen(uri)
    return almacen.uri(str(relativa)) if relativa is not None else uri


def _leer(almacen: Almacen, uri: str, que: str) -> bytes:
    try:
        return almacen.leer(ubicar(almacen, uri))
    except ErrorAlmacen:
        raise _proceso("ARCHIVO_NO_ENCONTRADO", f"No se encontró {que} en el almacén.", reintentable=True) from None


def _huella(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def validar(solicitud) -> None:
    """Lanza `SolicitudInvalida` si la solicitud no cumple el contrato de entrada (R26)."""
    problemas = contratos.errores(contratos.ENTRADA, solicitud)
    if problemas:
        raise SolicitudInvalida(problemas)


def preparar(solicitud: dict, almacen: Almacen) -> Entrada:
    """Valida la solicitud, lee la lectura, el PDF y los anexos, y revisa huellas y rango."""
    validar(solicitud)
    if "version_modelo" not in solicitud:
        # El contrato la deja opcional, con la versión registrada del proceso como
        # respaldo, pero la extracción no guarda las versiones de los procesos: las
        # fija el orquestador, que la manda siempre. Nunca se usa la vigente (R30).
        raise _proceso("VERSION_NO_INDICADA", "La solicitud no trae la versión del modelo.", reintentable=False)

    try:
        lectura = json.loads(_leer(almacen, solicitud["lectura"], "la lectura del documento"))
    except json.JSONDecodeError:
        raise _proceso("LECTURA_INVALIDA", "La lectura del documento no es JSON.", reintentable=False) from None
    if lectura.get("id_documento") != solicitud["id_documento"] or not isinstance(lectura.get("paginas"), list):
        raise _proceso("LECTURA_INVALIDA", "La lectura no es la del documento pedido.", reintentable=False)

    pdf = _leer(almacen, solicitud["archivo"]["uri"], "el PDF normalizado")
    huella = _huella(pdf)
    esperada = solicitud["archivo"].get("sha256")
    if (esperada and huella != esperada) or huella != lectura.get("hash_pdf"):
        # El documento cambió después de clasificarse y leerse (R28).
        raise _proceso("ARCHIVO_DISTINTO", "El PDF no es el mismo que se clasificó y se leyó.", reintentable=False)

    total = len(lectura["paginas"])
    desde, hasta = solicitud["paginas"]["desde"], solicitud["paginas"]["hasta"]
    if desde > hasta or hasta > total:
        raise ErrorDeSolicitud(
            ERROR_ENTRADA, "PAGINAS_FUERA_DE_RANGO",
            f"El archivo tiene {total} páginas y se pidió de la {desde} a la {hasta}.", reintentable=False,
        )

    anexos = tuple(_leer(almacen, uri, "un anexo del documento") for uri in solicitud["anexos"])
    return Entrada(solicitud=solicitud, lectura=lectura, pdf=pdf, anexos=anexos)
