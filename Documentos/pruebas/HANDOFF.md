# Handoff: pruebas del modelo semántico por tipo documental

Estado al 2026-10-29. Modelo publicado: **v21** (`extraccion_documental`, Cosmos DB). Proceso de prueba: SR5658940621, con 6 oferentes (AICOSS, BV, GOODS, LEVIN, LONJACUN, PWC).

## Qué estamos haciendo

Se prueba un tipo documental (TD-NN) a la vez contra el MCP desplegado, se anotan los fallos y se proponen mejoras al modelo. Con el visto bueno del usuario se aplican, el usuario publica y se verifica con una corrida corta. No se aplica ni se publica nada sin pedirlo.

## Estado por tipo documental

| TD | Estado | Corridas | Pendiente |
|---|---|---|---|
| TD-30 Certificación o acta de contrato | Cerrado (alta y media) | 18 docs; última v10 sobre 6 livianos | M25 (revisión de campos enteros en null), M12, bajas (M18, M19, M21-M23); 2 docs largos sin correr (LEVIN 3b de 41 p, LONJACUN C1 de 30 p: `--max-paginas 0`) |
| TD-29 Formulario de experiencia | Cerrado (N01-N04) | 6 docs; verificado en v11 | Bajas N05-N07 |
| TD-03 Carta de presentación | Cerrado (P01-P05) | 6 docs; verificado en v12 | P05b (el bloque del representante no tiene nombre, cargo ni cédula), P06, P07 |
| TD-05 Acuerdo de confidencialidad | Q01-Q03 aplicadas | Los 6 archivos son el mismo PDF en blanco | Decidir si el texto impreso "Representante Legal Principal" es un dato; hacen falta acuerdos llenos de otros procesos |
| TD-17 Demandas, multas y sanciones | Cerrado (R01-R03) | 6 docs; verificado en v15 | Nada |
| TD-16 Aportes a seguridad social | Cerrado (S01-S06, S05b) | 6 docs; verificado en v15 | Nada |
| TD-15 Composición accionaria | Cerrado salvo T02 (T01, T03-T09) | 15 + 5 docs; verificado en v16 | T02 espera NEG-02 (hoy es la única causa de revisión, 5 de 5); T10 (media), T11 y T12 (bajas) |
| TD-18 Listas restrictivas | Cerrado (U01-U03) | 15 docs en v16; verificado en v17 | U04 espera NEG-10 y NEG-11; bajas U05-U08 |
| TD-35 Oferta económica | Cerrado (V01-V04, V06-V09, V11, V13); V03 verificado en v19; V14 y V09b verificados en v20 | 5 docs × 3 en v17 (GOODS solo en .xlsx, convertido a PDF) | Confirmar V09b en la próxima corrida (1 de 1 en v20); confirmar quién calcula TD35-09 y los demás Calculados en producción; V10 espera NEG-16; NEG-14 a NEG-17; V05 (ingesta de Excel) es del otro equipo |
| TD-27 Antecedentes JCC | W03, W04, W06, W07 verificadas en v20 | 5 docs × 3 en v19, × 1 en v20 | W01 parcial y W10 verificadas en v21: ningún número equivocado se acepta sin revisión (5 de 5 en revisión con 0,50); la lectura sigue en 0 de 5 exactos hasta que el otro equipo arregle la imagen; W01 es de resolución (va en el diagnóstico); W02 espera NEG-18, W05 espera NEG-19; NEG-18 a NEG-21 |
| TD-26 Tarjeta profesional | X02, X04, X05 verificadas en v20 | 3 docs × 3 en v19, × 1 en v20 | X01 es de resolución |
| **Siguientes** | Por hacer | | TD-04 (3, 7); con un solo proceso o pocos documentos: TD-07, TD-02, TD-14, TD-23, TD-01, TD-13 |

Cada carpeta `pruebas/TD-NN/` tiene `mejoras_modelo.md` (hallazgos, propuestas, lo aplicado, lo verificado y las notas para el evaluador), `generar_plantilla_gold.py` y `gold_TD-NN.xlsx`. TD-29 tiene además `comparar_con_gold.py`.

## Cambios globales ya aplicados (afectan a todos los TD)

- **Convertidor (M14):** `convertir_tipos_documentales.py` parte los objetos `{a; b SI/NO; c AAAA-MM}` en `atributos.propiedades` (nombre, valores, formato), y `formato_valores` queda solo con los nombres. Los formatos ambiguos se dejan como están. **Regla para escribir formatos en `campos.py`:** `{nombre OPCION1/OPCION2; nombre formato}`, un nombre de una sola palabra por propiedad, sin `:` ni texto fuera de las llaves. Si no se puede partir, el agente inventa las claves.
- **Guía (`tipos_documentales.guia.md`, se edita a mano):**
  - clave = `nombre` de `atributos.propiedades`
  - un dato ausente no baja la confianza (M24)
  - una fila que solo dice N/A no es un registro (R01)
  - marcas de plantilla y texto impreso no son datos (Q01)
  - firma: describir lo que hay sobre la línea antes de decidir (S01)
- **Campos de firma** de TD-03, TD-04, TD-05, TD-16 y TD-17: regla "Firmado (firma = SI)" (S06).

