# Plan 003 — Extracción (segunda entrega)

Estado al 2026-11-10: **implementado** (T01 a T10). Lo que cambió al implementar está al final. Implementa la sección "Entrega 2 — Extracción" de `spec.md`. El plan de la primera entrega es `plan.md`.

## Resumen

Un paquete de Python, `extraccion`, en `servicios/extraccion/`. Recibe una solicitud del contrato `modulo3-extraccion/0.2` y devuelve un resultado del mismo contrato. Por dentro, cinco pasos:

```
solicitud ─► entrada: valida, resuelve las URI, comprueba la huella, lee la lectura
          ─► ficha: guía + elementos del TD en la versión fijada (FuenteModelo)
          ─► preprocesamiento: qué va de cada página (texto, imagen, firma ampliada, anexo)
          ─► llamada: un solo mensaje al LLM (ClienteLLM), con reintentos
          ─► posvalidación: forma, alineación con la ficha, validadores, motivos, sobre
          ─► resultado (validado contra salida.schema.json) en el almacén de resultados
```

Se usa como función (`extraer_segmento`) y por línea de comandos (`extraer`), que lee el `solicitudes-extraccion.jsonl` de una corrida del orquestador y escribe un archivo por segmento. Nada de Azure en esta entrega: la cola `extraer`, la cola `resultados` y el despliegue como Container App (D21) quedan para cuando el orquestador haga su entrega 2.

## Tecnología

Todas con licencia permisiva, como en la entrega 1 (A-6 sin respuesta).

| Necesidad | Herramienta | Licencia | Por qué |
|---|---|---|---|
| Lenguaje y dependencias | Python 3.12, `uv` | — | Igual que los otros servicios |
| Lectura, almacén y fábrica de documentos | `normalizacion`, como dependencia de ruta (`../normalizacion`) | — | Mismo repo. Las pruebas normalizan documentos inventados para tener lecturas reales |
| Imagen de una página y recorte de la firma | `pypdfium2` | Apache-2.0 / BSD-3 | Sin poppler (GPL) ni PyMuPDF (AGPL). Dibuja una página o una zona a cualquier resolución |
| JPEG | `Pillow` | MIT-CMU | Ya está por la normalización |
| Valores de la hoja original | `openpyxl` (solo lectura, valores guardados) | MIT | No ejecuta fórmulas: lee el último valor que guardó Excel |
| LLM | `openai` (cliente de Azure OpenAI, chat completions) | Apache-2.0 | El plan B de D21, como `chat.py` |
| Ficha desde el MCP (T08) | `mcp` (cliente) | MIT | El servidor del modelo semántico que ya existe |
| Validar contra los contratos | `jsonschema` | MIT | Como en el orquestador |
| Pruebas | `pytest`; `reportlab` y `openpyxl` para fabricar | BSD, MIT | Como en la normalización |

**Modelo:** gpt-5.4, obligatorio (gpt-5.4-mini no respeta las reglas de evidencia). El nombre del deployment va en la configuración (`AZURE_OPENAI_DEPLOYMENT`), y el servicio rechaza arrancar si el deployment configurado contiene `mini`.

## Interfaces

Como en el orquestador: cada pieza externa detrás de una interfaz pequeña, con una versión local.

| Interfaz | Qué hace | Versión local (pruebas) | Versión real |
|---|---|---|---|
| `FuenteModelo` | `ficha(version, td) → Ficha`: guía de interpretación, diccionario y elementos del TD, ya resueltos (`valores_permitidos`) | `FuenteModeloArchivo`: un JSON con la forma de lo que devuelve el MCP | `FuenteModeloMCP` (T08): llama `describir_modelo` y `obtener_seccion` con la versión fijada. Es la versión final que pidió el usuario |
| `ClienteLLM` | `responder(mensajes) → Respuesta(texto, tokens_entrada, tokens_salida, modelo)`. Lanza `LimiteDeUso(espera)`, `FallaPasajera` o deja pasar cualquier otra excepción | `LLMFalso`: respuestas preparadas por TD, con fallas programables | `LLMAzureOpenAI` (T06) |
| `Almacen` | Leer la lectura, el PDF y el anexo | `AlmacenLocal` de la normalización | Blob Storage (O2) |
| `Resultados` | `buscar(clave)`, `guardar(clave, resultado)` | `ResultadosEnCarpeta`: un JSON por clave | Blob o Cosmos, con la entrega 2 del orquestador |

