"""El bucle de un worker: vacía una cola con un manejador y termina (T02 de
`specs/005-orquestador/tasks-workers.md`, decisiones 5 y 10).

Cada worker corre como un Container Apps Job. Una ejecución toma mensajes con
`procesar_uno` hasta que se cumple lo primero de esto:

- no queda nada visible en la cola (los mensajes con demora no hacen esperar: el
  disparador lanza otra ejecución cuando se vuelven visibles);
- se cumple el límite para tomar mensajes nuevos (`tomar_mensajes_s`), que debe
  dejar margen hasta el tiempo máximo del job para terminar el último;
- se cumple `max_mensajes`, si se dio;
- llega `SIGTERM` o `SIGINT`: no se toman mensajes nuevos y el que está en curso
  se termina. Si Azure corta antes, el mensaje no se completó y Service Bus lo
  vuelve a entregar.

Con varios hilos, cada uno recibe con su propia `Cola` (en Service Bus, su propio
cliente, receptor y renovador del bloqueo) y comparte el manejador.

Código de salida:

- 0: terminó normalmente, aunque algún mensaje haya ido a errores (ya se alertó);
- 2: la cola rechazó la configuración (`ErrorDeConfiguracion`, por ejemplo un
  permiso que falta);
- 1: cualquier otra falla de la cola o del entorno cortó la ejecución.
"""

import logging
import signal
import threading
import time
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field

from .cola import Cola
from .errores import ErrorDeConfiguracion, Manejador, procesar_uno
from .parametros import PARAMETROS, Parametros
from .registros import lugar_de_la_excepcion

registro = logging.getLogger("mensajeria.worker")

VACIA = "vacia"
TIEMPO = "tiempo"
MENSAJES = "mensajes"
SENAL = "senal"
FALLA = "falla"

SALIDA_OK = 0
SALIDA_FALLA = 1
SALIDA_CONFIGURACION = 2


@dataclass(frozen=True)
class Limites:
    tomar_mensajes_s: float = 1500
    """No se toman mensajes nuevos pasado este tiempo: 25 minutos, para un job de 30."""
    max_mensajes: int | None = None
    """Mensajes que toma la ejecución entre todos los hilos, si se quiere un tope."""

    def __post_init__(self) -> None:
        if self.tomar_mensajes_s <= 0:
            raise ValueError("tomar_mensajes_s debe ser positivo")
        if self.max_mensajes is not None and self.max_mensajes < 1:
            raise ValueError("max_mensajes debe ser 1 o más")


@dataclass
class Resumen:
    cola: str
    desenlaces: Counter = field(default_factory=Counter)
    """Mensajes por desenlace de `procesar_uno` (ok, reintento, a_errores, etc.)."""
    motivo_fin: str = VACIA
    duracion_s: float = 0
    falla: BaseException | None = None

    @property
    def mensajes(self) -> int:
        return sum(self.desenlaces.values())

    @property
    def codigo_salida(self) -> int:
        if self.falla is None:
            return SALIDA_OK
        if isinstance(self.falla, ErrorDeConfiguracion):
            return SALIDA_CONFIGURACION
        return SALIDA_FALLA


class _Control:
    """Lo que comparten los hilos: cuándo dejar de tomar mensajes y cuántos van."""

    def __init__(self, limites: Limites, detener: threading.Event, reloj: Callable[[], float]) -> None:
        self._limites = limites
        self._detener = detener
        self._reloj = reloj
        self._inicio = reloj()
        self._tomados = 0
        self._candado = threading.Lock()
        self.motivo: str | None = None

    def puede_tomar(self) -> bool:
        with self._candado:
            if self.motivo is not None:
                return False
            if self._detener.is_set():
                self.motivo = SENAL
            elif self._reloj() - self._inicio >= self._limites.tomar_mensajes_s:
                self.motivo = TIEMPO
            elif self._limites.max_mensajes is not None and self._tomados >= self._limites.max_mensajes:
                self.motivo = MENSAJES
            else:
                self._tomados += 1
                return True
            return False

    def devolver_turno(self) -> None:
        """La recepción no trajo nada: el turno no cuenta como mensaje tomado."""
        with self._candado:
            self._tomados -= 1

    def terminar(self, motivo: str) -> None:
        """El primer motivo queda, salvo `FALLA`, que siempre gana: el código de
        salida es 1 y el resumen debe decir por qué."""
        with self._candado:
            if self.motivo is None or motivo == FALLA:
                self.motivo = motivo

    def duracion(self) -> float:
        return self._reloj() - self._inicio


def vaciar(
    colas: Sequence[Cola],
    manejador: Manejador,
    *,
    parametros: Parametros = PARAMETROS,
    limites: Limites = Limites(),
    detener: threading.Event | None = None,
    reloj: Callable[[], float] = time.monotonic,
) -> Resumen:
    """Procesa mensajes de la cola del manejador, un hilo por cada `Cola` de `colas`.

    No lanza: una falla de la cola corta todos los hilos y queda en `Resumen.falla`.
    """
    if not colas:
        raise ValueError("Se necesita al menos una cola")
    control = _Control(limites, detener or threading.Event(), reloj)
    resumen = Resumen(manejador.cola)
    candado = threading.Lock()

    def consumir(cola: Cola) -> None:
        while control.puede_tomar():
            try:
                resultado = procesar_uno(cola, manejador, parametros)
            except BaseException as error:
                control.terminar(FALLA)
                with candado:
                    if resumen.falla is None:
                        resumen.falla = error
                return
            if resultado is None:
                control.devolver_turno()
                control.terminar(VACIA)
                return
            with candado:
                resumen.desenlaces[resultado.desenlace] += 1

    if len(colas) == 1:
        consumir(colas[0])
    else:
        with ThreadPoolExecutor(max_workers=len(colas), thread_name_prefix=manejador.cola) as grupo:
            list(grupo.map(consumir, colas))

    resumen.motivo_fin = control.motivo or VACIA
    resumen.duracion_s = round(control.duracion(), 1)
    return resumen


@contextmanager
def atender_senales(detener: threading.Event):
    """Mientras dura el bloque, `SIGTERM` y `SIGINT` piden terminar en vez de cortar.

    Solo se puede usar desde el hilo principal. Al salir, deja las señales como estaban.
    """
    def pedir_que_termine(numero, _marco):
        registro.warning("Señal %s: no se toman mensajes nuevos", signal.Signals(numero).name)
        detener.set()

    anteriores = {s: signal.signal(s, pedir_que_termine) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        yield detener
    finally:
        for senal, anterior in anteriores.items():
            signal.signal(senal, anterior)


def informar(resumen: Resumen) -> int:
    """Registra el resumen de la ejecución, solo con conteos, y devuelve el código de salida."""
    datos = (resumen.cola, resumen.mensajes, dict(sorted(resumen.desenlaces.items())),
             resumen.motivo_fin, resumen.duracion_s)
    if resumen.falla is None:
        registro.info("Worker %s: %s mensajes %s, terminó por %s en %s s", *datos)
    else:
        registro.error("Worker %s: %s mensajes %s, terminó por %s (%s) en %s s", *datos[:4],
                       lugar_de_la_excepcion(resumen.falla), datos[4])
    return resumen.codigo_salida
