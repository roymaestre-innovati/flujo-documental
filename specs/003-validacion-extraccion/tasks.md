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

- [ ] **T01 — Contrato.** Escribir `contracts/modulo3-normalizacion/v0/`: `README.md`, `manifiesto.schema.json`, `lectura.schema.json` y `palabras.schema.json` (JSON Schema 2020-12), más ejemplos: una entrega con un normalizado, un duplicado, un error y un descartado, y una lectura con una página de cada tipo. Validar los ejemplos contra los esquemas, como en `contracts/modulo3-extraccion/v0/README.md`. **Detenerse aquí para revisión del usuario** antes de seguir (principio 5).
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

(Vacío.)
