# Contrato del módulo 3 — normalización y lectura (v0, versión 0.2)

Contrato de salida de la pieza que normaliza y lee una entrega: la carpeta de documentos de un oferente, o la del proceso (condiciones, adendas, anexos). Lo usan el clasificador (A-5), la unidad de extracción (cambio 2 del contrato 0.2) y el orquestador (iniciativa 005). Sale de `specs/003-validacion-extraccion/spec.md` y `plan.md`; el diseño está en `contexto/flujo-documental-opcion-a.md`, pasos 1 y 2.

Es una propuesta para revisar antes de escribir el código (principio 5).

## Archivos

| Archivo | Qué es |
|---|---|
| `manifiesto.schema.json` | El inventario de la entrega: una entrada por archivo, con su huella, su estado y los enlaces al PDF y a la lectura, más la lista de archivos de sistema descartados |
| `lectura.schema.json` | La lectura por página de un PDF normalizado: tipo de página, texto, origen del texto, cobertura de imagen, rotación y zonas visuales (anclas) |
| `palabras.schema.json` | Las palabras de cada página con su posición, en un archivo aparte porque pesa |
| `ejemplos/` | Ejemplos que sirven como doble de prueba para los otros equipos |

Los ejemplos usan datos ficticios: el proceso `SR0000000001`, el oferente `OF-002` (`OFERENTE EJEMPLO LTDA`), nombres de persona inventados y huellas que no corresponden a ningún archivo. Las posiciones de las palabras son ilustrativas.

- `manifiesto_of002.json`: una entrega con un documento normalizado (`carta_presentacion.pdf`, con firma digital), una copia exacta de ese documento en otra carpeta, un PDF que pide contraseña y un archivo `._*` de Mac descartado.
- `lectura_of002_carta.json`: la lectura del documento normalizado, con una página de cada tipo (`texto`, `escaneo_con_ocr`, `imagen` y `vacia`) y anclas de los tres tipos en la primera.
- `palabras_of002_carta.json`: las palabras de ese mismo documento.

## Salida en el almacén

Los enlaces (`pdf`, `anexo_nativo`, `lectura`, `palabras`) son URI. En esta versión el almacén es una carpeta local con URI `file://`; la forma final depende de A-1.

```
<salida>/<id_proceso>/<id_oferente o PROCESO>/
  manifiesto.json
  pdf/<id_documento>.pdf
  anexos/<id_documento>.<ext>
  lectura/<id_documento>.json
  palabras/<id_documento>.json
```

## Lo que el contrato fija

- **Forma estable.** Cada entrada lleva siempre las mismas claves; lo que no aplica va en `null` o en una lista vacía.
- **Un estado por archivo.** `normalizado`, `duplicado` o `error_entrada`. Los archivos de sistema no son documentos: van en `descartados`, con su ruta y su motivo, sin huella ni identificador.
- **Qué lleva cada estado.**
  - `normalizado`: `pdf`, `lectura` y `paginas` con valor; `duplicado_de` y `error` en `null`.
  - `duplicado`: `duplicado_de` con el `id_documento` del original (el primero por orden de ruta). Repite todos los datos del original (`pdf`, `anexo_nativo`, `lectura`, `paginas`, `paginas_sin_texto`, `restricciones`, `firma_digital` y `reparado`), para no tener que seguir el enlace; solo cambian `id_documento`, `ruta_origen`, `estado` y `duplicado_de`. La copia no se procesa ni se borra.
  - `error_entrada`: `error` con su código; `pdf`, `anexo_nativo`, `lectura`, `paginas` y `duplicado_de` en `null`, y `paginas_sin_texto` vacía. `restricciones` y `firma_digital` van en `null`, que quiere decir "no se sabe": el documento no se pudo abrir. Un error no frena a los demás documentos.
