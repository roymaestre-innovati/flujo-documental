import datetime

import pytest

from extraccion.reloj import RelojManual, RelojSistema


def test_reloj_manual_avanza_al_dormir():
    reloj = RelojManual()
    inicio = reloj.ahora()
    reloj.dormir(2)
    reloj.dormir(4)
    assert reloj.esperas == [2, 4]
    assert reloj.ahora() - inicio == datetime.timedelta(seconds=6)
    assert reloj.monotono() == 6


def test_reloj_manual_no_retrocede_ni_acepta_fecha_sin_zona():
    with pytest.raises(ValueError):
        RelojManual().adelantar(-1)
    with pytest.raises(ValueError):
        RelojManual(datetime.datetime(2026, 1, 1))


def test_reloj_sistema_con_zona():
    assert RelojSistema().ahora().tzinfo is not None
