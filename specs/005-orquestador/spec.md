# Spec 005 — Orquestador (módulo 5)

Estado al 2026-11-09. **Entrega 1 cerrada** (T01 a T11 de `tasks.md`). A1 a A3 se cumplen con las pruebas automáticas y A4 con la muestra real, con las salvedades anotadas en T11. Sale del paso 0 (entrada) y del paso 4 (orquestación) de `contexto/flujo-documental-opcion-a.md`, decisiones 15 a 24 y 32 a 35.

El orquestador lleva cada proceso de selección desde que el módulo 1 avisa que sus documentos están listos hasta que cada oferente tiene su informe. Guarda en qué va cada proceso, oferente y documento, pasa cada documento por la normalización, el clasificador y la extracción, le hace llegar cada error a quien lo puede resolver y garantiza que todos los oferentes de un proceso se evalúen con las mismas versiones.

Se construye por entregas. **Esta versión de la spec cubre solo la primera: desde que llega el aviso de un proceso hasta que sus documentos quedan clasificados y listos para extraer.** La vuelta de los resultados de la extracción, la ficha del proceso, las tareas en la Power App y el paso a las reglas se agregan a esta misma spec en la entrega 2.

Siguiendo el principio 1 de la constitución, esta spec habla en términos del proceso de selección. Las herramientas concretas están en `plan.md`.

## Para qué

Hoy el evaluador recibe las carpetas de cada oferente y sabe de memoria, o en una hoja de cálculo, qué revisó y qué le falta. Con varias piezas automáticas en medio (normalización, clasificación, extracción) hace falta alguien que:

- reciba el proceso completo y lo reparta entre sus oferentes;
- lleve a cada documento por los pasos en orden, sin perder ninguno ni procesarlo dos veces;
- decida qué hacer con cada clasificación según su confianza;
- separe los problemas del documento, que decide el evaluador, de las fallas técnicas, que arregla operación;
- fije las versiones del proceso al abrirlo, para que todos los oferentes se evalúen igual (principio 7).

## Quién lo usa

| Actor | Qué hace con el orquestador |
|---|---|
| Módulo 1 (otro equipo) | Avisa que un proceso está listo, con todos sus documentos |
| Normalización (iniciativa 003) | Recibe cada entrega para normalizarla y leerla |
| Clasificador (otro equipo) | Recibe cada documento normalizado y devuelve sus segmentos |
| Unidad de extracción (iniciativa 003, entrega 2) | Recibe una solicitud por segmento |
| Evaluador | Recibe las tareas: documento con error y clasificación |
| Operación (nosotros) | Recibe las alertas de fallas técnicas y reenvía lo que quedó en errores |

## Historias

1. **Aviso del proceso.** Como módulo 1, aviso una sola vez que un proceso está listo, con la carpeta donde quedaron las condiciones, las adendas y los documentos de todos los oferentes.
2. **Apertura con versiones fijas.** Como evaluador, sé que todos los oferentes de un proceso se evalúan con las mismas versiones del modelo de extracción, de la ontología del clasificador y de las reglas, aunque se publique una versión nueva a mitad de la evaluación.
3. **Cada entrega preparada.** Como clasificador y como extracción, recibo solo documentos ya normalizados y leídos, una sola vez cada uno.
4. **Clasificación según confianza.** Como evaluador, un documento clasificado con poca confianza no se extrae sin que alguien confirme su tipo, y uno con confianza media se extrae pero me llega marcado para revisar.
5. **Documentos que no abren.** Como evaluador, recibo una tarea por cada documento que no se pudo procesar, con su motivo, para decidir si pido subsanación.
6. **Fallas técnicas.** Como operación, me entero de cada falla técnica que no se arregló sola, y puedo reenviar el trabajo cuando la corrijo. Si no la corrijo en 24 horas, el evaluador recibe una tarea para revisar el documento a mano y el proceso no se frena.
7. **En qué va cada oferente.** Como evaluador y como operación, puedo ver en qué paso está cada oferente y cada documento.
8. **Listo para extraer.** Como extracción, recibo por cada segmento una solicitud con el tipo documental, las páginas, la versión fijada del proceso y la marca de clasificación dudosa cuando aplica.

## Requisitos

### Aviso y apertura

