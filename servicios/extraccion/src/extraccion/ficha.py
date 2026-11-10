"""La ficha del tipo documental: qué extraer y cómo validarlo, en la versión fijada.

La ficha tiene la forma de lo que devuelve el servidor MCP del modelo semántico:
`describir_modelo` da la guía, el diccionario y las secciones, y `obtener_seccion`
da los elementos de un TD ya limpios (sin `formula`, `depende_de` ni
`trazabilidad`) y con los catálogos resueltos en `valores_permitidos`. Así una
ficha leída de un archivo y una pedida al MCP son iguales.

La versión siempre la trae la solicitud: nunca se usa la vigente (principio 7).
"""

import json
import os
import tempfile
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass


class FichaNoEncontrada(Exception):
    """La versión del modelo o el tipo documental no existen en la fuente."""


@dataclass(frozen=True)
class Ficha:
    modelo: str
    version: int
    guia: str
    """Guía de interpretación del modelo, en la misma versión."""
    diccionario: dict
    seccion: dict
    """La entrada del TD en `secciones`: `id`, `nombre`, `orden` y, cuando la matriz la traiga, `td_probado`."""
    elementos: tuple[dict, ...]
    """Los elementos del TD, en el orden del modelo."""

    @property
    def tipo_documental(self) -> str:
        return self.seccion["id"]

    @property
    def td_probado(self) -> bool:
        """Sin la marca en la ficha, el TD se trata como no probado (R46)."""
        return self.seccion.get("td_probado") is True

    def a_extraer(self) -> list[dict]:
        """Los elementos que se extraen, en orden. Los calculados no (R37)."""
        return [e for e in self.elementos if e.get("atributos", {}).get("modo_captura", "Extraer") == "Extraer"]


class FuenteModelo(ABC):
    @abstractmethod
    def ficha(self, version: int, tipo_documental: str) -> Ficha:
        """La ficha del TD en esa versión. Lanza `FichaNoEncontrada` si no existe."""


def ficha_desde(modelo: dict, tipo_documental: str) -> Ficha:
    """Arma la ficha de un TD desde un modelo con la forma de `describir_modelo` más los elementos."""
    seccion = next((s for s in modelo["secciones"] if s["id"] == tipo_documental), None)
    if seccion is None:
        raise FichaNoEncontrada(f"La versión {modelo['version']} no tiene la sección {tipo_documental}")
    elementos = sorted(
        (e for e in modelo["elementos"] if e["seccion"] == tipo_documental),
        key=lambda e: e.get("orden", 0),
    )
    return Ficha(
        modelo=modelo["modelo"],
        version=modelo["version"],
        guia=modelo["guia_interpretacion"],
        diccionario=modelo["diccionario"],
        seccion=seccion,
        elementos=tuple(elementos),
    )


class FuenteModeloArchivo(FuenteModelo):
    """Versiones del modelo guardadas en archivos JSON, una versión por archivo.

    Cada archivo trae `modelo`, `version`, `guia_interpretacion`, `diccionario`,
    `secciones` y `elementos` (los de todas sus secciones, con la forma de
    `obtener_seccion`).
    """

    def __init__(self, *rutas: str | os.PathLike[str]) -> None:
        self._modelos: dict[int, dict] = {}
        for ruta in rutas:
            with open(ruta, encoding="utf-8") as archivo:
                modelo = json.load(archivo)
            if modelo["version"] in self._modelos:
                raise ValueError(f"La versión {modelo['version']} está en más de un archivo")
            self._modelos[modelo["version"]] = modelo

    def ficha(self, version: int, tipo_documental: str) -> Ficha:
        modelo = self._modelos.get(version)
        if modelo is None:
            raise FichaNoEncontrada(f"No existe la versión {version} del modelo")
        return ficha_desde(modelo, tipo_documental)


class FuenteQueGuarda(FuenteModelo):
    """Guarda cada ficha usada en `<carpeta>/v<versión>/<TD>.json`, para el visor.

    Lo guardado son metadatos del modelo (elementos, umbrales, reglas), sin datos
    de documentos.
    """

    def __init__(self, fuente: FuenteModelo, carpeta: str | os.PathLike[str]) -> None:
        self._fuente = fuente
        self.carpeta = os.fspath(carpeta)
        # Varios segmentos del mismo TD piden la ficha a la vez: se guarda una sola vez.
        self._candado = threading.Lock()

    def ficha(self, version: int, tipo_documental: str) -> Ficha:
        ficha = self._fuente.ficha(version, tipo_documental)
        ruta = os.path.join(self.carpeta, f"v{version}", f"{tipo_documental}.json")
        with self._candado:
            if not os.path.exists(ruta):
                os.makedirs(os.path.dirname(ruta), exist_ok=True)
                datos = {"modelo": ficha.modelo, "version": ficha.version, "seccion": ficha.seccion,
                         "elementos": list(ficha.elementos)}
                descriptor, temporal = tempfile.mkstemp(dir=os.path.dirname(ruta), prefix=".", suffix=".tmp")
                with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
                    json.dump(datos, archivo, ensure_ascii=False, indent=1)
                os.replace(temporal, ruta)
        return ficha