El reloj y la espera también son inyectables, para probar los reintentos sin esperar.

**Ficha.** La forma de la ficha es la salida de `obtener_seccion` del MCP (`elemento_para_agente` en `modelo-semantico/src/modelo_semantico/formato.py`): sin `formula`, `depende_de` ni `trazabilidad`, y con los catálogos resueltos. Así el archivo local y el MCP dan exactamente lo mismo. Las versiones publicadas no cambian, así que la ficha se guarda en memoria por (versión, TD) mientras el proceso vive.

**Cómo se usa el MCP en la versión final.** El servicio llama al MCP como cliente, con código, antes de armar el mensaje: no es el LLM el que llama las tools. El LLM recibe la ficha ya puesta en el mensaje y responde en una vuelta (decisión 26). El MCP solo entrega metadatos del modelo semántico, nunca contenido de documentos.

## Contratos (principio 5)

El contrato `modulo3-extraccion/0.2` ya está publicado y no cambia. Los ejemplos de `contracts/modulo3-extraccion/v0.2/ejemplos/` son el doble de prueba principal: las fichas de prueba y las respuestas del `LLMFalso` se arman para que cada `entrada_*.json` dé su `salida_*.json`.

**Respuesta del LLM (interna, no es un contrato entre módulos).** Esquema en `servicios/extraccion/src/extraccion/datos/respuesta.schema.json`:

```json
{
  "corresponde": true,
  "motivo_no_corresponde": null,
  "resultados": [
    {
      "id_tecnico": "td16.firmante",
      "evidencia": [{"pagina": 1, "cita": "…", "visual": "imagen: línea vacía"}],
      "valor": [ … ],
      "confianza": 0.97,
      "cumple": "NO",
      "reglas_pendientes": [{"texto": "…", "requiere": ["TD-07"]}],
      "motivos": ["PLANTILLA_SIN_LLENAR"],
      "observacion": "…"
    }
  ],
  "alertas": [{"codigo": "…", "mensaje": "…", "id_tecnico": null}]
}
```

- Se pide con `response_format: {"type": "json_object"}` y se valida con el esquema. Un esquema estricto (`json_schema`) no sirve porque `valor` cambia de forma según el campo.
- `motivos` solo admite los cuatro que propone el LLM (R44). Los otros los pone el código.
- `id_regla` no lo pone el LLM: lo asigna el código, `<id_tecnico>.r<n>` en el orden en que llegan (R1 provisional).
- No hay `revision`: el LLM no la decide (R43).

## Cómo se decide cada cosa

### Entrada (R26 a R30)

| Situación | Resultado |
|---|---|
| La solicitud no cumple `entrada.schema.json` | `SolicitudInvalida` (bug de quien la manda, clase 4). En el comando, la línea se informa y se sigue con la siguiente |
| `paginas.hasta` mayor que las páginas de la lectura, o `desde > hasta` | `error_entrada`, `PAGINAS_FUERA_DE_RANGO`, no reintentable |
| La lectura o el PDF no están en el almacén | `error_proceso`, `ARCHIVO_NO_ENCONTRADO`, reintentable |
| La huella del PDF no coincide con `archivo.sha256` o con `hash_pdf` de la lectura | `error_proceso`, `ARCHIVO_DISTINTO`, no reintentable (R28) |
| La versión o el TD no existen en la fuente | `error_proceso`, `FICHA_NO_ENCONTRADA`, no reintentable |

Las URI `file://` se resuelven por lo que va después de `almacen/`, como `en_el_almacen` del visor, para que una corrida se pueda mover de carpeta. Esa función se pasa a la normalización (`normalizacion.almacen`) para que la usen el visor y la extracción, sin copiarla.

### Qué va de cada página (R31 a R34, R36)

| Tipo | Texto | Imagen de la página | Firma ampliada |
|---|---|---|---|
| `texto` | Sí | Solo si tiene anclas | Una por `linea_firma` |
| `escaneo_con_ocr` | Sí, marcado "texto del escáner, puede estar incompleto" | Sí, `detail: "original"` | Una por `linea_firma` |
| `imagen` | No | Sí, `detail: "original"` | No (no tiene anclas; la imagen completa va igual) |
| `vacia` | No | No | No |

