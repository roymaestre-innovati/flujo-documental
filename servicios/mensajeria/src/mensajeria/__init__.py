"""Mensajería compartida del flujo documental: colas, Service Bus y el bucle de
errores que corre cada manejador.

La usan el orquestador (módulo 5) y la extracción (módulo 3), sin depender uno
del otro. `Cola` y `ColaEnMemoria` en `cola`, `ColaServiceBus` en
`cola_servicebus`, `procesar_uno` y las clases de error en `errores`.
"""

VERSION = "0.1.0"
