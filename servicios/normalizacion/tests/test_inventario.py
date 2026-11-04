"""Inventario de la entrega: requisitos R1 a R5."""

import hashlib
import re
import shutil
import unicodedata


import fabrica
from normalizacion.inventario import (
    MOTIVO_MAC,
    MOTIVO_WINDOWS,
    id_documento,
    inventariar,
)


def _por_ruta(inventario):
    return {archivo.ruta_origen: archivo for archivo in inventario.archivos}


def _descartados(inventario):
    return {d.ruta_origen: d.motivo for d in inventario.descartados}


# R1 -------------------------------------------------------------------------


def test_r1_recorre_carpetas_anidadas_y_guarda_la_ruta(tmp_path):
    fabrica.pdf_texto(tmp_path / "juridico" / "representacion")
    fabrica.xlsx_ancho(tmp_path / "financiero")
    fabrica.jpg(tmp_path)
    inventario = inventariar(tmp_path, "OF-002")
    assert [a.ruta_origen for a in inventario.archivos] == [
        "cedula_representante.jpg",
        "financiero/experiencia.xlsx",
        "juridico/representacion/carta_presentacion.pdf",
    ]
    for archivo in inventario.archivos:
        assert archivo.ruta == tmp_path / archivo.ruta_origen


def test_r1_entrega_vacia(tmp_path):
    inventario = inventariar(tmp_path, "OF-002")
    assert inventario.archivos == [] and inventario.descartados == []


# R2 -------------------------------------------------------------------------


def test_r2_descarta_los_archivos_de_sistema_con_su_motivo(tmp_path):
    fabrica.archivos_de_sistema(tmp_path)
    fabrica.pdf_texto(tmp_path)
    inventario = inventariar(tmp_path, "OF-002")
    assert [a.ruta_origen for a in inventario.archivos] == ["carta_presentacion.pdf"]
    assert inventario.descartados == sorted(inventario.descartados, key=lambda d: d.ruta_origen)
    assert _descartados(inventario) == {
        ".DS_Store": MOTIVO_MAC,
        "._carta_presentacion.pdf": MOTIVO_MAC,
        "__MACOSX/._carta_presentacion.pdf": MOTIVO_MAC,
        "__MACOSX/anexos/._experiencia.xlsx": MOTIVO_MAC,
        "imagenes/Thumbs.db": MOTIVO_WINDOWS,
    }


def test_r2_descarta_appledouble_por_contenido_aunque_el_nombre_sea_normal(tmp_path):
    fabrica.appledouble_sin_prefijo(tmp_path)
    inventario = inventariar(tmp_path, "OF-002")
    assert inventario.archivos == []
    assert _descartados(inventario) == {"anexo_tecnico.pdf": MOTIVO_MAC}


def test_r2_un_punto_guion_bajo_que_no_es_appledouble_es_documento(tmp_path):
    (tmp_path / "._propuesta.pdf").write_bytes(fabrica.pdf_texto_bytes())
    inventario = inventariar(tmp_path, "OF-002")
    assert [a.ruta_origen for a in inventario.archivos] == ["._propuesta.pdf"]
    assert inventario.descartados == []


def test_r2_todo_lo_de_macosx_se_descarta(tmp_path):
    (tmp_path / "__MACOSX" / "sub").mkdir(parents=True)
    (tmp_path / "__MACOSX" / "sub" / "carta.pdf").write_bytes(fabrica.pdf_texto_bytes())
    inventario = inventariar(tmp_path, "OF-002")
    assert inventario.archivos == []
    assert _descartados(inventario) == {"__MACOSX/sub/carta.pdf": MOTIVO_MAC}


def test_r2_thumbs_db_sin_importar_mayusculas(tmp_path):
    (tmp_path / "THUMBS.DB").write_bytes(b"x")
    assert _descartados(inventariar(tmp_path, "OF-002")) == {"THUMBS.DB": MOTIVO_WINDOWS}


def test_r2_no_descarta_por_extension(tmp_path):
    (tmp_path / "DS_Store.pdf").write_bytes(fabrica.pdf_texto_bytes())
    (tmp_path / "__MACOSX.pdf").write_bytes(b"otro")
    inventario = inventariar(tmp_path, "OF-002")
    assert len(inventario.archivos) == 2 and inventario.descartados == []


# R3 -------------------------------------------------------------------------


def test_r3_huella_sha256_del_original(tmp_path):
    (ruta,) = fabrica.pdf_firmado(tmp_path)
    (archivo,) = inventariar(tmp_path, "OF-002").archivos
    assert archivo.hash == hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_r3_huella_de_un_archivo_vacio(tmp_path):
    (tmp_path / "vacio.pdf").write_bytes(b"")
    (archivo,) = inventariar(tmp_path, "OF-002").archivos
    assert archivo.hash == hashlib.sha256(b"").hexdigest()


# R4 -------------------------------------------------------------------------


def test_r4_la_copia_apunta_al_primero_por_orden_de_ruta(tmp_path):
    original, copia = fabrica.duplicados(tmp_path)
    archivos = _por_ruta(inventariar(tmp_path, "OF-002"))
    primero = archivos["anexos/certificado_bancario.pdf"]
    segundo = archivos["copias/certificado_bancario.pdf"]
    assert primero.duplicado_de is None
    assert segundo.duplicado_de == primero.id_documento
    assert primero.hash == segundo.hash
    assert original.exists() and copia.exists()


