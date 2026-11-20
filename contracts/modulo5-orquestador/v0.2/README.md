# Contrato del módulo 5 — orquestador (v0.2, versión 0.2)

Las dos fronteras externas del orquestador en su entrega 1: el aviso que publica el módulo 1 cuando un proceso está listo, y la clasificación de cada documento con el clasificador del otro equipo. Sale de `specs/005-orquestador/spec.md` y `plan.md`; el diseño está en `contexto/flujo-documental-opcion-a.md`, pasos 0, 3 y 4.

Es una propuesta para llevar al módulo 1 (A-1) y a clasificación (C1 a C3). La frontera con la extracción es otro contrato: `contracts/modulo3-extraccion/v0.2/`. La versión anterior, 0.1, sigue en `../v0/` sin cambios.

## Cambios frente a la 0.1

Salen de la prueba de acceso a OneLake y de la revisión de las tablas del módulo 1 (`specs/005-orquestador/tasks-entrada-onelake.md`, T01 a T03). Solo cambia el aviso de proceso listo; la clasificación es igual y solo cambia el número de versión.

| Cambio en `proceso-listo` | Por qué |
|---|---|
| `id_proceso` es el evento de Ariba (`Doc…`) | Las tablas del módulo 1 no traen el SR, y el evento no cambia con sus versiones (decisión del usuario, 2026-11-20) |
| `id_proyecto`, opcional | El proyecto de Ariba (`WS…`) del evento, para guardarlo en el proceso |
| `tamano` y `md5` en cada archivo, opcionales | Para revisar cada archivo al bajarlo. El módulo 1 ya los registra (`downloaded_bytes`, `md5_hex`) |
| `comprimidos_sin_contenido`, opcional | Los ZIP y RAR no se bajan (decisión del usuario, 2026-11-18). Si el módulo 1 no pudo descomprimir uno, el aviso lo dice y el orquestador crea una tarea para el evaluador |
| `archivos` no lleva ZIP ni RAR | Van sus archivos descomprimidos, cada uno con su entrada |
| `ruta` con la forma del módulo 1 | `informacion-adjuntos/fase2/<event_id>`, por el shortcut del lakehouse |

Los campos nuevos son opcionales: un aviso 0.1 pasa a 0.2 cambiando solo `contrato`. Mientras el módulo 1 no publique el aviso, lo arma el orquestador con sus tablas (`servicios/orquestador/src/orquestador/entrada_modulo1.py`). La vista que prometió el módulo 1 debería traer justo estos datos.

## Archivos

| Archivo | Frontera | Qué es |
|---|---|---|
| `proceso-listo.schema.json` | Módulo 1 → orquestador | El aviso de que un proceso quedó completo en el datalake |
| `clasificacion-solicitud.schema.json` | Orquestador → clasificador | Un documento normalizado para clasificar |
| `clasificacion-respuesta.schema.json` | Clasificador → orquestador | Los segmentos de ese documento |
| `ejemplos/` | | Ejemplos que sirven como doble de prueba para los otros equipos |

Los ejemplos usan datos ficticios: el proceso `SR0000000001` y los oferentes `OF-001` a `OF-003`, o, en el ejemplo del módulo 1, el evento `Doc0000000001` y los oferentes `S0000001` y `S0000002`. Las huellas y los MD5 no corresponden a ningún archivo.

- `proceso-listo_sin_archivos.json`: el aviso mínimo. El orquestador lista la carpeta.
- `proceso-listo_con_archivos.json`: el aviso con la lista de archivos y su oferente; dos son del proceso.
- `proceso-listo_modulo1.json`: el aviso con la forma del módulo 1: evento y proyecto de Ariba, carpetas `Documentos del proceso/` y `Oferentes/`, archivos descomprimidos en `_contenido/`, tamaño y MD5, y un RAR sin contenido.
- `clasificacion-solicitud_of002.json`: una carta de presentación de 16 páginas.
- `clasificacion-respuesta_normal.json`: un documento, un segmento, confianza alta.
- `clasificacion-respuesta_compuesta.json`: la respuesta a la solicitud de ejemplo. El archivo trae carta, Cámara de Comercio, cédula y RUT, como la carta de BV en la muestra.
- `clasificacion-respuesta_dudosa.json`: confianza 0,82 en un TD con umbral 0,90. Se extrae y va a revisión.
- `clasificacion-respuesta_desempate.json`: un soporte de desempate (TD-98 con subtipo) y una hoja sin tipo (TD-99).
- `clasificacion-respuesta_invalida.json`: cumple el esquema, pero falta la página 7. El orquestador la rechaza (ver abajo).

