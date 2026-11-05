"""Entrega completa, de punta a punta: R1 a R25 juntos, A1 y A2."""

import copy
import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest

import fabrica
from normalizacion import entrega as modulo_entrega
from normalizacion import registros
from normalizacion.almacen import AlmacenLocal
from normalizacion.cli import main
from normalizacion.entrega import ErrorEntrega, normalizar_entrega
from normalizacion.parametros import PARAMETROS

from contrato import validador

PROCESO = "SR0000000001"
OFERENTE = "OF-002"

# Casos que necesitan LibreOffice para convertirse en la entrega.
CONVERTIDOS_CON_LIBREOFFICE = {"docx", "odt", "doc", "xlsx_ancho", "xlsx_con_vinculos", "xls", "ods", "odt_con_macro", "extension_falsa", "pptx"}
CASOS_SIN_LIBREOFFICE = [c for c in fabrica.CASOS if c not in CONVERTIDOS_CON_LIBREOFFICE | fabrica.CASOS_CON_LIBREOFFICE]


def _armar(carpeta: Path, casos) -> dict[str, list[str]]:
    """Cada caso en su subcarpeta. Devuelve, por caso, las rutas relativas."""
    rutas = {}
    for caso in casos:
        rutas[caso] = [r.relative_to(carpeta).as_posix() for r in fabrica.CASOS[caso](carpeta / caso)]
    return rutas


def _normalizar(carpeta, salida, **opciones):
    return normalizar_entrega(carpeta, PROCESO, OFERENTE, AlmacenLocal(salida), **opciones)


def _leer_json(uri_o_ruta):
    ruta = Path(uri_o_ruta.removeprefix("file://")) if isinstance(uri_o_ruta, str) else uri_o_ruta
    return json.loads(ruta.read_text(encoding="utf-8"))


def _ruta(uri: str) -> Path:
    return Path(uri.removeprefix("file://"))


def _sin_ejecucion(manifiesto):
    copia = copy.deepcopy(manifiesto)
    copia.pop("ejecucion")
    return copia


def _por_ruta(manifiesto):
    return {a["ruta_origen"]: a for a in manifiesto["archivos"]}


def _validar_todo(manifiesto, salida):
    """Manifiesto, lecturas y palabras cumplen el contrato y son coherentes entre sí."""
    validador("manifiesto").validate(manifiesto)
    rutas = [a["ruta_origen"] for a in manifiesto["archivos"]]
    assert rutas == sorted(rutas)
    for entrada in manifiesto["archivos"]:
        if entrada["estado"] != "normalizado":
            continue
        pdf = _ruta(entrada["pdf"]).read_bytes()
        lectura = _leer_json(entrada["lectura"])
        validador("lectura").validate(lectura)
        assert lectura["id_documento"] == entrada["id_documento"]
        assert lectura["hash_pdf"] == hashlib.sha256(pdf).hexdigest()
        assert len(lectura["paginas"]) == entrada["paginas"]
        assert entrada["paginas_sin_texto"] == [p["pagina"] for p in lectura["paginas"] if p["caracteres"] == 0]
        assert lectura["firma_digital"] == entrada["firma_digital"]
        palabras = _leer_json(lectura["palabras"])
        validador("palabras").validate(palabras)
        assert len(palabras["paginas"]) == entrada["paginas"]
        if entrada["anexo_nativo"]:
            assert _ruta(entrada["anexo_nativo"]).is_file()


# Entrega completa ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def entrega_completa(tmp_path_factory):
    if not shutil.which("soffice"):
        pytest.skip("soffice (LibreOffice) no está instalado")
    base = tmp_path_factory.mktemp("completa")
    rutas = _armar(base / "entrega", fabrica.CASOS)
    resultado = _normalizar(base / "entrega", base / "salida")
    return base, rutas, resultado


@pytest.mark.libreoffice
def test_entrega_completa_cumple_el_contrato(entrega_completa):
    base, _, resultado = entrega_completa
    _validar_todo(resultado.manifiesto, base / "salida")
    escrito = _leer_json(base / "salida" / PROCESO / OFERENTE / "manifiesto.json")
    assert escrito == resultado.manifiesto