def test_r4_varias_copias_apuntan_todas_al_original(tmp_path):
    datos = fabrica.pdf_texto_bytes()
    for ruta in ("c/carta.pdf", "a/carta.pdf", "b/carta.pdf"):
        (tmp_path / ruta).parent.mkdir(parents=True)
        (tmp_path / ruta).write_bytes(datos)
    archivos = _por_ruta(inventariar(tmp_path, "OF-002"))
    original = archivos["a/carta.pdf"]
    assert original.duplicado_de is None
    assert archivos["b/carta.pdf"].duplicado_de == original.id_documento
    assert archivos["c/carta.pdf"].duplicado_de == original.id_documento


def test_r4_un_descartado_no_cuenta_como_original(tmp_path):
    datos = fabrica.pdf_texto_bytes()
    (tmp_path / "__MACOSX").mkdir()
    (tmp_path / "__MACOSX" / "carta.pdf").write_bytes(datos)
    (tmp_path / "carta.pdf").write_bytes(datos)
    (archivo,) = inventariar(tmp_path, "OF-002").archivos
    assert archivo.duplicado_de is None


# R5 -------------------------------------------------------------------------


def test_r5_formato_del_identificador(tmp_path):
    fabrica.pdf_texto(tmp_path)
    (archivo,) = inventariar(tmp_path, "OF-002").archivos
    esperado = hashlib.sha256(b"carta_presentacion.pdf").hexdigest()[:12]
    assert archivo.id_documento == f"OF-002-{esperado}"
    assert re.fullmatch(r"OF-002-[0-9a-f]{12}", archivo.id_documento)


def test_r5_entrega_del_proceso(tmp_path):
    fabrica.pdf_texto(tmp_path)
    (archivo,) = inventariar(tmp_path, None).archivos
    assert archivo.id_documento.startswith("PROCESO-")


def test_r5_mismo_resultado_en_dos_corridas_y_en_otra_carpeta(tmp_path):
    for caso in ("pdf_texto", "duplicados", "archivos_de_sistema", "jpg", "no_soportados"):
        fabrica.CASOS[caso](tmp_path / "entrega" / caso)
    primera = inventariar(tmp_path / "entrega", "OF-002")
    segunda = inventariar(tmp_path / "entrega", "OF-002")
    shutil.copytree(tmp_path / "entrega", tmp_path / "otra" / "copia")
    tercera = inventariar(tmp_path / "otra" / "copia", "OF-002")

    def sin_ruta_en_disco(inventario):
        return [(a.id_documento, a.ruta_origen, a.hash, a.duplicado_de) for a in inventario.archivos]

    assert primera == segunda
    assert sin_ruta_en_disco(primera) == sin_ruta_en_disco(tercera)
    assert primera.descartados == tercera.descartados


def test_r5_dos_copias_tienen_identificadores_distintos(tmp_path):
    fabrica.duplicados(tmp_path)
    archivos = inventariar(tmp_path, "OF-002").archivos
    assert len({a.id_documento for a in archivos}) == 2


def test_r5_tildes_de_mac_y_de_windows_dan_lo_mismo(tmp_path):
    nombre = "presentación/declaración.pdf"
    for carpeta, forma in (("windows", "NFC"), ("mac", "NFD")):
        ruta = tmp_path / carpeta / unicodedata.normalize(forma, nombre)
        ruta.parent.mkdir(parents=True)
        ruta.write_bytes(fabrica.pdf_texto_bytes())
    (de_windows,) = inventariar(tmp_path / "windows", "OF-002").archivos
    (de_mac,) = inventariar(tmp_path / "mac", "OF-002").archivos
    assert de_mac.ruta_origen == de_windows.ruta_origen == unicodedata.normalize("NFC", nombre)
    assert de_mac.id_documento == de_windows.id_documento
    assert de_mac.ruta.exists()


def test_r5_id_documento_normaliza_la_ruta():
    nombre = "declaración.pdf"
    assert id_documento(unicodedata.normalize("NFD", nombre), "OF-002") == id_documento(nombre, "OF-002")


def test_dos_nombres_iguales_al_normalizar_llevan_sufijo(tmp_path):
    nombre = "declaración.pdf"
    nfc, nfd = (unicodedata.normalize(forma, nombre) for forma in ("NFC", "NFD"))
    (tmp_path / nfc).write_bytes(b"uno")
    (tmp_path / nfd).write_bytes(b"dos")
    # Ya existe un archivo con el primer sufijo: el siguiente salta al (3).
    (tmp_path / "declaración (2).pdf").write_bytes(b"tres")
    archivos = _por_ruta(inventariar(tmp_path, "OF-002"))
    assert sorted(archivos) == ["declaración (2).pdf", "declaración (3).pdf", "declaración.pdf"]
    # El primero por orden de la ruta en disco (NFD) conserva el nombre.
    assert archivos["declaración.pdf"].ruta.name == min(nfc, nfd)
    assert archivos["declaración (3).pdf"].ruta.read_bytes() in (b"uno", b"dos")
    assert len({a.id_documento for a in archivos.values()}) == 3
    assert inventariar(tmp_path, "OF-002") == inventariar(tmp_path, "OF-002")


def test_sufijo_en_carpeta_y_sin_extension(tmp_path):
    for forma in ("NFC", "NFD"):
        carpeta = tmp_path / unicodedata.normalize(forma, "presentación")
        carpeta.mkdir()
        (carpeta / "LEAME").write_bytes(forma.encode())
    rutas = sorted(a.ruta_origen for a in inventariar(tmp_path, "OF-002").archivos)
    assert rutas == ["presentación/LEAME", "presentación/LEAME (2)"]


def test_sufijo_en_nombre_que_empieza_por_punto():
    from normalizacion.inventario import _con_sufijo

    assert _con_sufijo(".oculto", 2) == ".oculto (2)"
    assert _con_sufijo("a/b.tar.gz", 2) == "a/b.tar (2).gz"
