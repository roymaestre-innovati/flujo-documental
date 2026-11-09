"""Extracción de los datos de cada segmento de documento (módulo 3, spec 003, entrega 2).

Recibe una solicitud del contrato `modulo3-extraccion/0.2` (un segmento: documento,
páginas, tipo documental y versión del modelo) y devuelve un resultado del mismo
contrato. Por dentro: entrada, ficha del tipo documental, preprocesamiento, una
llamada al LLM y posvalidación determinista. Cada pieza externa (fuente del modelo
semántico, LLM, almacén de resultados) queda detrás de una interfaz; en las pruebas
solo se usan sus versiones locales.
"""

VERSION = "0.1.0"
CONTRATO = "modulo3-extraccion/0.2"
