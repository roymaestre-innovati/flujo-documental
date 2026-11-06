# Tareas 005 — Orquestador, entrega 1: del aviso a la cola de extracción

Sale de `plan.md`. Cada tarea termina con sus pruebas en verde y un commit propio.

**Estado al 2026-11-06: por empezar.** Primero se revisan `spec.md` y `plan.md`.

## Para quien implemente

- Leer antes `spec.md` y `plan.md` de esta carpeta. El diseño está en `contexto/flujo-documental-opcion-a.md` (pasos 0, 3 y 4) y las reglas del proyecto, en `contexto/constitucion.md`.
- La normalización es `servicios/normalizacion/` (iniciativa 003). Se usa como está; si algo hace falta cambiarle, se anota aquí y se le pregunta al usuario antes.
- Solo documentos inventados, fabricados por las pruebas. Nada de Azure ni de LLM en este código.
- Escribir en español: código con nombres en español y documentos en prosa.
- Flujo por tarea: rama nueva desde `main`, pruebas en verde, notas aquí, commit, push y un resumen corto. **Después, alto para revisión del usuario.**
- Lo ambiguo se anota en "Notas de implementación" y se le pregunta al usuario, con una recomendación.

## Tareas

- [ ] **T01 — Contratos.** Escribir `contracts/modulo5-orquestador/v0/` (`README.md`, `proceso-listo.schema.json`, `clasificacion-solicitud.schema.json`, `clasificacion-respuesta.schema.json` y ejemplos: un aviso con y sin lista de archivos, una solicitud, y respuestas normal, compuesta, dudosa e inválida) y `contracts/modulo3-extraccion/v0.2/` (`README.md`, `entrada.schema.json` y `salida.schema.json` con los ocho cambios del plan, y los ejemplos de TD-16 y TD-29 pasados a 0.2, más uno de un documento del proceso sin oferente). Validar los ejemplos contra los esquemas. `v0/` de extracción no se toca. **Detenerse aquí para revisión del usuario** (principio 5), incluido el cambio de `id_documento` a `id_segmento`.
- [ ] **T02 — Esqueleto.** `servicios/orquestador/` con `pyproject.toml` (uv, pytest, `normalizacion` como dependencia de ruta), `VERSION = "0.1.0"`, los datos (`versiones.json`, `umbrales.json`, `tipos_documentales.json`) y las interfaces con su versión local: `ColaEnMemoria`, `EstadoEnMemoria`, `OrigenLocal`, `ClasificadorFalso` y el reloj. Prueba que valida los ejemplos de los contratos.
- [ ] **T03 — Estado.** Las cinco entidades, sus transiciones permitidas, el cambio condicional con historial y `consultar(id_proceso)`. Una transición no permitida es un bug (clase 4). Requisitos R24 a R26 y R28.
- [ ] **T04 — Bucle y errores.** El bucle común que corre un manejador sobre un mensaje y traduce cada excepción a su clase: reintentos con demora creciente, espera pedida por el servicio sin contar intento, cola de errores, `error_proceso`, registro de alerta y `reenviar_errores`. Se prueba con manejadores de juguete. Requisitos R18 a R21 y R23.
- [ ] **T05 — Apertura.** Manejador de `procesos-listos`: valida el aviso, abre el proceso con `crear_si_no_existe`, fija las versiones, reparte las entregas (con la lista de archivos del aviso, sin leer el origen, o listando las carpetas) y publica un `normalizar` por entrega. Requisitos R1 a R5.
- [ ] **T06 — Normalizar.** Manejador de `normalizar`: baja los originales de `Origen` a una carpeta temporal que se borra al terminar, llama a `normalizar_entrega` con la versión fijada, registra cada documento, crea la tarea `documento_con_error` por cada `error_entrada` y publica un `clasificar` por documento normalizado. `ErrorEntrega` es clase 4. Como máximo 2 entregas a la vez (`paralelo_normalizar`), también en la versión local. Requisitos R3, R6 a R8.
- [ ] **T07 — Clasificar.** Manejador de `clasificar`: arma la solicitud del contrato, llama al clasificador, valida la respuesta (un reintento), aplica los umbrales fijados, crea los segmentos y las tareas de clasificación. Las copias toman los segmentos del original. TD-98 y TD-99 quedan `sin_extraccion`. Requisitos R9 a R14.
- [ ] **T08 — Solicitudes de extracción.** Por cada segmento que se extrae, arma la solicitud 0.2, la valida contra el esquema y la publica en `extraer`. Incluye los documentos del proceso sin oferente. Requisitos R16 y R17.
- [ ] **T09 — Tareas.** Resolver una tarea de clasificación (asigna TD, registra quién y publica la solicitud) y `escalar_fallas(ahora)` para las 24 horas. Requisitos R15 y R22.
- [ ] **T10 — Punta a punta.** Comando `orquestar` y prueba de punta a punta con un proceso inventado (proceso y dos oferentes, con copia, contraseña, dudosa, baja confianza y TD-99). Prueba de mensajes repetidos: cada mensaje entregado dos veces da el mismo estado y las mismas solicitudes. README del servicio. Criterios A2 y A3.
- [ ] **T11 — Corrida con la muestra.** `scripts/correr_muestra.py`: convierte `manifiesto.csv` de la clasificación manual al CSV del clasificador falso y corre `orquestar` sobre la muestra, imprimiendo solo conteos (criterio A4). Lo corre el usuario en su máquina; se le dan los comandos y cuánto tarda.

**Al cerrar la entrega:** actualizar el estado en `spec.md`, `plan.md` (sección "Lo que cambió al implementar"), el README del repo y `contexto/HANDOFF-implementacion.md`.

## Notas de implementación