ESPERADOS = {
    # caso: (estado, tipo_origen, código de error)
    "pdf_texto": ("normalizado", "pdf", None),
    "pdf_escaneo_sin_texto": ("normalizado", "pdf", None),
    "pdf_escaneo_con_ocr": ("normalizado", "pdf", None),
    "pdf_vacio": ("normalizado", "pdf", None),
    "pdf_sin_paginas": ("error_entrada", "pdf", "SIN_PAGINAS"),
    "pdf_rotado": ("normalizado", "pdf", None),
    "pdf_con_contrasena": ("error_entrada", "pdf", "CONTRASENA"),
    "pdf_solo_restricciones": ("normalizado", "pdf", None),
    "pdf_danado_reparable": ("normalizado", "pdf", None),
    "pdf_danado_irreparable": ("error_entrada", "pdf", "DANADO"),
    "pdf_firmado": ("normalizado", "pdf", None),
    "pdf_modificado_despues_de_firmar": ("normalizado", "pdf", None),
    "pdf_firma_ilegible": ("normalizado", "pdf", None),
    "pdf_firmado_con_sello_de_tiempo": ("normalizado", "pdf", None),
    "docx": ("normalizado", "docx", None),
    "odt": ("normalizado", "odt", None),
    "doc": ("normalizado", "doc", None),
    "xlsx_ancho": ("normalizado", "xlsx", None),
    "xlsx_con_vinculos": ("normalizado", "xlsx", None),
    "xls": ("normalizado", "xls", None),
    "ods": ("normalizado", "ods", None),
    "docx_con_contrasena": ("error_entrada", "no_soportado", "CONTRASENA"),
    "xlsx_con_contrasena": ("error_entrada", "no_soportado", "CONTRASENA"),
    "odt_con_macro": ("normalizado", "odt", None),
    "jpg": ("normalizado", "imagen", None),
    "png": ("normalizado", "imagen", None),
    "png_transparente": ("normalizado", "imagen", None),
    "tiff_tres_paginas": ("normalizado", "imagen", None),
    "extension_falsa": ("normalizado", "docx", None),
    "pdf_anclas": ("normalizado", "pdf", None),
    "pptx": ("normalizado", "pptx", None),
    "ppt": ("normalizado", "ppt", None),
    "odp": ("normalizado", "odp", None),
}


@pytest.mark.libreoffice
@pytest.mark.parametrize("caso", ESPERADOS)
def test_entrega_completa_cada_caso(entrega_completa, caso):
    _, rutas, resultado = entrega_completa
    (ruta,) = rutas[caso]
    entrada = _por_ruta(resultado.manifiesto)[ruta]
    estado, tipo_origen, codigo = ESPERADOS[caso]
    assert (entrada["estado"], entrada["tipo_origen"]) == (estado, tipo_origen)
    assert (entrada["error"] or {}).get("codigo") == codigo


@pytest.mark.libreoffice
def test_entrega_completa_detalles(entrega_completa):
    base, rutas, resultado = entrega_completa
    archivos = _por_ruta(resultado.manifiesto)

    def entrada(caso, indice=0):
        return archivos[rutas[caso][indice]]

    def original(caso):
        return (base / "entrega" / rutas[caso][0]).read_bytes()

    # R11: el PDF que viene bien se usa tal cual; R10: el firmado no se reescribe.
    for caso in ("pdf_texto", "pdf_firmado", "pdf_solo_restricciones"):
        assert _ruta(entrada(caso)["pdf"]).read_bytes() == original(caso)
    # R12: el reparado es una copia aparte.
    assert entrada("pdf_danado_reparable")["reparado"] is True
    assert _ruta(entrada("pdf_danado_reparable")["pdf"]).read_bytes() != original("pdf_danado_reparable")
    # R13
    assert entrada("pdf_solo_restricciones")["restricciones"] is True
    assert entrada("pdf_texto")["restricciones"] is False
    # Documentos que no abren: restricciones y firma en null ("no se sabe").
    for caso in ("pdf_con_contrasena", "pdf_danado_irreparable", "docx_con_contrasena"):
        assert entrada(caso)["restricciones"] is None and entrada(caso)["firma_digital"] is None
    assert entrada("pdf_con_contrasena")["error"]["detalle"].startswith("El PDF pide contraseña")
    assert entrada("docx_con_contrasena")["error"]["detalle"].startswith("El archivo pide contraseña")
    # R15
    (firma,) = entrada("pdf_firmado")["firma_digital"]
    assert firma["leida"] and firma["integro"] and firma["firmante"] == fabrica.FIRMANTE_DIGITAL
    (firma,) = entrada("pdf_modificado_despues_de_firmar")["firma_digital"]
    assert firma["leida"] and firma["integro"] is False
    (firma,) = entrada("pdf_firma_ilegible")["firma_digital"]
    assert firma == {"firmante": None, "fecha": None, "integro": None, "formato": "adbe.pkcs7.sha1", "leida": False}
    (firma,) = entrada("pdf_firmado_con_sello_de_tiempo")["firma_digital"]
    assert firma["leida"] and firma["formato"] == "adbe.pkcs7.detached"
    assert entrada("docx")["firma_digital"] == []
    # R9: la hoja de cálculo trae su original como anexo.
    for caso, extension in (("xlsx_ancho", "xlsx"), ("xls", "xls"), ("ods", "ods")):
        anexo = _ruta(entrada(caso)["anexo_nativo"])
        assert anexo.suffix == f".{extension}"
        assert anexo.read_bytes() == original(caso)
    assert entrada("docx")["anexo_nativo"] is None
    # R8: el TIFF de tres páginas da tres páginas.
    assert entrada("tiff_tres_paginas")["paginas"] == 3
    # R7: la macro no se ejecutó.
    assert not (base / "entrega" / "odt_con_macro" / fabrica.MARCA_MACRO).exists()
    # Rotación y lectura.
    lectura = _leer_json(entrada("pdf_rotado")["lectura"])
    assert lectura["paginas"][0]["rotacion"] == 90
    tipos = [_leer_json(entrada(c)["lectura"])["paginas"][0]["tipo"] for c in (
        "pdf_texto", "pdf_escaneo_con_ocr", "pdf_escaneo_sin_texto", "pdf_vacio")]
    assert tipos == ["texto", "escaneo_con_ocr", "imagen", "vacia"]
    anclas = _leer_json(entrada("pdf_anclas")["lectura"])["paginas"][0]["anclas"]
    assert {a["tipo"] for a in anclas} == {"linea_firma", "casilla", "tabla_si_no"}


