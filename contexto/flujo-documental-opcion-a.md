# Flujo documental — opción A: etapas separadas

Estado al 2026-11-03. Cómo pasa un documento de la oferta desde que llega hasta que sus datos quedan listos para el módulo 4, con la clasificación y la extracción como etapas separadas, a cargo de equipos distintos. Se eligió esta opción entre las de `opciones-flujo-clasificacion-extraccion.md`: la B (clasificación guiada por casillas del portal) se vio compleja y la C (un solo agente) se descartó.

Parte de las decisiones D1-D24 (`refinamiento-grill-me-2.md`) y del contrato v0 (`contracts/modulo3-extraccion/v0/`).

**Estado de cada paso:** *Revisado* = discutido en detalle; *Propuesto* = hay propuesta, falta revisarla; *Por revisar* = solo esbozado.

## El flujo en una vista

```
0 Entrada              archivos del oferente y del proceso                 (módulo 1, otro equipo)
        │
1 Normalización        PDF normalizados + manifiesto                       (nosotros)
        │
2 Lectura              texto por página, tipo de página, sin LLM           (nosotros)
        │
3 Clasificación        segmentos: archivo + páginas + TD + confianza       (clasificador: otro equipo)
        │
4 Orquestación         estado, versiones fijas, colas, ficha del proceso   (nosotros)
        │
5 Extracción           contrato 0.2: ficha del TD, gpt-5.4, posvalidación  (nosotros)
        │
6 Reglas e informe     reglas como datos, tareas de revisión, informe      (nosotros)
        │
7 Revisión humana      Power App                                           (otro equipo)
```

| Paso | Dueño | Estado |
|---|---|---|
| 0. Entrada de documentos | Módulo 1 (otro equipo) | Fuera de alcance |
| 1. Normalización | Nosotros | Revisado |
| 2. Lectura | Nosotros | Revisado |
| 3. Clasificación | Equipo de clasificación (el clasificador); nosotros, lo que lo rodea | Revisado |
| 4. Orquestación | Nosotros | Revisado |
| 5. Extracción | Nosotros | Revisado (cambios para el contrato 0.2) |
| 6. Reglas, informe y tareas de revisión | Nosotros (módulo 4 incluido) | Revisado |
| 7. Power App de revisión | Otro equipo | Fuera de alcance |

### Reparto (2026-11-03)

Somos dueños de todo el flujo menos tres piezas: la entrada de documentos (módulo 1), el clasificador y la Power App de revisión. Eso incluye la normalización, la orquestación, la extracción, el módulo 4 (reglas del proceso, cruces entre documentos, campos `Calculado`, puntaje e informe) y la creación de las tareas de revisión.

Consecuencias:

- Las preguntas que el refinamiento dirigía a orquestación (O1-O7) y al módulo 4 (R1-R3) pasan a ser decisiones nuestras.
- El contrato v0 entre el orquestador y la extracción queda como frontera interna. Se mantiene, porque deja probar cada pieza por separado, pero ya no hay que negociarlo con nadie.
- Solo quedan tres fronteras externas para acordar con otros equipos:

| Frontera | Con quién | Qué hay que acordar |
|---|---|---|
| Entrada → flujo | Módulo 1 | Dónde dejan los archivos de cada oferente (blob o SharePoint), cómo avisan que un oferente terminó de entregar, y los identificadores de proceso, oferente y archivo |
| Flujo ↔ clasificador | Clasificación | Cómo lo llamamos, sobre qué PDF clasifica (el normalizado), qué devuelve por segmento (C1-C3) y qué hacemos con `no_corresponde` (C4) |
| Flujo → Power App | Equipo de la Power App | Dónde escribimos las tareas de revisión (p. ej. tablas de Dataverse), con qué forma, y cómo leemos las correcciones de vuelta (P1-P3) |

## Datos de partida

Muestra: proceso SR5658940621, 6 oferentes.

- Unas 80 páginas y unos 19 archivos por oferente. Proyectado a ~4.000 ofertas al año: ~320.000 páginas.
- El 19 % de las páginas son escaneos: 8 % sin texto y 11 % con una capa de texto puesta por el escáner, poco confiable.
- 15 PDF vienen "cifrados", pero solo con restricciones de copia: se leen sin contraseña.
- 7 PDF traen firma digital.
- 9 archivos están duplicados exactos.
- La oferta económica y la experiencia llegan a veces solo en Excel.
- Extraer un documento hoy toma ~22.000 tokens de entrada y ~1.500 de salida con gpt-5.4 (mediana de 346 corridas), entre 13 y 44 segundos.

---

## Paso 1 — Normalización · Revisado

**Para qué:** que el clasificador y la extracción trabajen sobre el mismo PDF, con la misma paginación (D18), y que lleguen solo archivos legibles y sin repetir.

**Dueño:** nosotros. El módulo 1 solo deja los archivos tal como los entregó el oferente; así controlamos el PDF sobre el que trabajan el clasificador y la extracción.

**Entrada:** los archivos de cada oferente, **ya descomprimidos** (confirmado: no llegan ZIP ni RAR), posiblemente en carpetas anidadas, en el storage que defina el módulo 1.

**Qué hace:**

1. **Inventario:** recorre la carpeta del oferente, guarda la ruta de origen de cada archivo y descarta los archivos de sistema (`.DS_Store`, `Thumbs.db`, la carpeta `__MACOSX` y los archivos `._*`). Ojo: los `._*` de Mac llevan la extensión del original (en la muestra, 15 "PDF" que no abren), así que el filtro va por nombre y por contenido, no por extensión.
2. **Hash:** calcula el SHA-256 de cada archivo. Un duplicado se marca con `duplicado_de` y no se procesa otra vez; no se borra.
3. **Tipo real:** identifica el tipo por el contenido, no por la extensión.
4. **Conversión a PDF:** DOC, DOCX y ODT con LibreOffice headless, sin ejecutar macros; imágenes (JPG, PNG, TIFF) con img2pdf, una página por imagen. El original no se modifica nunca: el PDF normalizado es una copia aparte, lo que además conserva intactas las firmas digitales.
5. **Excel:** se genera el PDF, para clasificar y para citar páginas, y se conserva el Excel nativo como anexo que la extracción lee como tabla. Pasarlo solo a PDF corta las hojas anchas y pierde la estructura (pasó con TD-35 de GOODS).
6. **Revisión del PDF:**
   - si abre;
   - si pide contraseña para abrir (`error_entrada`) o solo trae restricciones de copia (se lee normal);
   - número de páginas;
   - qué páginas no tienen texto;
   - si tiene firma digital, y en ese caso quién firma, cuándo y si el PDF está íntegro.

