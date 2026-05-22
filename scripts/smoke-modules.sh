#!/usr/bin/env bash
# Smoke test moduli: bootstrap, list, toggle, enforcement 403.
set -euo pipefail
API="${API:-http://localhost:8000}"

green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
log()   { printf "\033[33m==> %s\033[0m\n" "$*"; }

NOW=$(date +%s)
SLUG="mod-$NOW"

log "Bootstrap tenant"
BOOT=$(curl -fsS -X POST "$API/api/v1/dev/bootstrap" \
  -H "Content-Type: application/json" \
  --data-binary @- <<JSON
{"slug":"$SLUG","name":"Studio $SLUG","kind":"notarile","admin_email":"a@$SLUG.test","admin_display_name":"A"}
JSON
)
TOK=$(echo "$BOOT" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

log "GET /modules - elenca tutti i moduli"
LIST=$(curl -fsS "$API/api/v1/modules" -H "Authorization: Bearer $TOK")
echo "$LIST" | python3 -c "import sys,json;d=json.load(sys.stdin);print(f\"  totale moduli: {d['count']}\"); [print(f\"  - [{m['category']:14s}] {m['id']:40s} enabled={m['enabled']} essential={m['essential']}\") for m in d['modules'][:8]]; print('  ...')"

N=$(echo "$LIST" | python3 -c "import sys,json;print(json.load(sys.stdin)['count'])")
if [ "$N" -lt 15 ]; then
  red "[KO] meno di 15 moduli nel registry ($N)"; exit 1
fi
green "[ok] $N moduli registrati"

log "PUT /modules/notaio.workflow {enabled:false} - disattivo workflow"
curl -fsS -X PUT "$API/api/v1/modules/notaio.workflow" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"enabled":false,"note":"smoke test"}' | python3 -m json.tool

log "Verifica enforcement: start workflow su nuovo atto deve dare 403"
PR=$(curl -fsS -X POST "$API/api/v1/practices" -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"code":"P/M/'$NOW'","kind":"notarile.compravendita","title":"Test moduli"}')
PID=$(echo "$PR" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
ACT=$(curl -fsS -X POST "$API/api/v1/acts" -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d "{\"practice_id\":\"$PID\",\"kind\":\"notarile.compravendita\",\"title\":\"X\"}")
AID=$(echo "$ACT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

STATUS=$(curl -s -o /tmp/notai-403.json -w "%{http_code}" \
  -X POST "$API/api/v1/acts/$AID/workflow/start" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"template_id":"x:v1","base_imponibile":100,"is_prima_casa":false,"parties":[]}')
echo "  HTTP $STATUS"
cat /tmp/notai-403.json | python3 -m json.tool 2>&1 | head -10
if [ "$STATUS" != "403" ]; then
  red "[KO] atteso 403 quando modulo disattivato, ricevuto $STATUS"; exit 1
fi
green "[ok] HTTP 403 con detail strutturato"

log "Tentativo disattivare modulo essenziale (core.audit) - deve dare 409"
S=$(curl -s -o /tmp/notai-409.json -w "%{http_code}" \
  -X PUT "$API/api/v1/modules/core.audit" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"enabled":false}')
echo "  HTTP $S"
if [ "$S" != "409" ]; then
  red "[KO] atteso 409 disattivando core.audit, ricevuto $S"; exit 1
fi
green "[ok] HTTP 409 - modulo essenziale protetto"

log "Riattivo workflow e ritento start - deve passare"
curl -fsS -X PUT "$API/api/v1/modules/notaio.workflow" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"enabled":true}' >/dev/null
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$API/api/v1/acts/$AID/workflow/start" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"template_id":"x:v1","base_imponibile":100,"is_prima_casa":false,"parties":[]}')
if [ "$STATUS" != "202" ]; then
  red "[KO] atteso 202 dopo riattivazione, ricevuto $STATUS"; exit 1
fi
green "[ok] HTTP 202 dopo riattivazione"

green "==> Smoke moduli PASSED"
