"""Posvalidación: de la respuesta del LLM al resultado del contrato (R37 a R48, R55, R56)."""

import copy
import json

import pytest

from extraccion.entrada import ErrorDeSolicitud
from extraccion.posvalidacion import RespuestaInvalida, SalidaInvalida, interpretar, sobre, sobre_de_error
from extraccion.preproceso import Contenido, Imagen, Pagina

from conftest import EJEMPLOS, cargar, respuesta_falsa

IMAGEN = Imagen(b"jpeg", "high", 1, 1)
CONTENIDO = Contenido(
    paginas=(Pagina(1, "texto", "…", False, IMAGEN, (IMAGEN,)), Pagina(2, "texto", "…", False, None, ())),
    anexos=(),
)


def _sobre(fuente_modelo, td="16", respuesta=None, contenido=CONTENIDO, **cambios):
    solicitud = {**cargar(EJEMPLOS / f"entrada_td{td}.json"), **cambios}
    ficha = fuente_modelo.ficha(21, solicitud["tipo_documental"])
    respuesta = respuesta if respuesta is not None else interpretar(respuesta_falsa(f"TD-{td}"))
    return sobre(solicitud, ficha, contenido, respuesta, cargar(EJEMPLOS / f"salida_td{td}.json")["ejecucion"])


def _por_id(salida):
    return {r["id_tecnico"]: r for r in salida["resultados"]}


@pytest.mark.parametrize("td", ["16", "29"])
def test_los_ejemplos_del_contrato(fuente_modelo, td):
    """Criterio A7: la respuesta falsa da la salida de ejemplo.

    Difieren solo `id_regla` (provisional, R1: aquí se numeran las pendientes; el
    ejemplo numeraba todas las reglas del elemento) y la `observacion`, a la que se
    suma la explicación de cada validador que falla.
    """
    esperada, salida = cargar(EJEMPLOS / f"salida_td{td}.json"), _sobre(fuente_modelo, td)
    for clave in esperada:
        if clave != "resultados":
            assert salida[clave] == esperada[clave], clave
    for e, s in zip(esperada["resultados"], salida["resultados"], strict=True):
        for clave in e:
            if clave == "reglas_pendientes":
                assert [(r["texto"], r["requiere"]) for r in s[clave]] == [(r["texto"], r["requiere"]) for r in e[clave]]
            elif clave == "observacion":
                assert (s[clave] or "").startswith(e[clave] or "")
            else:
                assert s[clave] == e[clave], (e["id_tecnico"], clave)


def test_id_regla_provisional(fuente_modelo):
    reglas = _por_id(_sobre(fuente_modelo))["td16.firmante"]["reglas_pendientes"]
    assert [r["id_regla"] for r in reglas] == ["td16.firmante.r1", "td16.firmante.r2"]


def test_validadores_explican_la_falla(fuente_modelo):
    contratos = _por_id(_sobre(fuente_modelo, "29"))["td29.contratos"]
    assert contratos["observacion"].endswith("Validador fecha_orden: fila 2: fecha_inicio 2027-07-10 es posterior a fecha_fin 2020-12-31.")


# --- Interpretar la respuesta ------------------------------------------------


def test_respuesta_que_no_es_json():
    with pytest.raises(RespuestaInvalida) as error:
        interpretar("Aquí está el resultado: ```json [ ] ```")
    assert error.value.errores[0].startswith("no es JSON")


def test_respuesta_sin_la_forma_pedida():
    with pytest.raises(RespuestaInvalida) as error:
        interpretar(json.dumps([{"id_tecnico": "td16.subtipo"}]))
    assert error.value.errores == ["(raíz): no cumple 'type'"]


# --- Motivos --------------------------------------------------------------


def _respuesta(td="TD-16"):
    return interpretar(respuesta_falsa(td))


def _cambiar(respuesta, id_tecnico, **cambios):
    for r in respuesta["resultados"]:
        if r["id_tecnico"] == id_tecnico:
            r.update(cambios)
    return respuesta