**Salida: manifiesto por oferente.** Por cada archivo:

| Campo | Contenido |
|---|---|
| `id_documento` | Identificador del archivo en el proceso |
| `ruta_origen` | Ruta tal como la entregó el oferente |
| `hash` | SHA-256 del original |
| `tipo_origen` | pdf, docx, xlsx, imagen… |
| `pdf` | URI del PDF normalizado |
| `anexo_nativo` | URI del Excel original, si aplica |
| `paginas` | Número de páginas |
| `paginas_sin_texto` | Lista de páginas sin capa de texto |
| `duplicado_de` | `id_documento` del original, si es copia |
| `restricciones` | El PDF trae restricciones de copia (sí/no) |
| `firma_digital` | Lista de `{firmante, fecha, integro}`, o vacía |
| `error` | `null`, o el motivo por el que no se pudo normalizar |

**Tecnología propuesta:** un Container Apps Job (Python, LibreOffice, qpdf, PyMuPDF, pyHanko) que se dispara desde la cola cuando el oferente termina de entregar, y que escala a cero. Un oferente tarda del orden de un minuto, y el volumen anual cabe en la cuota gratis del plan de consumo. Si el módulo 1 guarda los archivos en SharePoint, Graph API puede convertir DOCX y XLSX a PDF sin LibreOffice. Power Automate no encaja bien con el hash ni con el análisis por página.

### Firma digital: qué se puede decir y qué no

Hay dos firmas distintas:

- **Manuscrita o escaneada:** una imagen sobre la línea. La decide la extracción, mirando la página y el recorte ampliado (D20). La normalización no puede decir nada sobre ella.
- **Digital:** un certificado dentro del PDF. Se revisa con código, sin LLM.

Prueba con pyHanko sobre los 7 PDF firmados digitalmente:

| Documento | Quién firma | Resultado |
|---|---|---|
| Certificados de Cámara de Comercio (2) y RUP (1) | La Cámara de Comercio | Formato antiguo (`adbe.pkcs7.sha1`) que pyHanko no lee; hace falta otra herramienta |
| Certificación de experiencia (Acueducto) | Sello electrónico de InfoCert (Italia) | Firma correcta, pero **el PDF se modificó después de firmarse** |
| Certificación de experiencia (ODL) | DocuSign | Íntegro, firma correcta |
| Carta de referencia (RECOPE) | Persona natural de Costa Rica | Íntegro, firma correcta |

En ninguno se pudo decir si el certificado es confiable: para eso hace falta cargar las autoridades certificadoras raíz de cada país.

**Conclusiones:**

- La firma digital casi siempre es de quien **emite** el documento (Cámara, entidades contratantes), no del oferente. Los campos "Firmado" de nuestros TD (TD-03, TD-16, TD-17…) son del oferente, y en la muestra venían todos a mano o escaneados. La normalización no puede contestar "ya está firmado" en general.
- **Decisión para v0:** la normalización solo **detecta** la firma digital y anota en el manifiesto quién firma, cuándo y si el PDF está íntegro. La extracción puede usarlo como evidencia adicional.
- **Fuera de v0:** validar que la firma es legalmente confiable (cadena de certificados, revocación), salvo que negocio lo exija (pregunta N-A).
- **Señal útil para el evaluador:** un PDF que se modificó después de firmarse (caso Acueducto).

### Cuándo corre

Probablemente los oferentes no llegan todos juntos. **No afecta la normalización ni la extracción:** cada archivo y cada segmento se procesan solos, y los cruces entre documentos son del módulo 4. Solo cambia el volumen de golpe, y eso lo absorbe la cola (paso 4). Lo que sí exige que lleguen en momentos distintos es fijar la versión del proceso (paso 4).

---

## Paso 2 — Lectura · Revisado

**Para qué:** saber qué hay en cada página (texto, escaneo, nada) y dejar el texto listo, para que la extracción decida qué le manda al LLM.

**Dueño:** nosotros. Corre una vez por archivo, justo después de normalizar y en el mismo job. El resultado se guarda y cada segmento toma de ahí sus páginas.

**Sin agentes ni LLM:** es código determinista. El mismo PDF da siempre la misma lectura (principio 3), en milisegundos por página. La única pieza de IA posible es el OCR, que es un modelo de reconocimiento de caracteres y no un LLM. El LLM queda solo en los pasos que necesitan interpretar: clasificación (3) y extracción (5).

### Qué páginas hay

Muestra: 415 páginas únicas, sin duplicados ni archivos basura.

| Tipo de página | % | Cómo se detecta |
|---|---|---|
| `texto`: generada en computador | 76 % | Tiene texto y la imagen cubre poco de la página |
| `escaneo_con_ocr`: escaneada, con la capa de texto que le puso el escáner | 11 % | Tiene texto, pero una imagen cubre más del 80 % de la página |
| `imagen`: escaneada, sin texto | 8 % | Casi sin texto y una imagen cubre la página |
| `vacia`: en blanco o casi | 5 % | Casi sin texto y sin imagen |

"Tiene texto" no significa "es digital": el 19 % de las páginas son escaneos, no el 14 % que daba contar solo las páginas sin texto. La capa de texto del escáner no es confiable: a veces trae solo el encabezado (30 a 70 caracteres en una página llena).

### Qué guarda por página

| Campo | Contenido |
|---|---|
| `pagina` | Número sobre el PDF normalizado completo |
| `tipo` | `texto`, `escaneo_con_ocr`, `imagen` o `vacia` |
| `texto` | El texto de la página |
| `origen_texto` | `nativo`, `ocr_escaner` u `ocr_propio` |
| `cobertura_imagen` | Fracción de la página cubierta por imágenes |
| `rotacion` | Rotación de la página |
| `anclas` | Zonas visuales genéricas: líneas de firma, casillas, tablas SI/NO, ubicadas por palabras clave y posición (las mismas que usa el recorte de firma, D20) |

Las posiciones de cada palabra se guardan en un archivo aparte, porque pesan.

### Qué se le manda al LLM según el tipo de página

Lo decide la extracción (paso 5) con la lectura:

| Tipo | Se manda |
|---|---|
| `texto` | Solo el texto. La imagen, solo si la página tiene anclas y el TD tiene campos visuales (firma, casillas) |
| `escaneo_con_ocr`, `imagen` | La imagen en resolución original. El OCR, si existe, como apoyo y marcado como OCR |
| `vacia` | Nada. Queda declarada en `lectura` de la salida |
| Zonas de firma | El recorte ampliado (D20) |

