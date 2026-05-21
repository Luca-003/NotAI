#!/usr/bin/env bash
# NotAI - Smoke test Fase 1.
# Verifica:
#   1. Bootstrap di 2 tenant
#   2. Ognuno crea una pratica
#   3. Cross-tenant isolation (RLS)
#   4. Audit chain verification via CLI

set -euo pipefail
API="${API:-http://localhost:8000}"

green()  { printf "\033[32m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
log() { yellow "==> $*"; }

NOW=$(date +%s)
SLUG_A="alfa-$NOW"
SLUG_B="beta-$NOW"

bootstrap() {
  local slug="$1"
  curl -fsS -X POST "$API/api/v1/dev/bootstrap" \
    -H "Content-Type: application/json" \
    -d "{\"slug\":\"$slug\",\"name\":\"Studio $slug\",\"kind\":\"misto\",\"admin_email\":\"admin@$slug.test\",\"admin_display_name\":\"Admin $slug\"}"
}

log "Bootstrap tenant A ($SLUG_A)"
A_BOOT=$(bootstrap "$SLUG_A")
TID_A=$(echo "$A_BOOT" | python3 -c "import sys,json;print(json.load(sys.stdin)['tenant_id'])")
TOK_A=$(echo "$A_BOOT" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "  tenant_id_A=$TID_A"

log "Bootstrap tenant B ($SLUG_B)"
B_BOOT=$(bootstrap "$SLUG_B")
TID_B=$(echo "$B_BOOT" | python3 -c "import sys,json;print(json.load(sys.stdin)['tenant_id'])")
TOK_B=$(echo "$B_BOOT" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "  tenant_id_B=$TID_B"

create_practice() {
  local token="$1" code="$2" kind="$3" title="$4"
  curl -fsS -X POST "$API/api/v1/practices" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $token" \
    -d "{\"code\":\"$code\",\"kind\":\"$kind\",\"title\":\"$title\"}"
}

log "Tenant A crea pratica"
PA=$(create_practice "$TOK_A" "P/A/$NOW" "notarile.compravendita" "Atto A")
PA_ID=$(echo "$PA" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  practice_A=$PA_ID"

log "Tenant B crea pratica"
PB=$(create_practice "$TOK_B" "P/B/$NOW" "legale.civile" "Atto B")
PB_ID=$(echo "$PB" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  practice_B=$PB_ID"

log "Verifica cross-tenant: A NON deve vedere la pratica di B"
A_LIST=$(curl -fsS "$API/api/v1/practices" -H "Authorization: Bearer $TOK_A")
if echo "$A_LIST" | python3 -c "import sys,json; sys.exit(0 if '$PB_ID' not in [p['id'] for p in json.load(sys.stdin)] else 1)"; then
  green "  [ok] tenant A non vede la pratica di B nella list"
else
  red "  [KO] RLS LEAK: tenant A vede la pratica di B!"
  exit 1
fi

log "Verifica cross-tenant: GET diretto su pratica B con token A -> 404"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$API/api/v1/practices/$PB_ID" -H "Authorization: Bearer $TOK_A")
if [ "$STATUS" = "404" ]; then
  green "  [ok] HTTP 404 (RLS nasconde la risorsa)"
else
  red "  [KO] RLS LEAK: GET di B con token A torna HTTP $STATUS (atteso 404)"
  exit 1
fi

log "Verifica catena audit per tenant A (via CLI)"
docker compose -f compose.yml -f compose.dev.yml exec -T notai-api \
  python -m apps.cli.audit_verify --tenant "$TID_A"

log "Verifica catena audit per tenant B (via CLI)"
docker compose -f compose.yml -f compose.dev.yml exec -T notai-api \
  python -m apps.cli.audit_verify --tenant "$TID_B"

green "==> Smoke Fase 1 PASSED"
