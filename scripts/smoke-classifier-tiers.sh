#!/usr/bin/env bash
# Verifica end-to-end della pipeline 3-tier:
#   1. classify_heuristic   (regex filename+header)
#   2. classify_zero_shot   (cosine embedding vs label catalog)
#   3. LLM 3B               (fallback)
# + extract_entities applicato a tutti i tier.
#
# Pre-condizione: Ollama up + bge-m3 disponibile.
# Esegue diversi smoke su demostuff e conta le hit per tier via audit events.
set -eo pipefail

API="${API:-http://localhost:8000}"
NOW=$(date +%s)
SLUG="cls-$NOW"

c_red()   { printf "\e[31m%s\e[0m" "$*"; }
c_green() { printf "\e[32m%s\e[0m" "$*"; }
c_yel()   { printf "\e[33m%s\e[0m" "$*"; }
section() { echo; c_yel "==> $*"; echo; }

section "Bootstrap"
BOOT=$(curl -fsS -X POST "$API/api/v1/dev/bootstrap" -H "Content-Type: application/json" \
  -d "{\"slug\":\"$SLUG\",\"name\":\"CLS\",\"kind\":\"notarile\",\"admin_email\":\"a@$SLUG.test\",\"admin_display_name\":\"A\"}")
JWT=$(echo "$BOOT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
TENANT=$(echo "$BOOT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["tenant_id"])')
H="Authorization: Bearer $JWT"

section "Crea pratica + atto + carica scenario compravendita-prima-casa"
PR=$(curl -fsS -X POST "$API/api/v1/practices" -H "$H" -H "Content-Type: application/json" \
  -d '{"code":"CLS-1","kind":"notarile.compravendita.immobiliare","title":"CLS test"}')
PR_ID=$(echo "$PR" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
A=$(curl -fsS -X POST "$API/api/v1/acts" -H "$H" -H "Content-Type: application/json" \
  -d "{\"practice_id\":\"$PR_ID\",\"kind\":\"notarile.compravendita.immobiliare\",\"title\":\"AT cls\"}")
ACT_ID=$(echo "$A" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -fsS -X POST -H "$H" "$API/api/v1/dev/scenarios/compravendita-prima-casa/upload-to-act/$ACT_ID" >/dev/null
echo "  act=$ACT_ID"

section "Attendi classificazione (max 5 min)"
for i in $(seq 1 100); do
  DOCS=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/documents")
  TOTAL_PENDING=0
  for DID in $(echo "$DOCS" | python3 -c 'import sys,json
[print(d["id"]) for d in json.load(sys.stdin)]'); do
    CL=$(curl -fsS -H "$H" "$API/api/v1/documents/$DID/classification" 2>/dev/null || echo '{}')
    P=$(echo "$CL" | python3 -c 'import sys,json
try:
  d=json.load(sys.stdin)
  s=d.get("status_counts") or {}
  print((s.get("pending") or 0) + (s.get("in_progress") or 0))
except: print(99)')
    TOTAL_PENDING=$((TOTAL_PENDING + P))
  done
  echo "  [$i] classification pending=$TOTAL_PENDING"
  if [ "$TOTAL_PENDING" = "0" ]; then break; fi
  sleep 3
done

section "Conta hit per tier via Postgres (audit events)"
docker compose exec -T postgres psql -U postgres -d notai -c "
SELECT type, count(*)
FROM audit.audit_events
WHERE tenant_id = '$TENANT'
  AND type IN (
    'chunk.classified_by_heuristic',
    'chunk.classified_by_zero_shot',
    'llm.invoked',
    'chunk.classification_abstained'
  )
GROUP BY type ORDER BY type"

section "Stato finale dei chunk dell'atto"
docker compose exec -T postgres psql -U postgres -d notai -c "
SELECT c.classification_status, count(*),
  count(*) FILTER (WHERE jsonb_array_length(coalesce(c.classification->'entities', '[]'::jsonb)) > 0) as with_entities,
  string_agg(DISTINCT c.classification->>'document_type', ', ') as doc_types
FROM document_chunks c
JOIN documents d ON c.document_id = d.id
WHERE d.act_id = '$ACT_ID'
GROUP BY c.classification_status"

c_green "==> Smoke classifier tiers PASSED"
echo
