# Handoff: servicio de extracción (iniciativa 003, entrega 2)

## Estado al 2026-11-10

**La entrega 2 está construida:** T01 a T10 de `specs/003-validacion-extraccion/tasks-extraccion.md`, en `servicios/extraccion/` (servicio 0.1.0, 207 pruebas sobre documentos inventados). Corre de punta a punta en local: `orquestar`, después `extraer` (LLM falso o gpt-5.4; ficha de archivo o del MCP) y después `visor`. Lo que cambió respecto del plan está al final de `plan-extraccion.md`.

Lo que queda abierto:

1. **A9:** el usuario corre `medir-gold` con TD-16 y TD-29 (comando en el README del servicio) después de autorizar que esos documentos vayan a gpt-5.4, y pega los conteos. Si un campo baja frente a `lote.py`, no se usa la versión de una vuelta con documentos reales hasta corregirlo.
2. **`describir_modelo` con versión**, en el modelo semántico: tarea escrita en `~/GEB/modelo-semantico/docs/tarea-version-en-describir-modelo.md`. Sin ella, con `--modelo mcp` la extracción se detiene cuando se publique la v22.
3. **Cumplimiento (S2, HD-10 y HD-5):** sigue sin respuesta. Ver abajo.
4. **Trabajo del modelo semántico** (`id_regla`, ámbito, validadores y `td_probado` en la matriz): sigue pendiente. Mientras tanto todo va a revisión por `TD_NO_PROBADO`.
5. **Lo que sigue en el diseño:** la entrega 2 del orquestador (recibir los resultados en la cola `resultados`, tareas de revisión de campos), Azure (Service Bus, Container App, Blob para O2), las trazas de 30 días (D23) y el gate de regresión con los gold (D24, que puede partir de `medir-gold`).

El resto de este archivo es el punto de partida que se escribió antes de empezar (2026-11-09). Sirve de contexto. La sección "Lo que está abierto" de más abajo se resolvió en la spec, salvo lo que lista esta sección.

Este archivo dice qué existe, qué entra, qué tiene que salir y qué está abierto. El estado general del proyecto y el detalle de la normalización y del orquestador están en `contexto/HANDOFF-implementacion.md`.

## Qué se pide

Un servicio que toma una solicitud de extracción (un segmento: archivo normalizado, páginas, tipo documental y versión del modelo), le pide los campos del tipo documental a gpt-5.4 y devuelve un resultado con la forma del contrato `modulo3-extraccion/0.2`: un valor, una confianza, una evidencia y una marca de revisión por campo.

Por dentro tiene tres partes (diseño, paso 5, y `contexto/refinamiento-grill-me-2.md`, D10 a D24):

1. **Preprocesamiento:** arma lo que ve el modelo a partir de la lectura que ya hizo la normalización (texto por página, tipo de página, anclas de firma y casillas). No vuelve a leer el PDF salvo para las imágenes de las páginas que lo necesitan (D19, D20, D22).
2. **Llamada al modelo:** gpt-5.4 con el prompt y la ficha del tipo documental del modelo semántico `extraccion_documental` (versión fijada en la solicitud).
3. **Posvalidación determinista:** valida la forma de la salida, aplica los validadores, calcula `revision` y los `motivos` y arma el sobre (D13 a D17). `CLASIFICACION_DUDOSA` manda todos los campos a revisión.

En producción será un Container App que consume la cola `extraer` y publica en la cola `resultados` (D21). Como en el orquestador, conviene empezar local, con interfaces y versiones en memoria, y dejar Azure para después.

## Qué leer, en este orden

1. Este archivo.
2. `contexto/constitucion.md`: los siete principios.
3. `contexto/flujo-documental-opcion-a.md`: el **paso 5 (Extracción)** completo, incluido "Costo: inyectar la ficha del TD". Después el paso 2 (Lectura: qué se le manda al LLM según el tipo de página) y las decisiones 6 a 9, 12, 14, 18, 25 a 27.
4. `contexto/refinamiento-grill-me-2.md`: **D10 a D24** son el diseño de la unidad de extracción (sobre, motivos, forma estable por resultado, validadores como datos, confianza, imágenes, firmas, dónde corre, reintentos e idempotencia, trazas, gate de regresión). La sección "Trabajo que sale de estas decisiones" lista lo que falta.
5. `contracts/modulo3-extraccion/v0.2/`: `README.md`, `entrada.schema.json`, `salida.schema.json` y los ejemplos (sirven de doble de prueba).
6. `contracts/modulo3-normalizacion/v0/`: sobre todo `lectura.schema.json` (lo que se lee de cada página) y `manifiesto.schema.json`.
7. `specs/003-validacion-extraccion/`: `spec.md`, `plan.md` y `tasks.md` de la entrega 1, para seguir la misma forma. La entrega 2 se agrega a esta misma spec.
8. `servicios/orquestador/src/orquestador/extraer.py`: cómo se arma hoy cada solicitud.
9. En `~/GEB/modelo-semantico` (otro repositorio): `HANDOFF.md`, `README.md`, `agente_local/chat.py`, `agente_local/lote.py` y `modelos/extraccion_documental/` (`prompt.md`, `tipos_documentales.json`, `tipos_documentales.guia.md`, `catalogos.json`).

