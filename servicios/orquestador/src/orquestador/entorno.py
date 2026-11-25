"""Las piezas de Azure de un worker, armadas desde el entorno (T03 de
`specs/005-orquestador/tasks-workers.md`, decisiones 9 y 11).

Un worker exige las versiones de Azure: no cae a la versión local si falta una
variable. Antes de crear nada se revisan todas las variables y, si falta alguna,
se lanza un solo `ErrorDeConfiguracion` que las nombra (nunca sus valores). Así
el worker sale con código 2 sin tocar la cola.

| Pieza | Variables |
|---|---|
| Cola (Service Bus) | `SERVICEBUS_NAMESPACE`; `COLAS_PREFIJO` opcional |
| Estado (Mongo) | `ESTADO_MONGO_URL`; `ESTADO_MONGO_BASE` y `ESTADO_MONGO_COLECCION` opcionales |
| Almacén (Blob) | `ALMACEN_BLOB_CUENTA`; `ALMACEN_BLOB_CONTENEDOR` opcional |
| Origen (OneLake), si el worker lo usa | `ONELAKE_WORKSPACE` y `ONELAKE_LAKEHOUSE` |

La identidad es `DefaultAzureCredential`: en Azure, la identidad administrada del
job (`AZURE_CLIENT_ID` si es asignada por el usuario).
"""

import os
from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Self

from normalizacion.almacen import Almacen, AlmacenSinPermiso

from .cola import Cola
from .cola_servicebus import cola_desde_entorno
from .errores import ErrorDeConfiguracion
from .estado import Estado
from .origen import Origen

VARIABLES_COMUNES = ("SERVICEBUS_NAMESPACE", "ESTADO_MONGO_URL", "ALMACEN_BLOB_CUENTA")
VARIABLES_ORIGEN = ("ONELAKE_WORKSPACE", "ONELAKE_LAKEHOUSE")


def estado_desde_entorno():
    """`EstadoMongo` con la cadena del entorno, y el cliente que hay que cerrar al terminar."""
    from .estado_mongo import EstadoMongo, coleccion_desde_entorno

    coleccion = coleccion_desde_entorno()
    cliente = coleccion.database.client
    try:
        return EstadoMongo(coleccion), cliente
    except BaseException:
        cliente.close()  # nadie más lo va a cerrar
        raise


def _crear_almacen():
    from normalizacion.almacen_blob import almacen_blob_desde_entorno

    return almacen_blob_desde_entorno()


def _crear_origen():
    from .origen_onelake import OrigenOneLake

    return OrigenOneLake(os.environ["ONELAKE_WORKSPACE"].strip(), os.environ["ONELAKE_LAKEHOUSE"].strip())


@contextmanager
def _como_configuracion():
    """Un `AlmacenSinPermiso` al armar las piezas es configuración, como en la cola y el estado."""
    try:
        yield
    except AlmacenSinPermiso as error:
        raise ErrorDeConfiguracion(str(error)) from None


@dataclass
class Fabricas:
    """Cómo se crea cada pieza. Las pruebas pasan versiones falsas."""

    cola: Callable[[], Cola] = cola_desde_entorno
    estado: Callable[[], tuple[Estado, object]] = estado_desde_entorno
    """Devuelve el estado y el recurso que hay que cerrar al terminar (el cliente de Mongo)."""
    almacen: Callable[[], Almacen] = _crear_almacen
    origen: Callable[[], Origen] = _crear_origen


@dataclass
class Piezas:
    estado: Estado
    almacen: Almacen
    origen: Origen | None
    _crear_cola: Callable[[], Cola]
    _recursos: ExitStack = field(repr=False)

    def cola(self) -> Cola:
        """Una cola nueva (en Service Bus, con su cliente y su receptor), cerrada al terminar."""
        with _como_configuracion():
            cola = self._crear_cola()
        if hasattr(cola, "cerrar"):
            self._recursos.callback(cola.cerrar)
        return cola

    def colas(self, cuantas: int) -> list[Cola]:
        """Una cola por hilo consumidor (decisión 4)."""
        return [self.cola() for _ in range(cuantas)]

    def cerrar(self) -> None:
        self._recursos.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.cerrar()


def faltantes(con_origen: bool) -> list[str]:
    """Las variables obligatorias que faltan o están vacías."""
    requeridas = VARIABLES_COMUNES + (VARIABLES_ORIGEN if con_origen else ())
    return [nombre for nombre in requeridas if not os.environ.get(nombre, "").strip()]


def piezas_desde_entorno(*, con_origen: bool, fabricas: Fabricas | None = None) -> Piezas:
    """Revisa el entorno y arma el estado, el almacén y, si se pide, el origen.

    Las colas se crean después, una por hilo, con `Piezas.colas`. Todo lo que se
    crea se cierra con `Piezas.cerrar`, también si algo falla a la mitad.
    """
    if faltan := faltantes(con_origen):
        raise ErrorDeConfiguracion("Faltan variables de entorno: " + ", ".join(faltan))
    fabricas = fabricas or Fabricas()
    with ExitStack() as recursos:
        with _como_configuracion():
            estado, cliente = fabricas.estado()
            if hasattr(cliente, "close"):
                recursos.callback(cliente.close)
            almacen = recursos.enter_context(fabricas.almacen())
            origen = fabricas.origen() if con_origen else None
        piezas = Piezas(estado, almacen, origen, fabricas.cola, recursos.pop_all())
    return piezas
