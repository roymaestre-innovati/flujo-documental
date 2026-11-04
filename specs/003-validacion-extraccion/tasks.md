# Tareas 003 — Normalización y lectura (primera entrega)

Sale de `plan.md`. Cada tarea termina con sus pruebas en verde y un commit propio.

## Para quien implemente

- Leer antes `spec.md` y `plan.md` de esta carpeta. El contexto de diseño está en `contexto/flujo-documental-opcion-a.md` (pasos 1 y 2) y las reglas del proyecto, en `contexto/constitucion.md`.
- Los documentos de `contexto/` nombran `Documentos/clasificados/manifiesto.csv`, `matriz/` y documentos reales de oferentes. No están en el repo a propósito, porque traen datos personales, y no hacen falta para esta entrega. No buscarlos ni inventarlos.
- Solo documentos sintéticos, fabricados por las pruebas. No subir ningún PDF fuera de `tests/`.
- Nada de LLM ni de servicios de Azure en este código.
- Escribir en español: código con nombres en español, como en el contrato, y documentos en prosa.
- Si algo del plan no se puede hacer como está escrito, anotarlo en "Notas de implementación", al final de este archivo, y seguir con la alternativa más simple.

Dependencias del sistema: `libreoffice` (writer y calc) y Python 3.12 con `uv`. En Debian o Ubuntu: `apt-get install -y libreoffice-writer libreoffice-calc`.

## Tareas

- [x] **T01 — Contrato.** Escribir `contracts/modulo3-normalizacion/v0/`: `README.md`, `manifiesto.schema.json`, `lectura.schema.json` y `palabras.schema.json` (JSON Schema 2020-12), más ejemplos: una entrega con un normalizado, un duplicado, un error y un descartado, y una lectura con una página de cada tipo. Validar los ejemplos contra los esquemas, como en `contracts/modulo3-extraccion/v0/README.md`. **Detenerse aquí para revisión del usuario** antes de seguir (principio 5).
- [ ] **T02 — Esqueleto.** `servicios/normalizacion/` con `pyproject.toml` (uv, pytest), `__init__.py` con `VERSION = "0.1.0"`, `parametros.py`, `almacen.py` (interfaz y `AlmacenLocal`) y el comando `normalizar` que por ahora solo lista la entrega. Agregar la prueba que valida los ejemplos del contrato.
- [ ] **T03 — Fábrica de pruebas.** `tests/fabrica.py` con todos los casos de la tabla de pruebas del plan. Una prueba por caso que solo confirma que el archivo se fabricó.
- [ ] **T04 — Inventario.** Recorrido recursivo, descarte de archivos de sistema (por nombre y por contenido), SHA-256, duplicados por orden de ruta e `id_documento`. Requisitos R1 a R5.
- [ ] **T05 — Tipo real.** `tipos.py` con la tabla del plan. Incluye la extensión falsa y los no soportados. Requisito R6.
- [ ] **T06 — Revisión del PDF.** Abrir, reparar una vez, detectar contraseña y restricciones, contar páginas. Requisitos R11 a R13 y R16.
- [ ] **T07 — Conversión.** LibreOffice con perfil temporal y macros bloqueadas, con tiempo máximo y un reintento; imágenes con img2pdf, incluido el TIFF de varias páginas; Excel convertido y conservado como anexo. Requisitos R7 a R10.
- [ ] **T08 — Firma digital.** Firmante, fecha, integridad, formato y `leida`. Casos: íntegro, modificado después de firmar, sin firma. Requisito R15.
- [ ] **T09 — Lectura.** Texto, caracteres, cobertura de imagen (grilla de 200 × 200), rotación, tipo de página, origen del texto y archivo de palabras. Requisitos R14 y R18 a R20, R22 y R23.
- [ ] **T10 — Anclas.** `linea_firma`, `casilla` y `tabla_si_no`, según el plan. Requisito R21.
- [ ] **T11 — Entrega completa.** `entrega.py` une todo y escribe manifiesto, PDF, anexos, lecturas y palabras en el almacén. Aislamiento de errores (R17), errores de clase 4 relanzados al final, idempotencia y `--forzar`, y registros sin datos personales. Prueba de punta a punta con una entrega sintética que trae todos los casos, validada contra el contrato. Prueba de determinismo (R24 y R25, criterio A2).
- [ ] **T12 — Imagen del job.** `Dockerfile` (Python 3.12 slim, LibreOffice writer y calc, uv) que corre `normalizar`. Comprobar que las pruebas pasan dentro de la imagen.
- [ ] **T13 — Script de la muestra.** `scripts/medir_muestra.py <carpeta>`: corre `normalizar` sobre cada oferente de una carpeta e imprime solo conteos (páginas únicas, duplicados, restricciones, firmas, descartados, proporción de tipos de página y tiempo por oferente), para los criterios A3 a A5. No se corre en la nube: lo corre el usuario con la muestra real.