@pytest.mark.libreoffice
def test_entrega_completa_no_soportados_descartados_y_duplicados(entrega_completa):
    _, rutas, resultado = entrega_completa
    archivos = _por_ruta(resultado.manifiesto)
    # R16 y R6
    for ruta in rutas["no_soportados"]:
        assert archivos[ruta]["error"]["codigo"] == "NO_SOPORTADO"
        assert archivos[ruta]["tipo_origen"] == "no_soportado"
    # R2: descartados por nombre y por contenido, con su motivo, y fuera de archivos.
    descartados = {d["ruta_origen"]: d["motivo"] for d in resultado.manifiesto["descartados"]}
    for ruta in rutas["archivos_de_sistema"] + rutas["appledouble_sin_prefijo"]:
        assert ruta in descartados and ruta not in archivos
    assert descartados["archivos_de_sistema/imagenes/Thumbs.db"] == "archivo_sistema_windows"
    # R4: la copia apunta al original y repite sus datos.
    primero, segundo = (archivos[r] for r in rutas["duplicados"])
    assert primero["estado"] == "normalizado" and segundo["estado"] == "duplicado"
    assert segundo["duplicado_de"] == primero["id_documento"]
    for campo in ("hash", "tipo_origen", "pdf", "lectura", "paginas", "paginas_sin_texto", "restricciones", "firma_digital", "reparado"):
        assert segundo[campo] == primero[campo]
    # Conteos por tipo de página para el resumen.
    assert sum(resultado.tipos_de_pagina.values()) == sum(
        a["paginas"] for a in resultado.manifiesto["archivos"] if a["estado"] == "normalizado"
    )


# Determinismo (R23 a R25, A2) -------------------------------------------------------------


def _foto(salida: Path) -> dict[str, bytes]:
    return {str(p.relative_to(salida)): p.read_bytes() for p in sorted(salida.rglob("*")) if p.is_file()}


@pytest.mark.libreoffice
def test_a2_dos_corridas_dan_lo_mismo_salvo_la_ejecucion(tmp_path):
    _armar(tmp_path / "entrega", fabrica.CASOS)
    primera = _normalizar(tmp_path / "entrega", tmp_path / "salida")
    foto = _foto(tmp_path / "salida")
    segunda = _normalizar(tmp_path / "entrega", tmp_path / "salida", forzar=True)
    assert segunda.reusados == 0
    assert _sin_ejecucion(primera.manifiesto) == _sin_ejecucion(segunda.manifiesto)
    nueva = _foto(tmp_path / "salida")
    manifiesto = f"{PROCESO}/{OFERENTE}/manifiesto.json"
    assert set(foto) == set(nueva)
    assert {k: v for k, v in foto.items() if k != manifiesto} == {k: v for k, v in nueva.items() if k != manifiesto}


