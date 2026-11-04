
# Constitución: Evaluación de Ofertas — Fábrica de Agentes

**Versión**: 1.0.0 | **Ratificada**: 2026-08-13 | **Última modificación**: 2026-08-13

## Propósito

Esta constitución define los principios no negociables que rigen cómo se especifican,
planifican, construyen y entregan las iniciativas de transformación digital de esta
fábrica de agentes. Todo `plan.md` debe pasar el "Chequeo de Constitución" antes de
avanzar a `tareas`, y toda excepción debe quedar documentada en `Complejidad y Excepciones`.

Esta fábrica construye **Evaluación_OfertasV2**: un sistema que evalúa a los oferentes de
un proceso de selección en cuatro dimensiones (económica, financiera, jurídica, técnica),
a partir de datos analíticos y evidencias documentales que cada oferente aporta, y produce
un informe de cumplimiento y puntuación por oferente. La solución se construye en cinco
módulos funcionales, cada uno a cargo de un equipo distinto: (1) Obtener el paquete de
documentos, (2) Obtener el paquete de datos, (3) Validación, clasificación y extracción,
(4) Aplicación de reglas y generación de informe, (5) Orquestador.

## Principios

### 1. El proceso de selección manda sobre la tecnología

Todo `spec.md` se escribe en lenguaje de contratación (oferente, condiciones del proceso,
requisito habilitante, factor de puntaje, subsanación), nunca en términos de stack. Un
`spec.md` que nombre una tecnología concreta antes de `/planificar` se devuelve para
reescritura.

**Por qué**: los cinco módulos los construyen equipos distintos; el único vocabulario común
posible entre todos ellos es el del negocio, no el de una tecnología que un equipo eligió.

### 2. Las condiciones del proceso son datos, no código

Requisitos habilitantes, fórmulas de puntaje, ponderaciones y umbrales de cada proceso de
selección se configuran y versionan como datos del proceso. Un cambio de condiciones no
puede requerir un despliegue de software. Cualquier regla que un plan proponga codificar en
vez de configurar debe justificarse explícitamente en "Complejidad y Excepciones".

**Por qué**: cada proceso de selección trae condiciones distintas; codificarlas convertiría
cada proceso nuevo en un proyecto de desarrollo.

### 3. Todo veredicto es reproducible y trazable hasta su evidencia

El cumplimiento y el puntaje de cada oferente deben poder reconstruirse mostrando: el dato
usado, el documento y página de origen de ese dato, la versión de la regla del proceso que
se aplicó, y quién validó el dato. No se publica un puntaje sin evidencia enlazada, y una
versión de regla ya aplicada no se modifica retroactivamente — un cambio de regla genera una
nueva versión.

**Por qué**: un oferente puede reclamar su calificación; "lo calculó el sistema" no es una
respuesta defendible sin poder mostrar de dónde salió cada cifra.

### 4. La IA extrae; el evaluador decide cuando hay duda o rechazo

La extracción automática de datos desde documentos (actas, estados financieros, documentos
de identidad, etc.) se acepta sin confirmación humana solo cuando supera el umbral de
confianza declarado para ese tipo documental. La revisión humana es obligatoria cuando la
confianza está por debajo de ese umbral, o cuando el resultado de la extracción llevaría a
un veredicto de "no cumple". Todo `spec.md` que incorpore un tipo documental nuevo debe
declarar su umbral de confianza y el rol que revisa.

**Por qué**: rechazar a un oferente por un error de OCR tiene costo legal y reputacional;
exigir confirmación humana del 100% de las extracciones mata el tiempo de ciclo del proceso.

### 5. Contrato primero entre módulos

Ningún módulo se codifica antes de publicar su contrato (esquema de datos y/o API)
versionado en `contracts/`. Cada uno de los cinco módulos debe poder construirse, probarse
y desplegarse de forma independiente, usando dobles de prueba para representar a los demás
módulos. Un cambio incompatible de contrato exige una nueva versión, no la edición de la
vigente.