- R1. El aviso trae el identificador del proceso, la carpeta donde quedaron sus documentos y, opcional, la lista de archivos con su oferente. Un aviso que no cumple esa forma no se procesa y va a operación.
- R2. Un aviso repetido del mismo proceso no abre el proceso otra vez ni repite trabajo.
- R3. Los documentos se leen donde los dejó el módulo 1. No se guarda una copia de los originales: solo lo que produce el flujo (decisión 32).
- R4. Los documentos del proceso (condiciones, adendas, anexos) se separan de los de cada oferente. Mientras A-1 no se responda, se distinguen por la estructura de carpetas (ver `plan.md`).
- R5. Al abrir el proceso se fijan las versiones que usará: modelo de extracción, ontología del clasificador, reglas, normalizador y sus parámetros, y umbrales de clasificación. Publicar una versión nueva no cambia los procesos abiertos.

### Preparación de cada entrega

- R6. Cada entrega (la del proceso y la de cada oferente) se normaliza y se lee con la iniciativa 003. Una entrega con una falla no frena a las demás.
- R7. Cada documento del inventario queda registrado con su estado: normalizado, copia de otro o con error de entrada.
- R8. Un documento con error de entrada genera una tarea "documento con error" para el evaluador, con el motivo que dio la normalización.

### Clasificación

- R9. Cada documento normalizado se manda al clasificador una sola vez, con su documento normalizado, su nombre y ruta de origen y su lectura por página.
- R10. Una copia exacta de otro documento no se clasifica: toma el resultado del original.
- R11. La respuesta del clasificador se valida: cada página cae en exactamente un segmento, sin huecos ni solapes, y los tipos documentales existen en la matriz (incluidos TD-98 y TD-99). Una respuesta inválida se pide una vez más; si sigue inválida, se crea una tarea de clasificación.
- R12. Cada segmento sigue según su confianza (decisión 12):
  - desde el umbral de su tipo documental: se extrae normal;
  - entre 0,75 y el umbral de su tipo: se extrae y se marca como clasificación dudosa;
  - por debajo de 0,75: no se extrae y se crea una tarea de clasificación.
- R13. Los umbrales por tipo documental son datos con versión, no código (principio 2).
- R14. Los segmentos TD-98 (desempate) y TD-99 (sin tipo) no se extraen. Quedan en el inventario del oferente, visibles para el evaluador.
- R15. Cuando una persona asigna el tipo en una tarea de clasificación, el segmento sigue a extracción con ese tipo, y queda registrado quién lo asignó.

### Hacia la extracción

- R16. Por cada segmento que se extrae se publica una solicitud de extracción con la forma del contrato `modulo3-extraccion/0.2`, con la versión del modelo fijada en el proceso.
- R17. Los segmentos de los documentos del proceso (condiciones, adendas) también se mandan a extraer, sin oferente.

### Errores (decisiones 17 y 18)

- R18. Cada error le llega a quien lo puede resolver: los del documento, al evaluador; las fallas técnicas, a operación. El evaluador no ve fallas técnicas.
- R19. Una falla transitoria (servicio caído, tiempo agotado, límite de uso) se reintenta hasta 3 veces con espera creciente. Cuando el servicio dice cuánto esperar por límite de uso, se espera eso y no cuenta como intento. Si se agotan, el documento queda con error de proceso.
- R20. Una falla que se repite igual (un defecto del programa) no se reintenta: va directo a errores.
- R21. Un documento con error de proceso avisa a operación y no deja que el oferente quede completo. Operación puede reenviarlo cuando corrige la causa.
- R22. Si un error de proceso no se resuelve en 24 horas (configurable), se crea una tarea "documento sin procesar por falla técnica" para el evaluador.
- R23. Un documento con error no frena a los demás del oferente.

### Estado y trazabilidad

- R24. Se guarda el estado del proceso, de cada oferente, de cada documento, de cada segmento y de cada tarea humana, con los estados del paso 4 del diseño.
- R25. Se puede consultar en qué va un proceso: cuántos documentos y segmentos hay en cada estado, por oferente, y qué tareas están abiertas.
- R26. Un cambio de estado solo se aplica si el estado anterior es el esperado, para que dos avisos cruzados no se pisen.
- R27. Recibir dos veces el mismo aviso o el mismo pedido de trabajo da el mismo resultado, sin trabajo ni tareas repetidas.
- R28. Cada cambio de estado guarda cuándo ocurrió y el motivo. Los registros llevan solo identificadores, nunca texto de los documentos ni nombres de archivo.

