"""Posvalidación determinista: de la respuesta del LLM al resultado del contrato (R37 a R48).

Sin LLM. En este orden:

1. Forma: la respuesta se valida con `datos/respuesta.schema.json`.
2. `no_corresponde`: sin resultados y con una alerta.
3. Alineación con la ficha: un resultado por elemento que se extrae, en orden.
4. Citas fuera del segmento: se quitan y el campo lleva `VALIDACION_FALLIDA`.
5. Validadores (`validadores.py`).
6. Motivos y revisión: los calcula el código; del LLM solo se aceptan los cuatro
   que se reconocen leyendo el documento.
7. `datos_personales`, desde la ficha.
8. Sobre, validado contra el contrato de salida.
"""

import json

from . import CONTRATO, contratos
from .entrada import ErrorDeSolicitud
from .ficha import Ficha
from .preproceso import Contenido
from .validadores import validar

MOTIVOS = (
    "CONFIANZA_BAJA", "NO_CUMPLE", "OBLIGATORIO_VACIO", "REQUIERE_IMAGEN", "PLANTILLA_SIN_LLENAR",
    "NOTA_ELEMENTO", "CONTRADICCION", "VALIDACION_FALLIDA", "TD_NO_PROBADO", "CLASIFICACION_DUDOSA",
)
"""El catálogo del contrato, en su orden: los motivos de cada campo salen en este orden."""
MOTIVOS_DEL_LLM = {"REQUIERE_IMAGEN", "PLANTILLA_SIN_LLENAR", "NOTA_ELEMENTO", "CONTRADICCION"}


class RespuestaInvalida(Exception):
    """La respuesta del LLM no tiene la forma pedida. Se pide otra vez (R50)."""

    def __init__(self, errores: list[str]) -> None:
        self.errores = errores
        super().__init__("La respuesta del LLM no tiene la forma pedida: " + "; ".join(errores))


class SalidaInvalida(Exception):
    """El resultado armado no cumple el contrato de salida: un bug del servicio (R56)."""


def interpretar(texto: str) -> dict:
    """La respuesta del LLM como dict, o `RespuestaInvalida`."""
    try:
        respuesta = json.loads(texto)
    except json.JSONDecodeError as error:
        raise RespuestaInvalida([f"no es JSON ({error.msg}, posición {error.pos})"]) from None
    problemas = contratos.errores(contratos.RESPUESTA, respuesta)
    if problemas:
        raise RespuestaInvalida(problemas)
    return respuesta


def _alerta(codigo: str, mensaje: str, id_tecnico: str | None = None) -> dict:
    return {"codigo": codigo, "mensaje": mensaje, "id_tecnico": id_tecnico}


def _datos_personales(elemento: dict) -> bool:
    # "Sí: …", "Sí" o "Posible: …" cuentan; solo "No" (o nada) no.
    marca = str(elemento.get("atributos", {}).get("datos_personales", "")).strip()
    return bool(marca) and not marca.startswith("No")


def _vacio(id_tecnico: str) -> dict:
    return {"id_tecnico": id_tecnico, "evidencia": [], "valor": None, "confianza": None, "cumple": None,
            "reglas_pendientes": [], "motivos": [], "observacion": None}


def _alinear(respuesta: dict, ficha: Ficha) -> tuple[list[tuple[dict, dict]], list[dict]]:
    """Pares (elemento, resultado del LLM) en el orden de la ficha, y las alertas de la alineación."""
    alertas, por_id = [], {}
    esperados = {e["id_tecnico"] for e in ficha.a_extraer()}
    for resultado in respuesta["resultados"]:
        id_tecnico = resultado["id_tecnico"]
        if id_tecnico not in esperados:
            alertas.append(_alerta("CAMPO_DESCONOCIDO", f"El LLM devolvió el campo {id_tecnico}, que no está en la ficha; se descartó."))
        elif id_tecnico in por_id:
            alertas.append(_alerta("CAMPO_REPETIDO", f"El LLM devolvió {id_tecnico} más de una vez; se tomó la primera.", id_tecnico))
        else:
            por_id[id_tecnico] = resultado
    pares = []
    for elemento in ficha.a_extraer():
        id_tecnico = elemento["id_tecnico"]
        if id_tecnico not in por_id:
            alertas.append(_alerta("CAMPO_SIN_RESPUESTA", f"El LLM no devolvió {id_tecnico}; queda sin valor.", id_tecnico))
        pares.append((elemento, por_id.get(id_tecnico) or _vacio(id_tecnico)))
    return pares, alertas


