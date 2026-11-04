# Checklist de habeas data — Módulo 3 (validación y extracción documental)

Estado al 2026-11-04. Borrador del equipo técnico para revisión de cumplimiento.

Lo pide el principio 6 de la constitución: antes de procesar documentos reales de oferentes, se revisa el cumplimiento de la Ley 1581 de 2012 (protección de datos personales, o habeas data) y sus decretos reglamentarios.

## Para quien revisa

- **Qué es este documento.** Una lista de preguntas sobre cómo el módulo 3 trata los datos personales que vienen en los documentos de los oferentes. En cada punto, el equipo técnico dice qué hace hoy el sistema, con la fuente de la que sale, y deja marcado lo que tiene que decidir cumplimiento.
- **Qué no es.** No es un concepto jurídico. El equipo técnico describe el sistema; la valoración legal es de cumplimiento.
- **Alcance.** La entrega 1 del módulo 3, normalización y lectura, ya construida y probada solo con documentos inventados. Al final hay una sección con lo que agrega la extracción (entrega 2), que todavía no se construye pero ya tiene preguntas abiertas.
- **Cómo responder.** Cada punto que necesita una decisión tiene un código (HD-1, HD-2…) y dice si **bloquea** procesar documentos reales. El resumen está al final.

Fuentes: `spec.md` y `plan.md` de esta carpeta, `tasks.md` (notas de implementación), `contexto/constitucion.md`, `contexto/flujo-documental-opcion-a.md` y `contexto/refinamiento-grill-me-2.md`.

---

## 1. Qué datos personales se tratan

**Qué hace el sistema.** Recibe los documentos completos que entrega cada oferente: PDF, Word, Excel e imágenes. Los convierte a PDF y saca el texto de cada página. En esta entrega no extrae ningún campo suelto (como un número de cédula), pero guarda el documento entero y su texto (spec, "Datos personales").

Los documentos de una oferta suelen traer:

| Dato | Ejemplos de documento | De quién |
|---|---|---|
| Identificación | Cédula (con foto), RUT | Representantes legales, personas naturales oferentes |
| Información financiera | Estados financieros, certificaciones bancarias, declaraciones | Oferentes; en personas naturales, datos financieros personales |
| Firmas | Firma manuscrita escaneada; firma digital con el nombre del firmante | Representante legal, revisor fiscal, contador, quien emite una certificación |
| Contacto | Teléfonos, correos, direcciones | Representantes y contactos del oferente |
| Datos profesionales | Tarjetas profesionales, certificaciones de experiencia | Revisor fiscal, contador, personal propuesto |

Además, el sistema guarda por cada firma digital el nombre de quien firma (tomado del certificado) y la fecha (spec, R15).

**Para cumplimiento:**

- **HD-1.** La foto de la cédula y la firma manuscrita, ¿se consideran datos sensibles (por ejemplo, biométricos) para efectos de la Ley 1581? Si es así, ¿qué exigencias adicionales aplican? **Bloquea.**

## 2. Finalidad

**Qué hace el sistema.** Los datos se usan solo para evaluar la oferta en el proceso de selección: verificar los requisitos habilitantes y los factores de puntaje que se acreditan con documentos. Sin normalizar y leer los documentos no hay extracción ni evaluación (spec, "Datos personales"). Ningún oferente se compara con otro, y no se detectan copias entre oferentes distintos (spec, "Fuera de esta entrega"; principio 6).

**Para cumplimiento:**

- **HD-2.** ¿La finalidad "evaluar la oferta en el proceso de selección" está cubierta por la política de tratamiento de datos de la empresa? **Bloquea.**

## 3. Autorización de los titulares

**Qué hace el sistema.** Nada: el sistema recibe los documentos que el oferente entrega en Ariba por medio del módulo 1. La autorización, si hace falta, se obtiene antes, en el proceso de selección.

**Para cumplimiento:**

- **HD-3.** ¿Las condiciones del proceso (CPC) o la plataforma Ariba incluyen la autorización para tratar los datos personales que vienen en la oferta? **Bloquea.**
- **HD-4.** Esa autorización, ¿cubre a las personas que aparecen en los documentos sin ser el oferente (representante legal, revisor fiscal, contador, personal propuesto, quien firma una certificación)? ¿Quién debe obtenerla? **Bloquea.**

## 4. Responsable y encargados

