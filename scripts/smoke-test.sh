#!/usr/bin/env bash
# NotAI - smoke test: verifica che lo stack containerizzato sia raggiungibile e sano.
# Esegue contro lo stack avviato con `make up`.

set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
MINIO_BASE="${MINIO_BASE:-http://localhost:9000}"
QDRANT_BASE="${QDRANT_BASE:-http://localhost:6333}"
TEMPORAL_UI="${TEMPORAL_UI:-http://localhost:8088}"
TIMEOUT="${TIMEOUT:-300}"

red()    { printf "\033[31m%s\033[0m\n" "$*"; }
green()  { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }

wait_for() {
  local name="$1"
  local url="$2"
  local end=$(( SECONDS + TIMEOUT ))
  while (( SECONDS < end )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      green "[ok] $name pronto ($url)"
      return 0
    fi
    sleep 3
  done
  red "[KO] $name non pronto entro ${TIMEOUT}s ($url)"
  return 1
}

yellow "==> NotAI smoke test (timeout ${TIMEOUT}s)"

wait_for "api /health"        "$API_BASE/health"
wait_for "api /readyz"        "$API_BASE/readyz"
wait_for "minio live"         "$MINIO_BASE/minio/health/live"
wait_for "qdrant readyz"      "$QDRANT_BASE/readyz"
wait_for "temporal-ui"        "$TEMPORAL_UI"

# Verifica che /readyz riporti almeno 'ok' globale
ready=$(curl -fsS "$API_BASE/readyz")
status=$(echo "$ready" | python -c "import sys,json; print(json.load(sys.stdin)['status'])")
if [[ "$status" == "ok" ]]; then
  green "[ok] /readyz globale = ok"
else
  red "[KO] /readyz globale = $status"
  echo "$ready"
  exit 1
fi

green "==> smoke test passato"
