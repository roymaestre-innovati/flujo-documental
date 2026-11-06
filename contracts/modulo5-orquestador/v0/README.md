# Contrato del módulo 5 — orquestador (v0, versión 0.1)

Las dos fronteras externas del orquestador en su entrega 1: el aviso que publica el módulo 1 cuando un proceso está listo, y la clasificación de cada documento con el clasificador del otro equipo. Sale de `specs/005-orquestador/spec.md` y `plan.md`; el diseño está en `contexto/flujo-documental-opcion-a.md`, pasos 0, 3 y 4.

Es una propuesta para revisar antes de escribir el código (principio 5) y para llevar al módulo 1 (A-1) y a clasificación (C1 a C3). La frontera con la extracción es otro contrato: `contracts/modulo3-extraccion/v0.2/`.

## Archivos

| Archivo | Frontera | Qué es |
|---|---|---|
| `proceso-listo.schema.json` | Módulo 1 → orquestador | El aviso de que un proceso quedó completo en el datalake |
| `clasificacion-solicitud.schema.json` | Orquestador → clasificador | Un documento normalizado para clasificar |
| `clasificacion-respuesta.schema.json` | Clasificador → orquestador | Los segmentos de ese documento |
| `ejemplos/` | | Ejemplos que sirven como doble de prueba para los otros equipos |

Los ejemplos usan datos ficticios: el proceso `SR0000000001` y los oferentes `OF-001` a `OF-003`. Las huellas no corresponden a ningún archivo.

- `proceso-listo_sin_archivos.json`: el aviso mínimo. El orquestador lista la carpeta.
- `proceso-listo_con_archivos.json`: el aviso con la lista de archivos y su oferente; dos son del proceso.
- `clasificacion-solicitud_of002.json`: una carta de presentación de 16 páginas.
- `clasificacion-respuesta_normal.json`: un documento, un segmento, confianza alta.
- `clasificacion-respuesta_compuesta.json`: la respuesta a la solicitud de ejemplo. El archivo trae carta, Cámara de Comercio, cédula y RUT, como la carta de BV en la muestra.
- `clasificacion-respuesta_dudosa.json`: confianza 0,82 en un TD con umbral 0,90. Se extrae y va a revisión.
- `clasificacion-respuesta_desempate.json`: un soporte de desempate (TD-98 con subtipo) y una hoja sin tipo (TD-99).
- `clasificacion-respuesta_invalida.json`: cumple el esquema, pero falta la página 7. El orquestador la rechaza (ver abajo).

## Aviso de proceso listo

- **Un aviso por proceso,** cuando están todos los documentos: los del proceso y los de todos los oferentes (decisión 34). Llega a la cola `procesos-listos` de Service Bus (decisión 33). Plan B, si el módulo 1 no puede publicar en Service Bus: un endpoint mínimo que deja este mismo mensaje en esa cola.
- **`ruta`** es la carpeta del proceso dentro de `Files` del lakehouse. El orquestador lee de ahí con su identidad administrada y no copia los originales (decisión 32).
- **Con o sin `archivos`.** Si llega la lista, el orquestador reparte con ella y no lista nada; `id_oferente: null` marca los documentos del proceso. Si no llega, la carpeta debe traer `PROCESO/` y una subcarpeta por oferente, nombrada con su identificador. Cualquier otra cosa en la raíz se reporta a operación.
- **Repetir el aviso no repite el trabajo.** El orquestador abre el proceso una sola vez por `id_proceso`.
- **Los archivos no cambian después del aviso.** Si hay que corregir algo, es un aviso nuevo, y eso está en pausa (A-10).

## Clasificación

- **Una solicitud por documento normalizado** (decisión 11). Las copias exactas no se mandan.
- **Se clasifica el PDF normalizado,** con su paginación (C3). La solicitud trae su huella para confirmar que es el mismo.
- **`ruta_origen`** incluye las carpetas y el nombre con que lo entregó el oferente. Sirve para reconocer, por ejemplo, los soportes de desempate ("EMPRENDIMIENTO MUJERES").
- **`lectura`** es la lectura por página de la normalización: texto, tipo de página y anclas. El clasificador decide si la usa (A-5).
- **`version_ontologia`** es la fijada para el proceso. Todos los documentos del proceso se clasifican con la misma (principio 7), y la respuesta dice cuál usó.
- **Lo que no es de ningún tipo va como TD-99**, no se omite. Los soportes de desempate van como TD-98 con su subtipo (`discapacidad`, `personas_mayores`, `mipyme`, `emprendimiento_mujeres` u `otro`), si clasificación lo acepta (A-7).

**Lo que revisa el orquestador además del esquema:**

1. Los segmentos van en orden y cubren de la página 1 a la última, sin huecos ni solapes.
2. Cada `tipo_documental` existe en la matriz (TD-01 a TD-35, TD-98 y TD-99).
3. `id_documento` y `version_ontologia` coinciden con los de la solicitud.

Si algo falla, pide la clasificación una vez más; si vuelve a fallar, crea una tarea de clasificación para el evaluador.

**Qué hace el orquestador con cada segmento** (decisión 12), con el umbral del TD fijado para el proceso:

| Confianza | Qué pasa |
|---|---|
| Desde el umbral del TD | Se extrae |
| Entre 0,75 y el umbral | Se extrae con `clasificacion_dudosa: true`; todo el documento va a revisión |
| Menos de 0,75 | No se extrae: tarea de clasificación |
| TD-98 o TD-99 | No se extrae: queda en el inventario del oferente |

## Lo que falta definir

| Tema | Pregunta | Efecto en el contrato |
|---|---|---|
| Forma del aviso | A-1 | Si el módulo 1 puede publicar en Service Bus, si manda la lista de archivos y cómo organiza las carpetas |
| Identificadores | A-1 | Si `id_proceso` y los de oferente son los de Ariba |
| Transporte con el clasificador | C1 | Cola, HTTP asíncrono o síncrono |
| Equivalencia de TD | C2 | Tabla de identificadores firmada por los dos equipos |
| Uso de la lectura | A-5 | Si el clasificador pide otros campos |
| Nombres de los formatos del proceso | Paso 3 | En la entrega 2, cuando exista la ficha del proceso, la solicitud puede sumar los nombres que el proceso da a sus formatos ("Apéndice No. 3 = oferta económica") |

## Versionado

`contrato` lleva la versión (`modulo5-orquestador/0.1`). Mientras sea 0.x se puede cambiar de forma incompatible avisando a los equipos; cada versión nueva va en su propia carpeta. Desde la 1.0, un cambio incompatible exige una versión mayor nueva, sin editar la vigente (principio 5).

## Validar los ejemplos

Desde esta carpeta:

```bash
uv run -q --with jsonschema --with rfc3987 python3 -c "
import json, glob
from jsonschema import Draft202012Validator
for k in ('proceso-listo', 'clasificacion-solicitud', 'clasificacion-respuesta'):
    v = Draft202012Validator(json.load(open(f'{k}.schema.json')), format_checker=Draft202012Validator.FORMAT_CHECKER)
    for f in sorted(glob.glob(f'ejemplos/{k}_*.json')):
        v.validate(json.load(open(f)))
        print(f, 'OK')
"
```