- **Imagen de la página:** JPEG a 100 dpi, calidad 80, como en las pruebas actuales (`chat.py`). En las páginas `texto` va con `detail: "high"`.
- **Firma ampliada (D20):** la caja del ancla, agrandada hacia arriba para tomar el trazo que cruza la línea (por defecto 3 renglones arriba y 1 abajo, a todo el ancho de la columna), dibujada a 300 dpi. Va justo después de su página, con un rótulo que dice de qué página es.
- **Más de 20 páginas (D22):** con la tabla de arriba ya se cumple, porque una página `texto` sin anclas nunca lleva imagen. Las páginas escaneadas sí la llevan siempre, sin importar el largo: sin imagen no hay nada que leer.
- **Anexo de hoja de cálculo:** los valores de cada hoja, fila por fila separados por tabuladores, con el nombre de la hoja. Tiene un tope de caracteres por anexo; si se pasa, se corta y queda una alerta `ANEXO_RECORTADO`.
- Todos los números (dpi, márgenes del recorte, topes) son parámetros con versión en `datos/parametros.json`, como en la normalización.

`lectura` de la salida: `paginas_con_texto` lleva las páginas a las que se les mandó texto; `paginas_solo_imagen`, las que solo llevaron imagen; `ampliaciones_firma`, las páginas con al menos un recorte.

### El mensaje (R35)

- **Sistema:** el prompt del servicio (`datos/prompt.md`, con su versión en `version_prompt`), seguido de la guía de interpretación de la versión fijada del modelo.
- **Usuario:** primero la ficha del TD (los elementos en JSON) y después el contenido, página por página, con `--- Página N ---`.

El prompt del servicio parte de `modelo-semantico/modelos/extraccion_documental/prompt.md` y hace los cambios del punto 3 de "Trabajo que sale de estas decisiones" (refinamiento 2):

- no hay herramientas: la sección ya viene en el mensaje;
- no llegan parámetros del proceso ni datos de otros documentos (D8);
- la evidencia va con la forma `{pagina, cita, visual}` (D12);
- `cumple` solo con las reglas que resuelve el documento, y las demás en `reglas_pendientes` (D14);
- la salida es un único objeto JSON, sin líneas después (D10).

El `prompt.md` del modelo semántico no se toca: lo sigue usando el agente de prueba y Foundry.

**Choque conocido con la guía v21.** La guía del modelo dice "llama `obtener_seccion`", usa `revision` SI/NO y pide la evidencia como "página y cita". El prompt del servicio dice que, si la guía y el prompt chocan, manda el prompt. Corregir la guía es trabajo del modelo semántico (versión nueva, cuando el usuario la pida). La medición A9 dice si esto afecta la exactitud.

### Posvalidación (R37 a R48)

En este orden, sin LLM:

1. **Forma:** la respuesta se valida con `respuesta.schema.json`. Si no cumple, es `RespuestaInvalida` (R50).
2. **No corresponde:** con `corresponde: false`, el estado es `no_corresponde`, sin resultados, con una alerta `NO_CORRESPONDE` que lleva el motivo.
3. **Alineación con la ficha:** un resultado por elemento con `modo_captura: Extraer`, en el orden de la ficha. Un elemento que el LLM no devolvió queda sin valor, sin evidencia y con confianza `null`, y además se agrega una alerta `CAMPO_SIN_RESPUESTA`. Un `id_tecnico` que no está en la ficha se descarta con la alerta `CAMPO_DESCONOCIDO`. Un `id_tecnico` repetido se toma la primera vez y se agrega la alerta.
4. **Citas:** una cita con página fuera del segmento se quita de la evidencia y el campo lleva `VALIDACION_FALLIDA` (R39).
5. **Validadores:** `en_catalogo` con `valores_permitidos` del elemento y con los `valores` de cada propiedad en `atributos.propiedades` (`SI / NO / null`). Los demás validadores de D16 (`nit_dv`, `fecha`, `fecha_orden`, `suma_igual`, `suma_100`, `claves_objeto`) se escriben y se prueban, pero solo corren si el elemento declara `atributos.validador` (hoy ninguno lo declara, R47). Un validador que falla agrega `VALIDACION_FALLIDA` y su explicación a `observacion`.
6. **Motivos (R43 a R46):**
   - `CONFIANZA_BAJA` si `confianza` es menor que `atributos.umbral_confianza`. Si el campo tiene valor y la confianza es `null`, también. Sin umbral en la ficha, no se aplica.
   - `NO_CUMPLE` si `cumple` es `NO`.
   - `OBLIGATORIO_VACIO` si `obligatoriedad` es `Si` y el valor es `null`. Un `Condicional` no se marca, porque la condición puede no aplicar (O3).
   - `TD_NO_PROBADO` si la entrada de la sección en `secciones` (de `describir_modelo`) no trae `td_probado: true`. Con v21 aplica a todos. Las fichas de prueba de TD-16 y TD-29 lo traen, para reproducir los ejemplos del contrato, y la de TD-29 declara los validadores que dan sus `VALIDACION_FALLIDA`.
   - `CLASIFICACION_DUDOSA` si la solicitud lo trae.
   - Los que propuso el LLM, si son de los cuatro permitidos.
   - `revision` es `true` si hay al menos un motivo. Los motivos van sin repetir y en el orden del catálogo del contrato.
