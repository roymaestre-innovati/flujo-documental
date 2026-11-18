# Tareas 005 — Entrada desde OneLake: primera versión

Es la primera pieza de la entrega 2 del orquestador: la interfaz `Origen` deja de ser una carpeta local y lee los archivos del módulo 1 en OneLake (plan, tabla de interfaces). El resto de la entrega 2 (Service Bus, Cosmos, Blob Storage, Container Apps) no entra aquí.

**Meta:** correr `orquestar` en la máquina del equipo sobre un evento real de `workspace-evaluacionofertas-dev`, leyendo directo de OneLake, sin copiar los originales, y llegar a los mismos conteos que reporta el módulo 1 en sus tablas.

**Estado al 2026-11-18:** por empezar. La prueba de acceso está hecha (`servicios/prueba-onelake/`, paso 0 del diseño).

## Dónde va

En el **orquestador**, no en la normalización ni en un servicio nuevo:

- La normalización recibe una carpeta local y no sabe de dónde vienen los archivos. Así se queda, y se prueba sin Azure.
- El orquestador ya tiene la interfaz `Origen` (`listar` y `bajar`) y el manejador `Normalizar`, que baja los originales a una carpeta temporal que se borra al terminar. Falta la versión de OneLake.
- El reparto entre el proceso y los oferentes ya está en la apertura (`repartir`), y es lo que hay que adaptar a las carpetas del módulo 1.

Un servicio aparte solo agregaría una copia de los originales o un salto de red más, y el diseño los evita (decisión 32).

## Para quien implemente

- Leer antes el paso 0 de `contexto/flujo-documental-opcion-a.md` ("Cómo leemos los archivos de Fabric"), `plan.md` y `tasks.md` de esta carpeta.
- Las pruebas usan un cliente de OneLake falso, en memoria, con carpetas inventadas que imitan la forma del módulo 1. Nada de Azure en las pruebas. Solo T06 toca OneLake, y la corre el usuario en su máquina.
- Con datos reales, por pantalla y en los registros salen solo conteos, extensiones y tamaños. Nunca nombres de oferentes, de carpetas ni de archivos (principio 6).
- `servicios/normalizacion/` no se toca. Si algo hace falta cambiarle, se anota aquí y se le pregunta al usuario antes.
- Mismo flujo que en `tasks.md`: rama, pruebas en verde, notas aquí, commit y **alto para revisión del usuario** después de cada tarea.

## Tareas

- [ ] **T01 — Metadatos del módulo 1.** Script de solo lectura (en `servicios/prueba-onelake/`) que, por evento, cruce el listado de OneLake con las tablas `bronce.tbl_evaluacionofertas_adjuntos_metadata` y `bronce.tbl_evaluacionofertas_oferentes_control`, e imprima solo conteos. Debe responder cuatro preguntas:
  - ¿Cada carpeta de oferente tiene un `sm_vendor_id` en `oferentes_control`?
  - ¿Los archivos de `_contenido/` se ligan a su comprimido con `parent_archive_key`?
  - ¿Qué traen los tres tipos de JSON del módulo 1? Solo las llaves, sin valores.
  - ¿Cómo se pasa de `event_id` al identificador del proceso (SR…)? Ver `tbl_evaluacionofertas_eventos_listados`.

  Las tablas se leen con `deltalake` o con `pyarrow` aplicando el log de Delta. Leer las parquet directo cuenta también las versiones viejas. **Alto: con las respuestas, el usuario decide cómo se identifica al oferente y qué se hace con los JSON en T03.**

- [ ] **T02 — `OrigenOneLake`.** En `servicios/orquestador/src/orquestador/origen.py`, con `azure-identity` y `azure-storage-file-datalake` como dependencias.
  - Se configura con workspace, lakehouse y `DefaultAzureCredential`.
  - Las rutas son relativas a `Files/`.
  - `listar` es recursivo, devuelve solo archivos, en orden y relativos a la carpeta.
  - `bajar` escribe al disco por partes, no carga el archivo entero en memoria (hay RAR de 78 MB), y revisa que el tamaño coincida con el listado.
  - Errores: 404 es `ErrorOrigen`; 429, 5xx y timeouts son `ErrorTransitorio`; 401 y 403 son una falla de configuración que va a operación sin reintentos.
  - Pruebas con el cliente falso, incluidas una ruta con `..` y un tamaño que no coincide.