**Qué hace el sistema.** Corre en la nube de Azure (decisión 16 del diseño). El almacenamiento de los documentos lo define el módulo 1; todavía no está decidido si es Blob Storage o SharePoint (pregunta A-1 del diseño).

**Para cumplimiento:**

- **HD-5.** ¿Quién es el responsable del tratamiento: la empresa que contrata? ¿Microsoft (Azure) actúa como encargado, y el contrato con Microsoft cubre este tratamiento? **No bloquea** la muestra local; **bloquea** el uso en la nube.

## 5. Datos al mínimo necesario

**Qué hace el sistema** (plan, "Registros"; tasks, T04 a T13):

- Guarda el documento completo, porque sostiene cada veredicto (principio 3) y la extracción lo necesita. No extrae campos en esta entrega.
- Los archivos de sistema (por ejemplo `.DS_Store` y `Thumbs.db`) se descartan. Solo se anota su ruta y el motivo.
- Los **registros técnicos (logs)** llevan solo identificadores (`id_proceso`, `id_oferente`, `id_documento`), los primeros 12 caracteres de la huella del archivo, conteos y códigos de error. Nunca llevan texto de las páginas, nombres de archivo ni nombres de quien firma. De un error inesperado se anota solo el tipo y el lugar del código, no su mensaje. Esto está probado con pruebas automáticas.
- Antes de convertir, el archivo se copia con un nombre fijo, para que el nombre del oferente no aparezca en la lista de procesos del servidor.
- Los avisos de error para el evaluador no llevan texto del documento.
- Las pruebas usan solo documentos inventados. En el repositorio no hay documentos reales, y la imagen del job no los incluye.

**Para cumplimiento:** nada que decidir, salvo que haya objeciones.

## 6. Acceso

**Qué hace el sistema** (spec, "Datos personales"):

| Quién | Qué ve |
|---|---|
| La unidad de extracción y el clasificador | Los documentos y su lectura, como servicios, sin personas de por medio |
| El evaluador | Los documentos de su proceso, por medio de su tarea de revisión. Los documentos con error le llegan con un aviso que no lleva texto del documento |
| Operación (equipo técnico) | Solo para resolver fallas |
| Otros oferentes | Nada: ningún oferente ve documentos de otro |

Lo que falta: los permisos concretos (quién tiene acceso al almacenamiento, con qué identidad) dependen de dónde guarde los archivos el módulo 1 (preguntas A-1 y O2), y todavía no están definidos.

**Para cumplimiento:**

- **HD-6.** ¿Este reparto de acceso es suficiente? ¿Operación debe dejar registro de cada vez que abre un documento para resolver una falla? **No bloquea** la muestra local; **bloquea** el uso en la nube.

## 7. Conservación y supresión

**Qué hace el sistema.**

- Los documentos normalizados, su lectura y el manifiesto se conservan lo mismo que la evidencia del proceso, porque sostienen cada veredicto (spec, pregunta S1). El plazo no está definido.
- Nada se borra ni se reemplaza durante el proceso: una subsanación agrega un documento nuevo (decisión 19).
- El script que mide la muestra real deja su salida en una carpeta temporal que se borra al terminar (tasks, T13).
- Para la extracción (entrega 2), el diseño propone guardar la traza completa 30 días y después solo metadatos, sin imágenes (decisión D23).

**Para cumplimiento:**

- **HD-7.** ¿Cuánto tiempo se conservan los documentos y su lectura después de cerrado el proceso? ¿Quién los borra al vencer y cómo queda constancia? **Bloquea** el uso en la nube.
- **HD-8.** ¿Bastan 30 días de traza completa de la extracción y después solo metadatos? (pregunta S1). **Bloquea** la entrega 2.

## 8. Seguridad

**Qué hace el sistema** (tasks, T07 y T12):

- El job corre en un contenedor con un usuario sin privilegios.
- Las macros de los documentos de Word y Excel se bloquean al convertirlos.
- La lectura no usa servicios externos ni inteligencia artificial: es código que corre dentro del contenedor. Probado sin conexión a internet.
- Las firmas digitales se revisan sin consultar servicios externos.

Lo que falta definir con la plataforma: cifrado del almacenamiento, red privada y región de Azure (ver el punto 9).

**Para cumplimiento:**

- **HD-9.** ¿Qué medidas mínimas exige la empresa para almacenar estos documentos en la nube (cifrado, red privada, monitoreo de accesos)? **Bloquea** el uso en la nube.

