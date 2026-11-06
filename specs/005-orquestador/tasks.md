# Tareas 005 — Orquestador, entrega 1: del aviso a la cola de extracción

Sale de `plan.md`. Cada tarea termina con sus pruebas en verde y un commit propio.

**Estado al 2026-11-06:** T01 a T03 fusionadas; T04 hecha, en revisión.

## Para quien implemente

- Leer antes `spec.md` y `plan.md` de esta carpeta. El diseño está en `contexto/flujo-documental-opcion-a.md` (pasos 0, 3 y 4) y las reglas del proyecto, en `contexto/constitucion.md`.
- La normalización es `servicios/normalizacion/` (iniciativa 003). Se usa como está; si algo hace falta cambiarle, se anota aquí y se le pregunta al usuario antes.
- Solo documentos inventados, fabricados por las pruebas. Nada de Azure ni de LLM en este código.
- Escribir en español: código con nombres en español y documentos en prosa.
- Flujo por tarea: rama nueva desde `main`, pruebas en verde, notas aquí, commit, push y un resumen corto. **Después, alto para revisión del usuario.**
- Lo ambiguo se anota en "Notas de implementación" y se le pregunta al usuario, con una recomendación.

## Tareas

- [x] **T01 — Contratos.** Escribir `contracts/modulo5-orquestador/v0/` (`README.md`, `proceso-listo.schema.json`, `clasificacion-solicitud.schema.json`, `clasificacion-respuesta.schema.json` y ejemplos: un aviso con y sin lista de archivos, una solicitud, y respuestas normal, compuesta, dudosa e inválida) y `contracts/modulo3-extraccion/v0.2/` (`README.md`, `entrada.schema.json` y `salida.schema.json` con los ocho cambios del plan, y los ejemplos de TD-16 y TD-29 pasados a 0.2, más uno de un documento del proceso sin oferente). Validar los ejemplos contra los esquemas. `v0/` de extracción no se toca. **Detenerse aquí para revisión del usuario** (principio 5), incluido el cambio de `id_documento` a `id_segmento`.
- [x] **T02 — Esqueleto.** `servicios/orquestador/` con `pyproject.toml` (uv, pytest, `normalizacion` como dependencia de ruta), `VERSION = "0.1.0"`, los datos (`versiones.json`, `umbrales.json`, `tipos_documentales.json`) y las interfaces con su versión local: `ColaEnMemoria`, `EstadoEnMemoria`, `OrigenLocal`, `ClasificadorFalso` y el reloj. Prueba que valida los ejemplos de los contratos.
- [x] **T03 — Estado.** Las cinco entidades, sus transiciones permitidas, el cambio condicional con historial y `consultar(id_proceso)`. Una transición no permitida es un bug (clase 4). Requisitos R24 a R26 y R28.
- [x] **T04 — Bucle y errores.** El bucle común que corre un manejador sobre un mensaje y traduce cada excepción a su clase: reintentos con demora creciente, espera pedida por el servicio sin contar intento, cola de errores, `error_proceso`, registro de alerta y `reenviar_errores`. Se prueba con manejadores de juguete. Requisitos R18 a R21 y R23.
- [ ] **T05 — Apertura.** Manejador de `procesos-listos`: valida el aviso, abre el proceso con `crear_si_no_existe`, fija las versiones, reparte las entregas (con la lista de archivos del aviso, sin leer el origen, o listando las carpetas) y publica un `normalizar` por entrega. Requisitos R1 a R5.
- [ ] **T06 — Normalizar.** Manejador de `normalizar`: baja los originales de `Origen` a una carpeta temporal que se borra al terminar, llama a `normalizar_entrega` con la versión fijada, registra cada documento, crea la tarea `documento_con_error` por cada `error_entrada` y publica un `clasificar` por documento normalizado. `ErrorEntrega` es clase 4. Como máximo 2 entregas a la vez (`paralelo_normalizar`), también en la versión local. Requisitos R3, R6 a R8.
- [ ] **T07 — Clasificar.** Manejador de `clasificar`: arma la solicitud del contrato, llama al clasificador, valida la respuesta (un reintento), aplica los umbrales fijados, crea los segmentos y las tareas de clasificación. Las copias toman los segmentos del original. TD-98 y TD-99 quedan `sin_extraccion`. Requisitos R9 a R14.
- [ ] **T08 — Solicitudes de extracción.** Por cada segmento que se extrae, arma la solicitud 0.2, la valida contra el esquema y la publica en `extraer`. Incluye los documentos del proceso sin oferente. Requisitos R16 y R17.
- [ ] **T09 — Tareas.** Resolver una tarea de clasificación (asigna TD, registra quién y publica la solicitud) y `escalar_fallas(ahora)` para las 24 horas. Requisitos R15 y R22.
- [ ] **T10 — Punta a punta.** Comando `orquestar` y prueba de punta a punta con un proceso inventado (proceso y dos oferentes, con copia, contraseña, dudosa, baja confianza y TD-99). Prueba de mensajes repetidos: cada mensaje entregado dos veces da el mismo estado y las mismas solicitudes. README del servicio. Criterios A2 y A3.
- [ ] **T11 — Corrida con la muestra.** `scripts/correr_muestra.py`: convierte `manifiesto.csv` de la clasificación manual al CSV del clasificador falso y corre `orquestar` sobre la muestra, imprimiendo solo conteos (criterio A4). Lo corre el usuario en su máquina; se le dan los comandos y cuánto tarda.