Hoy el arnés de pruebas manda texto e imagen de todas las páginas, y con las 4 vueltas actuales cada imagen se paga 4 veces.

### Decisiones

1. **Imágenes solo donde hacen falta**, pero no se cambia nada hasta medirlo con los gold de los TD cerrados (suite de D24). Riesgo conocido: sin imagen se pierden casillas y firmas, así que hay que comprobar que las anclas las encuentran todas.
2. **OCR de las páginas escaneadas como experimento** con TD-27 y TD-26, donde hoy fallamos al leer números escaneados (TD-27: 0 de 5 exactos). Document Intelligence Read cuesta del orden de $1,5 por 1.000 páginas; sobre el ~19 % escaneado serían unos $90 al año. El costo no decide: decide si mejora la exactitud frente a la imagen sola. Si se adopta, el texto queda en la lectura y le sirve también al clasificador.
3. **Se ofrece la lectura al clasificador.** Le ahorra el OCR y garantiza que vea el mismo texto y la misma paginación que nosotros (pregunta A-5).

**Caveat de licencias:** PyMuPDF haría todo en una librería, pero es AGPL y muchas empresas no la aceptan en un servicio. Alternativas con licencia permisiva: pypdfium2 y pdfplumber, o poppler como comando (lo que usa hoy el arnés). Hay que confirmarlo con arquitectura antes de elegir.

---

## Paso 3 — Clasificación · Revisado

**Dueño:** el equipo de clasificación hace el clasificador. Todo lo que lo rodea es nuestro: cómo lo llamamos, qué esperamos de vuelta y qué hacemos con cada resultado.

### Qué muestra la clasificación manual de la muestra

104 archivos de oferentes, clasificados a mano en `Documentos/clasificados/manifiesto.csv`:

| Hallazgo | Cantidad | Qué implica |
|---|---|---|
| Un archivo = un documento | ~97 % | El caso normal es simple |
| Archivos compuestos | 3 | La carta de BV trae carta (p1-6), Cámara de Comercio (p7-11), cédula (p12) y RUT (p13-16). La segmentación hace falta, pero es la excepción |
| Sin tipo en la matriz | 19 (18 %) | Sobre todo formatos de desempate y hojas "NO APLICA" (ver más abajo) |
| El nombre del formato cambia por proceso | — | En este proceso la oferta económica es el "Apéndice No. 3"; en PCA-SR5587392192 era el "Formulario 9" |

### Cómo lo llamamos

- **Una llamada por archivo**, no por página ni por oferente. Es la unidad natural para segmentar y permite procesar en paralelo.
- Le mandamos:
  - el PDF normalizado;
  - el nombre original del archivo y su ruta de origen (las carpetas ayudan: "EMPRENDIMIENTO MUJERES");
  - opcional: nuestra lectura por página (paso 2);
  - opcional: los nombres que este proceso da a sus formatos ("Apéndice No. 3 = oferta económica"), como contexto.
- Los duplicados (mismo hash) no se clasifican: reusan el resultado del original.

### Qué esperamos de vuelta

Por archivo, una lista de segmentos `{pagina_inicio, pagina_fin, tipo_documental, confianza}`. Al recibirla validamos:

- cada página cae en exactamente un segmento, sin huecos ni solapes;
- los TD usan los identificadores de la matriz (C2);
- lo que no es de ningún tipo sale como TD-99; no se omite.

### Qué hacemos con cada resultado

| Caso | Qué pasa |
|---|---|
| Confianza ≥ umbral del TD (0,85-0,95 según la ontología) | Se extrae normal |
| 0,75 ≤ confianza < umbral del TD | Se extrae, y todo el documento va a revisión con el motivo nuevo `CLASIFICACION_DUDOSA` |
| Confianza < 0,75 | **No se extrae.** Va directo a una tarea humana de clasificación. Cuando la persona asigna el TD, se extrae |
| La extracción responde `no_corresponde` | Va directo a una tarea humana de clasificación, sin reintento automático entre clasificador y extractor |
| TD-98 (desempate) | No se extrae en v0. Queda en el inventario; se extrae bajo demanda si hay empate |
| TD-99 o sin tipo en la matriz | No se extrae. Queda en el inventario del oferente como "documento sin tipo", visible para el evaluador |
| Respuesta inválida (huecos, solapes, TD desconocido) | Se reintenta una vez; si sigue mal, tarea humana de clasificación |

### Sin esperar al clasificador

El `manifiesto.csv` de la clasificación manual sirve de **clasificador falso** (doble de prueba, principio 5): con él se arma y se prueba todo el flujo ahora, y se cambia por el real cuando esté.

### Documentos de desempate: TD-98 · Revisado

**Qué son:** si dos oferentes empatan en puntaje total, las CPC definen cómo se decide cuál queda primero en el orden de elegibilidad. Algunos criterios se acreditan con documentos. GEB-ENLAZA (V2024) trae sus propios formatos en el paquete del proceso:

- **C-3:** personal con discapacidad. Cita la ley 361 de 1997 y la ley 2069 de 2020, y va con el certificado del Ministerio de Trabajo.
- **C-4ab:** personas mayores.
- **C-8-9:** Mipyme, mutual o cooperativa.

**El criterio cambia por proceso:**

- En SR5658940621 (numeral 6.3 de las CPC), el empate se decide por quién presentó primero la oferta en Ariba. Los documentos de desempate no se usan, pero cinco de los seis oferentes los entregaron igual.
- En PCA-SR5587392192, el orden de elegibilidad aplica "los criterios de desempate del 4.6".

**Decisión: un tipo propio, TD-98 "Soporte de criterio de desempate".** Así salen de TD-99 (lo no reconocido) y se encuentran fácil si hacen falta.

- **v0, solo clasificación:** TD-98 no tiene campos y no se extrae. Queda en el inventario del oferente.
- **Extracción bajo demanda:** cuando el módulo 4 detecta un empate y el proceso desempata con documentos, se extraen los TD-98 de los oferentes empatados. Los campos se definen cuando negocio confirme qué criterios se usan.
- **Subtipo por criterio:** `discapacidad`, `personas_mayores`, `mipyme`, `emprendimiento_mujeres`, `otro`. Sirve para saber qué documentos procesar según el criterio del proceso. La ontología ya maneja subtipos (TD-07).
- **Formato o soporte:** el formato firmado (C-3, C-4ab, C-8-9) y sus soportes van en el mismo TD-98.