def test_la_revision_del_llm_no_cuenta(fuente_modelo):
    # El LLM no puede mandar NO_CUMPLE ni decidir revisión: lo calcula el código.
    respuesta = _cambiar(_respuesta(), "td16.firmante", cumple="SI")
    firmante = _por_id(_sobre(fuente_modelo, respuesta=respuesta))["td16.firmante"]
    assert firmante["revision"] is False and firmante["motivos"] == []


def test_confianza_baja(fuente_modelo):
    respuesta = _cambiar(_respuesta(), "td16.fecha_certificacion", confianza=0.94)  # umbral 0,95
    assert _por_id(_sobre(fuente_modelo, respuesta=respuesta))["td16.fecha_certificacion"]["motivos"] == ["CONFIANZA_BAJA"]


def test_valor_sin_confianza_es_confianza_baja(fuente_modelo):
    respuesta = _cambiar(_respuesta(), "td16.subtipo", confianza=None)
    assert _por_id(_sobre(fuente_modelo, respuesta=respuesta))["td16.subtipo"]["motivos"] == ["CONFIANZA_BAJA"]


def test_obligatorio_vacio(fuente_modelo):
    respuesta = _cambiar(_respuesta(), "td16.version_formato", valor=None, confianza=None, evidencia=[])
    assert _por_id(_sobre(fuente_modelo, respuesta=respuesta))["td16.version_formato"]["motivos"] == ["OBLIGATORIO_VACIO"]


def test_casilla_ilegible_va_a_revision_por_confianza(fuente_modelo):
    respuesta = _cambiar(_respuesta(), "td16.version_formato", valor=None, confianza=0.4)
    assert _por_id(_sobre(fuente_modelo, respuesta=respuesta))["td16.version_formato"]["motivos"] == ["CONFIANZA_BAJA", "OBLIGATORIO_VACIO"]


def test_motivos_que_propone_el_llm(fuente_modelo):
    respuesta = _cambiar(_respuesta(), "td16.subtipo", motivos=["CONTRADICCION", "PLANTILLA_SIN_LLENAR"])
    assert _por_id(_sobre(fuente_modelo, respuesta=respuesta))["td16.subtipo"]["motivos"] == ["PLANTILLA_SIN_LLENAR", "CONTRADICCION"]


def test_valor_fuera_de_catalogo(fuente_modelo):
    respuesta = _cambiar(_respuesta(), "td16.subtipo", valor="Persona jurídica")
    subtipo = _por_id(_sobre(fuente_modelo, respuesta=respuesta))["td16.subtipo"]
    assert subtipo["motivos"] == ["VALIDACION_FALLIDA"]
    assert "no está entre los valores permitidos" in subtipo["observacion"]


def test_cita_fuera_del_segmento(fuente_modelo):
    respuesta = _respuesta()
    sociedad = _cambiar(respuesta, "td16.sociedad")["resultados"][1]
    sociedad["evidencia"].append({"pagina": 7, "cita": "otra página", "visual": None})
    resultado = _por_id(_sobre(fuente_modelo, respuesta=respuesta))["td16.sociedad"]
    assert [c["pagina"] for c in resultado["evidencia"]] == [1]
    assert resultado["motivos"] == ["VALIDACION_FALLIDA"]
    assert "fuera del segmento (7)" in resultado["observacion"]


def test_td_no_probado_manda_todo_a_revision(fuente_modelo):
    respuesta = {"corresponde": True, "motivo_no_corresponde": None, "alertas": [], "resultados": []}
    salida = _sobre(fuente_modelo, respuesta=respuesta, tipo_documental="TD-01")
    assert salida["td_probado"] is False
    assert all("TD_NO_PROBADO" in r["motivos"] for r in salida["resultados"])
    assert salida["campos_en_revision"] == [r["id_tecnico"] for r in salida["resultados"]]


