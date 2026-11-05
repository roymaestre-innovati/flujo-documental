"""Firma digital: R15."""

import datetime
import io
import logging

import pikepdf
import pytest

import fabrica
from normalizacion.firma import FirmaDigital, leer_firmas

from contrato import validador


def _firmas_del_caso(tmp_path, caso):
    (ruta,) = fabrica.CASOS[caso](tmp_path)
    return leer_firmas(ruta.read_bytes())


def _firmar(datos: bytes, campo: str, cifrar: bool = False) -> bytes:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers

    escritor = IncrementalPdfFileWriter(io.BytesIO(datos))
    if cifrar:
        escritor.encrypt("")
    return signers.sign_pdf(escritor, signers.PdfSignatureMetadata(field_name=campo), signer=fabrica._firmante()).getvalue()


def _cumple_el_contrato(firma: FirmaDigital):
    """La firma va en el manifiesto: tiene que cumplir el esquema."""
    esquema = validador("manifiesto").schema["$defs"]["firma"]
    from jsonschema import Draft202012Validator

    Draft202012Validator(esquema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(firma.como_dict())


def test_firmado_integro(tmp_path):
    (firma,) = _firmas_del_caso(tmp_path, "pdf_firmado")
    assert firma.leida is True
    assert firma.integro is True
    assert firma.firmante == fabrica.FIRMANTE_DIGITAL
    assert firma.formato == "adbe.pkcs7.detached"
    fecha = datetime.datetime.fromisoformat(firma.fecha)
    assert fecha.tzinfo is not None
    assert abs(datetime.datetime.now(datetime.timezone.utc) - fecha) < datetime.timedelta(hours=1)
    _cumple_el_contrato(firma)


def test_modificado_despues_de_firmar(tmp_path):
    (firma,) = _firmas_del_caso(tmp_path, "pdf_modificado_despues_de_firmar")
    assert firma.leida is True
    assert firma.integro is False
    assert firma.firmante == fabrica.FIRMANTE_DIGITAL
    _cumple_el_contrato(firma)


def test_el_sello_de_tiempo_no_cuenta_como_firma(tmp_path):
    # T14: un sello de tiempo del documento no tiene firmante; solo queda la firma.
    (firma,) = _firmas_del_caso(tmp_path, "pdf_firmado_con_sello_de_tiempo")
    assert firma.leida is True
    assert firma.integro is True
    assert firma.firmante == fabrica.FIRMANTE_DIGITAL
    assert firma.formato == "adbe.pkcs7.detached"
    _cumple_el_contrato(firma)


def test_solo_un_sello_de_tiempo_es_sin_firma(tmp_path):
    assert leer_firmas(fabrica.sellar(fabrica.pdf_texto_bytes())) == []


def test_firma_que_no_se_puede_leer(tmp_path):
    (firma,) = _firmas_del_caso(tmp_path, "pdf_firma_ilegible")
    assert firma == FirmaDigital(firmante=None, fecha=None, integro=None, formato="adbe.pkcs7.sha1", leida=False)
    _cumple_el_contrato(firma)


@pytest.mark.parametrize(
    "caso",
    ["pdf_texto", "pdf_escaneo_sin_texto", "pdf_solo_restricciones", "pdf_anclas", "pdf_danado_reparable"],
)
def test_sin_firma(tmp_path, caso):
    assert _firmas_del_caso(tmp_path, caso) == []


@pytest.mark.parametrize("datos", [b"", b"%PDF-1.7\n", b"no es un pdf"])
def test_lo_que_no_abre_no_tiene_firmas(datos):
    assert leer_firmas(datos) == []


def test_dos_firmas_en_orden(tmp_path):
    datos = _firmar(fabrica.pdf_firmado_bytes(), "Firma2")
    primera, segunda = leer_firmas(datos)
    # Una segunda firma es un cambio permitido: la primera sigue íntegra.
    assert primera.leida and primera.integro
    assert segunda.leida and segunda.integro


def test_firmado_con_restricciones(tmp_path):
    (ruta,) = fabrica.pdf_solo_restricciones(tmp_path)
    datos = _firmar(ruta.read_bytes(), "Firma1", cifrar=True)
    with pikepdf.open(io.BytesIO(datos)) as pdf:
        assert pdf.is_encrypted
    (firma,) = leer_firmas(datos)
    assert firma.leida and firma.integro
    assert firma.firmante == fabrica.FIRMANTE_DIGITAL


def test_campo_de_firma_vacio_no_cuenta():
    """Un formulario con el campo de firma pero sin firmar."""
    with pikepdf.open(io.BytesIO(fabrica.pdf_texto_bytes())) as pdf:
        campo = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name.Sig, T="Firma1"))
        pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([campo]))
        salida = io.BytesIO()
        pdf.save(salida)
    assert leer_firmas(salida.getvalue()) == []


def test_firma_dentro_de_un_campo_padre(tmp_path):
    """Campos anidados: el nombre completo es padre.hijo."""
    (ruta,) = fabrica.pdf_firma_ilegible(tmp_path)
    with pikepdf.open(ruta) as pdf:
        (campo,) = pdf.Root.AcroForm.Fields
        padre = pdf.make_indirect(pikepdf.Dictionary(T="Firmas", Kids=pikepdf.Array([campo])))
        campo.Parent = padre
        pdf.Root.AcroForm.Fields = pikepdf.Array([padre])
        salida = io.BytesIO()
        pdf.save(salida)
    (firma,) = leer_firmas(salida.getvalue())
    assert firma.formato == "adbe.pkcs7.sha1" and firma.leida is False


def test_el_registro_no_lleva_el_nombre_del_firmante(tmp_path, caplog):
    with caplog.at_level(logging.DEBUG):
        _firmas_del_caso(tmp_path, "pdf_firmado")
        _firmas_del_caso(tmp_path / "otra", "pdf_modificado_despues_de_firmar")
    assert fabrica.FIRMANTE_DIGITAL not in caplog.text


def test_leer_dos_veces_da_lo_mismo(tmp_path):
    (ruta,) = fabrica.pdf_modificado_despues_de_firmar(tmp_path)
    datos = ruta.read_bytes()
    assert leer_firmas(datos) == leer_firmas(datos)
