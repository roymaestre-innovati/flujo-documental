"""El mensaje para el LLM: una sola vuelta, sin herramientas (R35, decisión 26).

- **Sistema:** el prompt del servicio (`datos/prompt.md`) y la guía de
  interpretación de la versión fijada del modelo. Cambia solo con la versión del
  prompt o del modelo, así que sirve de prefijo fijo para la caché de prompt.
- **Usuario:** el encabezado (tipo documental, versión, tipo de oferente,
  páginas), la ficha del TD en JSON y el contenido, página por página.

El encabezado empieza con `Tipo documental: TD-NN`, que el LLM falso usa para
elegir su respuesta. No se mandan parámetros del proceso ni datos de otros
documentos (D8).
"""

import base64
import hashlib
import json
from functools import cache
from importlib import resources

from .entrada import Entrada
from .ficha import Ficha
from .preproceso import Contenido, Imagen

VERSION_PROMPT = "extraccion/prompt@1"
"""Sube cada vez que cambia `datos/prompt.md` (una prueba lo exige)."""


@cache
def prompt() -> str:
    return resources.files("extraccion").joinpath("datos/prompt.md").read_text(encoding="utf-8").strip()


def huella_prompt() -> str:
    return hashlib.sha256(prompt().encode("utf-8")).hexdigest()


def _imagen(imagen: Imagen) -> dict:
    url = "data:image/jpeg;base64," + base64.b64encode(imagen.jpeg).decode("ascii")
    return {"type": "image_url", "image_url": {"url": url, "detail": imagen.detalle}}


def _texto(texto: str) -> dict:
    return {"type": "text", "text": texto}


def encabezado(entrada: Entrada, ficha: Ficha) -> str:
    solicitud = entrada.solicitud
    return "\n".join([
        f"Tipo documental: {ficha.tipo_documental} ({ficha.seccion['nombre']})",
        f"Versión del modelo: {ficha.version}",
        f"Tipo de oferente: {solicitud.get('tipo_oferente') or 'no informado (las condiciones que dependen de él quedan sin evaluar)'}",
        f"Páginas del segmento: de la {entrada.desde} a la {entrada.hasta}, numeradas sobre el documento completo.",
    ])


def mensajes(entrada: Entrada, ficha: Ficha, contenido: Contenido) -> list[dict]:
    """Los mensajes de chat completions para extraer un segmento."""
    sistema = f"{prompt()}\n\n{ficha.guia.strip()}"
    partes = [
        _texto(encabezado(entrada, ficha)),
        _texto("Ficha del tipo documental (elementos, en orden):\n```json\n"
               + json.dumps(list(ficha.a_extraer()), ensure_ascii=False, indent=1) + "\n```"),
    ]
    for pagina in contenido.paginas:
        rotulo = f"--- Página {pagina.numero} ---"
        if pagina.texto:
            aviso = "Texto de la capa del escáner (puede estar incompleto):\n" if pagina.texto_de_escaner else ""
            partes.append(_texto(f"{rotulo}\n{aviso}{pagina.texto}"))
        elif pagina.imagen:
            partes.append(_texto(f"{rotulo}\n(sin texto: ver la imagen)"))
        else:
            partes.append(_texto(f"{rotulo}\n(página en blanco)"))
        if pagina.imagen:
            partes.append(_imagen(pagina.imagen))
        for n, firma in enumerate(pagina.firmas, start=1):
            partes.append(_texto(f"Ampliación de la línea de firma {n} de la página {pagina.numero}:"))
            partes.append(_imagen(firma))
    for anexo in contenido.anexos:
        if anexo.texto is not None:
            recorte = " (recortada: solo el comienzo)" if anexo.recortado else ""
            partes.append(_texto(f"--- Anexo {anexo.numero}: valores de la hoja de cálculo original{recorte} ---\n{anexo.texto}"))
    return [{"role": "system", "content": sistema}, {"role": "user", "content": partes}]