**Lo difícil son los soportes.** Muchos son documentos comunes que, mirados solos, parecen de otro tipo:

| Soporte (muestra) | Se parece a |
|---|---|
| Planillas de aportes (GOODS, 4) | TD-16 seguridad social |
| Cédula de la contadora | TD-14 documento de identidad |
| Certificaciones laborales, certificado de un seminario | TD-30 o nada |

Lo que los delata como desempate es el contexto: la carpeta ("EMPRENDIMIENTO MUJERES", "PERSONA EN CONDICION DE DISCAPACIDAD", "3.17 Criterios desempate") o que vienen detrás de un formato C-x en el mismo PDF. Por eso al clasificador le mandamos la **ruta de origen** del archivo, no solo el nombre.

**De la muestra:** de los 19 archivos de oferentes sin tipo, unos 15 serían TD-98. Los demás:

- 2 hojas "NO APLICA": siguen en TD-99, y quedan visibles para el evaluador.
- 2 cédulas que no son del representante legal (contadora, revisor fiscal): TD-14 hoy solo cubre representante o apoderado. Es un hueco de la matriz aparte.

**Hay que acordarlo con clasificación:** TD-98 entra en su ontología y en la tabla de equivalencias de identificadores (C2).

---

## Paso 4 — Orquestación · Revisado

**Dueño:** nosotros. Sin LLM: orquestar es determinista.

### Estado que guarda

| Entidad | Estados | Notas |
|---|---|---|
| **Proceso** | `abierto` → `ficha_por_confirmar` → `ficha_confirmada` → `evaluando` → `con_informe` | Guarda las versiones fijadas (modelo de extracción, ontología, reglas) y la ficha del proceso (parámetros de la CPC y sus adendas) |
| **Oferente** | `recibido` → `procesando` → `en_revision` → `listo_para_reglas` → `evaluado`; también `en_espera` (evaluación por menor precio, aún no es su turno) | Su estado se calcula a partir de sus archivos y segmentos |
| **Archivo** | `pendiente` → `normalizado` → `clasificado`; también `duplicado`, `error_entrada`, `esperando_clasificacion_humana` | Una entrada del manifiesto (paso 1) |
| **Segmento** | `pendiente` → `extrayendo` → `extraido` → `en_revision` → `confirmado`; también `sin_extraccion` (TD-98, TD-99), `error_proceso` | Un documento dentro del archivo (paso 3) |
| **Tarea humana** | `abierta` → `resuelta` | Cuatro clases: clasificación, revisión de campos, documento con error y confirmar ficha del proceso. Se escriben donde la Power App las lee |

**Cuándo está completo un oferente:** cuando ningún archivo ni segmento suyo está en un estado intermedio. Cada vez que algo de un oferente termina, el worker pregunta "¿le queda algo pendiente?". No se llevan contadores, que se pueden desincronizar.

**Reglas y estado:** las reglas corren de forma provisional desde que el oferente no tiene documentos pendientes y se vuelven definitivas cuando no le quedan tareas abiertas (paso 6).

### Tecnología: Service Bus + workers en Container Apps + estado en Cosmos

Cada paso es un worker que lee de una cola, trabaja, actualiza el estado en Cosmos y publica en la cola siguiente.

```
entrega lista ─► [cola normalizar] ─► worker normaliza + lee (pasos 1 y 2)
   ─► [cola clasificar] (un mensaje por archivo)
   ─► worker llama al clasificador, valida segmentos, aplica umbrales (paso 3)
   ─► [cola extraer] (un mensaje por segmento)
   ─► unidad de extracción (paso 5, contrato v0)
   ─► [cola resultados] ─► worker actualiza el estado
        ├─ campos en revisión ─► tarea humana (Dataverse) ◄── las correcciones vuelven por Service Bus
        └─ ¿oferente completo? ─► [cola reglas] ─► módulo 4 (paso 6)
```

- Cada cola tiene su cola de errores (dead-letter).
- La concurrencia de la cola de extracción se limita a 3, por los errores 429.
- Las correcciones del revisor vuelven como mensajes: Dataverse tiene integración nativa con Service Bus.

**Por qué esta opción:**

- Es el mismo stack que ya usa el MCP (Container Apps) y el modelo (Cosmos).
- El job de normalización y lectura ya es un worker de este tipo.
- El estado queda en tablas que se consultan fácil, también desde tableros o desde la Power App.
- Cada pieza se prueba por separado (principio 5).

**Lo que se escribe a mano:** la consulta de "¿terminó el oferente?" y los reintentos. Es poco código.

**Descartadas:**

- **Durable Functions:** trae incluidos el reparto, la espera de resultados y las esperas largas, pero su modelo de repetición tiene reglas propias y el estado queda dentro del framework, menos visible.
- **Logic Apps Standard:** cómodo para conectores y aprobaciones, pero la lógica fina (validar segmentos, fijar versiones, umbrales) queda incómoda, el versionado en git es más débil y cobra por acción.
- **Agente o flujo de Foundry:** orquestar no necesita un LLM.

**Costo:** Service Bus Standard, unos $10 al mes; Cosmos serverless, por uso; los workers escalan a cero. Unas decenas de dólares al mes.

### Manejo de errores

**Principio:** cada error le llega a quien puede resolverlo. El **evaluador** decide sobre documentos; **operación** (nosotros) arregla fallas técnicas. El evaluador no ve errores técnicos y operación no decide sobre documentos.

| Clase | Ejemplos | Reintentos | Estado final | Quién se entera |
|---|---|---|---|---|
| **1. Del documento** | No abre, está dañado, pide contraseña para abrir, la conversión falla, PDF vacío | Un solo intento de reparación (qpdf, convertir de nuevo) | `error_entrada` | **Evaluador**, con una tarea "documento con error" para que decida si pide subsanación |
| **2. Transitorio** | 429, timeout, el LLM o el MCP responde 5xx, el clasificador está caído, Cosmos limita | 3, con espera creciente (D22). El **429 no cuenta como intento**: se reprograma con el tiempo de espera que indica Azure | Si se agotan: `error_proceso` | **Operación** (alerta) |
| **3. Respuesta inválida del LLM** | JSON que no cumple el esquema, sobre incompleto | 2 inmediatos | Si persiste: `error_proceso` | **Operación** |
| **4. Bug** | Excepción que se repite igual cada vez | Ninguno | Directo a la cola de errores | **Operación** |