## Fuera de esta entrega

Van en la entrega 2, salvo que se diga otra cosa:

- Recibir los resultados de la extracción, las tareas de revisión de campos, el "¿oferente completo?" y el aviso a las reglas.
- La ficha del proceso (extraída de las condiciones y las adendas) y su confirmación humana.
- La evaluación por menor precio.
- Escribir las tareas donde las lee la Power App y recibir sus correcciones (A-2). En esta entrega las tareas quedan registradas en el estado.
- El comando `reprocesar`.
- Las piezas en Azure: colas, base de estado, lectura desde el datalake de Fabric, almacén de lo que producimos y alertas. En esta entrega todo corre en la máquina del equipo.
- Subsanación: por ahora no llegan documentos tardíos (A-10).
- La extracción bajo demanda de TD-98, cuando hay empate.

## Datos personales (principio 6)

| Pregunta | Respuesta |
|---|---|
| ¿Qué dato se captura? | El orquestador no extrae datos. Guarda identificadores, estados, huellas, tipos documentales y páginas. Las rutas de origen de los archivos están en los inventarios de la normalización, que pueden traer nombres de personas |
| ¿Para qué requisito? | Para seguir cada documento hasta el informe y poder reconstruir de dónde salió cada veredicto (principio 3) |
| ¿Quién puede verlo? | Operación, el evaluador del proceso por medio de sus tareas y los servicios del flujo. Ningún oferente ve el estado de otro |
| ¿Cuánto se conserva? | Lo mismo que la evidencia del proceso. El plazo lo define cumplimiento (pregunta S1) |
| Registros (logs) | Solo identificadores, estados, conteos y motivos de error |
| Pruebas | Solo con documentos inventados. La corrida con la muestra real la hace el equipo en su máquina e imprime solo conteos |

El checklist de habeas data de la iniciativa 003 (`specs/003-validacion-extraccion/checklist-habeas-data.md`) cubre los mismos documentos. Antes de correr el orquestador en un ambiente compartido se revisa si hace falta agregarle algo.

## Criterios de aceptación

Con documentos inventados, en las pruebas automáticas:

- A1. Cada requisito R1 a R28 tiene al menos una prueba.
- A2. Un proceso inventado (documentos del proceso y dos oferentes, con una copia, un documento con error, una clasificación dudosa, una de baja confianza y un TD-99) llega desde el aviso hasta las solicitudes de extracción, y cada solicitud cumple el contrato 0.2.
- A3. Entregar dos veces cada aviso y cada pedido de trabajo da el mismo estado y las mismas solicitudes, sin duplicados.

Con la muestra real SR5658940621, corrida por el equipo en su máquina con la clasificación manual como clasificador falso:

- A4. Todos los oferentes llegan hasta las solicitudes de extracción o a una tarea, y ningún documento queda en un estado intermedio. Se informan solo conteos: documentos y segmentos por estado, solicitudes por tipo documental, tareas por clase y tiempo total.

## Criterio de adopción (gestión del cambio)

Hoy el evaluador sigue en una hoja de cálculo qué documentos de cada oferente revisó. Esta parte se considera adoptada cuando, sobre los procesos de un trimestre, el evaluador consulta el avance de cada oferente en el sistema y no en una hoja paralela, y ningún documento se queda sin estado final sin que alguien se entere (por tarea o por alerta).

## Preguntas abiertas que tocan esta entrega

| # | Pregunta | Qué se supone mientras tanto |
|---|---|---|
| A-1 | Forma del aviso, carpetas e identificadores del módulo 1 | El mensaje propuesto en el paso 0 del diseño. Una subcarpeta por oferente, nombrada con su identificador, y una subcarpeta `PROCESO` para los documentos del proceso. Si el aviso no trae la lista de archivos, también hace falta permiso para listar la carpeta |
| C1 a C3 | Cómo se llama al clasificador y qué devuelve | Una consulta por documento que devuelve segmentos con páginas, tipo y confianza. Se prueba con el clasificador falso |
| A-5 | ¿El clasificador usa nuestro documento normalizado y nuestra lectura? | Sí |
| A-7 | ¿TD-98 entra en la ontología del clasificador? | Sí |
| A-2 | Dónde y cómo se escriben las tareas | Quedan en el estado; la integración va en la entrega 2 |
| S1 | Plazo de conservación | Igual al de la evidencia del proceso |
