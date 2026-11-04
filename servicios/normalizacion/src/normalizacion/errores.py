"""Errores del documento (clase 1 del diseño): quedan en el manifiesto, no se lanzan.

`detalle` es el aviso que le llega al evaluador por medio del orquestador: dice
qué pasó y qué pedirle al oferente si decide solicitar subsanación. Nunca lleva
texto del documento ni su nombre. Los textos siguen la tabla del README del
contrato.
"""

from dataclasses import dataclass

CONTRASENA = "CONTRASENA"
DANADO = "DANADO"
SIN_PAGINAS = "SIN_PAGINAS"
NO_SOPORTADO = "NO_SOPORTADO"
CONVERSION_FALLIDA = "CONVERSION_FALLIDA"

CODIGOS = (CONTRASENA, DANADO, SIN_PAGINAS, NO_SOPORTADO, CONVERSION_FALLIDA)

_DETALLES = {
    CONTRASENA: (
        "{documento} pide contraseña para abrirse. "
        "Si se pide subsanación, el oferente debe entregarlo sin contraseña."
    ),
    DANADO: (
        "{documento} está dañado y no se pudo reparar. "
        "Si se pide subsanación, el oferente debe entregarlo de nuevo."
    ),
    SIN_PAGINAS: (
        "{documento} no tiene páginas. "
        "Si se pide subsanación, el oferente debe entregarlo de nuevo."
    ),
    NO_SOPORTADO: (
        "El tipo de archivo no se puede leer. "
        "Si se pide subsanación, el oferente debe entregarlo en PDF."
    ),
    CONVERSION_FALLIDA: (
        "No se pudo convertir el archivo a PDF. "
        "Si se pide subsanación, el oferente debe entregarlo en PDF."
    ),
}


@dataclass(frozen=True)
class ErrorDocumento:
    codigo: str
    detalle: str

    def como_dict(self) -> dict[str, str]:
        return {"codigo": self.codigo, "detalle": self.detalle}


def error_documento(codigo: str, documento: str = "El archivo") -> ErrorDocumento:
    """Error con su aviso. `documento` es el sujeto de la frase: "El PDF", "El archivo"."""
    if codigo not in _DETALLES:
        raise ValueError(f"Código de error desconocido: {codigo}")
    return ErrorDocumento(codigo, _DETALLES[codigo].format(documento=documento))