## Aviso de proceso listo

- **Un aviso por proceso,** cuando están todos los documentos: los del proceso y los de todos los oferentes (decisión 34). Llega a la cola `procesos-listos` de Service Bus (decisión 33). Plan B, si el módulo 1 no puede publicar en Service Bus: un endpoint mínimo que deja este mismo mensaje en esa cola.
- **`ruta`** es la carpeta del proceso dentro de `Files` del lakehouse. Con el módulo 1 es `informacion-adjuntos/fase2/<event_id>`: los archivos están en su cuenta de ADLS y llegan por un shortcut. El orquestador lee de ahí con su identidad administrada y no copia los originales (decisión 32).
- **Con o sin `archivos`.** Si llega la lista, el orquestador reparte con ella y no lista nada; `id_oferente: null` marca los documentos del proceso. Si no llega, la carpeta debe traer `PROCESO/` y una subcarpeta por oferente, nombrada con su identificador. Cualquier otra cosa en la raíz se reporta a operación.
- **Sin ZIP ni RAR.** `archivos` trae lo descomprimido. Un comprimido que no se pudo descomprimir va en `comprimidos_sin_contenido`: no se baja, y el orquestador crea una tarea `documento_con_error` con motivo `COMPRIMIDO_SIN_CONTENIDO`.
- **`tamano` y `md5`.** Si llegan, el orquestador revisa cada archivo al bajarlo. Si no coincide, lo vuelve a bajar y, si sigue sin coincidir, el mensaje va a errores.
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
| Forma del aviso | A-1 | Si el módulo 1 puede publicar en Service Bus, o si arma la vista y el orquestador sigue armando el aviso |
| Identificadores | A-1 | Resuelto para el proceso (`event_id`) y los oferentes (`sm_vendor_id`). Falta: si un proyecto puede traer más de un evento a evaluar, y si hace falta el SR |
| Adjuntos tardíos | A-10 | Si un evento ya descargado puede recibir adjuntos nuevos |
| Transporte con el clasificador | C1 | Cola, HTTP asíncrono o síncrono |
| Equivalencia de TD | C2 | Tabla de identificadores firmada por los dos equipos |
| Uso de la lectura | A-5 | Si el clasificador pide otros campos |
| Nombres de los formatos del proceso | Paso 3 | En la entrega 2, cuando exista la ficha del proceso, la solicitud puede sumar los nombres que el proceso da a sus formatos ("Apéndice No. 3 = oferta económica") |

## Versionado

`contrato` lleva la versión (`modulo5-orquestador/0.2`). Mientras sea 0.x se puede cambiar de forma incompatible avisando a los equipos; cada versión nueva va en su propia carpeta. Desde la 1.0, un cambio incompatible exige una versión mayor nueva, sin editar la vigente (principio 5).

## Validar los ejemplos

Desde esta carpeta:

```bash
uv run -q --with jsonschema --with rfc3987 --with rfc3339-validator python3 -c "
import json, glob
from jsonschema import Draft202012Validator
for k in ('proceso-listo', 'clasificacion-solicitud', 'clasificacion-respuesta'):
    v = Draft202012Validator(json.load(open(f'{k}.schema.json')), format_checker=Draft202012Validator.FORMAT_CHECKER)
    for f in sorted(glob.glob(f'ejemplos/{k}_*.json')):
        v.validate(json.load(open(f)))
        print(f, 'OK')
"
```