def test_a2_sin_libreoffice(tmp_path):
    _armar(tmp_path / "entrega", CASOS_SIN_LIBREOFFICE)
    primera = _normalizar(tmp_path / "entrega", tmp_path / "salida")
    foto = _foto(tmp_path / "salida")
    segunda = _normalizar(tmp_path / "entrega", tmp_path / "salida", forzar=True)
    _validar_todo(segunda.manifiesto, tmp_path / "salida")
    assert _sin_ejecucion(primera.manifiesto) == _sin_ejecucion(segunda.manifiesto)
    manifiesto = f"{PROCESO}/{OFERENTE}/manifiesto.json"
    assert {k: v for k, v in foto.items() if k != manifiesto} == {
        k: v for k, v in _foto(tmp_path / "salida").items() if k != manifiesto
    }


# Idempotencia ----------------------------------------------------------------------------------


@pytest.fixture
def entrega_chica(tmp_path):
    rutas = _armar(tmp_path / "entrega", ["pdf_texto", "jpg", "duplicados", "pdf_con_contrasena", "archivos_de_sistema"])
    return tmp_path, rutas


def _prohibir_procesar(monkeypatch):
    def prohibido(*argumentos, **opciones):
        raise AssertionError("No debía volver a leer")

    monkeypatch.setattr(modulo_entrega, "leer", prohibido)


def test_idempotencia_reusa_lo_que_no_cambio(entrega_chica, monkeypatch):
    base, _ = entrega_chica
    primera = _normalizar(base / "entrega", base / "salida")
    _prohibir_procesar(monkeypatch)
    segunda = _normalizar(base / "entrega", base / "salida")
    assert segunda.reusados == 3  # pdf_texto, jpg y el original de los duplicados
    assert _sin_ejecucion(segunda.manifiesto) == _sin_ejecucion(primera.manifiesto)
    assert segunda.tipos_de_pagina == primera.tipos_de_pagina


def test_idempotencia_procesa_lo_que_cambio(entrega_chica):
    base, rutas = entrega_chica
    _normalizar(base / "entrega", base / "salida")
    (base / "entrega" / rutas["pdf_texto"][0]).write_bytes(fabrica.pdf_texto_bytes(paginas=2))
    segunda = _normalizar(base / "entrega", base / "salida")
    assert segunda.reusados == 2
    assert _por_ruta(segunda.manifiesto)[rutas["pdf_texto"][0]]["paginas"] == 2


def test_forzar_procesa_todo(entrega_chica):
    base, _ = entrega_chica
    _normalizar(base / "entrega", base / "salida")
    assert _normalizar(base / "entrega", base / "salida", forzar=True).reusados == 0


def test_otra_version_de_parametros_procesa_todo(entrega_chica):
    import dataclasses

    base, _ = entrega_chica
    _normalizar(base / "entrega", base / "salida")
    otros = dataclasses.replace(PARAMETROS, version="2")
    segunda = _normalizar(base / "entrega", base / "salida", parametros=otros)
    assert segunda.reusados == 0
    assert segunda.manifiesto["version_parametros"] == "2"


def test_si_falta_un_archivo_del_almacen_se_procesa_de_nuevo(entrega_chica):
    base, rutas = entrega_chica
    primera = _normalizar(base / "entrega", base / "salida")
    _ruta(_por_ruta(primera.manifiesto)[rutas["jpg"][0]]["lectura"]).unlink()
    assert _normalizar(base / "entrega", base / "salida").reusados == 2


# Errores: R17 y clase 4 ----------------------------------------------------------------------------


def test_r17_un_error_del_documento_no_frena_a_los_demas(entrega_chica):
    base, rutas = entrega_chica
    resultado = _normalizar(base / "entrega", base / "salida")
    archivos = _por_ruta(resultado.manifiesto)
    assert archivos[rutas["pdf_con_contrasena"][0]]["estado"] == "error_entrada"
    assert archivos[rutas["pdf_texto"][0]]["estado"] == "normalizado"
    assert archivos[rutas["jpg"][0]]["estado"] == "normalizado"


