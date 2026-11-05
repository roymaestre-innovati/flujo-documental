"""Firma digital de un PDF (R15).

Por cada firma: quién firma (CN del certificado), cuándo (la hora que declara la
firma), si el documento está íntegro (no se modificó después de firmar de una
forma que la invalide), el formato (subfiltro) y si se pudo leer.

No se valida la confianza del certificado: no se cargan autoridades raíz ni se
consulta revocación, así que no hay red (decisión 4 del diseño).

Las firmas se buscan en dos pasos. pikepdf lista todos los campos de firma con su
formato; pyHanko valida los que puede. pyHanko ni siquiera lista algunas firmas
(por ejemplo, las `adbe.pkcs7.sha1` de la Cámara de Comercio), y sin el primer paso
el manifiesto diría "sin firma" cuando hay una firma que no se pudo leer.

Un sello de tiempo del documento (`/DocTimeStamp`, `ETSI.RFC3161`) usa el mismo tipo
de campo, pero no es una firma: no tiene firmante. No se cuenta (T14).
"""

import io
import logging
from dataclasses import dataclass

import pikepdf

registro = logging.getLogger(__name__)

# pyHanko escribe en el registro los datos del certificado (nombres de personas)
# cuando la validación encuentra algo raro. No deben llegar a los registros
# del servicio (principio 6).
for _nombre in ("pyhanko", "pyhanko_certvalidator"):
    logging.getLogger(_nombre).setLevel(logging.CRITICAL)


@dataclass(frozen=True)
class FirmaDigital:
    firmante: str | None
    fecha: str | None
    """ISO 8601."""
    integro: bool | None
    formato: str
    """Subfiltro sin la barra: adbe.pkcs7.detached, ETSI.CAdES.detached…"""
    leida: bool

    def como_dict(self) -> dict:
        return {
            "firmante": self.firmante,
            "fecha": self.fecha,
            "integro": self.integro,
            "formato": self.formato,
            "leida": self.leida,
        }


def _sin_leer(formato: str) -> FirmaDigital:
    return FirmaDigital(firmante=None, fecha=None, integro=None, formato=formato, leida=False)


# ---------------------------------------------------------------------------
# Paso 1: campos de firma, con pikepdf


def _nombre_campo(campo: pikepdf.Dictionary, padre: str) -> str:
    propio = str(campo.get("/T", ""))
    return f"{padre}.{propio}" if padre and propio else (propio or padre)


def _es_sello_de_tiempo(valor: pikepdf.Dictionary) -> bool:
    return valor.get("/Type") == pikepdf.Name.DocTimeStamp or valor.get("/SubFilter") == pikepdf.Name("/ETSI.RFC3161")


def _campos_firmados(datos: bytes) -> list[tuple[str, str]]:
    """(nombre completo del campo, formato) de cada campo de firma con firma, en el
    orden del formulario."""
    try:
        with pikepdf.open(io.BytesIO(datos)) as pdf:
            formulario = pdf.Root.get("/AcroForm")
            if formulario is None:
                return []
            encontrados: list[tuple[str, str]] = []
            vistos: set[tuple[int, int]] = set()
            pendientes = [(campo, "") for campo in formulario.get("/Fields", [])]
            while pendientes:
                campo, padre = pendientes.pop(0)
                if not isinstance(campo, pikepdf.Dictionary):
                    continue
                if campo.is_indirect:
                    if campo.objgen in vistos:
                        continue
                    vistos.add(campo.objgen)
                nombre = _nombre_campo(campo, padre)
                valor = campo.get("/V")
                if (
                    campo.get("/FT") == pikepdf.Name.Sig
                    and isinstance(valor, pikepdf.Dictionary)
                    and not _es_sello_de_tiempo(valor)
                ):
                    formato = str(valor.get("/SubFilter", "/desconocido")).lstrip("/")
                    encontrados.append((nombre, formato))
                hijos = [(hijo, nombre) for hijo in campo.get("/Kids", [])]
                pendientes[0:0] = hijos
            return encontrados
    except (pikepdf.PdfError, AttributeError, TypeError, ValueError):
        registro.info("No se pudieron recorrer los campos de firma")
        return []


# ---------------------------------------------------------------------------
# Paso 2: validación, con pyHanko


def _firmante(estado) -> str | None:
    certificado = estado.signing_cert
    if certificado is None:
        return None
    nombre = certificado.subject.native.get("common_name")
    if isinstance(nombre, list):
        nombre = nombre[0] if nombre else None
    return nombre or certificado.subject.human_friendly


def _fecha(estado, firma) -> str | None:
    momento = estado.signer_reported_dt or firma.self_reported_timestamp
    return momento.isoformat() if momento else None


def _validar(firma, contexto) -> FirmaDigital:
    from pyhanko.sign.validation import validate_pdf_signature

    formato = str(firma.sig_object.get("/SubFilter", "/desconocido")).lstrip("/")
    estado = validate_pdf_signature(firma, contexto)
    integro = bool(estado.intact and estado.valid and estado.docmdp_ok)
    return FirmaDigital(
        firmante=_firmante(estado),
        fecha=_fecha(estado, firma),
        integro=integro,
        formato=formato,
        leida=True,
    )


def _validadas(datos: bytes) -> dict[str, FirmaDigital]:
    """Firmas que pyHanko puede validar, por nombre de campo."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko_certvalidator import ValidationContext

    try:
        lector = PdfFileReader(io.BytesIO(datos), strict=False)
        if lector.encrypted:
            # Un PDF con solo restricciones se abre con la contraseña vacía.
            lector.decrypt("")
        firmas = lector.embedded_signatures
    except Exception as error:  # noqa: BLE001 - pyHanko falla de muchas formas con PDF raros
        registro.info("pyHanko no pudo leer las firmas: %s", type(error).__name__)
        return {}
    contexto = ValidationContext(trust_roots=[], allow_fetching=False)
    resultado = {}
    for firma in firmas:
        try:
            resultado[firma.field_name] = _validar(firma, contexto)
        except Exception as error:  # noqa: BLE001 - una firma que no se lee no es error del documento
            registro.info("Firma que no se pudo validar: %s", type(error).__name__)
    return resultado


# ---------------------------------------------------------------------------


def leer_firmas(datos: bytes) -> list[FirmaDigital]:
    """Firmas digitales del PDF, en el orden del formulario. Lista vacía si no tiene.

    Se llama con el PDF original del oferente, no con una copia reparada, porque
    reescribir el archivo invalida la firma (R10).
    """
    campos = _campos_firmados(datos)
    if not campos:
        return []
    validadas = _validadas(datos)
    firmas = []
    for nombre, formato in campos:
        firma = validadas.get(nombre)
        if firma is None:
            firma = _sin_leer(formato)
        elif firma.fecha is None or firma.firmante is None:
            # El contrato pide firmante y fecha en una firma leída.
            registro.info("Firma sin firmante o sin fecha declarada: queda como no leída")
            firma = _sin_leer(firma.formato)
        firmas.append(firma)
    return firmas