**Al cerrar la entrega:** actualizar el estado en `spec.md`, `plan.md` (sección "Lo que cambió al implementar"), el README del repo y `contexto/HANDOFF-implementacion.md`.

## Notas de implementación

### T01 — Contratos (2026-11-06)

Escritos `contracts/modulo5-orquestador/v0/` (0.1) y `contracts/modulo3-extraccion/v0.2/`. Todos los ejemplos validan contra sus esquemas, con chequeo de formato de URI y fechas (por eso los comandos de validación suman `rfc3987` y `rfc3339-validator`; el segundo se agregó en T02, cuando se vio que sin él las fechas no se revisaban). La `v0/` de extracción no se tocó. Los ejemplos de 0.2 de TD-16 y TD-29 se generaron desde los de 0.1, para no perder datos.

Lo que se decidió al escribir y conviene revisar:

1. **`id_segmento` e `id_documento` en extracción.** El segmento es `<id_documento>-p<desde>-<hasta>`; `id_documento` es el del manifiesto. Va en la entrada y en la salida.
2. **`id_oferente` obligatorio con `null`** en extracción y en la solicitud de clasificación, en vez de opcional, como en el contrato de normalización. El plan decía "opcional"; ya está ajustado.
3. **`confianza_clasificacion` admite `null`** en extracción, para cuando una persona asigna el TD.
4. **Clasificación dudosa en la salida:** todos los resultados salen con `revision: true` y el motivo `CLASIFICACION_DUDOSA`, incluidos los campos no encontrados. Así lo dice el diseño ("todo el documento va a revisión"). El ejemplo de TD-29 lo muestra.
5. **Solicitud de clasificación:** se quitó `nombre_origen`, porque `ruta_origen` ya trae el nombre, y se agregó `version_ontologia`, la fijada para el proceso (principio 7). La respuesta devuelve la que usó y el orquestador revisa que coincida.
6. **El aviso lleva `fecha`** (cuándo quedó completo el proceso) y `contrato`. `archivos` es opcional y, si llega, cada archivo trae `id_oferente` (`null` para los del proceso).
7. **`subtipo` obligatorio con `null`** en cada segmento, para TD-98 y TD-07.
8. **Ejemplo de respuesta inválida:** cumple el esquema pero le falta la página 7. Muestra que la cobertura de páginas la revisa el orquestador, no el esquema.
9. **URI de ejemplo** con `cuenta.blob.core.windows.net`: la forma `<cuenta>` no pasa el chequeo de URI.

### T02 — Esqueleto (2026-11-06)

`servicios/orquestador/` con `uv`, Python 3.12 y `normalizacion` como dependencia de ruta editable. 41 pruebas.

1. **Datos con un archivo por versión.** `datos/umbrales/1.json` y `datos/tipos_documentales/1.json`, más `datos/versiones.json` con las vigentes. Un proceso abierto lee la versión que fijó, así que las anteriores no se pueden pisar: para cambiar un umbral se agrega `2.json` y se apunta `versiones.json` a él. El plan decía un solo `umbrales.json`; ya está ajustado.
2. **Umbrales y tipos sacados de la matriz** (`~/GEB/Extraccion/matriz/campos.py`): Alta 0,95, Media 0,90, Baja 0,85, para TD-01 a TD-35. TD-98 se agregó a mano (decisión 14). Una prueba exige que cada TD que se extrae tenga umbral; no hay umbral por defecto.
3. **`reglas: null`** en las versiones vigentes, porque todavía no hay reglas publicadas. Se fija igual en el proceso.
4. **Los contratos se leen de `contracts/`** del repositorio. `ORQUESTADOR_CONTRATOS` permite otra carpeta, para la imagen de la entrega 2.
5. **Los errores de validación no traen valores**, solo el campo y la regla que falló (`fecha: no cumple 'format'`), porque terminan en los registros y una ruta puede traer el nombre de una persona.
6. **Fechas:** `jsonschema` solo revisa `date-time` con el paquete `rfc3339-validator`, y sin él la acepta sin decir nada. Se agregó al orquestador y a los comandos de validación de los README de los dos contratos. Los ejemplos de T01 siguen siendo válidos.
7. **Cola en memoria:** imita lo que importa de Service Bus: mensaje bloqueado mientras se trabaja, `abandonar` para simular un trabajador caído (vuelve a entregarse y sube `entregas`), demora y cola de errores por cola. `proxima_visible()` existe solo en la versión en memoria, para que el comando local adelante el reloj en vez de esperar.
8. **Estado en memoria:** solo `leer`, `crear_si_no_existe`, `reemplazar` condicional por versión (como el ETag de Cosmos) y `listar` por proceso. Los estados y las transiciones van en T03.
9. **Clasificador falso:** columna `subtipo` opcional; un documento que no está en el CSV sale TD-99 con confianza 1. No valida la respuesta, para poder probar respuestas malas en T07.

