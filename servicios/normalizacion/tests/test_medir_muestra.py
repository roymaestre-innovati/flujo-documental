"""Script de la muestra (T13): solo conteos, nunca nombres."""

import importlib.util
import json
from pathlib import Path

import pytest

import fabrica
from normalizacion import entrega as modulo_entrega

RUTA_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "medir_muestra.py"
_spec = importlib.util.spec_from_file_location("medir_muestra", RUTA_SCRIPT)
medir_muestra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(medir_muestra)

# Nombres de carpeta como los de una muestra real: no deben salir en la salida.
# Los oferentes se numeran en el orden de sus carpetas: CARPETA_1 es OF-001.
CARPETA_1 = "Constructora Ejemplo LTDA"
CARPETA_2 = "Juan Pérez Gómez"


@pytest.fixture
def muestra(tmp_path):
    carpeta = tmp_path / "muestra"
    uno = carpeta / CARPETA_1
    for caso in ("pdf_texto", "duplicados", "pdf_solo_restricciones", "pdf_firmado",
                 "pdf_firma_ilegible", "pdf_modificado_despues_de_firmar", "archivos_de_sistema",
                 "pdf_con_contrasena", "jpg", "pdf_danado_reparable"):
        fabrica.CASOS[caso](uno / caso)
    dos = carpeta / CARPETA_2
    for caso in ("pdf_escaneo_con_ocr", "pdf_vacio", "tiff_tres_paginas", "pdf_escaneo_sin_texto"):
        fabrica.CASOS[caso](dos / caso)
    (carpeta / ".oculta").mkdir()
    (carpeta / "suelto.pdf").write_bytes(fabrica.pdf_texto_bytes())
    return carpeta


def _correr(argumentos, capsys):
    codigo = medir_muestra.main([str(a) for a in argumentos])
    capturado = capsys.readouterr()
    return codigo, capturado.out, capturado.err


def test_json_con_los_conteos(muestra, capsys):
    codigo, salida, _ = _correr([muestra, "--json"], capsys)
    assert codigo == 0
    datos = json.loads(salida)
    uno, dos = datos["oferentes"]
    assert (uno["oferente"], dos["oferente"]) == ("OF-001", "OF-002")
    assert uno["duplicados"] == 1
    assert uno["con_restricciones"] == 1
    assert uno["con_firma_digital"] == 3
    assert (uno["firmas_leidas"], uno["firmas_no_leidas"], uno["firmas_no_integras"]) == (2, 1, 1)
    assert uno["errores"] == {"CONTRASENA": 1}
    assert uno["descartados"] == 5 and uno["descartados_por_motivo"] == {
        "archivo_sistema_mac": 4, "archivo_sistema_windows": 1}
    assert uno["reparados"] == 1
    assert uno["convertidos"] == 1  # el JPG
    # OF-002: 1 + 1 + 3 + 1 páginas, una de cada tipo de escaneo.
    assert dos["paginas_unicas"] == 6
    assert dos["tipos_de_pagina"] == {"texto": 0, "escaneo_con_ocr": 1, "imagen": 4, "vacia": 1}
    total = datos["total"]
    assert total["paginas_unicas"] == uno["paginas_unicas"] + dos["paginas_unicas"]
    assert sum(total["tipos_de_pagina"].values()) == total["paginas_unicas"]
    assert sum(datos["proporcion_tipos_de_pagina"].values()) == pytest.approx(1.0)
    assert datos["diseno"]["paginas_unicas"] == 415


def test_tabla_con_lo_que_espera_el_diseno(muestra, capsys):
    codigo, salida, _ = _correr([muestra], capsys)
    assert codigo == 0
    assert "OF-001" in salida and "OF-002" in salida and "TOTAL" in salida
    assert "A3. Conteos frente al diseño" in salida and "(diseño: unas 415)" in salida
    assert "A4. Proporción de tipos de página" in salida and "(diseño: 76 %)" in salida
    assert "A5. Tiempo por oferente" in salida


@pytest.mark.parametrize("formato", [[], ["--json"]])
def test_nunca_imprime_nombres(muestra, capsys, formato):
    _, salida, errores = _correr([muestra, "--detalle", *formato], capsys)
    for texto in (salida, errores):
        for nombre in (CARPETA_1, CARPETA_2, "Constructora", "Pérez", "carta_presentacion",
                       "certificado", str(muestra), "suelto", fabrica.FIRMANTE_DIGITAL):
            assert nombre not in texto


def test_la_salida_temporal_se_borra(muestra, capsys, monkeypatch, tmp_path):
    temporales = []
    original = medir_muestra.tempfile.TemporaryDirectory

    def registrar(*argumentos, **opciones):
        temporal = original(*argumentos, dir=tmp_path, **opciones)
        temporales.append(Path(temporal.name))
        return temporal

    monkeypatch.setattr(medir_muestra.tempfile, "TemporaryDirectory", registrar)
    _correr([muestra, "--json"], capsys)
    assert temporales and not any(t.exists() for t in temporales)


def test_con_salida_se_conserva(muestra, capsys, tmp_path):
    _correr([muestra, "--json", "--salida", tmp_path / "salida"], capsys)
    assert (tmp_path / "salida" / "MUESTRA" / "OF-001" / "manifiesto.json").is_file()
    assert (tmp_path / "salida" / "MUESTRA" / "OF-002" / "manifiesto.json").is_file()


def test_una_falla_inesperada_no_frena_a_los_demas(muestra, capsys, monkeypatch):
    original = modulo_entrega.normalizar_entrega

    def falla_en_el_primero(carpeta, proceso, oferente, *resto, **opciones):
        if oferente == "OF-001":
            raise modulo_entrega.ErrorEntrega(["OF-001-000000000000"])
        return original(carpeta, proceso, oferente, *resto, **opciones)

    monkeypatch.setattr(medir_muestra, "normalizar_entrega", falla_en_el_primero)
    codigo, salida, _ = _correr([muestra], capsys)
    assert codigo == 1
    assert "FALLA INESPERADA" in salida and "Falla inesperada en: OF-001" in salida
    assert "OF-002" in salida


def test_carpeta_sin_oferentes(tmp_path, capsys):
    (tmp_path / "vacia").mkdir()
    with pytest.raises(SystemExit) as salida:
        medir_muestra.main([str(tmp_path / "vacia")])
    assert salida.value.code == 2