7. **`datos_personales`:** `true` si `atributos.datos_personales` empieza por "Sí".
8. **Sobre:** `requiere_revision`, `campos_en_revision` (en el orden de los resultados), `td_probado`, `version_modelo`, alertas del LLM y del código, `lectura` y `ejecucion`. Se valida contra `salida.schema.json` (R56): si no cumple, es un bug.

### Llamada, reintentos y concurrencia (R49 a R52)

Los reintentos los hace el propio servicio, alrededor de la llamada al LLM, porque es lo único pasajero del flujo:

| Falla | Reintentos | Espera |
|---|---|---|
| `LimiteDeUso` (429) | Sin tope de intentos, pero con un tope de espera total (por defecto 15 min) | La que pide el servicio (`retry-after`) o 30 s |
| `FallaPasajera` (tiempo agotado, 5xx, conexión) | 3 | 2, 4 y 8 s, como parámetros |
| `RespuestaInvalida` | 2 | Ninguna. Se manda otra vez el mismo mensaje más una línea con el error de forma |
| Cualquier otra | Ninguno | Bug: se lanza |

Agotados, el resultado es `error_proceso` con `LLM_NO_DISPONIBLE` o `RESPUESTA_INVALIDA`, `reintentable: true`. `ejecucion.reintentos` cuenta los reintentos sin los de 429.

**Concurrencia:** un semáforo global de 3 alrededor de la llamada al LLM (parámetro). El comando corre las solicitudes en un grupo de hilos, y así el preprocesamiento de una avanza mientras otra espera al LLM.

### Idempotencia (R53)

- Clave: `(id_documento, paginas.desde, paginas.hasta, tipo_documental, version_modelo)`, la de D22. El archivo es `resultados/<id_proceso>/<entrega>/<id_segmento>.<TD>.v<version>.json`, donde la entrega es el `id_oferente` o `PROCESO`.
- Si existe y no llega `forzar_reproceso`, se devuelve con `ejecucion.desde_cache: true` y sin llamar al LLM ni a la fuente.
- Se guardan `ok`, `no_corresponde` y `error_entrada`. `error_proceso` no se guarda.
- Con `forzar_reproceso` se extrae otra vez y se reemplaza el guardado. El anterior no se borra: queda con el sufijo de su `ejecucion.id`, para que se pueda reconstruir (principio 3).

### Comando local

```
extraer <solicitudes.jsonl> --corrida <carpeta de la corrida del orquestador>
        [--llm falso|azure] [--modelo archivo:<ficha.json>|mcp]
        [--solo <id_segmento>]… [--concurrencia 3] [--forzar]
```

- Las URI de las solicitudes se resuelven contra `<corrida>/almacen/`. Los resultados van a `<corrida>/extraccion/`, junto a lo demás de la corrida, y por eso el visor los encuentra.
- Imprime solo conteos: por estado, campos en revisión por motivo, tokens, tiempo y repetidos.
- `--llm azure` lee `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` y `AZURE_OPENAI_DEPLOYMENT` del `.env`, sin imprimirlos. `--modelo mcp` lee `MCP_URL` y `MCP_API_KEY`. Antes de mandar nada pregunta en la terminal "Esto manda documentos al modelo de lenguaje en la nube. ¿Seguir? (s/N)", salvo que llegue `--si-mando-documentos`.

### Registros

JSON por línea, como en los otros servicios: `id_segmento`, TD, versión, estado, conteos de campos y motivos, tokens, duración, reintentos y código de error. Nunca valores, citas, texto, nombres de archivo ni el mensaje al LLM.

### Visor (R57)