def test_un_bug_se_relanza_al_final_sin_manifiesto(entrega_chica, monkeypatch):
    base, rutas = entrega_chica
    leer_real = modulo_entrega.leer

    def falla_con_la_foto(datos, id_documento, *resto, **opciones):
        resultado = leer_real(datos, id_documento, *resto, **opciones)
        if resultado.lectura["paginas"][0]["tipo"] == "imagen":
            raise ValueError("cedula_representante.jpg con datos personales")
        return resultado

    monkeypatch.setattr(modulo_entrega, "leer", falla_con_la_foto)
    salida = io.StringIO()
    registros.configurar(salida=salida)
    with pytest.raises(ErrorEntrega) as error:
        _normalizar(base / "entrega", base / "salida")
    # Solo el documento con la falla, y sin su nombre.
    (fallido,) = error.value.id_documentos
    assert fallido.startswith("OF-002-")
    assert "cedula" not in str(error.value)
    # Lo demás se escribió; el manifiesto no.
    oferente = base / "salida" / PROCESO / OFERENTE
    assert not (oferente / "manifiesto.json").exists()
    assert len(list((oferente / "lectura").iterdir())) == 2
    # El registro dice qué falló y dónde, sin el mensaje de la excepción.
    lineas = [json.loads(linea) for linea in salida.getvalue().splitlines()]
    (falla,) = [linea for linea in lineas if linea["nivel"] == "ERROR" and "excepcion" in linea]
    assert falla["id_documento"] == fallido
    assert falla["excepcion"].startswith("ValueError en test_entrega.py:")
    assert "cedula" not in salida.getvalue()


def test_si_el_original_falla_la_copia_tambien(tmp_path, monkeypatch):
    _armar(tmp_path / "entrega", ["duplicados"])

    def falla(*argumentos, **opciones):
        raise RuntimeError("bug")

    monkeypatch.setattr(modulo_entrega, "leer", falla)
    with pytest.raises(ErrorEntrega) as error:
        _normalizar(tmp_path / "entrega", tmp_path / "salida")
    assert len(error.value.id_documentos) == 2


# Registros ------------------------------------------------------------------------------------------


def test_registros_en_json_sin_datos_personales(entrega_chica):
    base, rutas = entrega_chica
    salida = io.StringIO()
    registros.configurar(salida=salida)
    _normalizar(base / "entrega", base / "salida")
    lineas = [json.loads(linea) for linea in salida.getvalue().splitlines()]
    assert lineas
    for linea in lineas:
        assert linea["id_proceso"] == PROCESO and linea["id_oferente"] == OFERENTE
    por_documento = [linea for linea in lineas if "id_documento" in linea]
    assert por_documento and all(len(linea["hash"]) == 12 for linea in por_documento)
    texto = salida.getvalue()
    for nombres in rutas.values():
        for ruta in nombres:
            assert Path(ruta).stem not in texto
    assert fabrica.OFERENTE not in texto and "CARTA" not in texto


# Otros -------------------------------------------------------------------------------------------------


def test_entrega_del_proceso(tmp_path):
    _armar(tmp_path / "entrega", ["pdf_texto"])
    resultado = normalizar_entrega(tmp_path / "entrega", PROCESO, None, AlmacenLocal(tmp_path / "salida"))
    validador("manifiesto").validate(resultado.manifiesto)
    assert resultado.manifiesto["id_oferente"] is None
    assert resultado.manifiesto["archivos"][0]["id_documento"].startswith("PROCESO-")
    assert (tmp_path / "salida" / PROCESO / "PROCESO" / "manifiesto.json").is_file()


def test_entrega_vacia(tmp_path):
    (tmp_path / "entrega").mkdir()
    resultado = _normalizar(tmp_path / "entrega", tmp_path / "salida")
    validador("manifiesto").validate(resultado.manifiesto)
    assert resultado.manifiesto["archivos"] == [] and resultado.manifiesto["descartados"] == []


def test_el_comando_sale_con_1_ante_un_bug(entrega_chica, monkeypatch, capsys):
    base, _ = entrega_chica

    def falla(*argumentos, **opciones):
        raise RuntimeError("bug")

    monkeypatch.setattr(modulo_entrega, "leer", falla)
    codigo = main([str(base / "entrega"), "--proceso", PROCESO, "--oferente", OFERENTE, "--salida", str(base / "salida")])
    assert codigo == 1
    assert "Falla inesperada" in capsys.readouterr().err


def test_el_comando_imprime_el_resumen(entrega_chica, capsys):
    base, _ = entrega_chica
    codigo = main([str(base / "entrega"), "--proceso", PROCESO, "--oferente", OFERENTE, "--salida", str(base / "salida")])
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "5 archivos, 5 descartados, 0 reusados" in salida
    assert "normalizado 3, duplicado 1, error_entrada 1" in salida
    assert "texto 3, escaneo_con_ocr 0, imagen 1, vacia 0" in salida
    assert "CONTRASENA 1" in salida
