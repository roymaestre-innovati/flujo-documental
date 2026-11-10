# Orquestador

Lleva cada proceso de selección desde el aviso del módulo 1 hasta las solicitudes de extracción (iniciativa 005, entrega 1). La spec, el plan y las tareas están en `specs/005-orquestador/`; los contratos, en `contracts/modulo5-orquestador/v0/` y `contracts/modulo3-extraccion/v0.2/`.

**Estado:** entrega 1 cerrada (T01 a T11), en local. El resultado con la muestra real está en la nota de T11 de `tasks.md`. Azure (Service Bus, Cosmos, OneLake, Container Apps) va en la entrega 2.

## Cómo funciona

```
aviso del módulo 1 ──► procesos-listos ──► Apertura ──► normalizar (una por entrega, 2 a la vez)
                                                            │
                                     Normalizar ◄───────────┘
                                         │  un mensaje por documento normalizado
                                         ▼
                                     clasificar ──► Clasificar ──► extraer (contrato 0.2)
                                                        │
                                                        └──► tareas para una persona
```

1. **Apertura** valida el aviso, reparte los archivos entre la entrega del proceso (`PROCESO/`) y la de cada oferente, fija las versiones del proceso y publica un `normalizar` por entrega.
2. **Normalizar** baja los originales a una carpeta temporal, llama a la normalización (iniciativa 003), registra cada documento y publica un `clasificar` por cada uno normalizado. Las copias exactas no se clasifican; los documentos con error generan una tarea `documento_con_error`.
3. **Clasificar** llama al clasificador, revisa la respuesta, aplica los umbrales y crea los segmentos. Cada segmento que se extrae sale a `extraer`; TD-98 y TD-99 no se extraen; los de confianza baja esperan a una persona con una tarea `clasificacion`.
4. **Resolver** una tarea de clasificación (`resolucion.py`) aplica el tipo que asignó la persona y pide la extracción. En la entrega 2 lo dispara la Power App.
5. **Escalar** (`tareas.escalar_fallas`) convierte en tarea `falla_tecnica` lo que lleva más de 24 horas en error de proceso.

Cada manejador es idempotente: un mensaje repetido no duplica nada. Las fallas siguen las clases de error del diseño: reintentos, cola de errores y alerta a operación (`errores.py`).

## Instalar y probar

Python 3.12 y `uv`. Desde esta carpeta:

```bash
uv sync
uv run pytest
```

La normalización (`../normalizacion`) se instala como dependencia de ruta, editable: un cambio allá se ve aquí sin reinstalar. Las pruebas del orquestador no necesitan LibreOffice, salvo una marcada `libreoffice` (un Excel de punta a punta), que se salta si `soffice` no está instalado.

## Correr un proceso en local

```bash
uv run orquestar --origen <carpeta del proceso> --proceso SR0000000001 \
                 --clasificacion <csv> --salida <carpeta fuera del repo>
```

- `--origen`: la carpeta del proceso, con `PROCESO/` y una subcarpeta por oferente, nombrada con su identificador. Un archivo suelto en la raíz rechaza el aviso.
- `--clasificacion`: el CSV del clasificador falso, con las columnas `id_oferente` (vacío para los documentos del proceso), `ruta_origen` (relativa a la carpeta de la entrega), `pagina_inicio` y `pagina_fin` (vacíos para todo el documento), `tipo_documental`, `confianza` y, opcional, `subtipo`. Un documento que no está en el CSV sale como TD-99.
- `--paralelo`: entregas que se normalizan a la vez (2 por defecto). Cada conversión con LibreOffice usa cerca de un CPU.
- `--registros <archivo>`: registros en JSON, solo con identificadores. Sin él, por pantalla salen solo las advertencias.
- `--soffice`: la ruta de LibreOffice, si no está en el `PATH`.

Por pantalla salen **solo conteos**: entregas, documentos y segmentos por estado, solicitudes por tipo documental, tareas abiertas por clase y motivo, registros atascados (en un estado intermedio sin tarea; debe ser 0), mensajes en errores y tiempo. En `<salida>` quedan el almacén (PDF normalizados y lecturas), `estado.json`, `solicitudes-extraccion.jsonl`, `errores.json` y `conteos.json`. **Todo eso trae datos personales**: el comando se niega a escribir dentro de un repositorio git. Termina con 0 si nada quedó en errores, 1 si algo quedó y 2 si los argumentos están mal.

Las demoras de los reintentos no se esperan: el comando adelanta el reloj. Si algo queda en errores, se ve en `errores.json` con su motivo.

## Correr la muestra real

Solo en la máquina del equipo (principio 6). Imprime solo conteos:

