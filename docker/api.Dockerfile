# syntax=docker/dockerfile:1.7
# NotAI - immagine API FastAPI. Multi-stage: builder (uv) -> runtime slim non-root.

ARG PYTHON_VERSION=3.12

# -----------------------------------------------------------------------------
# Stage 1: builder - installa dipendenze in un venv riusabile
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# uv per install veloce e riproducibile
RUN pip install --no-cache-dir uv==0.4.27

WORKDIR /build

COPY pyproject.toml ./

# Crea venv e installa dipendenze runtime.
# Evitiamo process substitution `<(...)` (bash-only) usando un file intermedio,
# così funziona anche con /bin/sh (dash) di python:slim.
RUN uv venv /opt/venv && \
    uv pip compile pyproject.toml --quiet -o /tmp/requirements.txt && \
    uv pip install --no-cache --python /opt/venv/bin/python -r /tmp/requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: runtime - immagine snella, utente non-root
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=Europe/Rome

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tini \
      curl \
      wget \
      ca-certificates \
      libpq5 \
      tzdata && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r notai && useradd -r -g notai -d /app -s /usr/sbin/nologin notai

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Codice applicativo
COPY --chown=notai:notai notai ./notai
COPY --chown=notai:notai apps ./apps
COPY --chown=notai:notai migrations ./migrations
COPY --chown=notai:notai alembic.ini ./alembic.ini
COPY --chown=notai:notai pyproject.toml ./pyproject.toml

USER notai

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=10 \
  CMD wget -qO- http://localhost:8000/health || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
