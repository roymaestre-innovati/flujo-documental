"""Una entrega completa: inventario, cada archivo y el manifiesto.

    manifiesto = normalizar_entrega(carpeta, "SR0000000001", "OF-002", AlmacenLocal(salida))

Por cada archivo: tipo real, conversión si no es PDF, revisión del PDF, firma
digital, lectura y palabras. Escribe en el almacén el PDF normalizado, el anexo,
la lectura y las palabras de cada documento, y al final el manifiesto:

    <id_proceso>/<id_oferente o PROCESO>/
      manifiesto.json
      pdf/<id_documento>.pdf
      anexos/<id_documento>.<ext>
      lectura/<id_documento>.json
      palabras/<id_documento>.json

Errores (paso 4 del diseño):
- Clase 1, del documento: quedan en el manifiesto con `error_entrada` y su código.
  No frenan a los demás (R17).
- Clase 4, bug: una excepción inesperada en un archivo se registra y se sigue con
  los demás. Al final se lanza `ErrorEntrega`, después de escribir lo que sí se
  pudo, y el manifiesto no se escribe: una entrega con un bug no se da por hecha.
"""

import datetime
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import CONTRATO, VERSION, registros
from .almacen import Almacen
from .conversion import convertir
from .errores import CONVERSION_FALLIDA, SIN_PAGINAS, ErrorDocumento, error_documento
from .firma import FirmaDigital, leer_firmas
from .inventario import ENTREGA_DEL_PROCESO, Archivo, inventariar
from .lectura import leer
from .parametros import PARAMETROS, Parametros
from .revision_pdf import revisar
from .tipos import PDF, TipoReal, detectar

registro = logging.getLogger(__name__)

NORMALIZADO = "normalizado"
DUPLICADO = "duplicado"
ERROR_ENTRADA = "error_entrada"


class ErrorEntrega(Exception):
    """Uno o más archivos fallaron por un bug (clase 4). Lleva solo identificadores."""

    def __init__(self, id_documentos: list[str]):
        self.id_documentos = id_documentos
        super().__init__(f"Falla inesperada en {len(id_documentos)} documento(s): {', '.join(id_documentos)}")


@dataclass
class Resultado:
    manifiesto: dict
    tipos_de_pagina: Counter = field(default_factory=Counter)
    """Páginas por tipo, de los documentos normalizados (sin contar duplicados)."""
    reusados: int = 0
    """Documentos que no se volvieron a procesar porque ya estaban (idempotencia)."""


def _json(datos: dict, compacto: bool = False) -> bytes:
    if compacto:
        texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    else:
        texto = json.dumps(datos, ensure_ascii=False, indent=2)
    return (texto + "\n").encode("utf-8")


def _entrada(archivo: Archivo, tipo_origen: str) -> dict:
    """Entrada del manifiesto con todas las claves, en el orden del contrato."""
    return {
        "id_documento": archivo.id_documento,
        "ruta_origen": archivo.ruta_origen,
        "hash": archivo.hash,
        "tipo_origen": tipo_origen,
        "estado": ERROR_ENTRADA,
        "pdf": None,
        "anexo_nativo": None,
        "lectura": None,
        "paginas": None,
        "paginas_sin_texto": [],
        "duplicado_de": None,
        "restricciones": None,
        "firma_digital": None,
        "reparado": False,
        "error": None,
    }


def _con_error(entrada: dict, error: ErrorDocumento) -> dict:
    entrada.update(estado=ERROR_ENTRADA, error=error.como_dict())
    return entrada