## Lo que ya existe

| Pieza | Dónde | Qué sirve |
|---|---|---|
| Contrato 0.2 | `contracts/modulo3-extraccion/v0.2/` | Entrada y salida, con ejemplos de TD-16, TD-29 y TD-01 y uno de error |
| Solicitudes reales | El orquestador las publica en la cola `extraer`; con `orquestar --salida` o `correr_muestra.py --salida` quedan también en `solicitudes-extraccion.jsonl` | Entrada lista para probar. La corrida de la muestra (75 solicitudes de 16 TD) está guardada en `~/GEB/pruebas-orquestador`, con datos reales |
| Normalización y lectura | `servicios/normalizacion/` | Lo que referencian las solicitudes: PDF normalizado, `lectura/` (JSON por página), `palabras/` (cajas de palabras, para ubicar firmas) y `anexos/` (Excel nativo) |
| Modelo semántico | `~/GEB/modelo-semantico`, modelo `extraccion_documental` v21 en Cosmos, servidor MCP en Container Apps (eastus) | Fichas por tipo documental (campos, reglas, umbrales). El prompt de producción sale de `modelos/extraccion_documental/prompt.md` |
| Agente de prueba | `~/GEB/modelo-semantico/agente_local/chat.py` y `lote.py` | Loop de tools con el MCP, armado de páginas (texto + imagen con `pdftotext` y `pdftoppm`) y corrida por lote. Es el punto de partida del código (D21, plan B: chat completions directo). No es el servicio |
| Gold por tipo documental | `~/GEB/Extraccion/Documentos/pruebas/TD-NN/gold_TD-NN.xlsx`, fuera de git (datos reales) | TD-03, 05, 15, 16, 17, 18, 26, 27, 29, 30 y 35. Para medir exactitud y para el gate de regresión (D24) |
| Visor de extracción anterior | `~/GEB/Extraccion/visor/` | Resultados de `lote.py` al lado del PDF, con nombre y umbral de cada campo del modelo |
| Visor de corridas del orquestador | `servicios/orquestador/src/orquestador/visor/` (comando `visor`) | Hoy muestra clasificación, segmentos, tareas y solicitudes. Mostrar los resultados de extracción es el paso natural cuando existan |
| Matriz de campos | `~/GEB/Extraccion/matriz/campos.py` (genera el Excel) | Fuente de los campos por TD. El Excel no se edita a mano |

### Detalles de la entrada que importan

- Una solicitud por **segmento**. `id_segmento` es `<id_documento>-p<desde>-<hasta>`; las páginas se cuentan sobre el PDF normalizado completo.
- En las corridas locales, `archivo.uri`, `lectura` y `anexos` son URI `file:///…/almacen/…` absolutas. Si la corrida se movió de carpeta, hay que resolverlas por lo que va después de `almacen/`, como hace el visor (`en_el_almacen` en `visor/servidor.py`). En producción serán URI de Blob Storage (O2 sin cerrar).
- `archivo.sha256` permite verificar que el PDF es el mismo que se clasificó.
- `version_modelo` llega siempre: es la fijada en el proceso, nunca la vigente (principio 7).
- `id_oferente` es `null` en los documentos del proceso (condiciones, adendas).
- Nunca llegan TD-98 ni TD-99.

## Datos medidos y restricciones técnicas

- **gpt-5.4 es obligatorio:** gpt-5.4-mini no respeta las reglas de evidencia (prueba con TD-17).
- **429:** concurrencia global 3 (D22). Un proceso de 10 oferentes son unos 160 segmentos, unos 20 minutos. El 429 no cuenta como intento (decisión 18).
- **Reintentos:** 3 con espera creciente para fallas transitorias; 2 para una respuesta inválida del modelo; ninguno para bugs. Agotados, `error_proceso` (D22, decisión 18).
- **Idempotencia:** la clave es (`id_documento`, `paginas`, `tipo_documental`, `version_modelo`). Una solicitud repetida devuelve el resultado guardado, salvo `forzar_reproceso`. Service Bus entrega mensajes repetidos a veces, y el orquestador puede pedir dos veces el mismo segmento.
- **Costo:** hoy el agente hace 3 consultas al MCP antes de extraer y reenvía el documento en cada vuelta (mediana unos 22.000 tokens de entrada). La ficha inyectada en el mensaje (una sola vuelta) se mide con `lote.py` sobre TD-16 y TD-29 antes de adoptarla, y se adopta solo si la exactitud no baja (decisión 26).
- **Documentos largos:** de más de 20 páginas, texto completo e imágenes solo de las páginas con anclas visuales (D22).
- **Firmas:** recorte de la zona a 300 dpi ubicado con las anclas (D20). La lectura ya trae las anclas por página.