def test_clasificacion_dudosa(fuente_modelo):
    salida = _sobre(fuente_modelo, clasificacion_dudosa=True)
    assert all(r["motivos"][-1] == "CLASIFICACION_DUDOSA" for r in salida["resultados"])
    assert len(salida["campos_en_revision"]) == 6


def test_datos_personales_desde_la_ficha(fuente_modelo):
    salida = _por_id(_sobre(fuente_modelo))
    assert salida["td16.firmante"]["datos_personales"] is True
    assert salida["td16.subtipo"]["datos_personales"] is False


# --- Alineación con la ficha ----------------------------------------------------


def test_campos_faltantes_desconocidos_y_repetidos(fuente_modelo):
    respuesta = _respuesta()
    respuesta["resultados"] = [r for r in respuesta["resultados"] if r["id_tecnico"] != "td16.paz_y_salvo"]
    respuesta["resultados"].append(dict(copy.deepcopy(respuesta["resultados"][0]), id_tecnico="td16.inventado"))
    respuesta["resultados"].append(dict(copy.deepcopy(respuesta["resultados"][0]), valor="PN"))
    salida = _sobre(fuente_modelo, respuesta=respuesta)
    assert [r["id_tecnico"] for r in salida["resultados"]] == [
        "td16.subtipo", "td16.sociedad", "td16.firmante", "td16.paz_y_salvo", "td16.fecha_certificacion", "td16.version_formato",
    ]
    por_id = _por_id(salida)
    assert por_id["td16.subtipo"]["valor"] == "PJ"  # se toma la primera
    assert por_id["td16.paz_y_salvo"]["valor"] is None
    assert por_id["td16.paz_y_salvo"]["motivos"] == ["OBLIGATORIO_VACIO"]
    codigos = [(a["codigo"], a["id_tecnico"]) for a in salida["alertas"]]
    assert ("CAMPO_DESCONOCIDO", None) in codigos
    assert ("CAMPO_REPETIDO", "td16.subtipo") in codigos
    assert ("CAMPO_SIN_RESPUESTA", "td16.paz_y_salvo") in codigos


def test_no_corresponde(fuente_modelo):
    respuesta = {"corresponde": False, "motivo_no_corresponde": "es un RUT", "resultados": [], "alertas": []}
    salida = _sobre(fuente_modelo, respuesta=respuesta)
    assert salida["estado"] == "no_corresponde"
    assert salida["resultados"] == [] and salida["requiere_revision"] is False
    assert salida["alertas"] == [{"codigo": "NO_CORRESPONDE", "mensaje": "El contenido no parece ser TD-16: es un RUT", "id_tecnico": None}]


def test_alertas_del_preproceso_van_primero(fuente_modelo):
    alerta = {"codigo": "ANEXO_RECORTADO", "mensaje": "…", "id_tecnico": None}
    contenido = Contenido(paginas=CONTENIDO.paginas, anexos=(), alertas=(alerta,))
    assert [a["codigo"] for a in _sobre(fuente_modelo, contenido=contenido)["alertas"]] == ["ANEXO_RECORTADO", "FIRMA_AUSENTE"]


# --- Sobre --------------------------------------------------------------------


def test_salida_que_no_cumple_el_contrato_es_un_bug(fuente_modelo):
    with pytest.raises(SalidaInvalida):
        _sobre(fuente_modelo, id_segmento="")


def test_sobre_de_error_cumple_el_contrato():
    solicitud = cargar(EJEMPLOS / "entrada_td16.json")
    error = ErrorDeSolicitud("error_entrada", "PAGINAS_FUERA_DE_RANGO", "El archivo tiene 1 página.", False)
    ejecucion = cargar(EJEMPLOS / "salida_error.json")["ejecucion"]
    salida = sobre_de_error(solicitud, error, ejecucion)
    assert salida["estado"] == "error_entrada" and salida["resultados"] == []
    assert salida["error"] == {"codigo": "PAGINAS_FUERA_DE_RANGO", "mensaje": "El archivo tiene 1 página.", "reintentable": False}
