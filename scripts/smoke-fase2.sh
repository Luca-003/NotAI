#!/usr/bin/env bash
# NotAI - Smoke test Fase 2.
# Verifica workflow Atto end-to-end:
#   1. Bootstrap tenant + practice
#   2. Crea Atto (compravendita)
#   3. Start workflow Temporal (visure mock + draft + tax + review_requested)
#   4. Aspetta che il workflow arrivi in stato 'review_requested'
#   5. Invia signal human_review (approved)
#   6. Aspetta status 'review_completed'
#   7. Verifica catena audit per l'atto

set -euo pipefail
API="${API:-http://localhost:8000}"

green()  { printf "\033[32m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
log() { yellow "==> $*"; }

NOW=$(date +%s)
SLUG="atto-$NOW"

log "Bootstrap tenant $SLUG"
BOOT=$(curl -fsS -X POST "$API/api/v1/dev/bootstrap" \
  -H "Content-Type: application/json" \
  -d "{\"slug\":\"$SLUG\",\"name\":\"Studio $SLUG\",\"kind\":\"notarile\",\"admin_email\":\"a@$SLUG.test\",\"admin_display_name\":\"A\"}")
TID=$(echo "$BOOT" | python3 -c "import sys,json;print(json.load(sys.stdin)['tenant_id'])")
TOK=$(echo "$BOOT" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "  tenant_id=$TID"

log "Crea pratica"
PR=$(curl -fsS -X POST "$API/api/v1/practices" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"code":"P/'$NOW'/001","kind":"notarile.compravendita.immobiliare","title":"Compravendita test"}')
PID=$(echo "$PR" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  practice_id=$PID"

log "Crea atto"
ACT=$(curl -fsS -X POST "$API/api/v1/acts" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"practice_id":"'$PID'","kind":"notarile.compravendita.immobiliare","title":"Atto compravendita"}')
AID=$(echo "$ACT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  act_id=$AID"

log "Start workflow"
START=$(curl -fsS -X POST "$API/api/v1/acts/$AID/workflow/start" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{
    "template_id":"notarile.compravendita.immobiliare:v1",
    "base_imponibile":250000,
    "is_prima_casa":true,
    "parties":[
      {"role":"venditore","kind":"PF","fiscal_code":"RSSMRA70A01F205X"},
      {"role":"acquirente","kind":"PF","fiscal_code":"BNCLCA85B05H501Y"}
    ]
  }')
WFID=$(echo "$START" | python3 -c "import sys,json;print(json.load(sys.stdin)['workflow_id'])")
echo "  workflow_id=$WFID"

log "Attendo che il workflow arrivi a 'review_requested'..."
DEADLINE=$(( $(date +%s) + 90 ))
while true; do
  ST=$(curl -fsS "$API/api/v1/acts/$AID/workflow/status" -H "Authorization: Bearer $TOK" || echo "{}")
  STATUS=$(echo "$ST" | python3 -c "import sys,json;d=json.load(sys.stdin);print((d.get('state') or {}).get('status') or '-')" 2>/dev/null || echo "-")
  if [ "$STATUS" = "review_requested" ]; then
    green "  [ok] workflow stato=$STATUS"
    break
  fi
  if [ "$(date +%s)" -gt "$DEADLINE" ]; then
    red "  [KO] timeout (stato attuale=$STATUS)"
    echo "$ST" | python3 -m json.tool
    exit 1
  fi
  sleep 2
done

log "Invia signal human_review (approved)"
curl -fsS -X POST "$API/api/v1/acts/$AID/workflow/human-review" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"decision":"approved","notes":"OK procediamo"}' >/dev/null
green "  signal inviato"

log "Attendo stato 'review_completed'..."
DEADLINE=$(( $(date +%s) + 30 ))
while true; do
  ST=$(curl -fsS "$API/api/v1/acts/$AID/workflow/status" -H "Authorization: Bearer $TOK" || echo "{}")
  STATUS=$(echo "$ST" | python3 -c "import sys,json;d=json.load(sys.stdin);print((d.get('state') or {}).get('status') or '-')" 2>/dev/null || echo "-")
  if [ "$STATUS" = "review_completed" ]; then
    green "  [ok] workflow stato=$STATUS"
    break
  fi
  if [ "$(date +%s)" -gt "$DEADLINE" ]; then
    red "  [KO] timeout (stato attuale=$STATUS)"
    exit 1
  fi
  sleep 2
done

log "Stampa stato finale workflow"
curl -fsS "$API/api/v1/acts/$AID/workflow/status" -H "Authorization: Bearer $TOK" | python3 -m json.tool

log "Verifica catena audit per atto"
docker compose -f compose.yml -f compose.dev.yml exec -T notai-api \
  python -m apps.cli.audit_verify --tenant "$TID" --stream "act:$AID"

green "==> Smoke Fase 2 PASSED"