## Lo que está abierto

### Antes de tocar documentos reales: cumplimiento

Extraer manda el contenido de los documentos (cédulas, RUT) a gpt-5.4 y al MCP en eastus, Estados Unidos. Eso es la pregunta **S2** (HD-10 del checklist `specs/003-validacion-extraccion/checklist-habeas-data.md`), con HD-5 (Microsoft como encargado) para el uso en la nube. No hay respuestas todavía.

Hasta tenerlas: se construye y se prueba con documentos inventados y con un modelo falso que responde con los ejemplos del contrato. Correr gpt-5.4 sobre la muestra real o los gold solo si el usuario lo autoriza de forma explícita, y lo corre él (ver "Cómo trabaja el usuario").

### Decisiones para la spec, que hay que preguntarle al usuario

- **Dónde vive el código.** Recomendado: `servicios/extraccion/` en este repositorio, por la misma razón que el orquestador (constitución, diseño y contratos en un solo lugar; importa `normalizacion` para leer la lectura y el almacén). La alternativa es crecerlo dentro de `~/GEB/modelo-semantico`, donde está el agente de prueba.
- **Foundry o chat completions.** D21 dice agente de Foundry, con una prueba técnica pendiente (imagen `original` + recorte en el mismo turno); el plan B es chat completions directo, como `chat.py`. Con la ficha inyectada (decisión 26) el MCP deja de hacer falta en producción.
- **Cuánto entra en esta entrega.** Versión simple sugerida: servicio local que consume `solicitudes-extraccion.jsonl` o la cola en memoria, con preprocesamiento, llamada (falsa en las pruebas, gpt-5.4 detrás de una interfaz), posvalidación y salida 0.2 en un archivo por segmento. Queda fuera: Azure, Service Bus real, trazas de 30 días (D23) y el gate de regresión (D24), que pueden ser tareas posteriores.
- **Quién recibe los resultados.** Es la entrega 2 del orquestador (pasar segmentos a extraído o en revisión, tareas de revisión de campos). Para esta entrega basta con escribir la salida; el visor puede mostrarla leyendo los archivos.

### Trabajo del modelo semántico que falta

De "Trabajo que sale de estas decisiones" en `contexto/refinamiento-grill-me-2.md`, puntos 1 a 3. Revisado el 2026-11-09: `tipos_documentales.json` (v21) **todavía no trae** `id_regla`, ámbito, validador ni TD probado. Sin eso:

- `cumple` y `reglas_pendientes` (D14) no se pueden separar por ámbito;
- la posvalidación no sabe qué validador aplicar (D16);
- `TD_NO_PROBADO` no tiene de dónde salir.

Hay que decidir con el usuario si esa parte se hace antes (en `~/GEB/Extraccion/matriz/campos.py`, el convertidor y el prompt) o si la entrega 2 arranca con lo que hay y deja esos campos en su valor por defecto. Publicar una versión nueva del modelo semántico lo pide el usuario, nunca el agente.

### Preguntas del contrato sin cerrar

O2 (forma final de las URI), R1 (`id_regla` provisional), C4 (`no_corresponde` con TD sugerido) y P1 (caja por cita, después de v0). Están en el README del contrato.

## Cómo trabaja el usuario

El detalle está en `contexto/HANDOFF-implementacion.md`, "Cómo trabaja el usuario". Lo esencial:

- Todo en español: código con nombres en español, commits y documentos en prosa.
- Primero spec, plan y tareas (`tasks.md` con T01, T02…), revisados con el usuario. Después **una tarea a la vez:** rama nueva desde `main`, pruebas en verde, notas en `tasks.md`, commit, push y un resumen corto. Se detiene ahí; el usuario fusiona el pull request y escribe "merge listo" o "sigue con TNN". No crear pull requests.
- Lo ambiguo se le pregunta, con una recomendación primero. Prefiere la versión simple.
- Corre él mismo lo que toca documentos reales y pega solo conteos. Se le dan los comandos listos para copiar y cuánto tardan. Los secretos del `.env` nunca se imprimen.

## Qué no hacer

- No subir al repositorio documentos reales, gold, salidas ni registros con datos personales. Los registros llevan solo identificadores.
- No mandar documentos reales a gpt-5.4 sin las respuestas de cumplimiento o la autorización explícita del usuario.
- No usar gpt-5.4-mini para extraer.
- No editar el Excel de la matriz: se regenera desde `campos.py`.
- No publicar versiones del modelo semántico sin que el usuario lo pida.
- No meter LLM en la posvalidación, la lectura ni el orquestador: el LLM está solo en la llamada de extracción.
- No editar el contrato 0.2 de forma incompatible: si hace falta, va versión nueva en su propia carpeta (principio 5).
- No construir el clasificador ni la Power App.
