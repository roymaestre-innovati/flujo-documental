"""Almacén del estado. En producción, Cosmos (entrega 2); aquí, en memoria.

Guarda documentos JSON, uno por entidad, identificados por proceso, tipo e id.
El proceso es la partición: en Cosmos, `id_proceso` será la clave de partición y
todas las consultas son dentro de un proceso.

Esta capa no sabe de estados ni de transiciones (eso es T03). Solo garantiza dos
cosas que el resto necesita:

- `crear_si_no_existe`: si dos trabajadores crean lo mismo a la vez, gana el
  primero y el otro recibe lo que quedó;
- `reemplazar` condicional: solo escribe si nadie cambió el documento desde que
  se leyó (`version`, como el ETag de Cosmos). Si cambió, `Conflicto`.
"""

import copy
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

TIPOS = ("proceso", "oferente", "documento", "segmento", "tarea")


class ErrorEstado(Exception):
    """Uso incorrecto del estado: un bug (clase 4)."""


class Conflicto(Exception):
    """Otro trabajador cambió el documento desde que se leyó."""


@dataclass(frozen=True)
class Registro:
    id_proceso: str
    tipo: str
    id: str
    version: int
    """Sube con cada escritura. Es lo que se compara en `reemplazar`."""
    datos: dict


class Estado(ABC):
    @abstractmethod
    def leer(self, id_proceso: str, tipo: str, id: str) -> Registro | None: ...

    @abstractmethod
    def crear_si_no_existe(self, id_proceso: str, tipo: str, id: str, datos: dict) -> tuple[Registro, bool]:
        """Crea el registro si no existe. Devuelve el que quedó y si se creó ahora."""

    @abstractmethod
    def reemplazar(self, registro: Registro, datos: dict) -> Registro:
        """Escribe `datos` solo si el registro sigue en `registro.version`. Si no, `Conflicto`."""

    @abstractmethod
    def listar(self, id_proceso: str, tipo: str | None = None) -> list[Registro]:
        """Los registros de un proceso, de un tipo o de todos, ordenados por tipo e id."""


def _revisar(tipo: str, datos: dict) -> dict:
    if tipo not in TIPOS:
        raise ErrorEstado(f"Tipo desconocido: {tipo}")
    # Como en Cosmos, se guarda JSON: se copia y debe poder serializarse.
    return json.loads(json.dumps(datos, ensure_ascii=False))


class EstadoEnMemoria(Estado):
    def __init__(self) -> None:
        self._registros: dict[tuple[str, str, str], Registro] = {}

    def leer(self, id_proceso: str, tipo: str, id: str) -> Registro | None:
        registro = self._registros.get((id_proceso, tipo, id))
        return copy.deepcopy(registro)

    def crear_si_no_existe(self, id_proceso: str, tipo: str, id: str, datos: dict) -> tuple[Registro, bool]:
        datos = _revisar(tipo, datos)
        clave = (id_proceso, tipo, id)
        if clave in self._registros:
            return copy.deepcopy(self._registros[clave]), False
        registro = Registro(id_proceso, tipo, id, 1, datos)
        self._registros[clave] = registro
        return copy.deepcopy(registro), True

    def reemplazar(self, registro: Registro, datos: dict) -> Registro:
        datos = _revisar(registro.tipo, datos)
        clave = (registro.id_proceso, registro.tipo, registro.id)
        actual = self._registros.get(clave)
        if actual is None:
            raise ErrorEstado(f"No existe {registro.tipo} {registro.id} en {registro.id_proceso}")
        if actual.version != registro.version:
            raise Conflicto(f"{registro.tipo} {registro.id}: se leyó la versión {registro.version} y va en la {actual.version}")
        nuevo = Registro(registro.id_proceso, registro.tipo, registro.id, actual.version + 1, datos)
        self._registros[clave] = nuevo
        return copy.deepcopy(nuevo)

    def listar(self, id_proceso: str, tipo: str | None = None) -> list[Registro]:
        if tipo is not None and tipo not in TIPOS:
            raise ErrorEstado(f"Tipo desconocido: {tipo}")
        encontrados = [
            r for (p, t, _), r in self._registros.items() if p == id_proceso and (tipo is None or t == tipo)
        ]
        return copy.deepcopy(sorted(encontrados, key=lambda r: (TIPOS.index(r.tipo), r.id)))

    def guardar(self, ruta: Path) -> None:
        """Escribe todo el estado en un JSON, para revisar una corrida local."""
        contenido = [
            {"id_proceso": r.id_proceso, "tipo": r.tipo, "id": r.id, "version": r.version, "datos": r.datos}
            for r in sorted(self._registros.values(), key=lambda r: (r.id_proceso, TIPOS.index(r.tipo), r.id))
        ]
        ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
