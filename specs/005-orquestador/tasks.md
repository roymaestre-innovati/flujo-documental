# Tareas 005 — Orquestador, entrega 1: del aviso a la cola de extracción

Sale de `plan.md`. Cada tarea termina con sus pruebas en verde y un commit propio.

**Estado al 2026-11-09:** T01 a T07 fusionadas; T08 hecha, en revisión.

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
- [x] **T05 — Apertura.** Manejador de `procesos-listos`: valida el aviso, abre el proceso con `crear_si_no_existe`, fija las versiones, reparte las entregas (con la lista de archivos del aviso, sin leer el origen, o listando las carpetas) y publica un `normalizar` por entrega. Requisitos R1 a R5.
- [x] **T06 — Normalizar.** Manejador de `normalizar`: baja los originales de `Origen` a una carpeta temporal que se borra al terminar, llama a `normalizar_entrega` con la versión fijada, registra cada documento, crea la tarea `documento_con_error` por cada `error_entrada` y publica un `clasificar` por documento normalizado. `ErrorEntrega` es clase 4. Requisitos R3, R6 a R8. (El límite de 2 entregas a la vez pasó a T10: ver la nota de T06.)
- [x] **T07 — Clasificar.** Manejador de `clasificar`: arma la solicitud del contrato, llama al clasificador, valida la respuesta (un reintento), aplica los umbrales fijados, crea los segmentos y las tareas de clasificación. Las copias no llegan aquí (ver la nota de T07). TD-98 y TD-99 quedan `sin_extraccion`. Requisitos R9 a R14.
- [x] **T08 — Solicitudes de extracción.** Por cada segmento que se extrae, arma la solicitud 0.2, la valida contra el esquema y la publica en `extraer`. Incluye los documentos del proceso sin oferente. Requisitos R16 y R17.
- [ ] **T09 — Tareas.** Resolver una tarea de clasificación (asigna TD, registra quién y publica la solicitud) y `escalar_fallas(ahora)` para las 24 horas. Requisitos R15 y R22.
- [ ] **T10 — Punta a punta.** Comando `orquestar`, que normaliza como máximo 2 entregas a la vez (`paralelo_normalizar`), y prueba de punta a punta con un proceso inventado (proceso y dos oferentes, con copia, contraseña, dudosa, baja confianza y TD-99). Prueba de mensajes repetidos: cada mensaje entregado dos veces da el mismo estado y las mismas solicitudes. README del servicio completo (ya existe uno parcial). Criterios A2 y A3.
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

### T05 — Apertura (2026-11-09)

`apertura.py`: el manejador de `procesos-listos` y `repartir`, la función que reparte los archivos entre entregas. 94 pruebas.

1. **Aviso que no se puede procesar: clase nueva `MensajeRechazado`.** Va a errores sin reintento y con alerta, igual que un bug, pero con el motivo `Rechazado: …` en vez de `Bug: …`, para que operación sepa que hay que hablar con el módulo 1 y no arreglar código. `MensajeInvalido` (no cumple el contrato) es un caso de esta clase. El motivo lleva solo campos, conteos y códigos, nunca rutas.
2. **Se rechaza el aviso entero si:**
   - no cumple el contrato;
   - la carpeta no existe;
   - hay archivos sueltos en la raíz;
   - no trae archivos o no trae ningún oferente;
   - un oferente se llama `PROCESO`.
   
   No se procesa a medias: un archivo suelto podría ser de un oferente. Un proceso sin entrega `PROCESO` sí se acepta, con los oferentes solos: la ficha, que necesita la CPC, es de la entrega 2.
3. **El aviso repetido** se reconoce por la marca `entregas_publicadas` del proceso. Con la marca, no hace nada; si trae otra ruta o fecha, se registra un aviso y se ignora: gana el primero (A-10 sigue en pausa). Sin la marca, el trabajador anterior se cayó a la mitad: se publican otra vez todas las entregas y alguna sale repetida, cosa que absorbe T06.
4. **El mensaje `normalizar` lleva solo `id_proceso` y `entrega`.** La lista de archivos de cada entrega queda en su registro de estado, así los mensajes no llevan rutas con nombres. El plan ponía también la ruta; ya está ajustado.
5. **Versiones fijadas** en el proceso: las vigentes de `datos/versiones.json` más la versión del normalizador y de sus parámetros.
6. **El proceso no tiene estado de error.** Si la apertura falla, no se abrió nada que el evaluador deba ver: el aviso queda en errores y le llega a operación por la alerta. `al_fallar` solo lo registra.
7. **`estados.anotar`**: suma datos a un registro sin cambiar su estado, para marcas como `entregas_publicadas`.

### T06 — Normalizar (2026-11-09)

`normalizar.py`: el manejador de `normalizar`. 105 pruebas, con PDF inventados hechos con reportlab y pikepdf (sin LibreOffice).

