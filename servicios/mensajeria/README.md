# Mensajería

Colas, Service Bus y el bucle de errores que comparten el orquestador (módulo 5) y la extracción (módulo 3). Así cada worker usa la misma cola y las mismas clases de error sin que un servicio dependa del otro (decisión 1 de `specs/005-orquestador/tasks-workers.md`).

| Módulo | Qué hay |
|---|---|
| `cola.py` | La interfaz `Cola`, `ColaEnMemoria`, los nombres de las colas y `Mensaje` |
| `cola_servicebus.py` | `ColaServiceBus` y `cola_desde_entorno` (`SERVICEBUS_NAMESPACE`, `COLAS_PREFIJO`) |
| `errores.py` | `procesar_uno`, el bucle que corre cada manejador, y las clases de error (`ErrorTransitorio`, `ErrorDeConfiguracion`, `MensajeRechazado`, etc.) |
| `parametros.py` | Reintentos, esperas y renovación del bloqueo |
| `registros.py` | Contexto de los registros de un mensaje y el registro `mensajeria.alertas` |
| `reloj.py` | `Reloj`, `RelojSistema` y `RelojManual` |

Depende de la normalización solo por sus registros y por las excepciones del almacén, que el bucle trata como transitorias o de configuración.

El orquestador conserva sus módulos `orquestador.cola`, `orquestador.cola_servicebus`, `orquestador.errores` y `orquestador.reloj` como alias de estos. Las pruebas de la cola y del bucle siguen en `servicios/orquestador/tests` y corren sobre estos mismos módulos.

```bash
uv run pytest -q
```