class _Procesador:
    def __init__(self, almacen: Almacen, prefijo: str, parametros: Parametros, soffice: str | None):
        self.almacen = almacen
        self.prefijo = prefijo
        self.parametros = parametros
        self.soffice = soffice
        self.tipos_de_pagina: Counter = Counter()

    def uri(self, carpeta: str, nombre: str) -> str:
        return self.almacen.uri(f"{self.prefijo}/{carpeta}/{nombre}")

    def procesar(self, archivo: Archivo) -> dict:
        tipo = detectar(archivo.ruta)
        entrada = _entrada(archivo, tipo.tipo_origen)
        if tipo.tipo_origen == PDF:
            return self._pdf(archivo, entrada)
        return self._convertido(archivo, tipo, entrada)

    def _pdf(self, archivo: Archivo, entrada: dict) -> dict:
        original = archivo.ruta.read_bytes()
        revision = revisar(original)
        if not revision.ok:
            return _con_error(entrada, revision.error)
        # La firma se lee del original: reescribirlo (al repararlo) la invalida.
        firmas = leer_firmas(original)
        return self._normalizado(
            archivo, entrada, revision.datos, revision.paginas, revision.restricciones, revision.reparado, firmas, None
        )

    def _convertido(self, archivo: Archivo, tipo: TipoReal, entrada: dict) -> dict:
        conversion = convertir(archivo.ruta, tipo, soffice=self.soffice)
        if not conversion.ok:
            return _con_error(entrada, conversion.error)
        revision = revisar(conversion.datos)
        if not revision.ok:
            # El PDF lo hizo la conversión: si no sirve, la que falló es la conversión.
            codigo = SIN_PAGINAS if revision.error.codigo == SIN_PAGINAS else CONVERSION_FALLIDA
            return _con_error(entrada, error_documento(codigo))
        return self._normalizado(
            archivo, entrada, revision.datos, revision.paginas, False, False, [], conversion.anexo
        )

    def _normalizado(
        self,
        archivo: Archivo,
        entrada: dict,
        datos_pdf: bytes,
        paginas: int,
        restricciones: bool,
        reparado: bool,
        firmas: list[FirmaDigital],
        anexo: bytes | None,
    ) -> dict:
        identificador = archivo.id_documento
        uri_pdf = self.uri("pdf", f"{identificador}.pdf")
        uri_lectura = self.uri("lectura", f"{identificador}.json")
        uri_palabras = self.uri("palabras", f"{identificador}.json")
        resultado = leer(datos_pdf, identificador, firmas, uri_palabras, self.parametros)

        self.almacen.escribir(uri_pdf, datos_pdf)
        uri_anexo = None
        if anexo is not None:
            uri_anexo = self.uri("anexos", f"{identificador}.{entrada['tipo_origen']}")
            self.almacen.escribir(uri_anexo, anexo)
        self.almacen.escribir(uri_palabras, _json(resultado.palabras, compacto=True))
        self.almacen.escribir(uri_lectura, _json(resultado.lectura))

        self.tipos_de_pagina.update(p["tipo"] for p in resultado.lectura["paginas"])
        entrada.update(
            estado=NORMALIZADO,
            pdf=uri_pdf,
            anexo_nativo=uri_anexo,
            lectura=uri_lectura,
            paginas=paginas,
            paginas_sin_texto=resultado.paginas_sin_texto,
            restricciones=restricciones,
            firma_digital=[firma.como_dict() for firma in firmas],
            reparado=reparado,
        )
        return entrada


def _duplicado(archivo: Archivo, original: dict) -> dict:
    """Repite los datos del original (decisión 1 de T01), salvo el error."""
    entrada = dict(original)
    entrada.update(
        id_documento=archivo.id_documento,
        ruta_origen=archivo.ruta_origen,
        estado=DUPLICADO,
        duplicado_de=archivo.duplicado_de,
        error=None,
    )
    return entrada


def _anterior(almacen: Almacen, prefijo: str, parametros: Parametros) -> dict[str, dict]:
    """Entradas normalizadas del manifiesto anterior que se pueden reusar, por id."""
    uri_manifiesto = almacen.uri(f"{prefijo}/manifiesto.json")
    if not almacen.existe(uri_manifiesto):
        return {}
    try:
        manifiesto = json.loads(almacen.leer(uri_manifiesto))
    except (ValueError, UnicodeDecodeError):
        registro.warning("Manifiesto anterior ilegible: se procesa todo de nuevo")
        return {}
    if (
        manifiesto.get("contrato") != CONTRATO
        or manifiesto.get("version_normalizador") != VERSION
        or manifiesto.get("version_parametros") != parametros.version
    ):
        return {}
    reusables = {}
    for entrada in manifiesto.get("archivos", []):
        if entrada.get("estado") != NORMALIZADO:
            continue
        uris = [
            entrada.get("pdf"),
            entrada.get("lectura"),
            almacen.uri(f"{prefijo}/palabras/{entrada['id_documento']}.json"),
            *([entrada["anexo_nativo"]] if entrada.get("anexo_nativo") else []),
        ]
        if all(uri and almacen.existe(uri) for uri in uris):
            reusables[entrada["id_documento"]] = entrada
    return reusables


