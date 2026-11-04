# Imagen del job de normalización y lectura (Container Apps Job, decisión 16).
#
# Se construye desde la raíz del repositorio, porque la etapa de pruebas necesita
# el contrato (contracts/modulo3-normalizacion/v0):
#
#   docker build -f servicios/normalizacion/Dockerfile --target job -t normalizacion .
#   docker build -f servicios/normalizacion/Dockerfile --target pruebas -t normalizacion-pruebas .
#   docker run --rm normalizacion-pruebas
#
# Etapas:
#   base    Ubuntu 24.04 con Python 3.12, LibreOffice 24.2 (Writer y Calc, sin
#           interfaz), fuentes y uv.
#   pruebas base + dependencias de desarrollo, pruebas y contrato. Corre pytest.
#   job     base + solo las dependencias del paquete. Corre `normalizar`.
#
# Ubuntu 24.04 y no python:3.12-slim (Debian), como decía el plan: ver las notas
# de T12 en specs/003-validacion-extraccion/tasks.md.

# Se puede cambiar por un espejo de Docker Hub, por ejemplo:
#   --build-arg BASE_IMAGE=mirror.gcr.io/library/ubuntu:24.04
ARG BASE_IMAGE=ubuntu:24.04

# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS base

ARG UV_VERSION=0.11.32

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=/usr/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# LibreOffice sin interfaz gráfica (las variantes -nogui pesan menos). Fuentes con
# las mismas medidas que las de Office, para que los Word y Excel conserven su
# paginación al convertirse: Liberation (Arial, Times New Roman, Courier New),
# Carlito (Calibri) y Caladea (Cambria). Sin ellas el texto sale más ancho y se
# sale de la página.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        python3.12 \
        python3-pip \
        libreoffice-writer-nogui \
        libreoffice-calc-nogui \
        fonts-liberation \
        fonts-crosextra-carlito \
        fonts-crosextra-caladea \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && soffice --version

# uv desde PyPI, con la misma versión que se usa en desarrollo.
RUN /usr/bin/python3.12 -m pip install --no-cache-dir --break-system-packages "uv==${UV_VERSION}"

WORKDIR /app/servicios/normalizacion

# Primero las dependencias (capa que cambia poco), después el código.
COPY servicios/normalizacion/pyproject.toml servicios/normalizacion/uv.lock servicios/normalizacion/.python-version ./

# ---------------------------------------------------------------------------
FROM base AS pruebas

RUN uv sync --frozen --no-install-project
COPY contracts/modulo3-normalizacion /app/contracts/modulo3-normalizacion
COPY servicios/normalizacion/src ./src
COPY servicios/normalizacion/tests ./tests
RUN uv sync --frozen

CMD ["pytest", "-q", "-p", "no:cacheprovider"]

# ---------------------------------------------------------------------------
FROM base AS job

RUN uv sync --frozen --no-dev --no-install-project
COPY servicios/normalizacion/src ./src
RUN uv sync --frozen --no-dev --no-editable \
    && /usr/bin/python3.12 -m pip uninstall -y --break-system-packages uv

# Usuario sin privilegios. LibreOffice usa un perfil temporal por conversión, en /tmp.
RUN useradd --uid 10001 --create-home --home-dir /home/normalizador normalizador
USER normalizador
ENV HOME=/home/normalizador
WORKDIR /home/normalizador

ENTRYPOINT ["normalizar"]
CMD ["--help"]
