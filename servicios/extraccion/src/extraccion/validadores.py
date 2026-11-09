"""Validadores deterministas y genéricos (D16, R47).

El código no sabe nada de cada tipo documental: la ficha dice qué validador
aplica a cada campo y con qué parámetros, en `atributos.validador`, una lista de
`{"tipo": …, …parámetros}` (principio 2). Hoy v21 no declara ninguno; las fichas
de prueba sí.

Sin declararlo, siempre se aplica `en_catalogo` con lo que la ficha ya trae: los
`valores_permitidos` del elemento y, en las propiedades de un objeto, las opciones
que son códigos (`SI / NO / null`, `RL / RF / CONTADOR`). Las opciones en
minúsculas (`fecha / Indefinida`, `manuscrita / digital`) describen el dato más
que listarlo, y no se validan.

Cada validador devuelve la lista de fallas, en texto para quien revisa. Un valor
`null` no se valida: de eso se ocupa `OBLIGATORIO_VACIO`. Un dato que no se puede
leer como número o fecha no hace fallar a un validador que no es de formato.
"""

import datetime
import re
from decimal import Decimal, InvalidOperation

CODIGO = re.compile(r"^[A-Z0-9_]+$")
PESOS_NIT = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


class ValidadorDesconocido(Exception):
    """La ficha declara un validador que el código no tiene: un error de la ficha."""


def _registros(valor) -> list[dict]:
    if isinstance(valor, dict):
        return [valor]
    if isinstance(valor, list):
        return [v for v in valor if isinstance(v, dict)]
    return []


def _donde(valor, n: int) -> str:
    return f"fila {n}: " if isinstance(valor, list) else ""


def _numero(dato) -> Decimal | None:
    if isinstance(dato, bool) or dato is None:
        return None
    try:
        return Decimal(str(dato).strip())
    except InvalidOperation:
        return None


def _fecha(dato) -> datetime.date | None:
    if not isinstance(dato, str):
        return None
    try:
        return datetime.date.fromisoformat(dato.strip()) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dato.strip()) else None
    except ValueError:
        return None


def _opciones(texto: str) -> list[str | None]:
    return [None if o.strip() == "null" else o.strip() for o in texto.split("/")]


# --- Validadores -----------------------------------------------------------


def en_catalogo(elemento: dict, valor) -> list[str]:
    fallas = []
    permitidos = elemento.get("valores_permitidos")
    if isinstance(permitidos, list) and permitidos:
        validos = {p["valor"] if isinstance(p, dict) else p for p in permitidos}
        if isinstance(valor, str):
            if valor not in validos:
                fallas.append(f"'{valor}' no está entre los valores permitidos ({', '.join(sorted(map(str, validos)))}).")
        elif isinstance(valor, list):
            fuera = [v for v in valor if v not in validos]
            if fuera:
                fallas.append(f"{', '.join(map(repr, fuera))} no están entre los valores permitidos.")
    for propiedad in elemento.get("atributos", {}).get("propiedades", []):
        if "valores" not in propiedad:
            continue
        opciones = _opciones(propiedad["valores"])
        codigos = [o for o in opciones if o is not None]
        if not codigos or not all(CODIGO.match(o) for o in codigos):
            continue
        for n, registro in enumerate(_registros(valor), start=1):
            dato = registro.get(propiedad["nombre"])
            if dato is not None and dato not in codigos:
                fallas.append(f"{_donde(valor, n)}{propiedad['nombre']} = '{dato}' no está entre {propiedad['valores']}.")
    return fallas


def nit_dv(valor, propiedad: str | None = None) -> list[str]:
    """El dígito de verificación del NIT, con el algoritmo de la DIAN. Sin DV, no se verifica."""
    fallas = []
    datos = [r.get(propiedad) for r in _registros(valor)] if propiedad else [valor]
    for dato in datos:
        if not isinstance(dato, str):
            continue
        partes = re.fullmatch(r"(\d{5,15})-(\d)", re.sub(r"[.\s]", "", dato))
        if not partes:
            continue
        numero, dv = partes.groups()
        suma = sum(int(d) * p for d, p in zip(reversed(numero), PESOS_NIT))
        resto = suma % 11
        esperado = resto if resto < 2 else 11 - resto
        if int(dv) != esperado:
            fallas.append(f"El dígito de verificación del NIT {dato} no es correcto (debería ser {esperado}).")
    return fallas


