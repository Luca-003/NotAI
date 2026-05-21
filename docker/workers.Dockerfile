# syntax=docker/dockerfile:1.7
# NotAI - immagine workers (Temporal). Riusa lo stesso layer di api.Dockerfile.

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir uv==0.4.27

WORKDIR /build
COPY pyproject.toml ./

RUN uv venv /opt/venv && \
    uv pip compile pyproject.toml --quiet -o /tmp/requirements.txt && \
    uv pip install --no-cache --python /opt/venv/bin/python -r /tmp/requirements.txt

FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=Europe/Rome

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tini \
      curl \
      ca-certificates \
      libpq5 \
      tzdata && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r notai && useradd -r -g notai -d /app -s /usr/sbin/nologin notai

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=notai:notai notai ./notai
COPY --chown=notai:notai apps ./apps
COPY --chown=notai:notai pyproject.toml ./pyproject.toml

USER notai

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "apps.workers.main"]
