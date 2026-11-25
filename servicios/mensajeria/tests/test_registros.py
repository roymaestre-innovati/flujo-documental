"""El contexto de los registros lleva solo identificadores (principio 6)."""

from normalizacion import registros as base

from mensajeria.registros import contexto_de


def test_el_contexto_lleva_los_identificadores_del_mensaje():
    with contexto_de({"id_proceso": "P-1", "id_oferente": "OF-001", "id_segmento": "D-1-p1-2"}):
        assert base._contexto.get() == {"id_proceso": "P-1", "id_oferente": "OF-001", "id_documento": "D-1-p1-2"}


def test_un_campo_que_no_es_un_identificador_no_va_al_contexto():
    privado = {"nombre": "Dato privado del documento"}
    with contexto_de({"id_proceso": "P-1", "id_segmento": privado, "entrega": "x" * 500,
                      "id_documento": "línea\notra"}):
        contexto = base._contexto.get()
    assert contexto == {"id_proceso": "P-1", "id_oferente": None, "id_documento": None}
    assert "privado" not in repr(contexto)


def test_un_cuerpo_que_no_es_un_objeto_no_rompe_el_contexto():
    with contexto_de(["no", "es", "un", "objeto"]):
        assert base._contexto.get().get("id_proceso") is None