def fecha(valor, propiedad: str | None = None) -> list[str]:
    """El dato es una fecha AAAA-MM-DD que existe."""
    fallas = []
    datos = [(n, r.get(propiedad)) for n, r in enumerate(_registros(valor), start=1)] if propiedad else [(1, valor)]
    for n, dato in datos:
        if dato is not None and _fecha(dato) is None:
            fallas.append(f"{_donde(valor, n) if propiedad else ''}'{dato}' no es una fecha AAAA-MM-DD válida.")
    return fallas


def fecha_orden(valor, desde: str, hasta: str) -> list[str]:
    """`desde` no es posterior a `hasta`, en el objeto o en cada fila."""
    fallas = []
    for n, registro in enumerate(_registros(valor), start=1):
        inicio, fin = _fecha(registro.get(desde)), _fecha(registro.get(hasta))
        if inicio and fin and inicio > fin:
            fallas.append(f"{_donde(valor, n)}{desde} {inicio} es posterior a {hasta} {fin}.")
    return fallas


def _suma(filas: list[dict], columna: str) -> Decimal | None:
    numeros = [_numero(f.get(columna)) for f in filas]
    if not numeros or any(n is None for n in numeros):
        return None
    return sum(numeros, Decimal(0))


def suma_igual(valor, total: str, campo: str, columna: str, tolerancia=0, valores: dict | None = None) -> list[str]:
    """El `total` declarado es la suma de `columna` en las filas del campo `campo`."""
    declarado = _numero(valor.get(total)) if isinstance(valor, dict) else None
    filas = _registros((valores or {}).get(campo))
    calculado = _suma(filas, columna) if filas else None
    if declarado is None or calculado is None:
        return []
    diferencia = abs(declarado - calculado)
    if diferencia > _numero(tolerancia):
        return [f"{total} declarado {declarado}; la suma de {columna} en {campo} da {calculado} "
                f"(diferencia {diferencia}, tolerancia {tolerancia})."]
    return []


def suma_100(valor, columna: str, tolerancia=0) -> list[str]:
    """Los porcentajes de `columna` en las filas suman 100."""
    calculado = _suma(_registros(valor), columna)
    if calculado is None:
        return []
    if abs(calculado - 100) > _numero(tolerancia):
        return [f"{columna} suma {calculado}, no 100 (tolerancia {tolerancia})."]
    return []


def claves_objeto(valor, claves: list[str]) -> list[str]:
    """Cada registro tiene exactamente esas propiedades."""
    fallas = []
    esperadas = set(claves)
    for n, registro in enumerate(_registros(valor), start=1):
        sobran, faltan = sorted(set(registro) - esperadas), sorted(esperadas - set(registro))
        if sobran or faltan:
            detalle = "; ".join(filter(None, [sobran and f"sobran {', '.join(sobran)}", faltan and f"faltan {', '.join(faltan)}"]))
            fallas.append(f"{_donde(valor, n)}{detalle}.")
    if not isinstance(valor, (dict, list)):
        fallas.append("Se esperaba un objeto o una lista de objetos.")
    return fallas


VALIDADORES = {
    "nit_dv": nit_dv,
    "fecha": fecha,
    "fecha_orden": fecha_orden,
    "suma_igual": suma_igual,
    "suma_100": suma_100,
    "claves_objeto": claves_objeto,
    "en_catalogo": lambda valor, elemento: en_catalogo(elemento, valor),
}
CON_VALORES = {"suma_igual"}
"""Los que miran otros campos del mismo documento."""


def validar(elemento: dict, valor, valores: dict) -> list[str]:
    """Las fallas del valor de un elemento: `en_catalogo` siempre, más los que declara la ficha.

    `valores` son los valores de todos los campos del documento, por `id_tecnico`.
    """
    if valor is None:
        return []
    fallas = [f"Validador en_catalogo: {f}" for f in en_catalogo(elemento, valor)]
    for declarado in elemento.get("atributos", {}).get("validador", []):
        parametros = {k: v for k, v in declarado.items() if k != "tipo"}
        funcion = VALIDADORES.get(declarado.get("tipo"))
        if funcion is None:
            raise ValidadorDesconocido(f"{elemento['id_tecnico']}: validador desconocido {declarado.get('tipo')!r}")
        if declarado["tipo"] in CON_VALORES:
            parametros["valores"] = valores
        if declarado["tipo"] == "en_catalogo":
            continue  # ya se aplicó
        fallas.extend(f"Validador {declarado['tipo']}: {f}" for f in funcion(valor, **parametros))
    return fallas