- Un JSON válido con un campo raro no es error: la posvalidación lo manda a revisión con `VALIDACION_FALLIDA` (D13).
- Si el clasificador responde algo inválido: un reintento y, si no, clasificación humana (paso 3).

**Qué pasa con un `error_proceso`:**

1. El segmento bloquea que el oferente quede completo. No se evalúa a un oferente con un documento sin procesar.
2. Alerta inmediata a operación. El mensaje queda en la cola de errores con su contexto.
3. Corregida la causa, se reenvía desde la cola de errores. Es seguro porque todo es idempotente.
4. Si no se resuelve en **24 horas** (configurable), se crea una tarea humana "documento sin procesar por falla técnica", para que el evaluador lo revise a mano y el proceso no quede frenado.

**Tipos de tarea humana:** clasificación, revisión de campos, documento con error (incluye el escalamiento por falla técnica) y confirmar ficha del proceso.

**Mecanismos:**

- **Idempotencia en cada worker,** porque Service Bus puede entregar un mensaje dos veces. Las claves:
  - normalizar: hash del archivo;
  - clasificar: `id_documento` + hash;
  - extraer: `id_documento`, páginas, TD y versión (D22).
- **Cambios de estado condicionales:** solo se actualiza si el estado es el esperado, para que mensajes cruzados o fuera de orden no se pisen.
- **Aislamiento:** un archivo con error no frena a los demás del oferente.
- **Freno automático** (opcional en v0): si el LLM falla muchas veces seguidas, el worker deja de tomar mensajes unos minutos, en vez de mandar toda la cola a errores.
- **Trazabilidad:** todos los logs llevan `id_proceso`, `id_oferente` e `id_documento` (Application Insights).
- **Alertas:**
  - cola de errores con mensajes;
  - mensaje más viejo de una cola por encima de un umbral;
  - tasa de 429;
  - tasa de `error_proceso`.

### Versión del modelo por proceso

**Regla (principio 7):** todos los oferentes de un proceso se evalúan con la misma versión del modelo de extracción, aunque lleguen en momentos distintos.

**Cómo:**

1. Existe un registro por proceso: `id_proceso → version_modelo`, con la fecha y el documento que la fijó.
2. La versión se graba en la apertura del proceso. Si llega un segmento y todavía no hay versión (la oferta llegó antes que la CPC), se toma la vigente y se graba.
3. Los segmentos siguientes, de cualquier oferente, leen la versión grabada. No usan la vigente.
4. La grabación es condicional ("solo si no existe"). Si llegan dos oferentes a la vez, gana el primero y el otro lee la que quedó.
5. Publicar una versión nueva del modelo no toca los procesos abiertos.
6. Cambiar la versión de un proceso abierto es una decisión explícita. Obliga a reprocesar a todos sus oferentes (`reprocesar`) y a dejar registrado el motivo.

**Hueco en el contrato v0:** hoy dice que si no llega `version_modelo` se usa la vigente. Si los oferentes llegan en días distintos y se publica una versión en el medio, dos oferentes del mismo proceso quedarían evaluados con versiones distintas. Hay que cambiarlo: si no llega `version_modelo`, la unidad consulta el registro del proceso, y solo si está vacío toma la vigente y la graba.

**¿Quién guarda el registro?** Como el orquestador y la extracción son nuestros, el registro vive en el estado del proceso que lleva el orquestador, junto con el resto del estado. El orquestador manda `version_modelo` en cada llamada (D7). La extracción, si no le llega, consulta el mismo registro en vez de usar la vigente, para que la regla no dependa de que todos los llamadores la cumplan.

El mismo registro guarda la versión de la ontología del clasificador y la de las reglas del módulo 4: todas se fijan con el primer oferente del proceso.

### Subsanación y reprocesamiento · Revisado

**Qué dicen las CPC (SR5658940621, numeral 6.2):** se pueden subsanar los documentos que acreditan condiciones del oferente y los requisitos habilitantes o de cumple/no cumple. No se puede mejorar la oferta ni subsanar criterios que dan puntaje. El oferente tiene 48 horas desde la solicitud. La solicitud y la respuesta van por la mensajería de Ariba. Si no subsana a tiempo, la oferta se rechaza.

**Enfoque para v0: una subsanación son documentos que llegan tarde.** El flujo no necesita piezas nuevas.

1. **La solicitud, el plazo y el rechazo quedan fuera del sistema.** El evaluador los maneja en Ariba. No armamos solicitudes, no ponemos temporizadores y no contamos rondas.
2. **El documento de subsanación entra por el módulo 1 como cualquier otro:** normalización, lectura, clasificación y extracción, con la versión fijada del proceso (principio 7). Lleva un `id_documento` nuevo, la marca `subsanacion: true` y su fecha de recepción.
3. **Nada se reemplaza ni se borra** (principio 3). El original y el nuevo quedan los dos. Se corren de nuevo todas las reglas del oferente con todo lo que tiene: es código determinista y barato, y así no se escapa un cruce entre documentos. El evaluador ve los dos documentos lado a lado y decide cuál cuenta.
4. **La mejora de la oferta** (causal de rechazo) es juicio humano, como ya lo modela la matriz (SUB-05).

**Reprocesamiento:** un solo comando manual, `reprocesar(segmento o proceso, motivo)`, que queda registrado con quién lo pidió. Sirve para un cambio de versión en un proceso abierto, una clasificación corregida o un bug arreglado. No hay casos predefinidos.

**Lo que se deja para después,** si la operación lo pide. Se puede agregar sin romper nada, porque la marca y la fecha ya quedan guardadas:

- columna `cardinalidad` en la matriz, para decidir sola si el documento nuevo reemplaza al anterior o se suma;
- alerta automática de "posible mejora de la oferta";
- seguimiento del plazo y marca de entrega fuera de plazo.

**Costo de simplificar:** cuando el mismo TD aparece dos veces, elige el evaluador y no el sistema.

### Apertura del proceso · Revisado

**Qué muestra la muestra (SR5658940621):** el proceso abrió el 26/06/2026; las tres adendas son del 14/07, 17/07 y 27/07, y el cierre quedó el 30/07. Todas salieron antes del cierre y cambian la fecha de cierre y el plazo del contrato. Cuando llegan las ofertas, la CPC y sus adendas ya están completas. Una adenda en plena evaluación es posible, pero rara.

**Cómo se abre un proceso:**

