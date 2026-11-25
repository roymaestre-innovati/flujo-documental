"""Las cinco entidades del orquestador, sus estados y cómo se pasa de uno a otro
(paso 4 del diseño, decisión 15; requisitos R24 a R26 y R28).

Cada registro guarda, además de sus datos:

- `estado`: el estado actual;
- `entrega`: `PROCESO` o el `id_oferente` (no en el proceso);
- `historial`: cada cambio, con `de`, `a`, `cuando` y `motivo`.

El motivo es un código o una frase corta, nunca texto de los documentos ni
nombres de archivo (principio 6).

Solo están los estados que usa la entrega 1. Los de la extracción, la revisión,
la ficha del proceso y las reglas se agregan en la entrega 2.
"""

import datetime
from collections import Counter
from dataclasses import dataclass

from normalizacion.inventario import ENTREGA_DEL_PROCESO

from .estado import Conflicto, Estado, Registro
from .reloj import Reloj

PROCESO, OFERENTE, DOCUMENTO, SEGMENTO, TAREA = "proceso", "oferente", "documento", "segmento", "tarea"

# Estados
ABIERTO = "abierto"
RECIBIDO, NORMALIZANDO, PROCESANDO = "recibido", "normalizando", "procesando"
NORMALIZADO, DUPLICADO, ERROR_ENTRADA, CLASIFICADO = "normalizado", "duplicado", "error_entrada", "clasificado"
ESPERANDO_CLASIFICACION_HUMANA = "esperando_clasificacion_humana"
ERROR_PROCESO = "error_proceso"
PENDIENTE, SIN_EXTRACCION = "pendiente", "sin_extraccion"
ABIERTA, RESUELTA = "abierta", "resuelta"


@dataclass(frozen=True)
class Maquina:
    iniciales: frozenset[str]
    """Con qué estado se puede crear un registro."""
    transiciones: dict[str, frozenset[str]]
    """De qué estado a cuáles se puede pasar."""
    intermedios: frozenset[str]
    """Estados en los que todavía falta algo de esta entrega del orquestador.
    En la entrega 2 se suman los de la extracción y la revisión, y con ellos se
    responde "¿el oferente está completo?" (decisión 15)."""

    def estados(self) -> frozenset[str]:
        destinos = {a for lista in self.transiciones.values() for a in lista}
        return frozenset(self.iniciales | set(self.transiciones) | destinos)


def _m(iniciales, transiciones, intermedios=()):
    return Maquina(frozenset(iniciales), {k: frozenset(v) for k, v in transiciones.items()}, frozenset(intermedios))


MAQUINAS: dict[str, Maquina] = {
    PROCESO: _m([ABIERTO], {}),
    # El oferente es su entrega: un error de proceso aquí es una normalización
    # que falló entera (no hay manifiesto, así que no hay documentos todavía).
    # `normalizando` es la reserva de una ejecución (ver `reservar`).
    OFERENTE: _m(
        [RECIBIDO],
        {RECIBIDO: [NORMALIZANDO, ERROR_PROCESO], NORMALIZANDO: [PROCESANDO, ERROR_PROCESO, RECIBIDO],
         ERROR_PROCESO: [NORMALIZANDO]},
        intermedios=[RECIBIDO, NORMALIZANDO, ERROR_PROCESO],
    ),
    # Un documento se crea cuando la normalización ya lo inventarió, con el
    # estado que le dio. Una copia exacta se queda como `duplicado`: no se
    # clasifica ni se extrae otra vez (R10).
    DOCUMENTO: _m(
        [NORMALIZADO, DUPLICADO, ERROR_ENTRADA],
        {
            NORMALIZADO: [CLASIFICADO, ESPERANDO_CLASIFICACION_HUMANA, ERROR_PROCESO],
            ESPERANDO_CLASIFICACION_HUMANA: [CLASIFICADO],
            ERROR_PROCESO: [CLASIFICADO, ESPERANDO_CLASIFICACION_HUMANA],
        },
        intermedios=[NORMALIZADO, ESPERANDO_CLASIFICACION_HUMANA, ERROR_PROCESO],
    ),
    # Un segmento se crea al clasificar. `pendiente` quiere decir que su
    # solicitud de extracción ya salió; desde ahí sigue la entrega 2.
    SEGMENTO: _m(
        [PENDIENTE, SIN_EXTRACCION, ESPERANDO_CLASIFICACION_HUMANA],
        {ESPERANDO_CLASIFICACION_HUMANA: [PENDIENTE, SIN_EXTRACCION]},
        intermedios=[ESPERANDO_CLASIFICACION_HUMANA],
    ),
    TAREA: _m([ABIERTA], {ABIERTA: [RESUELTA]}),
}

