"""Dónde se guardan los resultados, por su clave de idempotencia (D22, R53).

La clave es (`id_documento`, páginas, tipo documental, `version_modelo`): la misma
solicitud repetida da el resultado guardado. Un reproceso no borra el anterior:
lo deja al lado, con el identificador de su ejecución (principio 3).
"""

import json
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from normalizacion.inventario import ENTREGA_DEL_PROCESO


@dataclass(frozen=True)
class Clave:
    id_proceso: str
    entrega: str
    """El `id_oferente`, o la entrega del proceso si no hay oferente."""
    id_documento: str
    desde: int
    hasta: int
    tipo_documental: str
    version_modelo: int

    @classmethod
    def de(cls, solicitud: dict) -> "Clave":
        return cls(
            id_proceso=solicitud["id_proceso"],
            entrega=solicitud["id_oferente"] or ENTREGA_DEL_PROCESO,
            id_documento=solicitud["id_documento"],
            desde=solicitud["paginas"]["desde"],
            hasta=solicitud["paginas"]["hasta"],
            tipo_documental=solicitud["tipo_documental"],
            version_modelo=solicitud["version_modelo"],
        )

    @property
    def nombre(self) -> str:
        return f"{self.id_documento}-p{self.desde}-{self.hasta}.{self.tipo_documental}.v{self.version_modelo}"


class Resultados(ABC):
    @abstractmethod
    def buscar(self, clave: Clave) -> dict | None:
        """El resultado vigente de esa clave, o None."""

    @abstractmethod
    def guardar(self, clave: Clave, resultado: dict) -> None:
        """Guarda el resultado como vigente. Si ya había uno, lo conserva aparte."""


class ResultadosEnCarpeta(Resultados):
    """Un JSON por clave: `<raiz>/<id_proceso>/<entrega>/<id_documento>-p<desde>-<hasta>.<TD>.v<N>.json`.

    Los reemplazados quedan como `<nombre>.anterior-<id de su ejecución>.json`.
    """

    def __init__(self, raiz: str | os.PathLike[str]) -> None:
        self.raiz = Path(raiz)

    def ruta(self, clave: Clave) -> Path:
        return self.raiz / clave.id_proceso / clave.entrega / f"{clave.nombre}.json"

    def buscar(self, clave: Clave) -> dict | None:
        ruta = self.ruta(clave)
        if not ruta.is_file():
            return None
        return json.loads(ruta.read_text(encoding="utf-8"))

    def guardar(self, clave: Clave, resultado: dict) -> None:
        ruta = self.ruta(clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        anterior = self.buscar(clave)
        if anterior is not None:
            id_anterior = anterior["ejecucion"]["id"]
            os.replace(ruta, ruta.with_name(f"{clave.nombre}.anterior-{id_anterior}.json"))
        datos = json.dumps(resultado, ensure_ascii=False, indent=1).encode("utf-8")
        # Completo o nada: se escribe al lado y se renombra.
        descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=".", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as archivo:
                archivo.write(datos)
            os.replace(temporal, ruta)
        except BaseException:
            Path(temporal).unlink(missing_ok=True)
            raise