### T03 — Estado (2026-11-06)

`estados.py`: las cinco máquinas de estado, `crear`, `cambiar` y `consultar`. 65 pruebas.

1. **Solo los estados de la entrega 1.** Los de extracción, revisión, ficha y reglas se agregan en la entrega 2, cuando se sepa cómo se usan. Una prueba comprueba que cada estado es alcanzable.
2. **El documento no tiene `pendiente`.** Se crea cuando la normalización ya lo inventarió, directo en `normalizado`, `duplicado` o `error_entrada`. Antes de eso no se sabe qué documentos hay.
3. **La normalización que falla entera es un error de la entrega, no de los documentos.** Si `normalizar_entrega` lanza `ErrorEntrega`, no hay manifiesto y no hay documentos que marcar. Por eso el oferente (que es su entrega) tiene `error_proceso` → `procesando`. El escalamiento a 24 horas (T09) mira documentos y entregas.
4. **Una copia exacta se queda `duplicado`** y no tiene segmentos: no se clasifica ni se extrae (R10). En la consulta aparece con su `duplicado_de`.
5. **`esperando_clasificacion_humana` también en el segmento.** El diseño lo tenía solo en el archivo. En un archivo compuesto, un segmento puede tener confianza baja y los demás no: los buenos se extraen y solo ese espera. El documento queda en `esperando_clasificacion_humana` solo cuando la respuesta entera es inválida.
6. **`cambiar` con mensaje repetido:** si el registro ya está en el estado pedido, no hace nada y responde `aplicado=False`. Si está en otro estado, `EstadoInesperado`, y quien llama decide qué hacer. Si otro trabajador lo cambió entre la lectura y la escritura, relee y decide de nuevo, hasta 5 veces.
7. **Una transición que no existe es un bug** (`TransicionNoPermitida`, clase 4), igual que crear con un estado inicial que no corresponde.
8. **`consultar`** devuelve, por entrega, el estado del oferente, los documentos y segmentos por estado, las tareas abiertas y `en_curso`: cuántos registros siguen en un estado intermedio. El "¿oferente completo?" de la decisión 15 se arma con eso en la entrega 2, cuando se sumen los estados de la extracción.

### T04 — Bucle y errores (2026-11-06)

`errores.py` (clases de error, `procesar_uno` y `reenviar_errores`), `parametros.py` y `registros.py`. 79 pruebas, con manejadores de juguete.

1. **`intento` y `esperas` van en las propiedades del mensaje, no en el cuerpo.** El plan los ponía en el cuerpo, pero el aviso del módulo 1 no admite campos extra (`additionalProperties: false`) y dejaría de cumplir su contrato al reintentarse. La cola en memoria suma `propiedades`, como las application properties de Service Bus. Plan ajustado.
2. **Cada manejador tiene `procesar` y `al_fallar`.** El bucle no sabe qué entidad toca cada mensaje: cuando se agotan los reintentos o hay un bug, llama a `al_fallar` del manejador, que deja su entidad en `error_proceso`. Si `al_fallar` también falla, el mensaje va a errores igual y queda registrado.
3. **Reintentar es publicar de nuevo y completar el original**, en ese orden. Si el trabajador se cae entre los dos, el mensaje se repite, y lo absorbe la idempotencia de cada manejador.
4. **Esperas pedidas por el servicio:** no cuentan como intento, pero hay un tope de 20 (`max_esperas`), para que un servicio que siempre pide esperar no deje el mensaje dando vueltas para siempre. Pasado el tope sigue como una falla transitoria normal.
5. **Demoras:** 2, 4 y 8 minutos, como parámetro (`demora_base_s`). Una falla transitoria agotada son 4 intentos en total.
6. **Motivos sin datos personales:** solo el tipo de la excepción y el lugar del código (`KeyError en clasificar.py:42`), nunca su mensaje, con la misma función que la normalización. La alerta va al registro `orquestador.alertas` con nivel ERROR y los identificadores del mensaje.
7. **Renovar el bloqueo** de Service Bus queda para el bucle de la entrega 2: en memoria no vence.
8. **`reenviar_errores`** publica de nuevo desde el primer intento y conserva las demás propiedades.

