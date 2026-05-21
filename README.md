# NotAI

Piattaforma di automazione per studi notarili e legali italiani.
Workflow engine, audit forense, tagging semantico, integrazione portali pubblici,
AI locale con vincolo di **zero-allucinazione** (in caso di dubbio: passaggio al professionista).

## Quick start (dev)

Prerequisiti: Docker Desktop 4.30+, ~16 GB RAM, ~30 GB disco libero.

```bash
cp .env.example .env
# Modifica le password "change_me_*" in .env
docker compose -f compose.yml -f compose.dev.yml up -d
```

### LLM locale: opzioni

**Opzione A — Ollama sul host (consigliata in dev su Windows/Mac):**
```powershell
# Una tantum: installa modelli su Ollama (https://ollama.com)
ollama pull qwen2.5:7b-instruct
ollama pull bge-m3

# Aggiungi l'override per puntare LiteLLM a Ollama
docker compose -f compose.yml -f compose.dev.yml -f compose.ollama.yml up -d litellm
```

**Opzione B — llama.cpp container (richiede un .gguf in `llama-cpp-models` volume):**
```bash
docker compose -f compose.yml -f compose.dev.yml --profile llm up -d
```

**Opzione C — vLLM su GPU NVIDIA:**
```bash
docker compose -f compose.yml -f compose.dev.yml -f compose.gpu.yml up -d
```

Apri:

- Web app: <http://localhost:5173>
- API: <http://localhost:8000/health>
- Temporal UI: <http://localhost:8088>
- MinIO console: <http://localhost:9001>
- OpenSearch dashboards: <http://localhost:5601>
- Qdrant UI: <http://localhost:6333/dashboard>
- Vault UI: <http://localhost:8200>

## Stack containerizzato

| Servizio | Porta dev | Scopo |
|---|---|---|
| `postgres` | 5432 | DB principale + audit event store (immutable trigger) |
| `temporal` | 7233 | Workflow engine (long-running, human-in-the-loop) |
| `temporal-ui` | 8088 | Web UI Temporal |
| `minio` | 9000 / 9001 | Object storage WORM per documenti |
| `opensearch` | 9200 | Full-text search + facet su clausole |
| `qdrant` | 6333 | Vector DB per RAG |
| `vault` | 8200 | Secret store (credenziali portali, chiavi audit) |
| `litellm` | 4000 | Gateway LLM unificato |
| `llama-cpp` | 8080 | LLM CPU fallback per dev senza GPU |
| `vllm` | 8001 | LLM GPU (solo profilo gpu) |
| `notai-api` | 8000 | FastAPI |
| `notai-workers` | - | Temporal worker (workflow + AI + RPA) |
| `notai-web` | 5173 (dev) / 80 (prod) | React frontend |
| `caddy` | 80 / 443 | Reverse proxy + TLS automatico |
| `otel-collector` | 4317 | Trace/metrics/logs collector |

## Layout

```
notai/
  contexts/    # bounded contexts (workflow, audit, ai, drafting, ...)
  shared/      # tenancy, events, errors
apps/
  api/         # FastAPI entrypoint
  workers/     # Temporal worker entrypoint
  web/         # React + Vite
docker/        # Dockerfile + config servizi
migrations/    # Alembic
scripts/       # smoke test, util
tests/         # unit + e2e
```

## Principi architetturali

- **Multi-tenant ready dal day-one** (RLS Postgres, `tenant_id` su tutte le entità) anche se MVP è single-studio on-premise.
- **Audit forense**: ogni evento è append-only con hash chain SHA-256 + timestamp RFC 3161.
- **Zero-allucinazione AI**: deterministico → LLM locale vincolato (structured output + citation grounded) → astensione → professionista. Mai testo giuridico senza fonte. Mai numeri da LLM.
- **Containerizzazione totale**: stessa immagine attraversa dev/staging/prod.

Vedi `C:\Users\luca.pietrini\.claude\plans\vorrei-crare-un-software-staged-harp.md` per il piano completo.
