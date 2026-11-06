# Contrato del módulo 3 — extracción (versión 0.2)

Contrato entre el orquestador y la unidad de extracción documental. Reemplaza a la 0.1 (`../v0/`), que queda sin cambios como estaba (principio 5, decisión 25). Los dos lados son nuestros (decisión 6), pero el contrato se mantiene porque deja probar cada pieza por separado.

Sale de `contexto/flujo-documental-opcion-a.md`, paso 5 ("Cambios para el contrato 0.2"), y de `specs/005-orquestador/plan.md`. Lo esencial de la 0.1 sigue igual: una solicitud por segmento, páginas sobre el archivo completo, forma estable de cada resultado, `revision` calculada por la posvalidación y reglas de otros documentos o del proceso en `reglas_pendientes`.

Es una propuesta para revisar antes de escribir el código (principio 5).

## Archivos

| Archivo | Qué es |
|---|---|
| `entrada.schema.json` | La solicitud: un segmento (archivo + páginas + TD) |
| `salida.schema.json` | El resultado: sobre con estado, versiones, resultados por campo, alertas y ejecución |
| `ejemplos/` | Pares de entrada y salida que sirven como doble de prueba |

Los ejemplos de TD-16 y TD-29 son los de la 0.1 pasados a 0.2, con los mismos datos ficticios. Cambian los identificadores, se agregan los campos nuevos y, en TD-29, la solicitud llega con `clasificacion_dudosa: true`, así que la salida manda todos los campos a revisión con `CLASIFICACION_DUDOSA`. `entrada_td01_proceso.json` es una solicitud de las condiciones del proceso, sin oferente.

## Cambios frente a la 0.1

| # | Cambio | En el esquema |
|---|---|---|
| 1 | **Transporte por cola** | La solicitud llega por la cola `extraer` y el resultado sale por la cola `resultados`, las dos de Service Bus. Un mensaje = una solicitud o un resultado. Cierra O1 |
| 2 | **Referencia a la lectura** | Campo nuevo obligatorio `lectura`: URI de la lectura por página del paso 2 (`modulo3-normalizacion`). La extracción la usa en vez de volver a leer el PDF |
| 3 | **Excel nativo** | Campo nuevo obligatorio `anexos`: lista de URI, vacía si no hay. Hoy solo trae el `anexo_nativo` del manifiesto |
| 4 | **Clasificación dudosa** | Campo nuevo obligatorio `clasificacion_dudosa`. Si es `true`, todos los resultados salen con `revision: true` y el motivo nuevo `CLASIFICACION_DUDOSA`. El umbral lo aplica solo el orquestador |
| 5 | **Versión del proceso** | `version_modelo` sigue siendo opcional, pero si no llega se usa la registrada para el proceso, nunca la vigente. El orquestador la manda siempre |
| 6 | **Sin oferente** | `id_oferente` admite `null` para los documentos del proceso (condiciones, adendas) |
| 7 | **TD-98 no se envía** | `tipo_documental` rechaza TD-98 y TD-99 |
| 8 | **`forzar_reproceso`** | Igual que en 0.1; solo lo activa el comando `reprocesar` del orquestador, que registra quién y por qué |

Además, tres cambios que no estaban en la lista del diseño:

- **`id_segmento` e `id_documento`.** En 0.1, `id_documento` identificaba el segmento. Ahora el segmento se llama `id_segmento` (`<id_documento>-p<desde>-<hasta>`, lo arma el orquestador) e `id_documento` es el del archivo normalizado, el mismo del manifiesto. Así un resultado se cruza con su archivo sin partir el identificador. Va en la entrada y en la salida.
- **`id_oferente` obligatorio con `null`**, en vez de opcional: lo que no aplica va en `null`, como en el contrato de normalización, para que la forma sea siempre la misma.
- **`confianza_clasificacion` admite `null`**: cuando el tipo lo asignó una persona en una tarea de clasificación.

No entran al contrato la marca `subsanacion` ni el orden por precio: los lleva el orquestador y la extracción no los usa.

## Lo que falta definir

| Tema | Pregunta | Efecto en el contrato |
|---|---|---|
| Referencia al archivo | O2 | Forma final de las URI (Blob Storage con identidad administrada). Los ejemplos usan `https://cuenta.blob.core.windows.net/flujo/...` |
| Identificador de regla | R1 | `id_regla` sigue provisional (`<id_tecnico>.r<n>`) hasta la hoja Reglas (decisión 28) |
| Señal a clasificación | C4 | Si `no_corresponde` necesita llevar un TD sugerido |
| Caja por cita | P1 | Después de v0 |

## Versionado

`contrato` lleva la versión (`modulo3-extraccion/0.2`). Mientras sea 0.x se puede cambiar de forma incompatible avisando, pero cada versión nueva va en su propia carpeta y la anterior no se edita.

## Validar los ejemplos

Desde esta carpeta:

```bash
uv run -q --with jsonschema --with rfc3987 python3 -c "
import json, glob
from jsonschema import Draft202012Validator
for k in ('entrada', 'salida'):
    v = Draft202012Validator(json.load(open(f'{k}.schema.json')), format_checker=Draft202012Validator.FORMAT_CHECKER)
    for f in sorted(glob.glob(f'ejemplos/{k}_*.json')):
        v.validate(json.load(open(f)))
        print(f, 'OK')
"
```
