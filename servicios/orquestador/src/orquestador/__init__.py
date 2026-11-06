"""Orquestador del flujo documental (módulo 5, spec 005).

Lleva cada proceso de selección desde el aviso del módulo 1 hasta las solicitudes
de extracción: apertura, normalización, clasificación y estado. Cada pieza externa
(colas, estado, origen de los archivos, clasificador) queda detrás de una interfaz;
en esta entrega solo existen sus versiones locales.
"""

VERSION = "0.1.0"
CONTRATO = "modulo5-orquestador/0.1"
CONTRATO_EXTRACCION = "modulo3-extraccion/0.2"