RESERVADOS = ("estado", "entrega", "historial")


class TransicionNoPermitida(Exception):
    """El código pidió un estado o un cambio que la máquina no tiene: un bug (clase 4)."""


class EstadoInesperado(Exception):
    """El registro no está en el estado del que se quería partir.

    No es un bug: suele ser un mensaje repetido o que llegó tarde. Quien llama
    decide qué hacer (R26).
    """

    def __init__(self, registro: Registro, esperados: frozenset[str]) -> None:
        self.registro = registro
        self.esperados = esperados
        super().__init__(
            f"{registro.tipo} {registro.id} está en {registro.datos['estado']}, "
            f"se esperaba {' o '.join(sorted(esperados))}"
        )


class NoExiste(Exception):
    """Se quiso cambiar un registro que no existe: un bug (clase 4)."""


@dataclass(frozen=True)
class Cambio:
    registro: Registro
    aplicado: bool
    """False si ya estaba en el estado pedido (un mensaje repetido) o si ya existía."""


def _maquina(tipo: str) -> Maquina:
    try:
        return MAQUINAS[tipo]
    except KeyError:
        raise TransicionNoPermitida(f"Tipo desconocido: {tipo}") from None


def _paso(de: str | None, a: str, cuando: str, motivo: str) -> dict:
    return {"de": de, "a": a, "cuando": cuando, "motivo": motivo}


def crear(
    estado: Estado,
    reloj: Reloj,
    id_proceso: str,
    tipo: str,
    id: str,
    inicial: str,
    motivo: str,
    datos: dict | None = None,
    entrega: str | None = None,
) -> Cambio:
    """Crea el registro con su estado inicial. Si ya existía, lo deja como estaba
    y devuelve el existente (R27)."""
    maquina = _maquina(tipo)
    if inicial not in maquina.iniciales:
        raise TransicionNoPermitida(f"Un {tipo} no puede empezar en {inicial}")
    datos = dict(datos or {})
    if reservados := [k for k in RESERVADOS if k in datos]:
        raise TransicionNoPermitida(f"Campos reservados en los datos: {', '.join(reservados)}")
    if tipo == PROCESO:
        if entrega is not None:
            raise TransicionNoPermitida("El proceso no lleva entrega")
    elif not entrega:
        raise TransicionNoPermitida(f"Un {tipo} necesita su entrega ({ENTREGA_DEL_PROCESO} o el oferente)")
    else:
        datos["entrega"] = entrega
    datos["estado"] = inicial
    datos["historial"] = [_paso(None, inicial, reloj.ahora().isoformat(), motivo)]
    registro, creado = estado.crear_si_no_existe(id_proceso, tipo, id, datos)
    return Cambio(registro, creado)


