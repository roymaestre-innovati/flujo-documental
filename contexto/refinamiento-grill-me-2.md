# Refinamiento con Grill Me (segunda sesión) — estado al 2026-10-30

Agente de extracción del módulo 3 (validación, clasificación y extracción) de Evaluación_OfertasV2. Esta sesión parte de la primera (`refinamiento-grill-me.md`, 2026-10-15) y de las pruebas por tipo documental (`Documentos/pruebas/HANDOFF.md`: 11 TD probados con documentos reales, modelo v21).

**Contexto que cambió desde la primera sesión:** el equipo solo es dueño del agente de extracción. La clasificación y la orquestación del flujo las construyen otros equipos. Esta sesión define qué le falta al agente para ser una pieza integrable, qué hay que preguntar a los demás equipos y cómo se ve el resultado final.

**Hallazgo que ordena todo:** hoy "el agente" es prompt + tool MCP + gpt-5.4. Pero buena parte de lo que hace correcta la extracción vive en el arnés de prueba (`modelo-semantico/agente_local/chat.py`): el texto con pdftotext, la imagen por página, el `detail` de la imagen, y ahí iría el recorte de firmas (`Documentos/pruebas/diagnostico_firmas.md`). En producción alguien tiene que hacer ese trabajo, y no estaba definido quién.

## Decisiones

### Frontera y alcance

- **D1 — Entregamos una unidad de extracción, no solo un agente.** La unidad tiene tres partes: preprocesamiento (texto + imágenes de página + recortes de firma), el agente de Foundry y una posvalidación determinista. Se expone como un solo punto de llamada. El orquestador solo pasa el archivo, el rango de páginas y el TD.
- **D2 — Contrato primero, propuesto por nosotros.** Redactamos el contrato v0 de entrada y salida, con ejemplos que sirven como doble de prueba para los otros equipos, y lo llevamos a orquestación y a clasificación para que lo ajusten (principio 5). Está en `contracts/modulo3-extraccion/v0/`.
- **D3 — Reparto de reglas.** El módulo 3 valida las propiedades del propio documento: formato, firmado, completo, aritmética interna, DV del NIT. El módulo 4 resuelve los cruces entre documentos, los parámetros del proceso (`PRO-NN`), las vigencias contra fechas del proceso y todos los campos `Calculado`.
- **D4 — Alcance de salida a producción.** Entran todos los TD. Los que no se han probado con documentos reales salen con revisión humana obligatoria en todos sus campos, hasta que se prueben. El orquestador no necesita saber cuáles están listos.

### Contrato de entrada

- **D5 — Unidad de trabajo.** Una llamada es un segmento: archivo + rango de páginas + TD, igual a lo que devuelve el clasificador. Si un PDF trae tres documentos, llegan tres llamadas.
- **D6 — Campos.**
  - Obligatorios: `id_proceso`, `id_oferente`, `id_documento` (los pone el orquestador), `archivo` (referencia), `paginas`, `tipo_documental`.
  - Opcionales: `tipo_oferente`, `version_modelo`, `confianza_clasificacion`, `forzar_reproceso`.
- **D7 — Versión del modelo fija por proceso.** El orquestador fija `version_modelo` al abrir el proceso y la manda en cada llamada (principio 7). Si no llega, usamos la vigente y la devolvemos en la salida. Las versiones publicadas no se borran.
- **D8 — Sin parámetros ni otros documentos en la entrada.** Las reglas que los necesitan salen como `reglas_pendientes` para el módulo 4. Hay que quitar del prompt la línea "Si te entregan parámetros del proceso o datos de otros documentos…".
- **D9 — Dónde vive el contrato.** JSON Schema + ejemplos en `contracts/modulo3-extraccion/v0/`. Un cambio incompatible es una versión mayor. Queda en este repo mientras no exista el repo compartido de `contracts/`.

### Contrato de salida