1. **El límite de 2 entregas a la vez pasó a T10.** Un manejador procesa un mensaje; cuántos corren en paralelo lo decide quien los corre: en producción, la configuración del job en Container Apps (entrega 2); en local, el comando `orquestar` de T10. Por eso se movió de T06 a T10.
2. **`ruta_origen` sin la carpeta de la entrega.** `OF-001/sub/carta.pdf` se baja como `sub/carta.pdf`, que es lo que entregó el oferente y de donde sale el `id_documento`. Con la lista del aviso, si el archivo no está bajo una carpeta con el nombre de la entrega, queda con su ruta completa.
3. **La entrega pasa a `procesando` al final**, después de registrar documentos, tareas y mensajes. Esa es la marca de "hecho": si el trabajador se cae antes, el mensaje se repite y todo se hace otra vez sin duplicar (la normalización reusa, `crear` no pisa). Los `clasificar` sí pueden salir dos veces; T07 los absorbe.
4. **Un archivo que falta en el origen es una falla transitoria**: se reintenta y, si no aparece, la entrega queda en `error_proceso` para operación. Con OneLake puede ser un problema de red o de permisos.
5. **Versión del normalizador distinta de la fijada:** no se normaliza; la entrega va a errores con `VersionNoCoincide`. Se resuelve con `reprocesar` (entrega 2), que deja constancia de por qué.
6. **El documento guarda del manifiesto** su ruta de origen, huella, tipo, URI del PDF, anexo y lectura, páginas, `duplicado_de` y error. La ruta de origen hace falta para la solicitud al clasificador.
7. **La tarea "documento con error"** lleva el código y el `detalle` que escribe la normalización, que dice qué pedirle al oferente y no trae texto del documento.
8. **Al volver de `error_proceso`** la entrega borra su `error`. El historial conserva el paso por el error.

### T07 — Clasificar (2026-11-09)

`clasificar.py`: el manejador de `clasificar` y `problemas_de_la_respuesta`. `tareas.py`: tareas humanas con identificador determinista, que ahora usa también la normalización. `tests/fabrica.py`: PDF inventados y un mundo local, compartidos por las pruebas. 132 pruebas.

1. **Las copias exactas no se clasifican ni tienen segmentos.** La tarea decía "las copias toman los segmentos del original", pero en T03 quedó que una copia se queda `duplicado`: si tuviera segmentos, se extraería dos veces lo mismo. "Toma el resultado del original" (R10) se cumple con `duplicado_de`: quien consulta la copia llega al original y a su clasificación.
2. **El reintento de una respuesta inválida es inmediato y dentro del mismo mensaje**, no un mensaje nuevo: el manejador llama al clasificador dos veces. Así la segunda falla crea la tarea de clasificación y no termina en la cola de errores, que es para fallas técnicas. Plan ajustado.
3. **Qué se revisa de la respuesta:** el contrato; páginas sin huecos, sin solapes, sin páginas de más y ningún segmento al revés; que cada TD exista en la versión de tipos fijada; y que `id_documento` y `version_ontologia` coincidan con la solicitud. Los problemas van en el `detalle` de la tarea, solo con códigos y números de página.
4. **Huella del PDF en la solicitud:** sale de `hash_pdf` de la lectura, que es la del PDF normalizado. La del manifiesto es la del original, que no coincide cuando hubo conversión.
5. **Umbrales:** la confianza igual al umbral se extrae normal y la igual al piso (0,75) se extrae como dudosa. Los umbrales y los tipos se leen de las versiones fijadas en el proceso, no de las vigentes.
6. **La tarea de confianza baja** dice qué TD sugiere el clasificador y con qué confianza, para ayudar a la persona. El documento queda `clasificado` y solo ese segmento espera; los demás del archivo siguen.
7. **Pedir la extracción está detrás de una interfaz (`Solicitudes`)**, que implementa T08. Las pruebas de T07 usan un doble que solo anota qué se pidió. Un mensaje repetido no vuelve a pedir nada; una caída antes de terminar sí puede pedir dos veces el mismo segmento, y la extracción lo absorbe con su clave de idempotencia (D22).
8. **Clasificador caído:** reintentos de la clase 2 y, si se agotan, el documento queda en `error_proceso`. Al reenviar, se clasifica y borra su `error`.

### T08 — Solicitudes de extracción (2026-11-09)

`extraer.py`: `solicitud` arma el mensaje 0.2 y `Extraer` lo valida y lo publica en `extraer`. Es la implementación de `Solicitudes` que usa T07. 140 pruebas, una de ellas con LibreOffice.

1. **Huella del PDF:** se lee `hash_pdf` de la lectura, como en la solicitud de clasificación. Leer la lectura otra vez cuesta poco y evita guardar la huella en dos lugares.
2. **`tipo_oferente` no se manda.** Es opcional en el contrato y todavía no se sabe de dónde sale (O3). Sin él, la extracción deja sin evaluar los campos condicionales.
3. **`confianza_clasificacion` va en `null`** cuando el tipo lo asignó una persona (T09).
4. **`anexos`** lleva el Excel original cuando el documento lo tiene, si no va vacía. Hay dos pruebas: una arma la solicitud con un documento de ejemplo, y otra sigue un Excel inventado de punta a punta (normalizar, clasificar y pedir la extracción) y comprueba que el anexo es el original byte a byte. Esa segunda necesita LibreOffice: está marcada `libreoffice` y se salta donde no está instalado, como en la normalización.
5. **Una solicitud que no cumple el contrato es un bug** (`SolicitudInvalida`, clase 4): el documento queda en `error_proceso` y operación lo ve. No pasa con datos bien formados; la prueba la provoca con un TD-99.
6. **`forzar_reproceso`** no se manda: lo activa `reprocesar`, que es de la entrega 2.

