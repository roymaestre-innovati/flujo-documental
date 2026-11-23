# Flujo documental: evaluación de ofertas

Validación, lectura y extracción de los documentos que entregan los oferentes de un proceso de selección (módulo 3 de Evaluación de Ofertas), más el orquestador y las reglas e informe, según el diseño de `contexto/flujo-documental-opcion-a.md`.

## Dónde está cada cosa

| Carpeta | Qué hay |
|---|---|
| `contexto/` | Constitución del proyecto, diseño del flujo, decisiones y handoffs. Empezar por `HANDOFF-implementacion.md`; para la extracción, `HANDOFF-extraccion.md` |
| `specs/NNN-nombre/` | Una iniciativa por carpeta: `spec.md`, `plan.md` y `tasks.md` |
| `contracts/` | Contratos versionados entre módulos (esquemas JSON y ejemplos) |
| `servicios/` | Código de cada pieza que se despliega por separado |
| `insumos/` | Plantillas de referencia |

## Estado

| Iniciativa | Estado |
|---|---|
| 003, entrega 1: normalización y lectura | Cerrada: `servicios/normalizacion/` (0.2.0), contrato `contracts/modulo3-normalizacion/v0/` (0.2), medida con la muestra real |
| 003, entrega 2: extracción | Construida (T01 a T10, 2026-11-10): `servicios/extraccion/` (0.1.0). Corre de punta a punta en local y se ve en el visor. Falta la medición con los gold (A9), que corre el usuario. Estado en `contexto/HANDOFF-extraccion.md` |
| Orquestador (iniciativa 005), entrega 1: del aviso a la cola de extracción | Cerrada (T01 a T11, 2026-11-09): `servicios/orquestador/` (0.1.0), contrato `contracts/modulo5-orquestador/v0.2/` (0.2 desde el 2026-11-20) |
| Orquestador, entrega 2: entrada desde OneLake | Primera versión cerrada (T01 a T07 de `specs/005-orquestador/tasks-entrada-onelake.md`, 2026-11-23): `orquestar` corre un evento real leyendo de OneLake. Sigue el resto de la entrega 2: Service Bus, Cosmos, Blob y Container Apps |
| Contrato de extracción 0.2 | Escrito en la 005: `contracts/modulo3-extraccion/v0.2/` |
| Reglas e informe | Por planear |

## Datos personales

Los documentos de los oferentes traen datos personales (Ley 1581 de 2012). No van al repositorio: ni documentos reales, ni la matriz, ni las salidas de la normalización. Las pruebas usan solo documentos inventados. Antes de procesar documentos reales, ver `specs/003-validacion-extraccion/checklist-habeas-data.md`.