- **D10 — Sobre JSON único y validado.** Lleva identificadores, `estado`, versiones (del modelo, del prompt, de la unidad y del LLM), `requiere_revision`, `campos_en_revision`, `resultados[]`, `alertas[]` y `ejecucion`. Desaparecen las "tres líneas para el evaluador" en texto libre: pasan a `alertas[]`.
- **D11 — Estados del documento.**
  - `ok`: se extrajo, aunque haya campos en revisión.
  - `no_corresponde`: el contenido no es del TD indicado; es una señal para clasificación, no reclasificamos.
  - `error_entrada`: archivo ilegible, con contraseña o páginas fuera de rango.
  - `error_proceso`: falló el LLM o el MCP después de los reintentos.
- **D12 — Evidencia estructurada.** Cada cita es `{pagina, cita, visual}`, y la página se numera sobre el archivo completo. No hay bounding box en v0. Un campo puede tener varias citas, así que `evidencia` es una lista.
- **D13 — La revisión la decide el código.** El agente propone. La posvalidación recalcula `revision` con el `umbral_confianza` del modelo, `cumple`, la obligatoriedad y el valor `null`. Los motivos salen de un catálogo cerrado:
  - `CONFIANZA_BAJA`
  - `NO_CUMPLE`
  - `OBLIGATORIO_VACIO`
  - `REQUIERE_IMAGEN`
  - `PLANTILLA_SIN_LLENAR`
  - `NOTA_ELEMENTO`
  - `CONTRADICCION`
  - `VALIDACION_FALLIDA`
  - `TD_NO_PROBADO`

  `observacion` queda como texto para la persona que revisa.
- **D14 — Forma estable por resultado.** Todo resultado lleva siempre las mismas claves: `id_tecnico`, `valor`, `confianza`, `evidencia`, `cumple`, `reglas_pendientes`, `revision`, `motivos`, `observacion` y `datos_personales`.
  - `cumple` evalúa solo las reglas de ámbito documento, y vale `null` si el elemento no tiene ninguna.
  - Una regla pendiente del módulo 4 no manda el campo a revisión: hoy el agente lo hace (ver el ejemplo de TD-16 en v14) y eso genera ruido.
- **D15 — Ejecución en el sobre.** El sobre lleva `id`, `inicio`, `duracion_ms`, los tokens, el modelo LLM y las versiones, más la forma de lectura (páginas con texto, páginas solo imagen, ampliaciones de firma). La traza completa queda en nuestros logs, no en la salida.

### Cómo se ve la unidad por dentro

- **D16 — Las validaciones deterministas son datos.** El código trae validadores genéricos: `nit_dv`, `fecha`, `fecha_orden`, `suma_igual`, `suma_100`, `en_catalogo`, `claves_objeto`. La matriz declara en una columna nueva cuál aplica a cada campo y con qué parámetros, como la tolerancia (principio 2).
- **D17 — Confianza sin fórmula compuesta en v0.** Se mantiene la `confianza` del agente. Si un validador falla, el campo va a revisión con `VALIDACION_FALLIDA`. Los umbrales se calibran después, con los gold y con las correcciones de los revisores.
- **D18 — La conversión a PDF ocurre una sola vez, antes de clasificar.** El clasificador y nosotros trabajamos sobre el mismo PDF; si no, los rangos de páginas no coinciden. Nosotros solo aceptamos PDF e imagen.
- **D19 — PDF escaneado o imagen.** Se detectan las páginas sin capa de texto, se mandan con `detail: "original"` y la salida las declara en `lectura.paginas_solo_imagen`. El OCR (Document Intelligence Read) queda como experimento, medido contra el gold.
- **D20 — Firmas: recorte ampliado.** Se recorta la zona de firma a 300 dpi, ubicada con anclas de `pdftotext -bbox`; si no hay ancla, se toma el tercio inferior de la página. Fue la opción 1 del diagnóstico: 6/6 aciertos, ~1.000 tokens por zona. Después hay que reverificar los TD cerrados que tienen firmas o casillas.
- **D21 — Dónde corre.** Un Container App, junto al MCP, que preprocesa, invoca y posvalida. El LLM se llama como agente de Foundry (prompt agent + tool MCP, por `agent_reference`). Falta verificar en una prueba que el agente de Foundry acepta `detail: "original"` y el recorte en el mismo turno. El plan B es chat completions directo con el cliente MCP, como `chat.py`.
- **D22 — Reintentos, concurrencia e idempotencia.**
  - La clave de idempotencia es (`id_documento`, `paginas`, `tipo_documental`, `version_modelo`). Si se repite la llamada, se devuelve el resultado guardado, salvo que llegue `forzar_reproceso`.
  - La concurrencia global queda limitada: hoy 3, por los errores 429.
  - Hasta 3 reintentos con backoff; si se agotan, `error_proceso`.
  - En documentos de más de 20 páginas se manda el texto completo, y las imágenes solo de las páginas con anclas visuales.