**Por qué**: cinco equipos trabajan en paralelo; sin contratos estables y versionados, la
integración entre módulos se convierte en el cuello de botella del proyecto.

### 6. Los datos personales del oferente se recolectan al mínimo y con propósito declarado

Toda spec que capture documentos de identidad, información financiera de personas o datos
de contacto declara: qué dato se captura, para cuál requisito del proceso se necesita,
quién puede verlo y por cuánto tiempo se conserva. El acceso a documentos y datos de un
oferente es por rol; ningún oferente puede ver información de otro oferente. Antes de
`/implementar` en cualquier módulo que toque estos datos, se corre `/checklist` de
cumplimiento de habeas data.

**Por qué**: el proceso de selección es privado, pero la información de identidad y
financiera de las personas involucradas sigue siendo dato personal regulado por la
Ley 1581 de 2012.

### 7. Igualdad de trato entre oferentes

Todos los oferentes de un mismo proceso se evalúan con la misma versión de las condiciones.
Si una condición del proceso cambia mientras la evaluación está en curso, se re-evalúa a
todos los oferentes afectados y queda registrado el motivo del cambio; nunca se aplica una
regla nueva a unos oferentes y la regla anterior a otros dentro del mismo proceso.

**Por qué**: es la base de la defensa del resultado ante una impugnación y evita el peor
bug posible del sistema — uno silencioso que solo se descubre cuando un oferente reclama.

## Restricciones organizacionales

- **Stack tecnológico permitido / preferido**: mixto por capa. Power Platform (Dataverse,
  Power Apps, Power Automate) para captura de datos, portal/entrega de oferentes y tareas
  humanas de revisión. Azure (cómputo serverless o contenedores, almacenamiento de
  documentos, servicios de extracción e IA) para ingesta documental, clasificación y
  extracción, motor de reglas y generación del informe. `/planificar` debe justificar cada
  elección concreta aplicando el principio de mínimo necesario: primero la capacidad que la
  plataforma ya ofrece, después construir algo nuevo.
- **Cumplimiento y regulación**: proceso de selección privado (no aplica normativa de
  contratación estatal); aplica protección de datos personales — Ley 1581 de 2012 y sus
  decretos reglamentarios (habeas data) — para documentos de identidad, RUT y estados
  financieros de personas naturales.
- **Gestión del cambio**: la evaluación de ofertas hoy la hacen personas con documentos y
  hojas de cálculo. Toda iniciativa que cambie ese trabajo declara en `spec.md` un criterio
  de éxito de adopción medible (por ejemplo, porcentaje de oferentes evaluados por el
  sistema sin hoja de cálculo paralela), y `/converger` lo evalúa junto con lo funcional.
- **Estructura de la iniciativa**: los cinco módulos funcionales (documentos, datos,
  validación/clasificación/extracción, reglas e informe, orquestador) se especifican como
  iniciativas numeradas independientes bajo `specs/NNN-nombre/`, cada una con su propio
  spec/plan/tasks y su contrato en `contracts/`.

## Gates de complejidad

Un `plan.md` que viole un principio debe justificarlo en su sección "Complejidad y
Excepciones" respondiendo: ¿por qué es necesario? ¿qué alternativa más simple se
descartó y por qué? Si no hay justificación razonable, el agente `plan` debe simplificar
el diseño antes de continuar.

## Gobernanza

Esta constitución tiene prioridad sobre preferencias individuales de stack o estilo.
Modificarla requiere: (1) documentar el motivo, (2) actualizar la versión según semver
(MAYOR: se elimina/redefine un principio de forma incompatible; MENOR: se agrega un
principio o restricción; PARCHE: aclaración de redacción), (3) revisar el impacto en
iniciativas activas.

**Versión**: 1.0.0 | **Ratificada**: 2026-08-13 | **Última modificación**: 2026-08-13