def _resultado(elemento: dict, propuesto: dict, valores: dict, solicitud: dict, ficha: Ficha) -> dict:
    desde, hasta = solicitud["paginas"]["desde"], solicitud["paginas"]["hasta"]
    motivos, notas = set(), []

    evidencia = [c for c in propuesto["evidencia"] if desde <= c["pagina"] <= hasta]
    fuera = sorted({c["pagina"] for c in propuesto["evidencia"] if not desde <= c["pagina"] <= hasta})
    if fuera:
        motivos.add("VALIDACION_FALLIDA")
        notas.append(f"Se quitaron citas de páginas fuera del segmento ({', '.join(map(str, fuera))}).")

    fallas = validar(elemento, propuesto["valor"], valores)
    if fallas:
        motivos.add("VALIDACION_FALLIDA")
        notas.extend(fallas)

    atributos = elemento.get("atributos", {})
    valor, confianza = propuesto["valor"], propuesto["confianza"]
    umbral = atributos.get("umbral_confianza")
    if umbral is not None and confianza is not None and confianza < umbral:
        motivos.add("CONFIANZA_BAJA")
    if valor is not None and confianza is None:
        motivos.add("CONFIANZA_BAJA")
    if propuesto["cumple"] == "NO":
        motivos.add("NO_CUMPLE")
    if elemento.get("obligatoriedad") == "Si" and valor is None:
        motivos.add("OBLIGATORIO_VACIO")
    if not ficha.td_probado:
        motivos.add("TD_NO_PROBADO")
    if solicitud["clasificacion_dudosa"]:
        motivos.add("CLASIFICACION_DUDOSA")
    motivos.update(m for m in propuesto["motivos"] if m in MOTIVOS_DEL_LLM)

    observacion = " ".join(filter(None, [propuesto["observacion"], *notas])) or None
    id_tecnico = elemento["id_tecnico"]
    ordenados = [m for m in MOTIVOS if m in motivos]
    return {
        "id_tecnico": id_tecnico,
        "valor": valor,
        "confianza": confianza,
        "evidencia": evidencia,
        "cumple": propuesto["cumple"],
        "reglas_pendientes": [
            {"id_regla": f"{id_tecnico}.r{n}", "texto": r["texto"], "requiere": r["requiere"]}
            for n, r in enumerate(propuesto["reglas_pendientes"], start=1)
        ],
        "revision": bool(ordenados),
        "motivos": ordenados,
        "observacion": observacion,
        "datos_personales": _datos_personales(elemento),
    }


def _base(solicitud: dict, estado: str) -> dict:
    return {
        "contrato": CONTRATO,
        "id_proceso": solicitud["id_proceso"],
        "id_oferente": solicitud["id_oferente"],
        "id_segmento": solicitud["id_segmento"],
        "id_documento": solicitud["id_documento"],
        "tipo_documental": solicitud["tipo_documental"],
        "paginas": dict(solicitud["paginas"]),
        "estado": estado,
        "version_modelo": solicitud["version_modelo"],
    }


def _validado(sobre: dict) -> dict:
    problemas = contratos.errores(contratos.SALIDA, sobre)
    if problemas:
        raise SalidaInvalida("El resultado no cumple modulo3-extraccion/0.2: " + "; ".join(problemas))
    return sobre


def sobre(solicitud: dict, ficha: Ficha, contenido: Contenido, respuesta: dict, ejecucion: dict) -> dict:
    """El resultado completo de un segmento extraído (`ok` o `no_corresponde`)."""
    alertas = list(contenido.alertas)
    if not respuesta["corresponde"]:
        motivo = respuesta["motivo_no_corresponde"] or "sin motivo"
        alertas.append(_alerta("NO_CORRESPONDE", f"El contenido no parece ser {ficha.tipo_documental}: {motivo}"))
        resultados, estado = [], "no_corresponde"
    else:
        pares, de_alinear = _alinear(respuesta, ficha)
        valores = {e["id_tecnico"]: r["valor"] for e, r in pares}
        resultados = [_resultado(e, r, valores, solicitud, ficha) for e, r in pares]
        alertas.extend(_alerta(a["codigo"], a["mensaje"], a["id_tecnico"]) for a in respuesta["alertas"])
        alertas.extend(de_alinear)
        estado = "ok"
    en_revision = [r["id_tecnico"] for r in resultados if r["revision"]]
    return _validado({
        **_base(solicitud, estado),
        "td_probado": ficha.td_probado,
        "requiere_revision": bool(en_revision),
        "campos_en_revision": en_revision,
        "resultados": resultados,
        "alertas": alertas,
        "lectura": contenido.lectura(),
        "ejecucion": ejecucion,
    })


def sobre_de_error(solicitud: dict, error: ErrorDeSolicitud, ejecucion: dict) -> dict:
    """El resultado de un segmento que no se pudo extraer (`error_entrada` o `error_proceso`)."""
    return _validado({
        **_base(solicitud, error.estado),
        "error": error.como_error(),
        "requiere_revision": False,
        "campos_en_revision": [],
        "resultados": [],
        "alertas": [],
        "ejecucion": ejecucion,
    })