1. **Los documentos del proceso entran por el módulo 1,** igual que las ofertas, pero marcados como del proceso y sin oferente: CPC, adendas, datos esenciales, anexos.
2. **Se extraen con la misma unidad de extracción:** TD-01 (campos TD01-01 a TD01-27) y TD-02 (TD02-01 a TD02-09), como cualquier otro TD.
3. **Ficha del proceso:** los valores de la CPC con las adendas aplicadas en orden de número; en cada parámetro gana la adenda más reciente. Cada valor guarda de qué documento y qué página salió (principio 3). Incluye, entre otros, documentos exigidos (TD01-22), plazo de subsanación (TD01-18), indicadores financieros (TD01-24), experiencia mínima (TD01-25), reglas económicas (TD01-26) y causales de rechazo (TD01-27).
4. **Un humano confirma la ficha completa, una vez por proceso** (principio 4). Un error ahí afecta a todos los oferentes y son solo unos 400 procesos al año. Es un tipo de tarea humana propio: "confirmar ficha del proceso".
5. **La ficha bloquea solo las reglas.** Las ofertas se extraen mientras tanto, porque la extracción no usa parámetros del proceso (D8). Las reglas del paso 6 esperan a que la ficha esté confirmada.
6. **Las versiones se fijan en la apertura** (modelo de extracción, ontología, reglas), como decía D7. La grabación condicional con el primer segmento queda como respaldo si llega una oferta antes que la CPC.
7. **La lista de documentos exigidos se usa dos veces:** se le pasa al clasificador (paso 3) y sirve para detectar los documentos que le faltan a cada oferente.

**Adenda después de confirmar la ficha:** se arma una ficha nueva, el humano la confirma de nuevo y se corren otra vez las reglas de todos los oferentes, que son baratas. No se vuelve a extraer nada, salvo que la adenda cambie un formulario.

**Evaluación por menor precio.** En los PCA de menor valor se evalúa primero la oferta más barata y solo se pasa a la siguiente si esa no cumple o no subsana. La ficha lo declara con `modo_evaluacion`: `menor_precio_secuencial` o `todos`.

Con `menor_precio_secuencial`:

1. Se extrae todo de todos los oferentes: cuesta poco y evita esperas.
2. Se ordenan por el valor de su oferta económica (TD-35).
3. Las tareas de revisión se crean solo para el oferente en turno.
4. Cuando el evaluador lo rechaza, se abren las del siguiente.

El ahorro está en el tiempo del revisor, no en tokens. Con `todos`, se crean tareas para todos los oferentes.

### Cola y volumen

- La extracción se recibe por cola (Service Bus), un mensaje por segmento. Responde O1 y absorbe los picos: un proceso de 10 oferentes son unos 160 segmentos, unos 20 minutos con concurrencia 3.
- La concurrencia queda limitada por los errores 429 (hoy 3). La cuota de tokens se dimensiona para el peor día (varios cierres juntos).


---

## Paso 5 — Extracción · Revisado

**Dueño:** nosotros. Lo define el contrato v0 (`contracts/modulo3-extraccion/v0/`): preprocesamiento, agente y posvalidación determinista, con un solo punto de llamada. Sigue valiendo lo esencial: una solicitud por segmento, páginas contadas sobre el archivo completo, `revision` calculada por la posvalidación y reglas que necesitan otros documentos o parámetros del proceso enviadas como `reglas_pendientes`.

**Se mantiene el contrato aunque el orquestador y la extracción sean nuestros:** permite probar cada pieza por separado con dobles de prueba (principio 5) y deja la extracción reutilizable.

### Cambios para el contrato 0.2

Todos salen de lo decidido en los pasos 1 a 4.

| # | Cambio | Por qué |
|---|---|---|
| 1 | **Transporte por cola:** la solicitud llega por la cola de extracción de Service Bus y el resultado sale por la cola de resultados | Paso 4. Cierra O1 |
| 2 | **Campo nuevo `lectura`:** referencia a la lectura del paso 2 (texto por página, tipo de página, firma digital) | La extracción reusa la lectura en vez de volver a leer el PDF. Se lee una sola vez y clasificador y extractor ven el mismo texto |
| 3 | **Campo nuevo `anexos`:** el Excel nativo | Paso 1 (cambia D18) |
| 4 | **Campo nuevo `clasificacion_dudosa`:** el orquestador lo pone cuando la confianza está entre 0,75 y el umbral del TD; la extracción marca el resultado para revisión con el motivo `CLASIFICACION_DUDOSA` | Paso 3. El umbral se aplica en un solo lugar, el orquestador |
| 5 | **Sin `version_modelo`, se usa la versión registrada del proceso,** no la vigente | Paso 4 (principio 7) |
| 6 | **`id_oferente` opcional** para los documentos del proceso (TD-01, TD-02) | Apertura del proceso: la CPC y las adendas no tienen oferente |
| 7 | **TD-98 no se envía en v0,** igual que TD-99 | Paso 3: no tiene campos; se extrae solo si el módulo 4 detecta un empate |
| 8 | **`forzar_reproceso` sigue igual,** pero solo lo activa el comando `reprocesar`, que guarda quién lo pidió y por qué | Subsanación y reprocesamiento (paso 4) |

**No entran al contrato:** la marca `subsanacion` y el orden por precio. Los lleva el orquestador; la extracción no los usa.

**Cuándo se actualizan los archivos del contrato:** cuando se cierre el diseño completo (después del paso 6), en una sola pasada: esquemas JSON, ejemplos y validación de los ejemplos contra los esquemas. Hasta entonces, los cambios viven en este documento.

**Pendientes que ahora son nuestros:**

- **R1, identificador de regla:** `id_regla` es provisional (`<id_tecnico>.r<n>`). Partir las reglas de la matriz en reglas atómicas con ámbito es trabajo interno. Se resuelve con la hoja **Reglas** del paso 6.
- **P1, caja por cita en la evidencia:** después de v0.

### Costo: inyectar la ficha del TD

**Hoy:** antes de extraer, el agente hace 3 consultas al MCP (`listar_modelos`, `describir_modelo`, la ficha del TD). Son 4 vueltas del LLM, y en cada una se reenvía el documento completo, con texto e imágenes. Por eso la mediana es de unos 22.000 tokens de entrada por documento.

**La palanca:** como el TD ya se conoce antes de llamar al agente, la ficha va directamente en el mensaje y el agente hace una sola vuelta. Estimado: cerca de la mitad de tokens de entrada, menos tiempo y un prefijo fijo que aprovecha la caché de prompt. El ahorro es del orden de $1.400 al año.