- **`anexo_nativo` solo en hojas de cálculo** (`xls`, `xlsx`, `ods`): es el archivo original, que la extracción lee como tabla.
- **Rutas en NFC.** `ruta_origen` se guarda normalizada a Unicode NFC. Mac y Windows escriben las tildes de forma distinta, y así la misma entrega da las mismas rutas e identificadores venga de donde venga.
- **Orden.** `archivos` y `descartados` van ordenados por `ruta_origen` (por punto de código, ya en NFC), y `paginas` en orden, una por página, sin saltos. Con esto, dos corridas sobre la misma entrega dan el mismo manifiesto y la misma lectura, salvo `ejecucion` (R25).
- **Páginas sobre el documento completo**, contadas desde 1, igual que en el contrato de extracción.
- **`id_documento` estable** entre corridas (R5): `<id_oferente o PROCESO>-<primeros 12 hex del SHA-256 de ruta_origen>`, con la ruta en UTF-8 y NFC. Depende de la ruta y no del contenido, así dos copias del mismo archivo tienen identificadores distintos. Es provisional hasta A-1: si el módulo 1 da identificadores, se usan los suyos.
- **PDF reparado.** `reparado` es `true` cuando el PDF del oferente llegó dañado y el normalizado es una copia reparada (R12). Así el evaluador sabe que las páginas que ve salen de una reparación. Solo puede ser `true` en un `pdf`.
- **`hash_pdf`** en la lectura es la huella del PDF que se leyó. Cuando el PDF del oferente se usa tal cual (R11), coincide con `hash` del manifiesto.
- **Tipo de página y origen del texto.** `texto` va con `nativo`, `escaneo_con_ocr` con `ocr_escaner`, e `imagen` y `vacia` con `null`. `ocr_propio` está reservado para el experimento de OCR y no se produce en 0.1.
- **`paginas_sin_texto`** son las páginas con 0 caracteres. No es lo mismo que las páginas de tipo `imagen`.
- **Anclas.** `linea_firma`, `casilla` y `tabla_si_no`. `texto` es el rótulo o la línea que dio lugar al ancla, y va en `null` en una casilla. Las páginas `imagen` no tienen anclas.
- **Cajas.** `[x0, y0, x1, y1]` en puntos PDF, con el origen arriba a la izquierda y sobre la página sin rotar.
- **Firma digital.** Por firma: `firmante`, `fecha`, `integro`, `formato` y `leida`. Si `leida` es `false`, hay una firma que no se pudo leer, y `firmante`, `fecha` e `integro` van en `null`. Una firma sin leer no es error del documento. No se valida la confianza del certificado. Un sello de tiempo del documento (`/DocTimeStamp`, formato `ETSI.RFC3161`) no va en la lista: no tiene firmante, así que no es una firma de persona.
- **Errores.** El error llega al evaluador por medio del orquestador, como una tarea "documento con error", y él decide si pide subsanación por Ariba. Por eso `detalle` dice qué pasó y qué pedirle al oferente, sin que el evaluador tenga que abrir el archivo. Nunca lleva texto del documento.

  | Código | Qué pasó | Ejemplo de `detalle` |
  |---|---|---|
  | `CONTRASENA` | El PDF pide contraseña para abrirse | El PDF pide contraseña para abrirse. Si se pide subsanación, el oferente debe entregarlo sin contraseña. |
  | `DANADO` | El archivo no abre y no se pudo reparar | El archivo está dañado y no se pudo reparar. Si se pide subsanación, el oferente debe entregarlo de nuevo. |
  | `SIN_PAGINAS` | El documento abre pero no tiene páginas | El documento no tiene páginas. Si se pide subsanación, el oferente debe entregarlo de nuevo. |
  | `NO_SOPORTADO` | El tipo de archivo no se puede leer | El tipo de archivo no se puede leer. Si se pide subsanación, el oferente debe entregarlo en PDF. |
  | `CONVERSION_FALLIDA` | El Word, Excel, PowerPoint o imagen no se pudo pasar a PDF | No se pudo convertir el archivo a PDF. Si se pide subsanación, el oferente debe entregarlo en PDF. |
- **Motivos de descarte.** `archivo_sistema_mac` (`.DS_Store`, todo lo que está dentro de `__MACOSX` y los archivos `._*`) y `archivo_sistema_windows` (`Thumbs.db`). Un registro por archivo.
- **Trazabilidad.** El manifiesto y la lectura llevan `version_normalizador` y `version_parametros` (R24).

## Lo que falta definir

| Tema | Pregunta | Efecto en el contrato |
|---|---|---|
| Almacén e identificadores | A-1 | Forma de las URI y de `id_documento` |
| Lectura para el clasificador | A-5 | Si el clasificador la usa, puede pedir campos nuevos |
| OCR propio | Decisión 9 | Cómo se marca una página `imagen` a la que el experimento le agrega texto |

Las dudas sobre este borrador están en "Notas de implementación" de `specs/003-validacion-extraccion/tasks.md`.

## Versionado

`contrato` lleva la versión (`modulo3-normalizacion/0.2`). Mientras sea 0.x se puede cambiar de forma incompatible avisando a los equipos. Desde la 1.0, un cambio incompatible exige una versión mayor nueva, sin editar la vigente (principio 5).

Cambios:

- **0.2 (2026-11-05):** `tipo_origen` suma `ppt`, `pptx` y `odp`. Las presentaciones se convierten a PDF, una página por diapositiva, sin anexo; las notas del orador no salen. Un consumidor que valide contra 0.1 rechazaría esos valores, por eso sube la versión. `version_normalizador` pasa a `0.2.0`.

- **Normalizador 0.3.0, parámetros 2 (2026-11-10), sin cambio del contrato:** una página sin texto y sin imagen grande que tiene tinta al dibujarla (por ejemplo, texto convertido en curvas) ahora es `imagen` y no `vacia`. El esquema no cambia; los ejemplos llevan las versiones nuevas.

Cambios dentro de 0.1, antes de que nadie lo use:

- 2026-11-04, revisión del borrador: el duplicado repite todos los datos del original; rutas en NFC; `restricciones` y `firma_digital` en `null` cuando el documento no abre; campo nuevo `reparado`; `detalle` con lo que hay que pedir al oferente.
- 2026-11-05, después de medir la muestra real: los sellos de tiempo del documento no se cuentan en `firma_digital`. El esquema no cambia.

## Validar los ejemplos

Los esquemas se refieren entre sí (la lectura usa la firma del manifiesto, y las palabras usan la caja de la lectura), así que se cargan juntos en un registro:

```bash
uv run -q --with jsonschema python3 -c "
import json, glob
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
esquemas = {k: json.load(open(f'{k}.schema.json')) for k in ('manifiesto', 'lectura', 'palabras')}
registro = Registry().with_resources(
    (f'modulo3-normalizacion/v0/{k}.schema.json', Resource.from_contents(s)) for k, s in esquemas.items())
for k, s in esquemas.items():
    v = Draft202012Validator(s, registry=registro, format_checker=Draft202012Validator.FORMAT_CHECKER)
    for f in sorted(glob.glob(f'ejemplos/{k}_*.json')):
        v.validate(json.load(open(f)))
        print(f, 'OK')
"
```