def _contar_tipos_de_lo_reusado(almacen: Almacen, entrada: dict, contador: Counter) -> None:
    try:
        lectura = json.loads(almacen.leer(entrada["lectura"]))
        contador.update(p["tipo"] for p in lectura["paginas"])
    except (ValueError, KeyError, UnicodeDecodeError):
        pass


def normalizar_entrega(
    carpeta: Path,
    id_proceso: str,
    id_oferente: str | None,
    almacen: Almacen,
    *,
    forzar: bool = False,
    soffice: str | None = None,
    parametros: Parametros = PARAMETROS,
) -> Resultado:
    """Normaliza y lee una entrega. Devuelve el manifiesto escrito y conteos.

    Idempotente: si el manifiesto anterior ya tiene un documento normalizado con
    la misma huella, la misma versión del normalizador y de los parámetros, y sus
    archivos siguen en el almacén, se reusa sin convertir ni leer. `forzar` lo
    ignora. Los documentos con error se vuelven a intentar siempre.
    """
    inicio = datetime.datetime.now(datetime.timezone.utc)
    reloj = time.perf_counter()
    entrega = id_oferente or ENTREGA_DEL_PROCESO
    prefijo = f"{id_proceso}/{entrega}"
    uri_manifiesto = almacen.uri(f"{prefijo}/manifiesto.json")

    with registros.contexto(id_proceso=id_proceso, id_oferente=entrega):
        inventario = inventariar(carpeta, id_oferente)
        anteriores = {} if forzar else _anterior(almacen, prefijo, parametros)
        procesador = _Procesador(almacen, prefijo, parametros, soffice)
        entradas: dict[str, dict] = {}
        fallidos: list[str] = []
        reusados = 0

        for archivo in inventario.archivos:
            with registros.contexto(id_documento=archivo.id_documento, hash=archivo.hash[:12]):
                if archivo.duplicado_de:
                    original = entradas.get(archivo.duplicado_de)
                    if original is None:  # el original falló por un bug
                        fallidos.append(archivo.id_documento)
                        continue
                    entradas[archivo.id_documento] = _duplicado(archivo, original)
                    registro.info("Documento duplicado")
                    continue
                previo = anteriores.get(archivo.id_documento)
                if previo is not None and previo.get("hash") == archivo.hash:
                    entradas[archivo.id_documento] = previo
                    _contar_tipos_de_lo_reusado(almacen, previo, procesador.tipos_de_pagina)
                    reusados += 1
                    registro.info("Documento reusado, sin cambios")
                    continue
                try:
                    entrada = procesador.procesar(archivo)
                except Exception:
                    registro.exception("Falla inesperada al procesar el documento")
                    fallidos.append(archivo.id_documento)
                    continue
                entradas[archivo.id_documento] = entrada
                if entrada["error"]:
                    registro.info("Documento con error: %s", entrada["error"]["codigo"])
                else:
                    registro.info("Documento normalizado: %d páginas", entrada["paginas"])

        if fallidos:
            registro.error("Entrega sin manifiesto: %d documento(s) con falla inesperada", len(fallidos))
            raise ErrorEntrega(fallidos)

        manifiesto = {
            "contrato": CONTRATO,
            "id_proceso": id_proceso,
            "id_oferente": id_oferente,
            "version_normalizador": VERSION,
            "version_parametros": parametros.version,
            "ejecucion": {
                "inicio": inicio.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "duracion_ms": round((time.perf_counter() - reloj) * 1000),
            },
            "archivos": [entradas[archivo.id_documento] for archivo in inventario.archivos],
            "descartados": [
                {"ruta_origen": descartado.ruta_origen, "motivo": descartado.motivo}
                for descartado in inventario.descartados
            ],
        }
        almacen.escribir(uri_manifiesto, _json(manifiesto))
        registro.info(
            "Entrega normalizada: %d archivos, %d descartados, %d reusados",
            len(manifiesto["archivos"]),
            len(manifiesto["descartados"]),
            reusados,
        )
    return Resultado(manifiesto=manifiesto, tipos_de_pagina=procesador.tipos_de_pagina, reusados=reusados)