- **D23 — Retención de trazas.** La traza completa se guarda 30 días en un almacenamiento restringido; después quedan solo los metadatos. No se guardan imágenes, y los threads de Foundry se borran al terminar cada documento. El plazo lo confirma cumplimiento.
- **D24 — Gate de regresión.** Los gold de los TD cerrados forman una suite. Antes de publicar una versión del modelo se corre 1 repetición por documento, y si la exactitud de un campo baja, no se publica. Hace falta porque U01 rompió 39 campos de 23 TD sin que nadie lo notara.

## Trabajo que sale de estas decisiones

1. **Matriz (`campos.py`):** partir las reglas en reglas atómicas con `id_regla` y ámbito (`documento` o `proceso`). Hoy una sola regla mezcla los dos ámbitos, por ejemplo `td16.firmante`: "Firmado por al menos un firmante…; RF si la sociedad está obligada (ver td07…); exigir TD-26 y TD-27". También hay que agregar las columnas de validador (D16), de rol revisor (P3) y de TD probado (D4).
2. **Convertidor y modelo:** llevar `id_regla`, ámbito y validador a `tipos_documentales.json`.
3. **Prompt y guía:**
   - quitar la entrada de parámetros (D8);
   - pedir la evidencia estructurada (D12);
   - `cumple` solo con las reglas de ámbito documento, y las pendientes en lista (D14);
   - quitar las líneas libres después del JSON (D10).
4. **Unidad de extracción:** el preprocesamiento (D18 a D20), la posvalidación (D13, D16, D17), el sobre (D10 a D15) y la operación (D21 a D23). Se parte de `chat.py` y `lote.py`.
5. **Suite de regresión** con los gold de los TD cerrados (D24).
6. **Prueba técnica previa:** el agente de Foundry con imagen `original` + recorte en el mismo turno (D21).

## Preguntas para los otros equipos

Las marcadas como **bloquea** frenan el contrato v0 o la implementación. Las de integración (O1, O2, C1, C2, C3, M1, R1) se llevan juntas a una reunión con orquestación, clasificación, módulo 1 y módulo 4, con el contrato v0 como agenda. S1 y S2 van por separado a cumplimiento.

### Orquestación

| # | Pregunta | Propuesta | |
|---|---|---|---|
| O1 | ¿Cómo nos llaman: HTTP síncrono, HTTP asíncrono (202 + consulta o callback) o cola? ¿Con qué tecnología orquestan? | HTTP asíncrono | **bloquea** |
| O2 | ¿El archivo llega como referencia a un blob? ¿En qué storage, con qué identidad y quién nos da el permiso de lectura? | URI + managed identity | **bloquea** |
| O3 | ¿Quién conoce el `tipo_oferente` y en qué momento? Sin él, los campos condicionales quedan sin evaluar. | Que llegue en cada llamada | |
| O4 | ¿Pueden fijar y guardar la `version_modelo` por proceso y mandarla en cada llamada? | Sí (principio 7) | |
| O5 | ¿Qué hacen con `no_corresponde`, `error_entrada` y `error_proceso`? | Lo deciden ellos; nosotros lo señalamos | |
| O6 | ¿Cuántos documentos simultáneos esperan por proceso y qué tiempo de respuesta esperan? | Dimensiona la cuota y la concurrencia | |
| O7 | En una subsanación, ¿el documento corregido llega con un `id_documento` nuevo? ¿Cuándo piden un reprocesamiento forzado? | Id nuevo; reprocesar solo si se pide | |

