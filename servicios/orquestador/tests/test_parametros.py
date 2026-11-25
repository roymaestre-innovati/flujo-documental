"""El orden de los parámetros por posición no cambia con la mensajería compartida."""

from orquestador.parametros import Parametros


def test_por_posicion_van_en_el_orden_de_antes():
    p = Parametros(3, 120, 2, 20, 48, 1, 4, 2)
    assert (p.reintentos_transitorio, p.demora_base_s, p.reintentos_respuesta_invalida, p.max_esperas,
            p.horas_escalamiento, p.paralelo_normalizar, p.paralelo_bajar, p.espera_limite_estado_s) == (
        3, 120, 2, 20, 48, 1, 4, 2)
    assert (p.renovacion_bloqueo_max_s, p.reserva_normalizar_s) == (1800, 2400)


def test_los_campos_nuevos_van_solo_por_nombre():
    assert Parametros(renovacion_bloqueo_max_s=60, reserva_normalizar_s=90).reserva_normalizar_s == 90
