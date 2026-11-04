"""Genera flujo_documental_c4.drawio: niveles C4 1 a 3 (objetivo) y una secuencia del flujo documental.

Fuente del contenido: contexto/flujo-documental-opcion-a.md.
Estilos y convención: skill diagramas-c4 (niveles acumulativos, integraciones como hexágonos, flechas punteadas).

Si el .drawio se retoca a mano, no volver a ejecutar este script sin avisar: se pierden los ajustes.
"""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/.claude/skills/diagramas-c4"))
from c4drawio import Pagina, guardar, nuevo_archivo  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flujo_documental_c4.drawio")

# Rejilla: columnas cada 300 px, filas fijas.
C = {0: -40, 1: 300, 2: 600, 3: 900, 4: 1200, 5: 1500, 6: 1800, 7: 2100}
R = {0: 0, 1: 300, 2: 560, 3: 860, 4: 1140}

# ---------- Cajas compartidas entre niveles ----------
def personas(p):
    p.c4("operacion", "persona", "Operación", "Equipo técnico: vigila colas y errores, y reprocesa cuando hace falta.", 1520, R[0])
    p.c4("evaluador", "persona", "Evaluador", "Revisa por área (jurídica, financiera, técnica, económica): confirma o corrige datos y veredictos.", 2010, R[0])
    p.c4("coordinador", "persona", "Coordinador", "Confirma la ficha del proceso y firma el informe de evaluación.", 2290, R[0])


def externos(p, clasificador=True):
    p.c4("ariba", "externo", "SAP Ariba", "Plataforma donde los oferentes presentan sus ofertas.", C[0], 30)
    p.c4("modulo1", "externo", "Módulo 1 - Entrada", "Recibe los archivos del oferente y del proceso y avisa cuando una entrega está completa. Otro equipo.", C[0], R[1])
    if clasificador:
        p.c4("clasificador", "externo", "Clasificador", "Identifica el tipo documental de cada archivo y lo segmenta, con su confianza. Usa LLM. Otro equipo.", 1180, 40)
    p.c4("powerapp", "externo", "Power App de revisión", "Muestra las tareas de revisión y recoge las correcciones (Dataverse). Otro equipo.", C[7], R[2])
    p.c4("foundry", "externo", "Azure AI Foundry", "Modelo gpt-5.4 que interpreta los documentos.", C[3], 1400)


def flechas_personas(p, destino_operacion, entra_op=(0.5, 0)):
    p.flecha("ariba", "modulo1", "Entrega ofertas")
    p.flecha("operacion", destino_operacion, "Vigila y<br>reprocesa", sale=(0.3, 1), entra=entra_op)
    p.flecha("evaluador", "powerapp", "Revisa y corrige", sale=(0.5, 1), entra=(0.3, 0))
    p.flecha("coordinador", "powerapp", "Confirma ficha,<br>firma informe", sale=(0.5, 1), entra=(0.8, 0))


def almacenes(p):
    p.c4("blob", "contenedor", "Blob Storage", "Originales, PDF normalizados, lectura por página e informes.", C[1], R[3], tec="Azure Blob Storage")
    p.c4("cosmos", "contenedor", "Base de estado y modelo", "Estado de procesos, oferentes, documentos y tareas; versiones fijadas; fichas de los tipos documentales; reglas.", C[6], R[3], tec="Cosmos DB")
    p.c4("sb", "contenedor", "Colas de mensajes", "Una cola por paso (normalizar, clasificar, extraer, resultados, reglas), con cola de errores.", C[2], R[1], tec="Azure Service Bus")
    p.c4("mcp", "contenedor", "Servidor MCP del modelo", "Sirve las fichas de cada tipo documental desde el modelo semántico.", C[4], R[4], tec="Python, Container Apps")


def flechas_almacenes_comunes(p):
    p.flecha("mcp", "cosmos", "Lee el modelo", sale=(1, 0.5), entra=(0.5, 1))