En el visor del orquestador (`servicios/orquestador/src/orquestador/visor/`), si la corrida tiene `extraccion/`, cada segmento muestra su resultado: estado, una fila por campo con valor, confianza contra umbral, motivos y reglas pendientes, y las citas como enlaces que abren el PDF en su página. Los campos en revisión van resaltados. El visor lee los archivos y no importa `extraccion`. El umbral de cada campo no viene en la salida: el visor lo muestra solo si encuentra la ficha en la corrida (`extraccion/fichas/`, que guarda el comando).

## Estructura

```
servicios/extraccion/
  README.md
  pyproject.toml
  uv.lock
  src/extraccion/
    __init__.py           # VERSION del servicio y CONTRATO
    cli.py                # comando `extraer`
    servicio.py           # extraer_segmento: une los pasos
    entrada.py            # validar, resolver URI, huella, lectura, rango
    ficha.py              # FuenteModelo, FuenteModeloArchivo, Ficha
    ficha_mcp.py          # FuenteModeloMCP (T08)
    preproceso.py         # qué va de cada página, imágenes, firmas, anexos
    mensaje.py            # prompt + guía + ficha + contenido
    llm.py                # ClienteLLM, LLMFalso, excepciones
    llm_azure.py          # LLMAzureOpenAI (T06)
    llamada.py            # reintentos y semáforo
    posvalidacion.py      # forma, alineación, motivos, sobre
    validadores.py        # validadores genéricos de D16
    resultados.py         # Resultados, ResultadosEnCarpeta, clave
    contratos.py          # validadores de los esquemas
    parametros.py         # lee datos/parametros.json
    registros.py
    datos/
      prompt.md
      respuesta.schema.json
      parametros.json
  tests/
    conftest.py
    fichas/               # fichas de prueba de TD-16, TD-29 y TD-01, con la forma del MCP
    respuestas/           # respuestas del LLMFalso que dan las salidas del contrato
    test_*.py
```

## Pruebas

Todo con documentos inventados y el `LLMFalso`. Para tener lecturas reales, las pruebas fabrican PDF con reportlab y los pasan por `normalizar_entrega`.

| Caso | Cómo |
|---|---|
| Ejemplos del contrato (A7) | `entrada_td16`, `entrada_td29` y `entrada_td01_proceso` con su ficha de prueba y su respuesta falsa dan `salida_td16` y `salida_td29` (salvo `ejecucion`) |
| Tipos de página | Un PDF con una página de cada tipo y una línea de firma: se comprueba qué va de cada página y `lectura` de la salida |
| Firma ampliada | El recorte cubre la línea y el renglón de arriba, y sale a 300 dpi |
| Hoja de cálculo | Un xlsx normalizado: el mensaje trae sus valores; una hoja enorme da `ANEXO_RECORTADO` |
| Errores de entrada | Rango fuera, lectura que falta, huella distinta, versión que no existe |
| Posvalidación | Un caso por motivo; campo faltante, desconocido y repetido; cita fuera del segmento; valor fuera de catálogo; `no_corresponde`; `clasificacion_dudosa` |
| Validadores | Uno por validador, con casos que pasan y que fallan |
| Reintentos | 429 con y sin `retry-after`; 3 fallas pasajeras y luego éxito; 4 fallas; 2 respuestas inválidas y luego válida; 3 inválidas; un bug |
| Concurrencia | 10 solicitudes con un LLM falso lento: nunca más de 3 llamadas a la vez |
| Idempotencia | Dos veces la misma solicitud: una sola llamada; `forzar_reproceso`; `error_proceso` no se guarda |
| Punta a punta (A8) | Normalización de un proceso inventado, solicitudes armadas con `orquestador.extraer.solicitud`, `extraer` sobre el jsonl, todo validado, y una segunda corrida sin llamadas |
| MCP | Un servidor MCP falso en memoria que responde `describir_modelo` y `obtener_seccion` |

**Con documentos reales (A9):** solo con autorización explícita del usuario, que lo corre en su máquina. Un script compara los resultados con los gold de TD-16 y TD-29 e imprime solo conteos de aciertos por campo. Ver T10.

## Chequeo de Constitución

