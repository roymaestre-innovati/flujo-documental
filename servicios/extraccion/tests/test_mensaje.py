"""El mensaje para el LLM: prompt, guía, ficha y contenido del segmento (R35)."""

import json
import re

import pytest

from extraccion.entrada import Entrada, preparar
from extraccion.llm import LLMFalso
from extraccion.mensaje import VERSION_PROMPT, huella_prompt, mensajes, prompt
from extraccion.preproceso import preparar_contenido

from fabrica import Corrida, pdf_mixto, xlsx

HUELLAS = {
    "extraccion/prompt@1": "3b560c0b9958f795c602bbee7653e74a15b668d2cf0caa4c1b2b72bdf5efec19",
}
"""Huella de `datos/prompt.md` por versión: si el prompt cambia, hay que subir VERSION_PROMPT."""


@pytest.fixture(scope="module")
def mixto(tmp_path_factory):
    corrida = Corrida(tmp_path_factory.mktemp("corrida"))
    (documento,) = corrida.normalizar({"mixto.pdf": pdf_mixto()})
    return corrida, documento


def _armar(mixto, fuente_modelo, desde=1, hasta=6, td="TD-16", anexos=(), **extra):
    corrida, documento = mixto
    entrada = preparar(corrida.solicitud(documento, desde, hasta, td, **extra), corrida.almacen)
    if anexos:
        entrada = Entrada(entrada.solicitud, entrada.lectura, entrada.pdf, tuple(anexos))
    ficha = fuente_modelo.ficha(entrada.solicitud["version_modelo"], td)
    return mensajes(entrada, ficha, preparar_contenido(entrada))


def _textos(lista):
    return [p["text"] for p in lista[1]["content"] if p["type"] == "text"]


def _imagenes(lista):
    return [p["image_url"] for p in lista[1]["content"] if p["type"] == "image_url"]


def test_cada_cambio_del_prompt_sube_su_version():
    assert HUELLAS.get(VERSION_PROMPT) == huella_prompt(), "Cambió datos/prompt.md: subir VERSION_PROMPT y anotar su huella"


def test_prompt_sin_herramientas_ni_parametros_del_proceso():
    texto = prompt()
    assert "No tienes herramientas" in texto
    assert "No recibes parámetros del proceso ni datos de otros documentos" in texto
    assert "Si te entregan parámetros" not in texto  # la línea que quita D8


def test_sistema_es_prompt_mas_guia_de_la_version(mixto, fuente_modelo):
    sistema = _armar(mixto, fuente_modelo)[0]
    assert sistema["role"] == "system"
    assert sistema["content"].startswith("# Rol")
    assert sistema["content"].endswith(fuente_modelo.ficha(21, "TD-16").guia.strip())


def test_sistema_igual_para_todos_los_segmentos(mixto, fuente_modelo):
    # Prefijo fijo para la caché de prompt: no depende del segmento ni del TD.
    uno = _armar(mixto, fuente_modelo, 1, 2, "TD-16")[0]
    otro = _armar(mixto, fuente_modelo, 3, 6, "TD-29")[0]
    assert uno == otro


def test_encabezado_y_ficha(mixto, fuente_modelo):
    textos = _textos(_armar(mixto, fuente_modelo, 2, 3, tipo_oferente="PJ_NAL"))
    assert textos[0].splitlines() == [
        "Tipo documental: TD-16 (Certificación de aportes a seguridad social y parafiscales)",
        "Versión del modelo: 21",
        "Tipo de oferente: PJ_NAL",
        "Páginas del segmento: de la 2 a la 3, numeradas sobre el documento completo.",
    ]
    ficha = json.loads(re.search(r"```json\n(.*)\n```", textos[1], re.S).group(1))
    assert [e["id_tecnico"] for e in ficha] == [e["id_tecnico"] for e in fuente_modelo.ficha(21, "TD-16").a_extraer()]


def test_sin_tipo_de_oferente(mixto, fuente_modelo):
    assert "Tipo de oferente: no informado" in _textos(_armar(mixto, fuente_modelo, 1, 1))[0]


def test_solo_las_paginas_del_segmento_con_su_numero(mixto, fuente_modelo):
    textos = _textos(_armar(mixto, fuente_modelo, 3, 5))
    rotulos = [t.splitlines()[0] for t in textos if t.startswith("--- Página")]
    assert rotulos == ["--- Página 3 ---", "--- Página 4 ---", "--- Página 5 ---"]
    assert "--- Página 3 ---\n(sin texto: ver la imagen)" in textos
    assert any(t.startswith("--- Página 4 ---\nTexto de la capa del escáner") for t in textos)
    assert "--- Página 5 ---\n(página en blanco)" in textos


def test_imagenes_y_firmas_en_su_lugar(mixto, fuente_modelo):
    contenido = _armar(mixto, fuente_modelo, 1, 6)[1]["content"]
    secuencia = [p["text"].splitlines()[0] if p["type"] == "text" else f"imagen {p['image_url']['detail']}" for p in contenido[2:]]
    assert secuencia == [
        "--- Página 1 ---",
        "--- Página 2 ---", "imagen high", "Ampliación de la línea de firma 1 de la página 2:", "imagen high",
        "--- Página 3 ---", "imagen original",
        "--- Página 4 ---", "imagen original", "Ampliación de la línea de firma 1 de la página 4:", "imagen high",
        "--- Página 5 ---",
        "--- Página 6 ---", "imagen high", "Ampliación de la línea de firma 1 de la página 6:", "imagen high",
    ]
    assert all(i["url"].startswith("data:image/jpeg;base64,") for i in _imagenes(_armar(mixto, fuente_modelo, 2, 2)))


def test_anexo_al_final(mixto, fuente_modelo):
    textos = _textos(_armar(mixto, fuente_modelo, 1, 1, anexos=[xlsx()]))
    assert textos[-1].startswith("--- Anexo 1: valores de la hoja de cálculo original ---\nHoja: Experiencia")


def test_anexo_ilegible_no_va(mixto, fuente_modelo):
    textos = _textos(_armar(mixto, fuente_modelo, 1, 1, anexos=[b"no es una hoja"]))
    assert not any("Anexo" in t for t in textos)


def test_el_llm_falso_reconoce_el_tipo_documental(mixto, fuente_modelo):
    llm = LLMFalso(por_tipo={"TD-29": "{}"})
    assert llm.responder(_armar(mixto, fuente_modelo, 1, 1, "TD-29")).texto == "{}"
