"""El script de la muestra (T11), con una muestra inventada."""

import importlib.util
import json
from pathlib import Path

from fabrica import pdf

_spec = importlib.util.spec_from_file_location(
    "correr_muestra", Path(__file__).parents[1] / "scripts" / "correr_muestra.py")
correr_muestra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(correr_muestra)

MANIFIESTO = """tipo_documental,oferente,archivo,origen,nota
TD-03,Uno,x.pdf,Comprimido Uno/carta.pdf,
TD-16,Uno,x.pdf,Comprimido Uno/sub/compuesto.pdf (p2-3),
TD-07,Uno,x.pdf,Comprimido Uno/sub/compuesto.pdf (p5),
SIN CLASIFICAR,Uno,x.pdf,Comprimido Uno/raro.pdf,
TD-05,Dos,x.pdf,Otra/certificado.pdf,
TD-05,Dos,x.pdf,Otra/no-esta.pdf,
TD-01,Tres,x.pdf,Nada/fantasma.pdf,
"""


def _muestra(raiz):
    # Las carpetas no se llaman como los oferentes del manifiesto, como en la real.
    uno, dos = raiz / "muestra" / "B Empresa", raiz / "muestra" / "A Empresa"
    (uno / "sub").mkdir(parents=True)
    dos.mkdir(parents=True)
    (uno / "carta.pdf").write_bytes(pdf(1, "carta"))
    (uno / "sub" / "compuesto.pdf").write_bytes(pdf(6, "compuesto"))
    (uno / "raro.pdf").write_bytes(pdf(1, "raro"))
    (uno / "sin clasificar.pdf").write_bytes(pdf(1, "suelto"))
    (dos / "certificado.pdf").write_bytes(pdf(1, "certificado"))
    (raiz / "manifiesto.csv").write_text(MANIFIESTO, encoding="utf-8")


def test_corre_la_muestra_e_imprime_solo_conteos(tmp_path, capsys):
    _muestra(tmp_path)
    assert correr_muestra.main(["--manifiesto", str(tmp_path / "manifiesto.csv"),
                                "--muestra", str(tmp_path / "muestra")]) == 0
    salida = capsys.readouterr()
    resumen = json.loads(salida.out)
    assert resumen["oferentes"] == 2
    assert resumen["emparejamiento"] == {
        "archivos_por_paginas": 1, "carpetas_sin_clasificacion": 0, "filas_del_manifiesto": 7,
        "filas_sin_archivo": 2, "filas_usadas": 5, "huecos_como_td99": 3, "oferentes_en_el_manifiesto": 3,
        "oferentes_sin_carpeta": 1, "sin_clasificar_como_td99": 1,
    }
    # carta TD-03, compuesto p2-3 TD-16 y p5 TD-07, certificado TD-05. El resto, TD-99.
    assert resumen["solicitudes_por_td"] == {"TD-03": 1, "TD-05": 1, "TD-07": 1, "TD-16": 1}
    assert resumen["segmentos"] == {"pendiente": 4, "sin_extraccion": 5}
    assert (resumen["atascados"], resumen["mensajes_en_errores"]) == (0, {})
    for nombre in ("Empresa", "Uno", "carta", "compuesto", "Comprimido"):
        assert nombre not in salida.out + salida.err


def test_la_salida_se_conserva_solo_si_se_pide(tmp_path, capsys):
    _muestra(tmp_path)
    argumentos = ["--manifiesto", str(tmp_path / "manifiesto.csv"), "--muestra", str(tmp_path / "muestra")]
    assert correr_muestra.main([*argumentos, "--salida", str(tmp_path / "salida")]) == 0
    assert (tmp_path / "salida" / "estado.json").is_file()
    assert correr_muestra.main([*argumentos, "--salida", str(tmp_path / "salida")]) == 2
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    assert correr_muestra.main([*argumentos, "--salida", str(tmp_path / "repo" / "salida")]) == 2