| Principio | ¿Cumple? | Cómo |
|---|---|---|
| 1. El proceso manda sobre la tecnología | Sí | La spec no nombra tecnología. Este plan la elige |
| 2. Condiciones como datos | Sí | Campos, umbrales, catálogos y validadores salen de la ficha versionada. El código solo trae validadores genéricos. Los parámetros del preprocesamiento tienen versión |
| 3. Veredicto trazable | Sí | Cada dato lleva página y cita. El resultado lleva la versión del modelo, del prompt y del servicio. Un reproceso no borra el resultado anterior |
| 4. La IA extrae y el evaluador decide | Sí | La revisión la calcula el código, con el umbral de la ficha y `NO_CUMPLE`. Los TD sin la marca de probados van enteros a revisión |
| 5. Contrato primero | Sí | El contrato 0.2 ya está publicado. Sus ejemplos son el doble de prueba. La respuesta del LLM tiene su esquema interno |
| 6. Datos personales | Con condición | Pruebas solo inventadas, registros sin valores, sin traza guardada. Nada real va al LLM sin HD-10 o la autorización del usuario, y el comando lo vuelve a preguntar |
| 7. Igualdad de trato | Sí | La ficha sale siempre de la versión de la solicitud. Las fichas en memoria se guardan por versión |

**Mínimo necesario:** chat completions directo en vez del agente de Foundry (D21, plan B). Así no hace falta la prueba técnica de imagen `original` más recorte en el mismo turno, ni guardar ni borrar threads (D23). Sin MCP dentro de la llamada: una vuelta en vez de cuatro (decisión 26).

## Complejidad y excepciones

- **La medición de la decisión 26 va al final (A9), no antes.** El servicio se construye directamente con un solo mensaje, porque es la versión que va a producción y no se puede medir sin documentos reales. Si A9 sale peor, el `ClienteLLM` admite una variante con el loop de tools, y el resto del servicio no cambia.
- **Prompt propio del servicio.** Duplica parte del `prompt.md` del modelo semántico. Se descartó editar ese archivo porque lo usan el agente de prueba y Foundry, que siguen llamando las tools.
- **Se mueve `en_el_almacen` a la normalización.** Toca un paquete de la entrega 1, pero evita una tercera copia de la misma regla.

## Riesgos

- **La guía v21 choca con el prompt del servicio** (tools, `revision`, forma de la evidencia). Puede bajar la exactitud. A9 lo mide; la corrección de fondo es una versión nueva del modelo.
- **Sin imagen en las páginas `texto` sin anclas** se pueden perder sellos o marcas que las anclas no encuentran (decisión 8). A9 lo muestra en TD-16 (firma) y TD-29.
- **`TD_NO_PROBADO` en todo** hace que hoy todo vaya a revisión. Es lo esperado hasta que la matriz traiga la marca; el visor y los conteos lo muestran aparte para que no tape los otros motivos.
- **429 con concurrencia 3:** el tope de espera total puede vencerse en un proceso grande. Queda como parámetro.

## Lo que cambió al implementar

El detalle de cada punto está en las notas de `tasks-extraccion.md`.

- **Solicitud sin `version_modelo`** (T05): es `SolicitudInvalida`, no `error_proceso`. La salida exige la versión, así que no hay cómo contestar con un error válido.
- **Errores que se sumaron a la tabla de entrada:** `LECTURA_INVALIDA` (T02); `LLM_NO_DISPONIBLE` y `RESPUESTA_INVALIDA`, reintentables (T06); `MODELO_NO_DISPONIBLE`, reintentable, cuando el MCP no responde (T08).
- **Zona de la firma** (T03): margen fijo de media pulgada a cada lado, no "todo el ancho de la columna", porque la lectura no dice dónde están las columnas.
- **`id_regla`** (T05): se numeran solo las reglas pendientes (`<id_tecnico>.r<n>`). La `observacion` suma la explicación de cada validador que falla.
- **Tiempo límite por llamada al LLM** (T06): 300 s, nuevo en `parametros.json`, que pasó a la versión 2.
- **pdfium no admite hilos** (T07): el preprocesamiento dibuja las páginas bajo un candado global. Las esperas al LLM siguen en paralelo.
- **`describir_modelo` del MCP no recibe versión** (T08): el servicio comprueba que la guía sea de la versión fijada y, si no, da `FICHA_NO_ENCONTRADA`. Está pedido en el modelo semántico: `~/GEB/modelo-semantico/docs/tarea-version-en-describir-modelo.md`.
- **Fichas guardadas para el visor** en `<corrida>/extraccion/fichas/v<N>/<TD>.json` (T08), con la ficha de archivo o la del MCP.
- **Comandos de más:** `probar-ficha-mcp` (T08) y `medir-gold` (T10), este último en el paquete y no en `scripts/`.
- **El visor** (T09) lee los archivos del contrato; no importa `extraccion`. El comando `extraer` registra las fallas internas con su segmento.