**Antes de adoptarla se mide** con `lote.py` sobre dos TD con gold (TD-16 y TD-29): versión actual contra versión de una vuelta, comparando tokens, tiempo y exactitud. Se adopta solo si la exactitud no baja. Toca D21: el MCP sigue sirviendo para diseñar el modelo, pero producción no lo necesitaría.

**Batch API queda para después de v0:**

- ahorra poco (del orden de $1.000 al año);
- la respuesta puede tardar hasta 24 horas, y la evaluación por menor precio necesita pronto la oferta económica de todos;
- no está confirmado que gpt-5.4 lo admita en el deployment.

Se puede agregar después sin cambiar el contrato.

---

## Paso 6 — Reglas, informe y tareas de revisión · Revisado

**Dueño:** nosotros. Sin LLM en la ejecución: las reglas son datos y el código las aplica.

**De dónde partimos:**

- **Las reglas pendientes que devuelve la extracción son texto libre.** Ejemplos: `td16.fecha_certificacion.r1` "≤ cierre" (requiere PRO-16), `td29.proceso_y_oferente.r1` "Proceso = td01.numero_proceso", `td29.contratos.r2` "Máximo de contratos de la CPC" (requiere PRO-23). Una persona las entiende; un programa no las puede ejecutar.
- **GEB evalúa por área y por criterio.** La plantilla de evaluación (proceso SR5587392192) tiene cuatro hojas, Jurídica, Financiera, Técnica y Económica, cada una con su evaluador. Cada fila es un criterio con código (JUR-01, ECO-P3, ARI-T2…). Al final, cada oferente queda hábil o no hábil, con puntaje y orden de elegibilidad.

### Reglas como datos (resuelve R1)

Una hoja nueva en la matriz, **Reglas**: una fila por regla atómica, con un `id_regla` estable, el criterio y el área a los que pertenece, y uno de cuatro tipos.

| Tipo | Qué hace | Ejemplo |
|---|---|---|
| `comparar` | Compara un campo con otro campo o con un parámetro de la ficha del proceso: `=`, `≤`, `≥`, `en_lista` | Fecha del certificado ≤ fecha de cierre (PRO-16) |
| `existe` | Revisa que el oferente haya entregado un TD | Si firma el revisor fiscal, deben existir TD-26 y TD-27 |
| `calculo` | Llama a una función con nombre, escrita y probada en código | Puntaje económico, indicadores financieros |
| `juicio` | No se automatiza: crea una tarea humana | Afinidad de la experiencia, mejora de la oferta |

- Agregar o cambiar una regla es editar una fila, no programar (principio 2). Las funciones de `calculo` son pocas y se prueban una por una. Lo que necesita criterio humano queda declarado como tal.
- **El LLM ayuda a escribir las reglas, pero no las ejecuta.** Al diseñar, un LLM puede convertir el texto libre de la matriz en filas de los cuatro tipos; una persona revisa cada fila antes de publicarla. En la ejecución no hay LLM, por cuatro razones:
  - el mismo dato da siempre el mismo resultado (principio 7);
  - cada veredicto se explica con exactitud ("fecha del certificado 15/08 > cierre 30/07, regla JUR-03.r1");
  - recalcular con cada corrección es inmediato y gratis;
  - cada regla se prueba con datos de ejemplo.
- Después de v0 se puede evaluar un LLM que sugiera, sin decidir, en las reglas de `juicio` (por ejemplo, la afinidad de la experiencia).
- Las reglas tienen versión y se fijan con el proceso (paso 4), igual que el modelo de extracción.

### Cuándo corren

1. Por primera vez, cuando la ficha del proceso está confirmada y el oferente no tiene documentos pendientes de extracción.
2. Un criterio que depende de un campo todavía en revisión sale **provisional**.
3. Cada corrección de un revisor recalcula todas las reglas del oferente. Es barato y más simple que decidir qué recalcular.
4. Cuando el oferente no tiene tareas abiertas, su resultado queda **definitivo**.

El evaluador ve un adelanto desde el principio, y no hay que programar una espera especial.

### Tareas de revisión

**Una tarea por oferente y por área,** por ejemplo "Revisión jurídica de Oferente X: 7 puntos". Cada punto trae el valor extraído, la evidencia (página y cita), el motivo de la revisión y tres acciones: confirmar, corregir o marcar no cumple. Los veredictos "no cumple" entran a la misma tarea, porque los confirma un humano (principio 4).

- Cada evaluador trabaja solo su área y ve todo lo del oferente en una pantalla.
- Son unas 4 tareas por oferente, en vez de decenas.
- Con evaluación por menor precio, se abren solo para el oferente en turno (decisión 24).

**Correcciones:** la Power App guarda la corrección en Dataverse y llega por Service Bus. Se guardan el valor del LLM y el corregido, con quién y cuándo: sirve para la trazabilidad (principio 3) y para calibrar umbrales (D17). Después se recalculan las reglas del oferente.

### Informe

Cuando los oferentes que se evalúan quedan definitivos (todos, o el oferente en turno según `modo_evaluacion`), el sistema genera el informe en **Excel con el formato de las plantillas de GEB**: las cuatro hojas por área y el consolidado (hábil o no hábil, puntaje, orden), con un enlace a la evidencia de cada criterio. Lo firma el coordinador. Si hay empate en el orden, el módulo 4 pide extraer los TD-98 del desempate (decisión 14).

---

## Costo

| Concepto | Estimado anual |
|---|---|
| Extracción, como hoy (~48.000 documentos, ~$0,08 c/u) | ~$3.700 |
| Extracción con ficha inyectada | ~$2.300 |
| Clasificación con mini en texto (~320.000 páginas) | ~$500-800 |
| Normalización (Container Apps, escala a cero) | Prácticamente cero |

Precios de referencia de agregadores, sin confirmar en Azure: gpt-5.4 a $2,50 / $15 por millón de tokens, gpt-5.4-mini a $0,75 / $4,50. El costo del LLM es pequeño. Pesan más el tiempo de revisión humana, la infraestructura encendida y mantener piezas duplicadas.

## Decisiones de esta revisión

