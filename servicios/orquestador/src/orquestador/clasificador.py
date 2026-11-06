"""El clasificador. En producción es del equipo de clasificación (C1 a C3); aquí,
un clasificador falso que lee un CSV (doble de prueba, principio 5).

Recibe la solicitud y devuelve la respuesta del contrato
`contracts/modulo5-orquestador/v0` (clasificacion-solicitud y
clasificacion-respuesta). No revisa que la respuesta tenga sentido: eso lo hace
el orquestador (T07), y así el CSV sirve también para probar respuestas malas.
"""

import csv
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
    """

    def __init__(self, csv_ruta: str | Path) -> None:
        self._filas: dict[tuple[str | None, str], list[dict]] = defaultdict(list)
        with open(csv_ruta, encoding="utf-8", newline="") as f:
            lector = csv.DictReader(f)
            faltan = [c for c in COLUMNAS if c not in (lector.fieldnames or [])]
            if faltan:
                raise ErrorClasificadorFalso(f"Faltan columnas en el CSV: {', '.join(faltan)}")
            for n, fila in enumerate(lector, start=2):
                try:
                    clave = (fila["id_oferente"].strip() or None, _nfc(fila["ruta_origen"].strip()))
                    self._filas[clave].append({
                        "pagina_inicio": int(fila["pagina_inicio"]) if fila["pagina_inicio"].strip() else None,
                        "pagina_fin": int(fila["pagina_fin"]) if fila["pagina_fin"].strip() else None,
                        "tipo_documental": fila["tipo_documental"].strip(),
                        "subtipo": (fila.get("subtipo") or "").strip() or None,
                        "confianza": float(fila["confianza"]),
                    })
                except ValueError as e:
                    raise ErrorClasificadorFalso(f"Línea {n} del CSV: {e}") from None

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