## Notas de implementación

### T01 — Contrato (2026-11-04)

Contrato escrito en `contracts/modulo3-normalizacion/v0/`, con los ejemplos validados. Queda a la espera de la revisión del usuario antes de T02.

**Dudas que el plan no resuelve.** El contrato las deja abiertas o sigue la lectura más literal del plan; hay que confirmarlas en la revisión:

1. **Campos del duplicado.** El plan dice que `pdf`, `lectura` y `paginas` apuntan a los del original, pero no dice qué pasa con `paginas_sin_texto`, `restricciones`, `firma_digital` y `anexo_nativo`. El esquema no lo restringe; el ejemplo copia los valores del original, siguiendo la idea de "que nadie tenga que seguir el enlace".
2. **Bytes de `ruta_origen` para `id_documento` y para ordenar.** No está fijada la codificación (¿UTF-8?) ni la normalización Unicode. Mac guarda los nombres con tildes en NFD y Windows en NFC, así que la misma entrega copiada desde otro equipo podría dar otros identificadores y otro orden (R5, R25). Los ejemplos usan UTF-8 sin normalizar.
3. **Documentos con error que no se pudieron abrir.** `restricciones` es booleano y `firma_digital` es una lista: en un PDF con contraseña no se sabe ni lo uno ni lo otro, pero el contrato obliga a poner `false` y `[]`, que se leen como "no tiene". Tampoco está claro si `SIN_PAGINAS` debe llevar `paginas: 0` o `null`; el esquema pide `null` en todo error.
4. **Descartados en el inventario.** R2 y la historia 1 hablan de un inventario con todos los archivos, "con su huella y su estado". El plan pone los descartados en una lista aparte, sin huella ni identificador. Se siguió el plan.
5. **Archivo de palabras sin versión.** El plan le da solo `{id_documento, paginas}`. Sin `contrato` ni `hash_pdf`, el archivo no dice por sí solo a qué versión ni a qué PDF corresponde (se sabe por la lectura que lo enlaza). Se siguió el plan.
6. **`ocr_propio`.** Está reservado, pero el plan dice que las páginas `imagen` llevan `origen_texto: null`. Si el experimento de OCR agrega texto a una página `imagen`, hay que decidir si cambia el tipo o la regla. En 0.1 el esquema exige `null` en `imagen` y `vacia`.
7. **PDF reparado.** Cuando se repara un PDF dañado, el plan solo lo anota en el registro. El manifiesto no dice que el normalizado es una copia reparada y no el original, lo que puede importar para la trazabilidad (principio 3).

**Decisiones que el plan no fijaba:**

- Todas las claves de cada entrada van siempre, con `null` o `[]` cuando no aplican, como en el contrato de extracción.
- Reglas por estado: `normalizado` exige `pdf`, `lectura` y `paginas`; `error_entrada` exige `error` y deja en `null` `pdf`, `anexo_nativo`, `lectura`, `paginas` y `duplicado_de`; `duplicado` exige `duplicado_de`. `anexo_nativo` solo puede tener valor en `xls`, `xlsx` y `ods`.
- Motivos de descarte: `archivo_sistema_mac` (`.DS_Store`, `__MACOSX/`, `._*`) y `archivo_sistema_windows` (`Thumbs.db`). El plan solo mostraba el primero. Un registro por archivo, ordenado por `ruta_origen`.
- En las anclas, `texto` va en `null` en una casilla. Las páginas `vacia` pueden tener anclas (por ejemplo, un formulario con casillas vacías); el plan solo las prohíbe en `imagen`.
- `rotacion` solo admite 0, 90, 180 o 270. `texto` es una cadena vacía cuando la página no tiene texto.
- El archivo de palabras trae todas las páginas, también las que no tienen palabras.
- Como los esquemas se refieren entre sí, el comando de validación del README los carga en un registro de `referencing`. T02 debe hacer lo mismo en su prueba.