1. Se trabaja sobre la opción A: clasificación y extracción como etapas separadas.
2. Los archivos llegan descomprimidos.
3. Excel: PDF para clasificar y citar páginas, más el Excel nativo como anexo para la extracción.
4. Firma digital: en v0 solo se detecta y se anota. No se valida la confianza del certificado.
5. Los oferentes pueden llegar en momentos distintos. La versión del modelo se fija en la apertura del proceso (o, si falta, con el primer segmento) y la usan todos los oferentes.
6. Somos dueños de todo el flujo menos la entrada de documentos, el clasificador y la Power App: normalización, lectura, orquestación, extracción, módulo 4 y creación de tareas de revisión.
7. La lectura es código determinista, sin LLM, y se guarda una vez por archivo.
8. Las imágenes se mandan al LLM solo donde hacen falta, después de medirlo con los gold.
9. El OCR de páginas escaneadas se prueba con TD-27 y TD-26 antes de adoptarlo.
10. La lectura se ofrece al clasificador.
11. Una llamada al clasificador por archivo.
12. Umbrales de clasificación: desde el umbral del TD, extracción normal; entre 0,75 y el umbral del TD, extracción con revisión (`CLASIFICACION_DUDOSA`); por debajo de 0,75, sin extracción y directo a clasificación humana.
13. `no_corresponde` va directo a clasificación humana, sin reintento automático.
14. Los documentos de desempate van a un tipo nuevo, TD-98, con subtipo por criterio. En v0 no se extraen; se extraen bajo demanda si el módulo 4 detecta un empate.
15. El orquestador guarda el estado de cinco entidades: proceso, oferente, archivo, segmento y tarea humana. Un oferente está completo cuando no le queda nada en estado intermedio.
16. Tecnología del orquestador: Service Bus + workers en Container Apps + estado en Cosmos.
17. Errores: los del documento van al evaluador como tarea "documento con error"; los técnicos van a operación. Un `error_proceso` bloquea al oferente y se escala a tarea humana a las 24 horas.
18. Reintentos: 3 con espera creciente para los transitorios (el 429 no cuenta como intento); 2 para la respuesta inválida del LLM; ninguno para bugs.
19. Subsanación en v0: los documentos entran por el flujo normal con la marca `subsanacion` y su fecha. Nada se reemplaza; se corren de nuevo todas las reglas del oferente y el evaluador decide cuál cuenta. La solicitud, el plazo y el rechazo se manejan fuera del sistema, en Ariba.
20. Reprocesamiento: un comando manual con motivo registrado.
21. Los documentos del proceso (CPC, adendas) entran por el módulo 1 y se extraen con nuestra unidad de extracción.
22. Ficha del proceso: CPC más adendas en orden de número; gana la más reciente. Un humano la confirma una vez por proceso, y la confirmación bloquea solo las reglas.
23. Adenda después de confirmar la ficha: ficha nueva, nueva confirmación y se corren otra vez las reglas de todos los oferentes, sin volver a extraer.
24. Evaluación por menor precio (`modo_evaluacion` en la ficha): se extrae todo, se ordena por el valor de la oferta económica y las tareas de revisión se abren solo para el oferente en turno.
25. Contrato 0.2: los ocho cambios del paso 5 (cola, `lectura`, `anexos`, `clasificacion_dudosa`, versión del proceso, `id_oferente` opcional, TD-98 sin envío, `forzar_reproceso` vía `reprocesar`). Los archivos del contrato se actualizan cuando se cierre el diseño completo.
26. La ficha del TD inyectada se mide con TD-16 y TD-29 antes de adoptarla; se adopta solo si la exactitud no baja.
27. Batch API queda para después de v0.
28. Reglas como datos: hoja Reglas en la matriz con cuatro tipos (`comparar`, `existe`, `calculo`, `juicio`). Sin LLM en la ejecución; un LLM puede ayudar a redactar las filas, que revisa una persona.
29. Las reglas corren de forma provisional y se recalculan con cada corrección; el resultado queda definitivo cuando el oferente no tiene tareas abiertas.
30. Tareas de revisión: una por oferente y por área, con los campos a revisar y los "no cumple" a confirmar.
31. Informe en Excel con el formato de las plantillas de evaluación de GEB, firmado por el coordinador.

## Cambios a decisiones anteriores

- **D18:** además de PDF e imagen, la extracción acepta el Excel nativo como anexo.
- **D13:** se agrega el motivo de revisión `CLASIFICACION_DUDOSA`, activado por el campo `clasificacion_dudosa` de la entrada.
- **O1:** el transporte es cola de Service Bus.
- **D7 y contrato v0:** las versiones se fijan en la apertura del proceso. Sin `version_modelo` en la entrada, se usa la versión registrada del proceso, no la vigente.

## Preguntas nuevas

| # | Para | Pregunta |
|---|---|---|
| A-1 | Módulo 1 | ¿Dónde dejan los archivos (blob o SharePoint)? ¿Cómo avisan que un oferente terminó de entregar? ¿Qué identificadores de proceso, oferente y archivo usan? ¿Nos pasan también los documentos del proceso (CPC, adendas, anexos), marcados como tales? |
| A-2 | Power App | ¿Dónde escribimos las tareas de revisión y con qué forma? Proponemos una tarea por oferente y área, con puntos que se confirman, corrigen o marcan no cumple. ¿Cómo leemos las correcciones? |
| A-3 | Negocio | ¿Un PDF modificado después de firmarse digitalmente debe alertar al evaluador? |
| A-4 | Negocio (N-A) | ¿Una firma digital del oferente cuenta como "Firmado"? ¿Hay que validar la confianza del certificado? |
| A-5 | Clasificación | ¿Clasifican sobre el PDF normalizado del manifiesto? ¿Les sirve nuestra lectura por página (texto, tipo de página, OCR)? |
| A-7 | Clasificación | ¿Agregan TD-98 (desempate, con subtipos) a la ontología? ¿Usan la ruta de origen del archivo para reconocer los soportes? |
| A-8 | Negocio | ¿Qué tan seguido hay empates? ¿Qué procesos desempatan con documentos y cuáles por orden de presentación? |
| A-9 | Negocio | ¿TD-14 debe cubrir también las cédulas de contador y revisor fiscal? |
| A-11 | Negocio | ¿El informe de evaluación se entrega en Excel con el formato de las plantillas actuales (Jurídica, Financiera, Técnica, Económica y consolidado)? |
| A-10 | Módulo 1 | ¿Cómo llegan los adjuntos de una subsanación, que vienen por la mensajería de Ariba? ¿Se pueden distinguir de la entrega original? |
| A-6 | Arquitectura | ¿Se acepta una librería AGPL (PyMuPDF) en el servicio, o hay que usar alternativas permisivas? |
