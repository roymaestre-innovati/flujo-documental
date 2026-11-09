"""Una corrida local completa: del aviso a las solicitudes de extracción (T10).

Arma los manejadores sobre las versiones en memoria y corre las colas hasta
vaciarlas. Sirve para la prueba de punta a punta (A2), la de mensajes repetidos
(A3) y la corrida con la muestra (A4, T11).

- La normalización corre en hilos, como máximo `paralelo_normalizar` entregas a
  la vez. Es lo que en producción hará la configuración del job (entrega 2).
- Las demoras de los reintentos no se esperan: cuando no queda nada visible, se
  adelanta el reloj hasta el siguiente mensaje.
- La cola `extraer` no la consume nadie en esta entrega: sus mensajes se sacan y
  se devuelven como las solicitudes de la corrida.
"""

import datetime
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from normalizacion.almacen import Almacen

from . import CONTRATO, estados
from .apertura import Apertura
from .clasificador import Clasificador
from .clasificar import Clasificar
from .cola import CLASIFICAR, COLAS, EXTRAER, NORMALIZAR, PROCESOS_LISTOS, ColaEnMemoria
from .errores import Manejador, procesar_uno
from .estado import Estado, EstadoEnMemoria
from .extraer import Extraer
from .normalizar import Normalizar
from .origen import Origen
from .parametros import PARAMETROS, Parametros
from .reloj import Reloj

registro = logging.getLogger("orquestador.local")


class RelojLocal(Reloj):
    """La hora del sistema, más lo que se adelantó para no esperar las demoras."""

    def __init__(self) -> None:
        self._desfase = datetime.timedelta()

    def ahora(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc) + self._desfase

    def adelantar(self, segundos: float) -> None:
        if segundos > 0:
            self._desfase += datetime.timedelta(seconds=segundos)


def aviso(id_proceso: str, ruta: str, reloj: Reloj) -> dict:
    """El aviso que mandaría el módulo 1 cuando el proceso queda completo."""
    return {"contrato": CONTRATO, "id_proceso": id_proceso, "ruta": ruta, "fecha": reloj.ahora().isoformat()}


@dataclass
class Corrida:
    origen: Origen
    almacen: Almacen
    clasificador: Clasificador
    reloj: Reloj = field(default_factory=RelojLocal)
    cola: ColaEnMemoria | None = None
    estado: Estado = field(default_factory=EstadoEnMemoria)
    parametros: Parametros = PARAMETROS
    soffice: str | None = None
    solicitudes: list[dict] = field(default_factory=list)
    """Las solicitudes de extracción publicadas, en orden."""

    def __post_init__(self) -> None:
        if self.cola is None:
            self.cola = ColaEnMemoria(self.reloj)
        self.extraer = Extraer(self.cola, self.almacen)
        self.apertura = Apertura(self.cola, self.estado, self.origen, self.reloj)
        self.normalizar = Normalizar(self.cola, self.estado, self.origen, self.almacen, self.reloj, self.soffice)
        self.clasificar = Clasificar(self.estado, self.almacen, self.clasificador, self.extraer, self.reloj)

    def publicar_aviso(self, cuerpo: dict) -> None:
        self.cola.publicar(PROCESOS_LISTOS, cuerpo)

    def correr(self) -> None:
        """Procesa todo lo que haya en las colas, hasta que no quede nada."""
        while True:
            trabajo = self._vaciar(self.apertura)
            trabajo += self._vaciar_en_paralelo(self.normalizar, self.parametros.paralelo_normalizar)
            trabajo += self._vaciar(self.clasificar)
            self._sacar_solicitudes()
            if trabajo:
                continue
            proxima = self.cola.proxima_visible()
            if proxima is None:
                return
            # Solo quedan mensajes con demora (reintentos): se adelanta el reloj.
            espera = (proxima - self.reloj.ahora()).total_seconds()
            registro.info("Se adelanta el reloj %.0f s hasta el siguiente reintento", max(espera, 0))
            self.reloj.adelantar(max(espera, 0))

    def _vaciar(self, manejador: Manejador) -> int:
        hechos = 0
        while procesar_uno(self.cola, manejador, self.parametros) is not None:
            hechos += 1
        return hechos

    def _vaciar_en_paralelo(self, manejador: Manejador, hilos: int) -> int:
        if hilos <= 1:
            return self._vaciar(manejador)
        with ThreadPoolExecutor(max_workers=hilos, thread_name_prefix=manejador.cola) as grupo:
            return sum(grupo.map(lambda _: self._vaciar(manejador), range(hilos)))

    def _sacar_solicitudes(self) -> None:
        while (mensaje := self.cola.recibir(EXTRAER)) is not None:
            self.solicitudes.append(mensaje.cuerpo)
            self.cola.completar(mensaje)


def conteos(corrida: Corrida, id_proceso: str) -> dict:
    """Lo que se informa de una corrida: solo conteos, sin nombres ni rutas (A4)."""
    estado = corrida.estado
    def por_estado(tipo):
        return dict(sorted(Counter(r.datos["estado"] for r in estado.listar(id_proceso, tipo)).items()))

    # A4: todo llega a las solicitudes o a una tarea. Lo que espera a una
    # persona tiene su tarea; lo demás en un estado intermedio quedó atascado.
    atascados = sum(
        1 for r in estado.listar(id_proceso)
        if r.datos["estado"] in estados.MAQUINAS[r.tipo].intermedios
        and r.datos["estado"] != estados.ESPERANDO_CLASIFICACION_HUMANA
    )
    tareas = [r for r in estado.listar(id_proceso, estados.TAREA) if r.datos["estado"] == estados.ABIERTA]
    return {
        "entregas": por_estado(estados.OFERENTE),
        "documentos": por_estado(estados.DOCUMENTO),
        "segmentos": por_estado(estados.SEGMENTO),
        "solicitudes_por_td": dict(sorted(Counter(s["tipo_documental"] for s in corrida.solicitudes).items())),
        "tareas_abiertas_por_clase": dict(sorted(Counter(t.datos["clase"] for t in tareas).items())),
        "tareas_abiertas_por_motivo": dict(sorted(Counter(t.datos["motivo"] for t in tareas).items())),
        "atascados": atascados,
        "mensajes_en_errores": {c: n for c in COLAS if (n := len(corrida.cola.errores(c)))},
        "mensajes_pendientes": {c: n for c in (NORMALIZAR, CLASIFICAR) if (n := corrida.cola.pendientes(c))},
    }
