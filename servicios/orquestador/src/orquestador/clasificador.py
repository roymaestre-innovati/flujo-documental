"""El clasificador. En producción es del equipo de clasificación (C1 a C3); aquí,
un clasificador falso que lee un CSV (doble de prueba, principio 5).

Recibe la solicitud y devuelve la respuesta del contrato
`contracts/modulo5-orquestador/v0` (clasificacion-solicitud y
clasificacion-respuesta). No revisa que la respuesta tenga sentido: eso lo hace
el orquestador (T07), y así el CSV sirve también para probar respuestas malas.
"""

import csv
import io
import unicodedata
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path

from . import CONTRATO

COLUMNAS = ("id_oferente", "ruta_origen", "pagina_inicio", "pagina_fin", "tipo_documental", "confianza")
"""Obligatorias. `subtipo` es opcional."""


class ErrorClasificadorFalso(Exception):
    """El CSV del clasificador falso está mal: un bug de la prueba."""


class Clasificador(ABC):
    @abstractmethod
    def clasificar(self, solicitud: dict) -> dict:
        """Devuelve la respuesta del clasificador para una solicitud."""


def _nfc(texto: str) -> str:
    return unicodedata.normalize("NFC", texto)


class ClasificadorFalso(Clasificador):
    """Busca el documento por oferente y ruta de origen en un CSV.

    - `id_oferente` vacío es un documento del proceso.
    - `pagina_inicio` y `pagina_fin` vacíos quieren decir "todo el documento".
    - Un documento que no está en el CSV sale como TD-99 con confianza 1.
    - Sin CSV, todos los documentos salen como TD-99.
    """

    def __init__(self, csv_ruta: str | Path | None = None, *, texto: str | None = None) -> None:
        """`csv_ruta` es un archivo local; `texto`, el contenido del CSV (por ejemplo,
        leído del almacén por el worker de `clasificar`)."""
        self._filas: dict[tuple[str | None, str], list[dict]] = defaultdict(list)
        if texto is not None:
            self._cargar(io.StringIO(texto, newline=""))
        elif csv_ruta is not None:
            with open(csv_ruta, encoding="utf-8", newline="") as f:
                self._cargar(f)

    @property
    def filas(self) -> int:
        return sum(len(partes) for partes in self._filas.values())

    def _cargar(self, archivo) -> None:
        lector = csv.DictReader(archivo)
        faltan = [c for c in COLUMNAS if c not in (lector.fieldnames or [])]
        if faltan:
            raise ErrorClasificadorFalso(f"Faltan columnas en el CSV: {', '.join(faltan)}")
        for n, fila in enumerate(lector, start=2):
            if any(fila[c] is None for c in COLUMNAS):
                raise ErrorClasificadorFalso(f"Línea {n} del CSV: le faltan columnas del encabezado")
            try:
                clave = (fila["id_oferente"].strip() or None, _nfc(fila["ruta_origen"].strip()))
                inicio = int(fila["pagina_inicio"]) if fila["pagina_inicio"].strip() else None
                fin = int(fila["pagina_fin"]) if fila["pagina_fin"].strip() else None
                confianza = float(fila["confianza"])
            except ValueError:
                raise ErrorClasificadorFalso(f"Línea {n} del CSV: una página o la confianza no es un número") from None
            if not 0 <= confianza <= 1:  # también descarta nan
                raise ErrorClasificadorFalso(f"Línea {n} del CSV: la confianza va de 0 a 1")
            if any(p is not None and p < 1 for p in (inicio, fin)) or (inicio and fin and fin < inicio):
                raise ErrorClasificadorFalso(f"Línea {n} del CSV: las páginas no forman un rango")
            if not fila["tipo_documental"].strip() or not clave[1]:
                raise ErrorClasificadorFalso(f"Línea {n} del CSV: falta la ruta o el tipo documental")
            self._filas[clave].append({
                "pagina_inicio": inicio,
                "pagina_fin": fin,
                "tipo_documental": fila["tipo_documental"].strip(),
                "subtipo": (fila.get("subtipo") or "").strip() or None,
                "confianza": confianza,
            })

    def clasificar(self, solicitud: dict) -> dict:
        clave = (solicitud["id_oferente"], _nfc(solicitud["ruta_origen"]))
        filas = self._filas.get(clave)
        paginas = solicitud["paginas"]
        if not filas:
            segmentos = [{"pagina_inicio": 1, "pagina_fin": paginas, "tipo_documental": "TD-99",
                          "subtipo": None, "confianza": 1.0}]
        else:
            segmentos = [
                {**f, "pagina_inicio": f["pagina_inicio"] or 1, "pagina_fin": f["pagina_fin"] or paginas}
                for f in sorted(filas, key=lambda f: f["pagina_inicio"] or 1)
            ]
        return {
            "contrato": CONTRATO,
            "id_documento": solicitud["id_documento"],
            "version_ontologia": solicitud["version_ontologia"],
            "segmentos": segmentos,
        }