# ---------- Nivel 1 ----------
def nivel1(mx):
    p = Pagina(mx, "Nivel 1 - System Context (Objetivo)", "n1")
    p.texto("Flujo documental de evaluación de ofertas · Nivel 1 · Contexto", 0, -80, 1200, 40)
    p.c4("ariba", "externo", "SAP Ariba", "Plataforma donde los oferentes presentan sus ofertas.", 0, 300)
    p.c4("modulo1", "externo", "Módulo 1 - Entrada", "Recibe los archivos del oferente y del proceso y avisa cuando una entrega está completa. Otro equipo.", 0, 560)
    p.c4("operacion", "persona", "Operación", "Equipo técnico: vigila colas y errores, y reprocesa cuando hace falta.", 620, 0)
    p.c4("sistema", "sistema", "Flujo documental de evaluación", "Normaliza, lee, clasifica, extrae y evalúa los documentos de cada oferta, y crea las tareas de revisión y el informe.", 600, 560)
    p.c4("clasificador", "externo", "Clasificador", "Identifica el tipo documental de cada archivo y lo segmenta. Usa LLM. Otro equipo.", 300, 860)
    p.c4("foundry", "externo", "Azure AI Foundry", "Modelo gpt-5.4 que interpreta los documentos.", 900, 860)
    p.c4("powerapp", "externo", "Power App de revisión", "Muestra las tareas de revisión y recoge las correcciones (Dataverse). Otro equipo.", 1200, 560)
    p.c4("evaluador", "persona", "Evaluador", "Revisa por área: confirma o corrige datos y veredictos.", 1100, 0)
    p.c4("coordinador", "persona", "Coordinador", "Confirma la ficha del proceso y firma el informe.", 1400, 0)
    p.flecha("ariba", "modulo1", "Entrega ofertas")
    p.flecha("modulo1", "sistema", "Entrega archivos<br>y avisa", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("operacion", "sistema", "Vigila y reprocesa")
    p.flecha("sistema", "clasificador", "Pide clasificar", sale=(0.25, 1), entra=(0.5, 0))
    p.flecha("sistema", "foundry", "Extrae datos", sale=(0.75, 1), entra=(0.5, 0))
    p.flecha("sistema", "powerapp", "Crea tareas<br>e informe", sale=(1, 0.3), entra=(0, 0.3))
    p.flecha("powerapp", "sistema", "Devuelve<br>correcciones", sale=(0, 0.75), entra=(1, 0.75))
    p.flecha("evaluador", "powerapp", "Revisa y corrige", entra=(0.3, 0))
    p.flecha("coordinador", "powerapp", "Confirma ficha,<br>firma informe", entra=(0.8, 0))
    return p


# ---------- Nivel 2 ----------
def nivel2(mx):
    p = Pagina(mx, "Nivel 2 - Container (Objetivo)", "n2")
    p.texto("Flujo documental de evaluación de ofertas · Nivel 2 · Contenedores", 0, -80, 1200, 40)
    personas(p)
    externos(p)
    almacenes(p)
    p.limite("Flujo documental de evaluación", "Software System", 260, 250, 1820, 1070)
    p.c4("job", "contenedor", "Normalización y lectura", "Convierte a PDF, quita duplicados, detecta firma digital y lee el texto y el tipo de cada página. Sin LLM.", C[1], R[1], tec="Container Apps Job, Python")
    p.c4("orq", "contenedor", "Workers de orquestación", "Llevan cada documento al paso siguiente, guardan el estado, aplican las reglas y crean tareas e informe. Sin LLM.", C[4], R[1], tec="Container Apps, Python")
    p.c4("ext", "contenedor", "Unidad de extracción", "Extrae los campos de cada documento con su evidencia y los valida con código.", C[3], R[3], tec="Container Apps, agente LLM")
    flechas_personas(p, "orq", entra_op=(0.75, 0))
    p.flecha("modulo1", "job", "Avisa entrega lista", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("job", "blob", "Guarda PDF<br>y lectura")
    p.flecha("job", "sb", "Archivo listo", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("sb", "orq", "Entrega mensajes", sale=(1, 0.4), entra=(0, 0.4))
    p.flecha("orq", "sb", "Publica el<br>siguiente paso", sale=(0, 0.8), entra=(1, 0.8))
    p.flecha("orq", "clasificador", "Pide clasificar", sale=(0.5, 0), entra=(0.5, 1))
    p.flecha("sb", "ext", "Segmento a extraer", sale=(0.5, 1), entra=(0, 0.5), puntos=[(720, 920)])
    p.flecha("ext", "sb", "Resultado", sale=(0.5, 0), entra=(0.83, 1), puntos=[(1020, 500), (800, 500)])
    p.flecha("ext", "blob", "Lee PDF<br>y lectura", sale=(0, 0.8), entra=(1, 0.8))
    p.flecha("ext", "foundry", "Interpreta con gpt-5.4", sale=(0.3, 1), entra=(0.3, 0))
    p.flecha("ext", "mcp", "Consulta la ficha", sale=(0.75, 1), entra=(0, 0.5), puntos=[(1080, 1200)])
    p.flecha("orq", "cosmos", "Lee y guarda<br>estado y reglas", sale=(0.5, 1), entra=(0, 0.5), puntos=[(1320, 920)])
    p.flecha("orq", "powerapp", "Escribe tareas<br>e informe", sale=(1, 0.5), entra=(0, 0.3), puntos=[(1980, 360), (1980, 596)])
    p.flecha("powerapp", "orq", "Devuelve correcciones", sale=(0, 0.7), entra=(0.75, 1), puntos=[(1380, 644)])
    flechas_almacenes_comunes(p)
    return p


# ---------- Nivel 3 ----------
def nivel3(mx):
    p = Pagina(mx, "Nivel 3 - Component (Objetivo)", "n3")
    p.texto("Flujo documental de evaluación de ofertas · Nivel 3 · Componentes", 0, -80, 1200, 40)
    personas(p)
    externos(p)
    almacenes(p)

    # Job de normalización y lectura
    p.limite("Normalización y lectura", "Container Apps Job", 280, 270, 280, 470)
    p.c4("norm", "componente", "Normalizador", "Filtra archivos de sistema, calcula el hash, marca duplicados, convierte a PDF y detecta firma digital.", C[1], R[1], tec="Python, LibreOffice, qpdf, pyHanko")
    p.c4("lector", "componente", "Lector de páginas", "Saca el texto de cada página y la clasifica: texto, escaneo, imagen o vacía. Sin LLM.", C[1], R[2], tec="Python")
    p.c4("ocr", "hexagono", "OCR", "Texto de páginas escaneadas (experimento).", C[0] + 20, R[2], tec="Document Intelligence Read")

    # Workers de orquestación
    p.limite("Workers de orquestación", "Container Apps", 880, 270, 880, 490)
    p.c4("wclas", "componente", "Worker de clasificación", "Llama al clasificador, valida los segmentos y aplica los umbrales de confianza.", C[3], R[1], tec="Python")
    p.c4("conector", "hexagono", "Conector del clasificador", "Llamada por archivo con PDF, nombre y ruta de origen.", C[4], R[1], tec="API HTTP")
    p.c4("repro", "componente", "Comando reprocesar", "Vuelve a encolar un segmento o un proceso y registra quién y por qué.", C[5], R[1], tec="Python")
    p.c4("wres", "componente", "Worker de resultados y estado", "Guarda cada resultado, decide si el oferente está completo y aplica correcciones.", C[3], R[2], tec="Python")
    p.c4("reglas", "componente", "Motor de reglas (módulo 4)", "Aplica las reglas del proceso, escritas como datos, contra la ficha del proceso. Sin LLM.", C[4], R[2], tec="Python")
    p.c4("tareas", "componente", "Tareas e informe", "Crea una tarea por oferente y área y genera el informe en Excel.", C[5], R[2], tec="Python, openpyxl")
    p.c4("dataverse", "hexagono", "Integración Dataverse", "Tareas hacia la Power App y correcciones de vuelta.", C[6], R[2], tec="Dataverse + Service Bus")

    # Unidad de extracción
    p.limite("Unidad de extracción", "Container Apps", 580, 830, 880, 210)
    p.c4("pre", "componente", "Preprocesamiento", "Toma las páginas del segmento desde la lectura y arma texto, imágenes y recortes de firma.", C[2], R[3], tec="Python")
    p.c4("agente", "componente", "Agente de extracción", "Extrae los campos con su evidencia siguiendo la ficha del tipo documental.", C[3], R[3], tec="Agente Foundry, gpt-5.4")
    p.c4("posval", "componente", "Posvalidación", "Valida con código (NIT, fechas, sumas) y decide qué va a revisión humana.", C[4], R[3], tec="Python")

    flechas_personas(p, "repro", entra_op=(0.25, 0))
    p.flecha("modulo1", "norm", "Avisa entrega lista", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("norm", "lector", "PDF normalizado")
    p.flecha("lector", "ocr", "Pide OCR", sale=(0, 0.5), entra=(1, 0.5))
    p.flecha("lector", "blob", "Guarda PDF<br>y lectura")
    p.flecha("norm", "sb", "Archivo listo", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("sb", "wclas", "Archivo a clasificar", sale=(1, 0.25), entra=(0, 0.25))
    p.flecha("wclas", "sb", "Segmentos<br>a extraer", sale=(0, 0.65), entra=(1, 0.65))
    p.flecha("wclas", "conector", "Clasifica", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("conector", "clasificador", "Llama API", sale=(0.5, 0), entra=(0.5, 1))
    p.flecha("sb", "wres", "Resultados y<br>correcciones", sale=(0.85, 1), entra=(0, 0.5), puntos=[(804, 620)])
    p.flecha("sb", "pre", "Segmento", sale=(0.2, 1), entra=(0.2, 0))
    p.flecha("posval", "sb", "Resultado", sale=(0.25, 0), entra=(0.5, 1), puntos=[(1260, 810), (720, 810)])
    p.flecha("repro", "sb", "Reencola", sale=(0.75, 0), entra=(0.5, 0), puntos=[(1680, 230), (720, 230)])
    p.flecha("pre", "blob", "Lee páginas", sale=(0, 0.5), entra=(1, 0.5))
    p.flecha("pre", "agente", "Texto e imágenes", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("agente", "posval", "Campos con<br>evidencia", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("agente", "foundry", "Interpreta", sale=(0.3, 1), entra=(0.3, 0))
    p.flecha("agente", "mcp", "Consulta la ficha", sale=(0.75, 1), entra=(0, 0.5), puntos=[(1080, 1200)])
    p.flecha("wres", "cosmos", "Guarda estado", sale=(0.5, 1), entra=(0.75, 0), puntos=[(1020, 775), (1980, 775)])
    p.flecha("wres", "reglas", "Oferente completo", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("reglas", "cosmos", "Lee datos, ficha<br>y reglas", sale=(0.75, 1), entra=(0.25, 0), puntos=[(1380, 795), (1860, 795)])
    p.flecha("reglas", "tareas", "Veredictos", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("tareas", "dataverse", "Escribe tareas<br>e informe", sale=(1, 0.5), entra=(0, 0.5))
    p.flecha("dataverse", "powerapp", "Tareas", sale=(1, 0.35), entra=(0, 0.35))
    p.flecha("powerapp", "dataverse", "Correcciones", sale=(0, 0.75), entra=(1, 0.65))
    p.flecha("dataverse", "sb", "Correcciones", sale=(0.5, 0), entra=(0.75, 0), puntos=[(1900, 255), (780, 255)])
    flechas_almacenes_comunes(p)
    return p


# ---------- Secuencia ----------
def secuencia(mx):
    p = Pagina(mx, "Secuencia - Un documento de punta a punta", "s1")
    p.secuencia(
        "Secuencia · Un documento de punta a punta",
        [("m1", "Módulo 1"), ("job", "Normalización y lectura"), ("sb", "Service Bus"), ("orq", "Orquestación"),
         ("cla", "Clasificador"), ("ext", "Unidad de extracción"), ("llm", "gpt-5.4 (Foundry)"),
         ("app", "Power App"), ("eva", "Evaluador")],
        [
            ("m", "m1", "job", "Entrega lista"),
            ("m", "job", "job", "Normaliza y lee"),
            ("m", "job", "sb", "Archivo listo"),
            ("m", "sb", "orq", "Archivo a clasificar"),
            ("m", "orq", "cla", "Clasificar archivo"),
            ("r", "cla", "orq", "Segmentos + confianza"),
            ("nota", "Confianza baja: tarea humana de clasificación, no se extrae.", 60),
            ("marco", "loop: por segmento", 6),
            ("m", "orq", "sb", "Segmento a extraer"),
            ("m", "sb", "ext", "Segmento"),
            ("m", "ext", "llm", "Ficha + páginas"),
            ("r", "llm", "ext", "Campos con evidencia"),
            ("m", "ext", "ext", "Posvalidación"),
            ("m", "ext", "sb", "Resultado"),
            ("m", "sb", "orq", "Resultado"),
            ("nota", "Las reglas corren cuando el oferente no tiene pendientes y la ficha del proceso está confirmada.", 80),
            ("m", "orq", "orq", "Reglas del oferente"),
            ("m", "orq", "app", "Tareas de revisión"),
            ("m", "eva", "app", "Confirma o corrige"),
            ("r", "app", "orq", "Corrección (Service Bus)"),
            ("m", "orq", "orq", "Recalcula reglas"),
        ],
    )
    return p


if __name__ == "__main__":
    mx = nuevo_archivo(4)
    paginas = [nivel1(mx), nivel2(mx), nivel3(mx), secuencia(mx)]
    guardar(mx, paginas, OUT)
    print(OUT)
