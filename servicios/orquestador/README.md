# Orquestador

Lleva cada proceso de selección desde el aviso del módulo 1 hasta las solicitudes de extracción (iniciativa 005, entrega 1). La spec, el plan y las tareas están en `specs/005-orquestador/`; los contratos, en `contracts/modulo5-orquestador/v0/` y `contracts/modulo3-extraccion/v0.2/`.

**Estado:** en construcción. Están las interfaces con su versión local, los estados de las entidades y el bucle de errores (T01 a T04). Faltan los manejadores de cada cola (T05 a T09) y el comando `orquestar` (T10).

## Instalar y probar

Python 3.12 y `uv`. Desde esta carpeta:

```bash
uv sync
uv run pytest
```

La normalización (`../normalizacion`) se instala como dependencia de ruta, editable: un cambio allá se ve aquí sin reinstalar. Las pruebas del orquestador no necesitan LibreOffice.

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

## Datos personales

Las pruebas usan solo datos inventados. Los registros y los motivos de error llevan identificadores, nunca texto de los documentos ni rutas de origen (principio 6).