```bash
uv run python scripts/correr_muestra.py \
    --manifiesto ~/GEB/Extraccion/Documentos/clasificados/manifiesto.csv \
    --muestra ~/GEB/pruebas-normalizacion/muestra1 --muestra ~/GEB/pruebas-normalizacion/muestra
```

Convierte la clasificación manual al CSV del clasificador falso (`SIN CLASIFICAR` como TD-99, los huecos de una clasificación por páginas como TD-99), nombra los oferentes OF-001, OF-002… en el orden de las carpetas y corre todo. Con `--salida <carpeta vacía fuera del repo>` conserva el estado y las solicitudes para revisarlos a mano.

## Ver las corridas en el navegador

```bash
uv run visor --corridas <carpeta>
```

Abre `http://127.0.0.1:8766` con lo que dejó una corrida guardada con `--salida` (de `orquestar` o de `correr_muestra.py`). `<carpeta>` puede ser la salida de una corrida o una carpeta con varias, una por subcarpeta; se elige en la lista de arriba. Hay cuatro vistas:

- **Resumen:** conteos, una fila por entrega (clic para ver sus documentos), solicitudes por tipo documental, tareas por motivo y versiones fijadas.
- **Documentos:** la lista por entrega, con filtros (texto, entrega, estado, con tarea, dudosa). El detalle muestra los segmentos con su confianza frente al umbral y el piso, las tareas, la lectura página por página, el historial y la solicitud de extracción de cada segmento. "Ver PDF" abre el PDF normalizado al lado; un clic en una página lo lleva a esa página.
- **Extracción** (si la corrida tiene `extraccion/`, que deja el comando `extraer` del servicio de extracción): en el resumen, segmentos con resultado, campos en revisión por motivo y tokens. En el detalle de un documento, la columna "Extracción" de cada segmento y, debajo, una tabla por segmento con cada campo: valor, confianza frente al umbral de la ficha, `cumple`, motivos, evidencia (un clic en la página abre el PDF ahí) y reglas pendientes. Los campos en revisión van resaltados. El filtro "Con campos en revisión" deja solo esos documentos. El visor lee los archivos del contrato `modulo3-extraccion/0.2`; no importa el servicio de extracción.
- **Tareas:** todas, abiertas primero; un clic abre el documento.
- **Errores:** mensajes en las colas de errores y entregas con error.

Las corridas traen datos personales: el servidor solo escucha en 127.0.0.1 y solo sirve archivos del almacén de la corrida. Se puede mover la carpeta de una corrida: los PDF se buscan en su `almacen/`. La página se recarga para ver una corrida nueva.

## Qué hay

| Archivo | Qué hace |
|---|---|
| `cola.py` | Colas (`procesos-listos`, `normalizar`, `clasificar`, `extraer`) y `ColaEnMemoria`, que imita Service Bus: bloqueo, reentrega, demora y cola de errores |
| `estado.py` | Almacén del estado y `EstadoEnMemoria`, con creación idempotente y escritura condicional, como Cosmos |
| `estados.py` | Las cinco entidades (proceso, oferente, documento, segmento y tarea), sus transiciones, el historial y `consultar` |
| `errores.py` | Clases de error y el bucle común: reintentos, esperas, cola de errores y alertas |
| `origen.py` | Dónde están los originales: `OrigenLocal`, una carpeta (OneLake en la entrega 2) |
| `clasificador.py` | `ClasificadorFalso`, que lee un CSV (el real es de otro equipo) |
| `contratos.py` | Valida mensajes contra los esquemas de `contracts/` |
| `datos.py` y `datos/` | Versiones vigentes, umbrales y tipos documentales, con un archivo por versión |
| `parametros.py` | Reintentos, demoras, escalamiento y paralelo de normalización |
| `registros.py` | Registros en JSON, solo con identificadores |
| `apertura.py` | Manejador de `procesos-listos`: valida el aviso, reparte las entregas y fija las versiones |
| `normalizar.py` | Manejador de `normalizar`: baja los originales, llama a la normalización y registra los documentos |
| `clasificar.py` | Manejador de `clasificar`: revisa la respuesta, aplica los umbrales y crea segmentos y tareas |
| `extraer.py` | Arma y valida las solicitudes de extracción 0.2 y las publica en `extraer` |
| `tareas.py` | Tareas para una persona y el escalamiento a 24 horas |
| `resolucion.py` | Resolver una tarea de clasificación |
| `local.py` | Una corrida completa sobre las versiones en memoria, con la normalización en paralelo |
| `cli.py` | El comando `orquestar` |
| `visor/` | El comando `visor`: servidor local y página para revisar corridas |

## Datos personales

Las pruebas usan solo datos inventados. Los registros y los motivos de error llevan identificadores, nunca texto de los documentos ni rutas de origen (principio 6).