def cambiar(
    estado: Estado,
    reloj: Reloj,
    id_proceso: str,
    tipo: str,
    id: str,
    de: str | tuple[str, ...],
    a: str,
    motivo: str,
    datos: dict | None = None,
    intentos: int = 5,
    *,
    respetar_reserva: bool = False,
    dueno: str | None = None,
) -> Cambio:
    """Pasa el registro de `de` (uno o varios estados) a `a`, y le suma `datos`.

    - Si ya está en `a`, no hace nada y devuelve `aplicado=False`: es un mensaje
      repetido (R27).
    - Si está en otro estado, `EstadoInesperado` (R26).
    - Si otro trabajador lo cambió entre la lectura y la escritura, lo vuelve a
      leer y decide de nuevo, hasta `intentos` veces.
    - Con `respetar_reserva`, si el registro tiene una reserva vigente que no es de
      `dueno`, `Reservado`. Se revisa sobre la misma versión que se reemplaza, así
      que una reserva tomada entre la lectura y la escritura también cuenta.
    """
    maquina = _maquina(tipo)
    origenes = frozenset([de] if isinstance(de, str) else de)
    for origen in origenes:
        if a not in maquina.transiciones.get(origen, ()):
            raise TransicionNoPermitida(f"Un {tipo} no pasa de {origen} a {a}")
    datos = dict(datos or {})
    if reservados := [k for k in RESERVADOS if k in datos]:
        raise TransicionNoPermitida(f"Campos reservados en los datos: {', '.join(reservados)}")

    for _ in range(intentos):
        registro = estado.leer(id_proceso, tipo, id)
        if registro is None:
            raise NoExiste(f"No existe {tipo} {id} en {id_proceso}")
        actual = registro.datos["estado"]
        if actual == a:
            return Cambio(registro, False)
        if actual not in origenes:
            raise EstadoInesperado(registro, origenes)
        if respetar_reserva and (vigente := reserva_vigente(registro, reloj.ahora())) and vigente["dueno"] != dueno:
            raise Reservado(registro, datetime.datetime.fromisoformat(vigente["vence"]))
        nuevos = {**registro.datos, **datos, "estado": a}
        nuevos["historial"] = registro.datos["historial"] + [_paso(actual, a, reloj.ahora().isoformat(), motivo)]
        try:
            return Cambio(estado.reemplazar(registro, nuevos), True)
        except Conflicto:
            continue
    raise Conflicto(f"{tipo} {id}: siguió cambiando después de {intentos} intentos")


class Reservado(Exception):
    """Otra ejecución tiene la reserva vigente del registro."""

    def __init__(self, registro: Registro, vence: datetime.datetime) -> None:
        self.registro = registro
        self.vence = vence
        super().__init__(f"{registro.tipo} {registro.id} está reservado hasta {vence.isoformat()}")


def reserva_vigente(registro: Registro, ahora: datetime.datetime) -> dict | None:
    """La reserva del registro, si tiene una que no ha vencido."""
    reserva = registro.datos.get("reserva")
    if reserva and datetime.datetime.fromisoformat(reserva["vence"]) > ahora:
        return reserva
    return None


def reservar(
    estado: Estado,
    reloj: Reloj,
    id_proceso: str,
    tipo: str,
    id: str,
    de: tuple[str, ...],
    reservado: str,
    dueno: str,
    duracion_s: float,
    motivo: str,
    intentos: int = 5,
) -> Registro:
    """Pasa el registro de `de` a `reservado` con una reserva de `dueno` que vence
    en `duracion_s`, para que una sola ejecución haga el trabajo (decisión 6 de
    `tasks-workers.md`).

    - Si ya está en `reservado` con una reserva vigente de otro, `Reservado`.
    - Si la reserva venció (la ejecución que la tenía ya no existe), la toma.
    - Si la reserva ya es de `dueno`, la devuelve sin cambios.
    - En otro estado, `EstadoInesperado`.

    El cambio es condicional: si dos ejecuciones reservan a la vez, gana una.
    """
    maquina = _maquina(tipo)
    origenes = frozenset(de)
    for origen in origenes:
        if reservado not in maquina.transiciones.get(origen, ()):
            raise TransicionNoPermitida(f"Un {tipo} no pasa de {origen} a {reservado}")
    for _ in range(intentos):
        registro = estado.leer(id_proceso, tipo, id)
        if registro is None:
            raise NoExiste(f"No existe {tipo} {id} en {id_proceso}")
        actual = registro.datos["estado"]
        ahora = reloj.ahora()
        paso = motivo
        reserva = registro.datos.get("reserva") or {}
        desde = actual
        if actual == reservado:
            if reserva.get("dueno") == dueno:
                return registro
            if vigente := reserva_vigente(registro, ahora):
                raise Reservado(registro, datetime.datetime.fromisoformat(vigente["vence"]))
            paso = "reserva vencida"
            desde = reserva.get("desde", actual)
        elif actual not in origenes:
            raise EstadoInesperado(registro, origenes)
        vence = ahora + datetime.timedelta(seconds=duracion_s)
        nuevos = {**registro.datos, "estado": reservado,
                  "reserva": {"dueno": dueno, "vence": vence.isoformat(), "desde": desde}}
        nuevos["historial"] = registro.datos["historial"] + [_paso(actual, reservado, ahora.isoformat(), paso)]
        try:
            return estado.reemplazar(registro, nuevos)
        except Conflicto:
            continue
    raise Conflicto(f"{tipo} {id}: siguió cambiando después de {intentos} intentos")


