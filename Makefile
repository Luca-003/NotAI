# NotAI - Makefile (uso su Linux/macOS o Git Bash su Windows).
# Su PowerShell puro usare i comandi `docker compose ...` direttamente.

SHELL := /bin/bash
COMPOSE_BASE := -f compose.yml
COMPOSE_DEV := $(COMPOSE_BASE) -f compose.dev.yml
COMPOSE_GPU := $(COMPOSE_DEV) -f compose.gpu.yml
COMPOSE_PROD := $(COMPOSE_BASE) -f compose.prod.yml

.PHONY: help up up-gpu down ps logs build smoke migrate seed-demo lint test e2e clean

help:
	@echo "NotAI - target principali:"
	@echo "  make up         - avvia stack dev (CPU LLM fallback)"
	@echo "  make up-gpu     - avvia stack dev con vLLM su GPU"
	@echo "  make down       - ferma stack"
	@echo "  make ps         - stato container"
	@echo "  make logs       - segui log"
	@echo "  make build      - rebuild immagini"
	@echo "  make smoke      - esegue smoke test end-to-end"
	@echo "  make migrate    - applica migrazioni Alembic"
	@echo "  make seed-demo  - carica dataset demo"
	@echo "  make lint       - ruff + mypy"
	@echo "  make test       - pytest unit"
	@echo "  make e2e        - pytest E2E + Playwright"
	@echo "  make clean      - rimuovi volumi (DISTRUTTIVO)"

up:
	docker compose $(COMPOSE_DEV) up -d

up-gpu:
	docker compose $(COMPOSE_GPU) up -d

down:
	docker compose $(COMPOSE_DEV) down

ps:
	docker compose $(COMPOSE_DEV) ps

logs:
	docker compose $(COMPOSE_DEV) logs -f --tail=200

build:
	docker compose $(COMPOSE_DEV) build

smoke:
	bash scripts/smoke-test.sh

migrate:
	docker compose $(COMPOSE_DEV) run --rm notai-migrator

seed-demo:
	docker compose $(COMPOSE_DEV) exec notai-api python -m apps.api.seed_demo

lint:
	ruff check .
	mypy notai apps

test:
	pytest tests/unit

e2e:
	pytest tests/e2e

clean:
	docker compose $(COMPOSE_DEV) down -v