- **Generador (U01, 2026-10-29):** hasta v16, toda regla que empezaba con "=" se guardaba en el Excel como fórmula y el convertidor la leía vacía: 39 campos de 23 TD quedaban sin regla. `generar_matriz.py` ahora las escribe como texto. Se reverificaron en v17 TD-05, TD-16, TD-29 y TD-30: ver "Verificación tras U01" en cada `mejoras_modelo.md`. Quedaron regresiones de firma en BV (TD-29 N08, alta; TD-16 S07) y el supervisor de BV en TD-30 (M26).

## Cómo se hace un TD (receta)

1. Ver los documentos y los campos:
   - `md5sum` en `clasificados/TD-NN*/` para detectar duplicados (lo que pasó con TD-05)
   - las notas de `clasificados/manifiesto.csv`
   - los elementos del TD en `modelo-semantico/modelos/extraccion_documental/tipos_documentales.json`
2. Correr, desde `~/GEB/modelo-semantico`:
   ```
   uv run -q --group agente agente_local/lote.py "<carpeta clasificados/TD-NN ...>" TD-NN \
     --salida ~/GEB/Extraccion/Documentos/pruebas/TD-NN --repeticiones 3 --concurrencia 3
   ```
   Con `--concurrencia` mayor que 3 aparecen errores 429 de Azure; se repite lo fallado con `--corrida <carpeta>`. `DOC_DPI=150` no mejoró nada en TD-16.
3. Gold: `generar_plantilla_gold.py`, prellenado por transcripción del PDF o mirando la imagen (`pdftoppm -r 70 -png` y leer el PNG). Lo diligencia alguien del equipo de evaluación.
4. Analizar: valores por campo en las 3 repeticiones, cuáles cambian, cuáles van a revisión, claves raras (con espacio, `/` o `:`). Escribir `mejoras_modelo.md` con una tabla # / elemento / problema / tipo / prioridad, las propuestas y las notas para el evaluador.
5. Aplicar en `~/GEB/Extraccion/matriz/campos.py`:
   - columnas: `f(cid, grupo, nombre, desc, tipo, valores, aplica, donde, valid, param, celda, sino, umb, rev, dp, origen, nota)`, o `campo(cid, td, …)` en los TD antiguos
   - poner en el origen "Pruebas TD-NN (fecha) (códigos)"
   - un campo Calculado lleva `CALC` como umbral
   - cuidado: los anclajes de texto se repiten entre TD (ciudad_fecha en TD-03 y TD-04); hay que reemplazar con contexto único
6. Regenerar y validar:
   ```
   cd ~/GEB/Extraccion && uv run -q --with openpyxl matriz/generar_matriz.py
   cd ~/GEB/modelo-semantico && cp modelos/extraccion_documental/tipos_documentales.json /tmp/antes.json
   uv run scripts/convertir_tipos_documentales.py ~/GEB/Extraccion/matriz/Matriz_Extraccion_Tipos_Documentales_TD01-TD35.xlsx modelos/extraccion_documental
   uv run scripts/publicar.py modelos/extraccion_documental/tipos_documentales.json --solo-validar
   uv run scripts/publicar.py modelos/extraccion_documental/catalogos.json --solo-validar
   ```
   Comparar contra `/tmp/antes.json` qué elementos cambiaron (que no se toque otro TD) y si cambiaron los catálogos.
7. **Publicar lo hace el usuario:** `uv run scripts/publicar.py modelos/extraccion_documental/tipos_documentales.json` (más `catalogos.json` si cambió). El clasificador de permisos le niega la publicación al agente.
8. Verificar con 1 repetición por documento y anotar en `mejoras_modelo.md` la sección "Verificación".

## Herramientas

- **Visor:** `python3 ~/GEB/Extraccion/visor/servidor.py` (127.0.0.1:8765). Filtro por tipo documental y por documento; corridas de la más reciente a la más antigua; PDF al lado. `index.html` se lee en cada petición, así que no hace falta reiniciar si cambia; `servidor.py` sí.
- **`lote.py`** (sin versionar en modelo-semantico): una sesión MCP por documento; guarda en JSON por ejecución la versión del modelo, los tokens, las llamadas y la respuesta.

## Repositorios (sin commit; commitear solo si el usuario lo pide)

- `~/GEB/Extraccion`: `matriz/campos.py`, el Excel de la matriz y `.gitignore` (con `visor/`).
- `~/GEB/modelo-semantico`:
  - modificados: `scripts/convertir_tipos_documentales.py`, `modelos/extraccion_documental/{tipos_documentales.json, catalogos.json, tipos_documentales.guia.md}`
  - sin versionar: `agente_local/lote.py`
  - `HANDOFF.md`, `modelos/comite_directivo/` y `scripts/convertir_comite_directivo.py` son de otro tema: no tocarlos.
- `Documentos/` está fuera de git porque tiene datos personales.

## Decisiones del usuario

- Gold: lo llena el equipo de evaluación; se diseña para alguien que no es técnico.
- Se prueba contra el MCP desplegado, con gpt-5.4 (gpt-5.4-mini ignora las reglas de evidencia).
- La clasificación es de otro equipo: aquí solo se extrae.
- Pendientes que decide el negocio: están en `preguntas_negocio.md`, numeradas NEG-01, NEG-02…, para no confundirse con los códigos de hallazgos de TD-29 (N01…) (en esta carpeta). Cada prueba de un TD agrega allí sus preguntas, y también los campos obligatorios que los documentos casi nunca traen.