- [ ] **T03 — Reparto con las carpetas del módulo 1.** Variante de `repartir` en `apertura.py`, elegida por configuración, que traduce la forma del módulo 1 a entregas:
  - `Documentos del proceso/` pasa a `PROCESO`.
  - `Oferentes/<carpeta>/` pasa al identificador del oferente, según T01.
  - Lo que esté fuera de esas dos carpetas rechaza el aviso, como hoy un archivo suelto.
  - **Comprimidos (decidido por el usuario, 2026-11-18):** solo se baja lo descomprimido. Ningún ZIP ni RAR entra en una entrega, tampoco los que vienen dentro de `_contenido/`. El tipo se reconoce por los primeros bytes o por los metadatos del módulo 1 (`is_compressed_archive`), no solo por la extensión.
  - Un comprimido cuyo contenido no está (el módulo 1 no lo pudo descomprimir) no se baja, pero no se calla: queda registrado en la entrega y genera una tarea `documento_con_error` con motivo `comprimido_sin_contenido`, para que no se evalúe a nadie con documentos de menos. Cómo se sabe que falta el contenido sale de T01 (`parent_archive_key` o la carpeta `_contenido/`).
  - Los JSON del módulo 1 también se dejan fuera, si T01 confirma que no son documentos.
  - Lo excluido se cuenta en el registro de la apertura, por motivo.
  - Pruebas con un proceso inventado: dos oferentes, un RAR con su `_contenido/`, un ZIP dentro de otro, un RAR sin descomprimir y un JSON del módulo 1.

- [ ] **T04 — Bajar en paralelo.** `Normalizar` baja hoy los archivos de uno en uno. A ~1,5 MB/s por archivo, un oferente de 200 MB tarda más de 2 minutos solo en bajar.
  - Se baja con varios hilos (`paralelo_bajar`, 4 por defecto) a la misma carpeta temporal.
  - Si un archivo falla, falla la entrega, como hoy.
  - Se mide en T06 y se ajusta el valor.

- [ ] **T05 — Comando.** `orquestar` acepta `--onelake-workspace`, `--onelake-lakehouse` y `--ruta` (por ejemplo `informacion-adjuntos/fase2/<event_id>`) en lugar de `--origen`, y arma el aviso con el identificador del proceso que salga de T01. Sin `--clasificacion` sigue saliendo todo TD-99. Prueba de punta a punta con el cliente falso. README del orquestador actualizado.

- [ ] **T06 — Corrida con un evento real.** La corre el usuario en su máquina, con `az login`, sobre el evento más chico de `fase2/` (39 archivos del proceso y 6 oferentes, o 21 y 9).
  - Debe imprimir solo conteos: archivos listados, excluidos por motivo, bajados, MB y tiempo de descarga.
  - Debe imprimir también los documentos normalizados, copias exactas y errores por tipo, y compararlos con los `file_status` de `adjuntos_metadata` de ese evento.
  - La salida va fuera del repositorio y se borra al terminar.
  - Criterio: ningún archivo de documentos queda sin entrega, no se baja ningún ZIP ni RAR y cada comprimido sin contenido tiene su tarea.

- [ ] **T07 — Cierre.** Notas de lo encontrado aquí. Actualizar el paso 0 y A-1 del diseño, la tabla de interfaces de `plan.md` ("Lo que cambió al implementar") y el README del repo.

## Fuera de esta versión

- La identidad administrada del job y el acceso en producción. Se pide al módulo 1 (A-1) y se prueba al desplegar en Container Apps.
- El aviso real por Service Bus. Aquí el aviso lo arma el comando.
- Leer las tablas Delta en cada corrida. Si T01 muestra que hacen falta para repartir, se propone primero que el módulo 1 mande la lista de archivos en el aviso (`archivos` del contrato `proceso-listo`).

## Notas de implementación

(vacío)
