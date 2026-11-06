# Contrato del módulo 3 — extracción (v0, borrador 0.1)

> **Reemplazada por la 0.2** (`../v0.2/`), que es la que usa el orquestador. Esta carpeta queda como estaba (principio 5).

Contrato entre el orquestador y la unidad de extracción documental. Es una propuesta del equipo de extracción para discutir con orquestación, clasificación, el módulo 1 y el módulo 4. Las decisiones que lo sustentan están en `contexto/refinamiento-grill-me-2.md` (D1 a D24).

## Archivos

| Archivo | Qué es |
|---|---|
| `entrada.schema.json` | La solicitud: un segmento (archivo + páginas + TD) |
| `salida.schema.json` | El resultado: sobre con estado, versiones, resultados por campo, alertas y ejecución |
| `ejemplos/` | Pares de entrada y salida que sirven como doble de prueba para los otros equipos |

Los ejemplos de TD-16 y TD-29 salen de corridas reales del modelo v17 (proceso SR5658940621). Tienen los nombres, documentos, NIT y entidades reemplazados, y la posvalidación aplicada a mano tal como la define el contrato. La firma de TD-29 muestra el resultado con el recorte ampliado (D20); sin el recorte, el agente decía `NO`.

## Lo que el contrato fija

- **Una solicitud = un segmento.** Si un PDF trae varios documentos, llegan varias solicitudes.
- **Páginas sobre el archivo completo.** Las páginas de la entrada y de la evidencia se cuentan sobre el PDF completo, que es el mismo que clasificó el clasificador.
- **`version_modelo` fija por proceso.** La manda el orquestador. Si no llega, se usa la vigente y se devuelve en la salida.
- **Forma estable de cada resultado.** Las mismas claves siempre, sin campos que aparecen o desaparecen.
- **`cumple` evalúa solo las reglas de ámbito documento.** Las reglas que necesitan otro documento o un parámetro del proceso van en `reglas_pendientes`, para el módulo 4. Esas reglas pendientes no mandan el campo a revisión.
- **`revision` y `motivos` los calcula la posvalidación**, no el agente. Si `revision` es `true`, hay al menos un motivo, y si es `false`, no hay ninguno.
- **Los campos `Calculado` no salen aquí:** son del módulo 4.

## Lo que falta definir

| Tema | Pregunta | Efecto en el contrato |
|---|---|---|
| Transporte | O1 | Si la llamada es HTTP asíncrona, se agregan `POST /extracciones` → 202 + `id` y `GET /extracciones/{id}`. Si es cola, los nombres de las colas. |
| Referencia al archivo | O2 | Forma final de `archivo` (URI con managed identity, SAS u otra) |
| Identificador de regla | R1 | `id_regla` hoy es provisional (`<id_tecnico>.r<n>`). Hace falta partir las reglas de la matriz en reglas atómicas con ámbito. |
| Señal a clasificación | C4 | Si `no_corresponde` necesita llevar un TD sugerido |
| Bounding box | P1 | Si se agrega una caja por cita en `evidencia` |

## Versionado

`contrato` lleva la versión (`modulo3-extraccion/0.1`). Mientras sea 0.x se puede cambiar de forma incompatible avisando a los equipos. Desde la 1.0, un cambio incompatible exige una versión mayor nueva, sin editar la vigente (principio 5).

## Validar los ejemplos

```bash
uv run -q --with jsonschema python3 -c "
import json, glob, jsonschema
for k in ('entrada', 'salida'):
    s = json.load(open(f'{k}.schema.json'))
    for f in sorted(glob.glob(f'ejemplos/{k}_*.json')):
        jsonschema.validate(json.load(open(f)), s)
        print(f, 'OK')
"
```