def liberar(estado: Estado, reloj: Reloj, id_proceso: str, tipo: str, id: str, dueno: str, motivo: str) -> None:
    """Si la reserva sigue siendo de `dueno`, devuelve el registro al estado del que
    se reservó, para que el reintento lo tome enseguida."""
    for _ in range(5):
        registro = estado.leer(id_proceso, tipo, id)
        reserva = registro.datos.get("reserva") if registro else None
        if not reserva or reserva.get("dueno") != dueno:
            return
        actual, desde = registro.datos["estado"], reserva["desde"]
        nuevos = {**registro.datos, "estado": desde, "reserva": None}
        nuevos["historial"] = registro.datos["historial"] + [_paso(actual, desde, reloj.ahora().isoformat(), motivo)]
        try:
            estado.reemplazar(registro, nuevos)
            return
        except Conflicto:
            continue


def anotar(
    estado: Estado, id_proceso: str, tipo: str, id: str, datos: dict, intentos: int = 5,
) -> Registro:
    """Suma `datos` al registro sin cambiar su estado ni su historial.

    Para marcas de trabajo hecho, como "ya se publicaron las entregas". Si otro
    trabajador lo cambió entre la lectura y la escritura, lo vuelve a intentar.
    """
    if reservados := [k for k in RESERVADOS if k in datos]:
        raise TransicionNoPermitida(f"Campos reservados en los datos: {', '.join(reservados)}")
    for _ in range(intentos):
        registro = estado.leer(id_proceso, tipo, id)
        if registro is None:
            raise NoExiste(f"No existe {tipo} {id} en {id_proceso}")
        try:
            return estado.reemplazar(registro, {**registro.datos, **datos})
        except Conflicto:
            continue
    raise Conflicto(f"{tipo} {id}: siguió cambiando después de {intentos} intentos")


def consultar(estado: Estado, id_proceso: str) -> dict | None:
    """En qué va un proceso (R25): por entrega, cuántos documentos y segmentos
    hay en cada estado, cuántos registros siguen en un estado intermedio
    (`en_curso`) y las tareas abiertas.

    None si el proceso no existe.
    """
    proceso = estado.leer(id_proceso, PROCESO, id_proceso)
    if proceso is None:
        return None
    entregas: dict[str, dict] = {}

    def de(entrega: str) -> dict:
        return entregas.setdefault(entrega, {
            "estado": None, "documentos": Counter(), "segmentos": Counter(), "tareas_abiertas": 0, "en_curso": 0,
        })

    tareas = []
    for r in estado.listar(id_proceso):
        if r.tipo == PROCESO:
            continue
        resumen = de(r.datos["entrega"])
        actual = r.datos["estado"]
        if r.tipo == OFERENTE:
            resumen["estado"] = actual
        elif r.tipo == DOCUMENTO:
            resumen["documentos"][actual] += 1
        elif r.tipo == SEGMENTO:
            resumen["segmentos"][actual] += 1
        elif r.tipo == TAREA and actual == ABIERTA:
            resumen["tareas_abiertas"] += 1
            tareas.append({"id": r.id, "entrega": r.datos["entrega"], "clase": r.datos.get("clase"),
                           "motivo": r.datos.get("motivo")})
        if actual in MAQUINAS[r.tipo].intermedios:
            resumen["en_curso"] += 1

    for resumen in entregas.values():
        resumen["documentos"] = dict(sorted(resumen["documentos"].items()))
        resumen["segmentos"] = dict(sorted(resumen["segmentos"].items()))
    return {
        "id_proceso": id_proceso,
        "estado": proceso.datos["estado"],
        "entregas": dict(sorted(entregas.items())),
        "tareas_abiertas": tareas,
    }