## 9. Transferencia y transmisión internacional

**Qué hace el sistema.**

- **Entrega 1 (normalización y lectura):** la región de Azure donde correrá aún no está definida.
- **Entrega 2 (extracción):** el diseño actual usa un modelo de lenguaje (gpt-5.4) y un servicio MCP desplegados en la región eastus, en Estados Unidos. Las cédulas y los RUT viajarían allá para extraer sus datos (pregunta S2).

**Para cumplimiento:**

- **HD-10.** ¿Es aceptable bajo la Ley 1581 (artículo 26) que documentos con datos personales se procesen en Estados Unidos? Si lo es, ¿con qué condiciones (contrato de transmisión, autorización expresa, otra)? **Bloquea** la entrega 2 y, si la entrega 1 también corre fuera de Colombia, el uso en la nube.
- **HD-11.** ¿Hay una región de Azure preferida o exigida para la entrega 1? **Bloquea** el uso en la nube.

## 10. Derechos de los titulares

**Qué hace el sistema.** Nada específico. Cada documento queda identificado (`id_documento`) y se puede ubicar por proceso y oferente, así que es posible encontrar los documentos de una persona si lo pide.

**Para cumplimiento:**

- **HD-12.** Si una persona pide conocer, corregir o suprimir sus datos, ¿por qué canal llega y quién responde? ¿Cómo se resuelve un pedido de supresión cuando el documento es evidencia de un proceso de selección que puede ser reclamado? **No bloquea** la muestra local.

## 11. Registro de la base de datos

**Para cumplimiento:**

- **HD-13.** ¿Este tratamiento exige inscribir o actualizar una base de datos en el Registro Nacional de Bases de Datos de la Superintendencia de Industria y Comercio? **No bloquea** la muestra local.

## 12. Uso de la muestra real para medir (criterios A3 a A5)

**Qué se propone** (spec, criterios A3 a A5; tasks, T13):

- La muestra SR5658940621 (6 oferentes) se procesa **solo en la máquina del equipo**, nunca en la nube ni en un ambiente compartido.
- El script imprime solo conteos. Los oferentes salen como OF-001, OF-002…, sin nombres de carpetas, de archivos ni de personas.
- La salida con datos personales (PDF y lecturas) va a una carpeta temporal que se borra al terminar. Si se conserva para revisarla a mano, no se sube al repositorio.
- Los conteos se pueden compartir con el equipo técnico, porque no llevan datos personales.

**Para cumplimiento:**

- **HD-14.** ¿Se autoriza procesar la muestra real en la máquina del equipo en estas condiciones? ¿Quién de la empresa puede hacerlo? **Bloquea** la medición con la muestra real.

---

## Resumen para cumplimiento

| Código | Pregunta | Bloquea |
|---|---|---|
| HD-1 | ¿La foto de la cédula y la firma manuscrita son datos sensibles? | Todo uso con documentos reales |
| HD-2 | ¿La política de tratamiento cubre la finalidad "evaluar la oferta"? | Todo uso con documentos reales |
| HD-3 | ¿Las CPC o Ariba incluyen la autorización del oferente? | Todo uso con documentos reales |
| HD-4 | ¿La autorización cubre a terceros que aparecen en los documentos? | Todo uso con documentos reales |
| HD-5 | Responsable y encargados (empresa, Microsoft) | Uso en la nube |
| HD-6 | ¿Es suficiente el reparto de acceso? ¿Se registra cada acceso de operación? | Uso en la nube |
| HD-7 | Plazo de conservación y cómo se borra al vencer | Uso en la nube |
| HD-8 | ¿Bastan 30 días de traza de la extracción? (S1) | Entrega 2 |
| HD-9 | Medidas mínimas de seguridad en la nube | Uso en la nube |
| HD-10 | ¿Se acepta procesar en Estados Unidos (eastus)? (S2) | Entrega 2; la entrega 1 si corre fuera de Colombia |
| HD-11 | Región de Azure para la entrega 1 | Uso en la nube |
| HD-12 | Canal y respuesta a consultas, correcciones y supresiones | No |
| HD-13 | ¿Hay que inscribir la base en el RNBD? | No |
| HD-14 | ¿Se autoriza procesar la muestra real en la máquina del equipo? | Medición con la muestra real |

**Lo mínimo para medir la muestra real** (criterios A3 a A5): HD-1 a HD-4 y HD-14.
