"""Entrega y renovación contra las colas de desarrollo de Service Bus."""

import os
from time import monotonic, sleep

import pytest
from orquestador.cola_servicebus import cola_desde_entorno
from servicebus_azure import COLA_PRUEBA_AZURE, ESPERA_SERVICEBUS_AZURE_S

pytestmark = pytest.mark.azure(variable="SERVICEBUS_NAMESPACE")


def test_cola_azure_cuenta_la_primera_entrega_y_el_abandono(cola_servicebus_de_prueba, procesos_de_prueba):
    cola = cola_servicebus_de_prueba
    nombre = COLA_PRUEBA_AZURE
    id_mensaje = cola.publicar(nombre, {"id_proceso": procesos_de_prueba[0]})
    primera = cola.recibir(nombre)
    assert primera is not None and (primera.id, primera.entregas) == (id_mensaje, 1)
    cola.abandonar(primera)
    segunda = cola.recibir(nombre)
    assert segunda is not None and (segunda.id, segunda.entregas) == (id_mensaje, 2)
    cola.completar(segunda)


@pytest.mark.skipif(
    bool(os.environ.get("SERVICEBUS_NAMESPACE")) and os.environ.get("SERVICEBUS_PRUEBA_LARGA") != "1",
    reason="la prueba tarda 6 minutos; activar con SERVICEBUS_PRUEBA_LARGA=1",
)
def test_cola_azure_renueva_durante_seis_minutos(cola_servicebus_de_prueba, procesos_de_prueba):
    cola = cola_servicebus_de_prueba
    nombre = COLA_PRUEBA_AZURE
    id_mensaje = cola.publicar(nombre, {"id_proceso": procesos_de_prueba[0]})
    mensaje = cola.recibir(nombre)
    assert mensaje is not None and mensaje.id == id_mensaje and mensaje.bloqueo
    token = mensaje.bloqueo
    inicio = monotonic()
    print(f"Mensaje {id_mensaje} bloqueado. Esperando 6 minutos.", flush=True)

    with cola_desde_entorno(espera_recibir_s=ESPERA_SERVICEBUS_AZURE_S) as otra:
        # Abre el enlace antes de la primera lectura con la espera corta.
        otra.pendientes(nombre)
        for minuto in range(7):
            sleep(max(0, inicio + minuto * 60 - monotonic()))
            recibido = otra.recibir(nombre)
            if recibido is not None:
                if recibido.id == id_mensaje:
                    otra.completar(recibido)
                else:
                    otra.abandonar(recibido)
                pytest.fail(f"El segundo receptor recibió el mensaje {recibido.id} en el minuto {minuto}")
            if minuto:
                print(f"Minuto {minuto}/6. El segundo receptor sigue sin recibir el mensaje.", flush=True)

    assert mensaje.bloqueo == token
    cola.completar(mensaje)
    print(f"Mensaje {id_mensaje} completado con el bloqueo original.", flush=True)
