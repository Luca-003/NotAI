# syntax=docker/dockerfile:1.7
# NotAI - immagine RPA Playwright (browser headful via Xvfb, OCR italiano).

FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Rome \
    DEBIAN_FRONTEND=noninteractive

# OCR italiano + font giuridici + tini
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tini \
      tesseract-ocr \
      tesseract-ocr-ita \
      fonts-liberation \
      fonts-dejavu \
      fonts-noto \
      xvfb \
      libpq5 \
      ca-certificates \
      tzdata && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.4.27
RUN groupadd -r notai && useradd -r -g notai -d /app -s /usr/sbin/nologin notai && \
    mkdir -p /app && chown -R notai:notai /app

WORKDIR /app

COPY --chown=notai:notai pyproject.toml ./
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache -r <(uv pip compile pyproject.toml --quiet) && \
    chown -R notai:notai /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=notai:notai notai ./notai
COPY --chown=notai:notai apps ./apps

USER notai

ENTRYPOINT ["tini", "--"]
# Avvia Xvfb + worker RPA
CMD ["bash", "-c", "Xvfb :99 -screen 0 1920x1080x24 & DISPLAY=:99 python -m apps.workers.rpa_main"]