### Clasificación

| # | Pregunta | Propuesta | |
|---|---|---|---|
| C1 | ¿Su salida trae por segmento: archivo, rango de páginas, TD y confianza? ¿Nos llegan los TD-99? | Sí; los TD-99 no nos llegan | **bloquea** |
| C2 | ¿Usan los mismos identificadores TD-NN que la matriz? La primera sesión vio 39 tipos en el contexto y 35 en la ontología (Q17). | Tabla de equivalencias firmada por los dos equipos | **bloquea** |
| C3 | ¿Clasifican el mismo PDF que recibimos nosotros, con la misma paginación? | Sí (ver M1) | **bloquea** |
| C4 | ¿Quieren recibir la señal `no_corresponde`? ¿En qué forma? | En el sobre, vía el orquestador | |
| C5 | ¿Pueden compartir los resultados y el baseline del clasificador (Q16)? | Para medir los errores en cadena | |

### Módulo 1 (paquete de documentos)

| # | Pregunta | Propuesta | |
|---|---|---|---|
| M1 | ¿Convierten DOCX y XLSX a PDF una sola vez, antes de clasificar? ¿Quién descomprime los ZIP? | Sí, ellos | **bloquea** |
| M2 | ¿Qué proporción de documentos llega escaneada, en imagen, con contraseña o firmada digitalmente? | Decide si hace falta OCR | |

### Módulo 4 (reglas e informe)

| # | Pregunta | Propuesta | |
|---|---|---|---|
| R1 | ¿Cómo referencian una regla pendiente? | Un `id_regla` estable en la matriz | **bloquea** |
| R2 | ¿Asumen todos los campos `Calculado` (TD35-09, el vencimiento de la JCC, el % de IVA)? | Sí | |
| R3 | ¿Quién convierte `revision: true` en una tarea humana? | Ellos u orquestación | |

### Revisión humana (Power Apps)

| # | Pregunta | Propuesta | |
|---|---|---|---|
| P1 | ¿Basta con página + cita, o necesitan un bounding box (Q20)? | Página + cita en v0 | |
| P2 | ¿Guardan las correcciones del revisor y nos dan acceso? | Sí: es la fuente para calibrar (D17) | |
| P3 | ¿Qué rol revisa cada TD? (principio 4) | Una columna en la matriz | |

### Cumplimiento y plataforma

| # | Pregunta | Propuesta | |
|---|---|---|---|
| S1 | ¿Bastan 30 días de traza completa y luego solo metadatos? ¿El checklist de habeas data se corre antes de implementar? | Sí | **bloquea** |
| S2 | El MCP y el deployment del modelo están en eastus, con cédulas y RUT en tránsito. ¿Es aceptable bajo la Ley 1581 (transferencia internacional)? | Que lo confirme cumplimiento | **bloquea** |
| I1 | ¿Quién gestiona la cuota TPM de gpt-5.4 en producción? | Un deployment dedicado al módulo 3 | |

### Negocio y evaluación

- NEG-01 a NEG-21: siguen abiertas en `Documentos/pruebas/preguntas_negocio.md`.
- **N-A:** ¿Una firma digital (certificado en el PDF) cuenta como "Firmado"?
- **N-B:** ¿Cuál es el umbral de confianza de cada TD? Hoy viene de la matriz, sin validar con negocio.
- **N-C:** ¿Quién arma el gold de los 24 TD que faltan? Hacen falta documentos de más procesos, porque TD-05 solo tiene formatos en blanco.

## Preguntas de la primera sesión que quedan resueltas o reemplazadas

- **Q16** queda en C5. **Q17** queda en C2. **Q19** queda en D16 y D17. **Q20** queda en P1. **Q24** queda en D3. **Q25** queda en D9. **Q27** queda en D23 y S1.
- **Q18** quedó resuelta con la matriz de 262 campos y las pruebas por TD.
- **Q21, Q22 y Q26** siguen abiertas, pero no bloquean la integración.
