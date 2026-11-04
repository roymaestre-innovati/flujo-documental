import pytest

from normalizacion.errores import CODIGOS, ErrorDocumento, error_documento

from contrato import esquemas


def test_los_codigos_son_los_del_contrato():
    codigos = esquemas()["manifiesto"]["$defs"]["error"]["properties"]["codigo"]["enum"]
    assert list(CODIGOS) == codigos


@pytest.mark.parametrize("codigo", CODIGOS)
def test_cada_codigo_dice_que_pedir_al_oferente(codigo):
    error = error_documento(codigo)
    assert error.codigo == codigo
    assert "Si se pide subsanación, el oferente debe" in error.detalle
    assert error.como_dict() == {"codigo": codigo, "detalle": error.detalle}


def test_el_sujeto_cambia_segun_el_documento():
    assert error_documento("CONTRASENA", "El PDF").detalle.startswith("El PDF pide contraseña")
    assert error_documento("CONTRASENA").detalle.startswith("El archivo pide contraseña")


def test_codigo_desconocido():
    with pytest.raises(ValueError):
        error_documento("OTRO")


def test_es_inmutable():
    error = error_documento("DANADO")
    assert isinstance(error, ErrorDocumento)
    with pytest.raises(AttributeError):
        error.codigo = "OTRO"
