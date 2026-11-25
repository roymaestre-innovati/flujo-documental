"""La mensajería se usa sola: no depende del orquestador ni de la extracción."""

import subprocess
import sys


def test_se_importa_sin_el_orquestador_ni_la_extraccion():
    programa = """
import sys
sys.modules['orquestador'] = None
sys.modules['extraccion'] = None
from mensajeria import cola, cola_servicebus, errores, parametros, registros, reloj
from mensajeria.cola import ColaEnMemoria
from mensajeria.errores import procesar_uno
assert cola_servicebus.ColaServiceBus
"""
    ejecucion = subprocess.run([sys.executable, "-c", programa], capture_output=True, text=True)
    assert ejecucion.returncode == 0, ejecucion.stderr


def test_el_bucle_completa_un_mensaje_en_memoria():
    from mensajeria.cola import ColaEnMemoria
    from mensajeria.errores import procesar_uno
    from mensajeria.reloj import RelojManual

    class Manejador:
        cola = "normalizar"
        vistos = []

        def procesar(self, cuerpo):
            self.vistos.append(cuerpo)

        def al_fallar(self, cuerpo, motivo):
            raise AssertionError(motivo)

    cola = ColaEnMemoria(RelojManual())
    cola.publicar("normalizar", {"id_proceso": "SR1", "entrega": "OF-001"})
    manejador = Manejador()
    resultado = procesar_uno(cola, manejador)
    assert resultado.desenlace == "ok"
    assert manejador.vistos == [{"id_proceso": "SR1", "entrega": "OF-001"}]
    assert procesar_uno(cola, manejador) is None
