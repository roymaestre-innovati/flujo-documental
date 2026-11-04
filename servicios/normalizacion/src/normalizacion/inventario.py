"""Inventario de una entrega (R1 a R5).

Recorre la carpeta, descarta los archivos de sistema, calcula la huella de cada
archivo, marca las copias exactas y le da a cada documento un identificador
estable. No abre ni convierte nada: eso viene después, archivo por archivo.
"""

import hashlib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .tipos import es_appledouble

ENTREGA_DEL_PROCESO = "PROCESO"

MOTIVO_MAC = "archivo_sistema_mac"
MOTIVO_WINDOWS = "archivo_sistema_windows"

_BLOQUE = 1024 * 1024


class ErrorInventario(Exception):
    """La entrega no se puede inventariar de forma estable."""


@dataclass(frozen=True)
class Archivo:
    id_documento: str
    ruta_origen: str
    """Ruta relativa con `/`, normalizada a NFC. Es la que va al manifiesto."""
    ruta: Path
    """Dónde está el archivo en disco, con el nombre tal como llegó."""
    hash: str
    duplicado_de: str | None


@dataclass(frozen=True)
class Descartado:
    ruta_origen: str
    motivo: str


@dataclass(frozen=True)
class Inventario:
    archivos: list[Archivo]
    """Ordenados por ruta_origen."""
    descartados: list[Descartado]
    """Ordenados por ruta_origen."""


def recorrer(carpeta: Path) -> list[str]:
    """Rutas relativas de todos los archivos de la entrega, con `/` y ordenadas.

    Son los nombres tal como están en disco, sin normalizar. Recorre las carpetas
    anidadas y no sigue enlaces simbólicos, para no salir de la entrega.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise NotADirectoryError("La entrega debe ser una carpeta.")
    rutas = []
    for actual, _carpetas, archivos in carpeta.walk(follow_symlinks=False):
        for nombre in archivos:
            ruta = actual / nombre
            if ruta.is_file() and not ruta.is_symlink():
                rutas.append(ruta.relative_to(carpeta).as_posix())
    return sorted(rutas)


def normalizar_ruta(ruta: str) -> str:
    """NFC, para que la misma entrega dé lo mismo venga de Mac o de Windows."""
    return unicodedata.normalize("NFC", ruta)


def id_documento(ruta_origen: str, id_oferente: str | None) -> str:
    """`<id_oferente o PROCESO>-<12 hex del SHA-256 de la ruta en UTF-8 y NFC>` (R5)."""
    huella_ruta = hashlib.sha256(normalizar_ruta(ruta_origen).encode("utf-8")).hexdigest()
    return f"{id_oferente or ENTREGA_DEL_PROCESO}-{huella_ruta[:12]}"


def huella(ruta: Path) -> str:
    """SHA-256 del archivo (R3)."""
    sha = hashlib.sha256()
    with Path(ruta).open("rb") as archivo:
        while bloque := archivo.read(_BLOQUE):
            sha.update(bloque)
    return sha.hexdigest()


def motivo_descarte(ruta_origen: str, ruta: Path) -> str | None:
    """Motivo por el que un archivo de sistema se descarta, o None si es documento (R2).

    - `.DS_Store` y todo lo que esté dentro de una carpeta `__MACOSX`: por nombre.
    - `Thumbs.db`: por nombre, sin importar mayúsculas (Windows no las distingue).
    - Archivos AppleDouble (los `._*`): por contenido, porque llevan la extensión
      del original. Un `._algo` que no es AppleDouble se trata como documento, y
      un AppleDouble con nombre normal se descarta igual.
    """
    partes = ruta_origen.split("/")
    nombre = partes[-1]
    if "__MACOSX" in partes[:-1] or nombre == ".DS_Store":
        return MOTIVO_MAC
    if nombre.casefold() == "thumbs.db":
        return MOTIVO_WINDOWS
    if es_appledouble(ruta):
        return MOTIVO_MAC
    return None


def _con_sufijo(ruta: str, numero: int) -> str:
    """`a/carta.pdf` → `a/carta (2).pdf`. El sufijo va en el nombre, antes de la extensión."""
    carpeta, _, nombre = ruta.rpartition("/")
    base, punto, extension = nombre.rpartition(".")
    if not base:  # sin extensión, o un nombre que empieza por punto
        base, punto, extension = nombre, "", ""
    nuevo = f"{base} ({numero}){punto}{extension}"
    return f"{carpeta}/{nuevo}" if carpeta else nuevo


def _rutas_unicas(relativas: list[str]) -> dict[str, str]:
    """Ruta en disco → ruta_origen en NFC, sin repetir.

    Dos nombres que solo se diferencian en cómo escriben las tildes (NFC y NFD)
    darían la misma ruta_origen. El primero en orden de la ruta en disco la
    conserva; los siguientes llevan un sufijo ` (2)`, ` (3)`… que no choque con
    ninguna otra ruta de la entrega. Es determinista: la misma carpeta da siempre
    los mismos sufijos.
    """
    normalizadas = {relativa: normalizar_ruta(relativa) for relativa in sorted(relativas)}
    ocupadas = set(normalizadas.values())
    asignadas: set[str] = set()
    resultado = {}
    for relativa, ruta_origen in normalizadas.items():
        if ruta_origen in asignadas:
            numero = 2
            while _con_sufijo(ruta_origen, numero) in ocupadas:
                numero += 1
            ruta_origen = _con_sufijo(ruta_origen, numero)
            ocupadas.add(ruta_origen)
        asignadas.add(ruta_origen)
        resultado[relativa] = ruta_origen
    return resultado


def inventariar(carpeta: Path, id_oferente: str | None) -> Inventario:
    """Inventario de una entrega. `id_oferente` es None en una entrega del proceso."""
    carpeta = Path(carpeta)
    encontrados = {
        ruta_origen: carpeta / relativa
        for relativa, ruta_origen in _rutas_unicas(recorrer(carpeta)).items()
    }

    archivos: list[Archivo] = []
    descartados: list[Descartado] = []
    originales: dict[str, str] = {}
    identificadores: set[str] = set()
    for ruta_origen in sorted(encontrados):
        ruta = encontrados[ruta_origen]
        motivo = motivo_descarte(ruta_origen, ruta)
        if motivo is not None:
            descartados.append(Descartado(ruta_origen, motivo))
            continue
        identificador = id_documento(ruta_origen, id_oferente)
        if identificador in identificadores:
            raise ErrorInventario("Dos archivos de la entrega dieron el mismo id_documento.")
        identificadores.add(identificador)
        huella_archivo = huella(ruta)
        duplicado_de = originales.setdefault(huella_archivo, identificador)
        archivos.append(
            Archivo(
                id_documento=identificador,
                ruta_origen=ruta_origen,
                ruta=ruta,
                hash=huella_archivo,
                duplicado_de=None if duplicado_de == identificador else duplicado_de,
            )
        )
    return Inventario(archivos=archivos, descartados=descartados)
