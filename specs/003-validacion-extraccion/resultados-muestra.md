# Normalización: resultados de la medición con la muestra real

Fecha: 2026-11-05. Criterios A3 a A5 de la entrega 1 (iniciativa 003). Solo conteos: ningún nombre ni contenido de los documentos.

**Entrega 1 cerrada.** Hubo dos mediciones: la primera con el normalizador 0.1.0 y la segunda con el 0.2.0, después de las tareas T14 a T16 que salieron de la primera.

## Resumen

La normalización funciona con documentos reales: en 7 oferentes y 1.034 páginas no hubo fallas del programa. La proporción de tipos de página coincide con el diseño, así que los umbrales no cambian.

La primera medición dejó cuatro hallazgos. Se resolvieron así: los ZIP y RAR fueron un error al armar la carpeta de prueba (en producción no llegan); los PowerPoint ahora se convierten (T15); el sello de tiempo ya no cuenta como firma (T14); y el Excel lento se debía a 201 vínculos a otros libros, que ahora se quitan antes de convertir (T16). La segunda medición lo confirma.

## Cómo se midió

Se corrió `scripts/medir_muestra.py` (normalizador 0.1.0, parámetros versión 1) en un portátil de trabajo, sin nube.

- **Muestra 1:** los 6 oferentes del proceso de referencia (OF-001 a OF-006).
- **Muestra 2:** un oferente más, medido aparte. En este documento se llama OF-007.
- **Antes:** las 387 pruebas automáticas pasaron en esta máquina, incluidas las de LibreOffice. Con documentos inventados el flujo completo también funcionó.
- **Máquina:** las pruebas tardan 2 min 56 s aquí, frente a 1 min 30 s en la referencia. Los tiempos de abajo pueden estar inflados por eso.

El detalle de firmas, comprimidos y tiempos sale de los manifiestos guardados, sin volver a procesar.

## Resultados frente al diseño (primera medición)

### A3. Conteos

La muestra 1 se parece a la que suponía el diseño: los PDF con restricciones son exactamente 15 y las copias y firmas difieren en uno. OF-007 es otro perfil: un solo oferente con más páginas que toda la muestra del diseño y muchos archivos de Office.

| Medida | Muestra 1 (6 oferentes) | Muestra 2 (OF-007) | Diseño |
| --- | --- | --- | --- |
| Páginas únicas | 451 | 553 | unas 415 |
| Copias exactas | 8 | 1 | 9 |
| PDF con restricciones | 15 | 0 | 15 |
| PDF con firma digital | 6 | 13 | 7 |
| Firmas leídas / no leídas / no íntegras | 3 / 4 / 2 | 10 / 3 / 0 | — |
| Descartados (archivos de sistema de Mac) | 23 | 0 | — |
| Con error `NO_SOPORTADO` | 12 (8 ZIP, 4 RAR) | 3 (1 RAR, 2 PPTX) | — |
| Convertidos a PDF | 5 (5 Excel) | 14 (8 Word, 6 Excel) | — |
| Reparados | 0 | 0 | — |

Las 451 páginas de la muestra 1 son un 9 % más que las 415 del diseño. Los 5 Excel convertidos solo suman 6 páginas, así que no lo explican; puede ser que el conteo del diseño se hiciera de otra forma. Un ZIP de OF-001 traía 3 PDF que no estaban sueltos en la carpeta y no se midieron, y los RAR de OF-002 no se abrieron: los conteos de esos dos oferentes quedan un poco cortos.

### A4. Tipos de página

En la muestra 1 la proporción coincide con el diseño con 2 puntos de diferencia o menos. OF-007 tiene más texto porque trae muchos Word y Excel, que al convertirse siempre dan páginas de texto.

| Tipo de página | Muestra 1 | OF-007 | Total | Diseño |
| --- | --- | --- | --- | --- |
| texto | 350 (78 %) | 505 (91 %) | 855 (85 %) | 76 % |
| escaneo_con_ocr | 48 (11 %) | 25 (5 %) | 73 (7 %) | 11 % |
| imagen | 28 (6 %) | 12 (2 %) | 40 (4 %) | 8 % |
| vacia | 25 (6 %) | 11 (2 %) | 36 (4 %) | 5 % |

Los umbrales (20 caracteres, 80 % de cobertura) quedan como están y `version_parametros` sigue en 1.

### A5. Tiempo por oferente

Solo OF-007 pasa de lejos el minuto que espera el diseño: 310 s para 553 páginas.

| Oferente | Segundos | Páginas |
| --- | --- | --- |
| OF-001 | 19,3 | 56 |
| OF-002 | 18,7 | 60 |
| OF-003 | 28,2 | 74 |
| OF-004 | 39,1 | 123 |
| OF-005 | 60,8 | 109 |
| OF-006 | 5,0 | 29 |
| OF-007 | 309,7 | 553 |

En los PDF el ritmo es parejo, unos 0,3 s por página. De los 310 s de OF-007, 156 s son PDF, 21 s son Word y 134 s son Excel, casi todo en dos archivos (85 s y 37 s). El promedio de los 7 oferentes es de unos 69 s.

## Segunda medición (normalizador 0.2.0)

Después de T14 a T16 se repitió la medición de las dos muestras. Todo cambió como se esperaba:

| Medida | Primera (0.1.0) | Segunda (0.2.0) |
| --- | --- | --- |
| Muestra 1, firmas leídas / no leídas / no íntegras | 3 / 4 / 2 | 3 / 3 / 2 |
| Muestra 1, tiempo total | 171 s | 117 s |
| Muestra 1, oferente más lento | 61 s | 43 s |
| OF-007, errores `NO_SOPORTADO` | 3 (1 RAR, 2 PPTX) | 1 (el RAR) |
| OF-007, convertidos a PDF | 14 | 16 |
| OF-007, páginas | 553 | 583 |
| OF-007, tiempo | 310 s | 149 s |

El resto de los conteos de la muestra 1 no cambió (451 páginas, 8 copias, 15 PDF con restricciones, 6 con firma digital, misma proporción de tipos de página).

Los tiempos bajaron más de lo que explica T16: la muestra 1 también bajó un 32 %, y ahí T16 casi no influye. La primera corrida se hizo con la máquina más cargada. Lo que sí se debe a T16 son unos 80 s de OF-007, medidos archivo por archivo (el Excel de 201 vínculos pasó de 64 s a 1,9 s, y el de 47 páginas de 22 s a 3,3 s).

En OF-007, de las 30 páginas de PowerPoint, 25 quedaron como `texto`, 4 como `escaneo_con_ocr` y 1 como `vacia`. Las 4 son, seguramente, diapositivas con una imagen grande de fondo y texto encima: cubren más del 80 % de la página y parecen un escaneo. El texto se lee bien; solo la etiqueta es imprecisa. Queda para calibrar.

## Hallazgos de la primera medición

### Archivos comprimidos

El diseño supone que los archivos llegan descomprimidos (confirmado en su momento), pero en las carpetas medidas hay 8 ZIP y 5 RAR. Los ZIP y RAR no se procesan: quedan como `NO_SOPORTADO`.

| Carpeta | Archivo | Archivos dentro | Ya están sueltos en la carpeta |
| --- | --- | --- | --- |
| OF-001 | ZIP | 5 | 5 |
| OF-001 | ZIP | 3 PDF | 0 |
| OF-002 | 4 RAR | sin revisar | sin revisar |
| OF-003 | 2 ZIP | 19 | 19 |
| OF-005 | ZIP | 5 | 5 |
| OF-006 | 3 ZIP | 7 | 7 |
| OF-007 | RAR | sin revisar | sin revisar |

En 7 de los 8 ZIP no se pierde nada: el oferente dejó el ZIP junto a su contenido. Un ZIP de OF-001 trae 3 PDF que no entraron en la medición. Los RAR no se pudieron abrir en esta máquina.

### PowerPoint

OF-007 entregó 2 archivos PPTX, que hoy quedan como `NO_SOPORTADO`. El handoff ya los listaba como formato a vigilar.

### Firmas digitales

De 20 firmas en documentos normalizados, se leyeron 13: 11 íntegras y 2 no íntegras. Las que no se leen o salen no íntegras tienen causas distintas:

| Caso | Cuántas | Causa | Lectura |
| --- | --- | --- | --- |
| `adbe.pkcs7.sha1` | 4 (3 en la muestra 1, las de Cámara de Comercio y RUP; 1 en OF-007) | Formato antiguo que pyHanko no valida (riesgo ya conocido) | Correcta: no leída |
| `adbe.pkcs7.detached` con el algoritmo mal declarado | 2 (OF-007) | El programa que firmó puso el algoritmo de firma donde va el de hash; pyHanko lo rechaza | No leída; Adobe probablemente la acepta |
| Sello de tiempo `ETSI.RFC3161` | 1 (OF-006) | No es una firma de persona: no tiene firmante. El mismo PDF trae una firma CAdES, así que sigue contando como PDF firmado | Ya no cuenta como firma (T14) |
| CAdES no íntegra, OF-005 | 1 | El archivo se reescribió después de firmarse | Correcta: no íntegra |
| CAdES no íntegra, OF-006 | 1 | La parte firmada está intacta, pero cambios posteriores tocan la estructura interna del PDF | Posible falsa alarma |

### Conversión de Excel

En OF-007, un Excel de una sola página y menos de 1 MB tardó 85 s en convertirse. El límite es 120 s, así que no falló, pero un archivo un poco más pesado sí fallaría. Cada conversión arranca LibreOffice desde cero.

## Decisiones tomadas

Revisadas una por una con el usuario el 2026-11-05:

| Tema | Decisión |
| --- | --- |
| ZIP y RAR | No se toca el código: fueron un error al armar la carpeta de prueba, y en la versión final no llegan comprimidos |
| PowerPoint | Se convierte con LibreOffice (T15). El contrato sube a `modulo3-normalizacion/0.2` |
| Excel lento | Se diagnosticó (201 vínculos a otros libros) y se quitan antes de convertir (T16) |
| Sello de tiempo `ETSI.RFC3161` | No se cuenta como firma (T14) |
| Firmas con el algoritmo mal declarado | Quedan como no leídas; se agrega la tolerancia si se repiten en más oferentes |
| CAdES de OF-006 | Queda no íntegra; el revisor la abre en Adobe |

## Datos personales

Las mediciones usaron documentos reales antes de tener las respuestas de cumplimiento (HD-1 a HD-4 y HD-14 del checklist de habeas data). Todo se hizo en un portátil de trabajo, sin nube, y la salida del normalizador no trae nombres. Durante el diagnóstico de firmas, una herramienta auxiliar mostró en consola el nombre de un firmante; el normalizador no lo hace. La segunda medición no guardó salidas: fueron a una carpeta temporal que se borró sola.

- [ ] Borrar las carpetas de salida de la primera medición (`salida` y `salida1`)
- [ ] Pasar el checklist de habeas data a cumplimiento, contando lo de arriba
