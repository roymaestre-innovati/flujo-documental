# Imagen liviana de los workers que no necesitan LibreOffice (T10 de
# specs/005-orquestador/tasks-workers.md): apertura, clasificar y extracción.
# El worker de normalizar usa la imagen de servicios/normalizacion/Dockerfile,
# etapa `worker`, que trae LibreOffice.
#
# Se construye desde la raíz del repositorio:
#
#   docker build -f servicios/workers/Dockerfile -t workers .
#
# Cada job elige su comando (en Azure, en la definición del job):
#
#   orquestar-worker apertura
#   orquestar-worker clasificar
#   extraer-worker --hilos 3
#   orquestar-operar escalar-fallas
#
# El orquestador y la extracción van en entornos separados (/opt/orquestador y
# /opt/extraccion): cada uno con sus dependencias y su lock, y la extracción sin
# las del orquestador. Los esquemas de los contratos van en /app/contracts.

ARG BASE_IMAGE=python:3.12-slim-bookworm

FROM ${BASE_IMAGE}

ARG UV_VERSION=0.11.32

ENV LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    ORQUESTADOR_CONTRATOS=/app/contracts \
    EXTRACCION_CONTRATOS=/app/contracts

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

WORKDIR /app
COPY contracts/modulo5-orquestador /app/contracts/modulo5-orquestador
COPY contracts/modulo3-extraccion /app/contracts/modulo3-extraccion
COPY servicios/normalizacion /app/servicios/normalizacion
COPY servicios/mensajeria /app/servicios/mensajeria
COPY servicios/orquestador /app/servicios/orquestador
COPY servicios/extraccion /app/servicios/extraccion

RUN cd /app/servicios/orquestador \
    && UV_PROJECT_ENVIRONMENT=/opt/orquestador uv sync --frozen --no-dev --no-editable \
    && cd /app/servicios/extraccion \
    && UV_PROJECT_ENVIRONMENT=/opt/extraccion uv sync --frozen --no-dev --no-editable \
    && pip uninstall -y uv \
    && rm -rf /app/servicios \
    && ln -s /opt/orquestador/bin/orquestar-worker /opt/orquestador/bin/orquestar-operar /usr/local/bin/ \
    && ln -s /opt/extraccion/bin/extraer-worker /usr/local/bin/

RUN useradd --uid 10001 --create-home --home-dir /home/worker worker
USER worker
ENV HOME=/home/worker
WORKDIR /home/worker

CMD ["orquestar-worker", "--help"]
