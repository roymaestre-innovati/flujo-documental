# Normalización: resultados de la medición con la muestra real

Fecha: 2026-11-05. Criterios A3 a A5 de la entrega 1 (iniciativa 003). Solo conteos: ningún nombre ni contenido de los documentos.

## Resumen

La normalización funciona con documentos reales: en 7 oferentes y 1.004 páginas no hubo fallas del programa. La proporción de tipos de página coincide con el diseño, así que los umbrales no cambian.

Quedan cuatro puntos abiertos: archivos comprimidos (ZIP y RAR) que el diseño no esperaba, PowerPoint sin soporte, tres formatos de firma que no se leen y un Excel que tarda 85 s en convertirse. Ninguno impide seguir; cada uno tiene una recomendación al final.

## Cómo se midió

Se corrió `scripts/medir_muestra.py` (normalizador 0.1.0, parámetros versión 1) en un portátil de trabajo, sin nube.

- **Muestra 1:** los 6 oferentes del proceso de referencia (OF-001 a OF-006).
- **Muestra 2:** un oferente más, medido aparte. En este documento se llama OF-007.
- **Antes:** las 387 pruebas automáticas pasaron en esta máquina, incluidas las de LibreOffice. Con documentos inventados el flujo completo también funcionó.
- **Máquina:** las pruebas tardan 2 min 56 s aquí, frente a 1 min 30 s en la referencia. Los tiempos de abajo pueden estar inflados por eso.

El detalle de firmas, comprimidos y tiempos sale de los manifiestos guardados, sin volver a procesar.

## Resultados frente al diseño

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

Las 451 páginas de la muestra 1 son un 9 % más que las 415 del diseño; la diferencia puede venir de las 5 hojas de Excel convertidas.

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

## Hallazgos

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
| `adbe.pkcs7.sha1` | 4 | Formato antiguo que pyHanko no valida (riesgo ya conocido) | Correcta: no leída |
| `adbe.pkcs7.detached` con el algoritmo mal declarado | 2 (OF-007) | El programa que firmó puso el algoritmo de firma donde va el de hash; pyHanko lo rechaza | No leída; Adobe probablemente la acepta |
| Sello de tiempo `ETSI.RFC3161` | 1 (OF-006) | No es una firma de persona: no tiene firmante | Hoy cuenta como firma no leída |
| CAdES no íntegra, OF-005 | 1 | El archivo se reescribió después de firmarse | Correcta: no íntegra |
| CAdES no íntegra, OF-006 | 1 | La parte firmada está intacta, pero cambios posteriores tocan la estructura interna del PDF | Posible falsa alarma |

### Conversión de Excel

En OF-007, un Excel de una sola página y menos de 1 MB tardó 85 s en convertirse. El límite es 120 s, así que no falló, pero un archivo un poco más pesado sí fallaría. Cada conversión arranca LibreOffice desde cero.

## Decisiones pendientes

Cada decisión trae primero la opción recomendada.

| Tema | Recomendación | Alternativa |
| --- | --- | --- |
| ZIP y RAR | Pedir al módulo 1 (pregunta A-1) que confirme que en producción todo llega descomprimido. Para la medición, descomprimir a mano lo que falta y repetir solo esos oferentes | Que el normalizador descomprima ZIP y RAR |
| PPTX | Convertirlos con LibreOffice, igual que los Word. Cambio pequeño | Dejarlos como `NO_SOPORTADO` y pedir subsanación en PDF |
| Excel de 85 s | Convertir solo ese archivo una vez, midiendo el tiempo, para ver qué lo frena (por ejemplo, vínculos externos) | Subir el límite de 120 s |
| Sello de tiempo `ETSI.RFC3161` | No contarlo como firma digital, porque no tiene firmante. Cambio pequeño del contrato 0.x | Dejarlo como firma no leída |
| Firmas con el algoritmo mal declarado | Dejarlas como no leídas y anotarlo. Si se repiten en otros oferentes, agregar la tolerancia | Tolerarlas desde ya |
| CAdES posiblemente falsa alarma (OF-006) | Dejarla como no íntegra: es lo prudente y el revisor la abre en Adobe | Aceptar cambios de estructura posteriores a la firma |

Siguen sin confirmar tres decisiones de la implementación: T10 (anclas de firma), T11 (manifiesto tras un bug) y T08 (firma sin firmante o fecha).

## Datos personales y siguientes pasos

La medición usó documentos reales antes de tener las respuestas de cumplimiento (HD-1 a HD-4 y HD-14 del checklist de habeas data). Todo se hizo en un portátil de trabajo, sin nube, y la salida del normalizador no trae nombres. Durante el diagnóstico de firmas, una herramienta auxiliar mostró en consola el nombre de un firmante; el normalizador no lo hace.

- [ ] Borrar las carpetas de salida con datos personales (`salida` y `salida1`)
- [ ] Pasar el checklist de habeas data a cumplimiento
- [ ] Preguntar al módulo 1 por los archivos comprimidos (A-1)
- [ ] Decidir los seis puntos de la tabla anterior
- [ ] Repetir la medición de OF-001, OF-002 y OF-007 con los comprimidos abiertos

Con eso se cierra la entrega 1. Después se elige entre la extracción (entrega 2), el orquestador (iniciativa 005) o las reglas e informe (módulo 4).
