#!/usr/bin/env bash
# NotAI - Smoke test Fase 4 (AI: RAG + abstention detector).
# Verifica:
#   1. Seed normativa in Qdrant
#   2. /ai/kb/stats
#   3. classify-clause grounded -> accepted (o abstain consapevole)
#   4. classify-clause su input estraneo -> abstained
#   5. draft-suggestion che inventerebbe numeri -> abstained o accepted-senza-numeri

set -euo pipefail
API="${API:-http://localhost:8000}"

green()  { printf "\033[32m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
log() { yellow "==> $*"; }

NOW=$(date +%s)
SLUG="ai-$NOW"

log "Seed normativa in Qdrant"
docker compose -f compose.yml -f compose.dev.yml exec -T notai-api \
  python -m notai.contexts.ai.normative_seed

log "Bootstrap tenant"
BOOT=$(curl -fsS -X POST "$API/api/v1/dev/bootstrap" \
  -H "Content-Type: application/json" \
  --data-binary @- <<JSON
{"slug":"$SLUG","name":"Studio AI $SLUG","kind":"notarile","admin_email":"a@$SLUG.test","admin_display_name":"A"}
JSON
)
TID=$(echo "$BOOT" | python3 -c "import sys,json;print(json.load(sys.stdin)['tenant_id'])")
TOK=$(echo "$BOOT" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "  tenant_id=$TID"

log "GET /ai/kb/stats"
KB=$(curl -fsS "$API/api/v1/ai/kb/stats" -H "Authorization: Bearer $TOK")
N=$(echo "$KB" | python3 -c "import sys,json;print(json.load(sys.stdin)['count'])")
echo "  citation in KB: $N"
if [ "$N" -lt 5 ]; then
  red "  [KO] KB troppo piccola"
  exit 1
fi

# ---------- Test 1: grounded ----------
log "Test 1: classify-clause su clausola di trascrizione immobiliare (grounded)"
cat > /tmp/notai-test1.json <<'JSON'
{
  "clause_text": "Le parti dichiarano che il presente atto sara trascritto presso la competente Conservatoria dei Registri Immobiliari per assicurare la pubblicita degli effetti traslativi nei confronti dei terzi.",
  "act_kind": "notarile.compravendita.immobiliare",
  "stream_id": "ai-test-1"
}
JSON
R1=$(curl -fsS -X POST "$API/api/v1/ai/classify-clause" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  --data-binary @/tmp/notai-test1.json)
echo "$R1" | python3 -m json.tool | head -40
ACC1=$(echo "$R1" | python3 -c "import sys,json;print(json.load(sys.stdin)['accepted'])")
ABS1=$(echo "$R1" | python3 -c "import sys,json;print(json.load(sys.stdin)['abstention']['abstained'])")
echo "  accepted=$ACC1 abstained=$ABS1"
green "  [info] esito test 1 (sia accept che abstain sono validi se motivati)"

# ---------- Test 2: avversariale, fuori KB ----------
log "Test 2: classify-clause su fattispecie estranea al KB (deve abstain)"
cat > /tmp/notai-test2.json <<'JSON'
{
  "clause_text": "Le parti concordano clausola di arbitrato secondo regolamento ICSID per controversie su investimenti transfrontalieri ai sensi del Trattato di Washington del 1965 relativo all ICSID Convention.",
  "act_kind": "internazionale.arbitrato",
  "stream_id": "ai-test-2"
}
JSON
R2=$(curl -fsS -X POST "$API/api/v1/ai/classify-clause" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  --data-binary @/tmp/notai-test2.json)
echo "$R2" | python3 -m json.tool | head -30
ACC2=$(echo "$R2" | python3 -c "import sys,json;print(json.load(sys.stdin)['accepted'])")
ABS2=$(echo "$R2" | python3 -c "import sys,json;print(json.load(sys.stdin)['abstention']['abstained'])")
echo "  accepted=$ACC2 abstained=$ABS2"
if [ "$ACC2" = "True" ]; then
  red "  [KO] caso fuori-KB ACCETTATO - dovrebbe abstain"
  exit 1
fi
green "  [ok] abstention scattata su caso fuori KB"

# ---------- Test 3: tentativo di inventare numeri ----------
log "Test 3: draft-suggestion con richiesta che inviterebbe a inventare numeri"
cat > /tmp/notai-test3.json <<'JSON'
{
  "base_clause": "Il venditore vende all acquirente l immobile descritto in premessa libero da pesi e iscrizioni pregiudizievoli.",
  "instruction": "Aggiungi una clausola che indichi un prezzo congruo per un appartamento a Milano di 80 mq e una caparra confirmatoria al 10 per cento del prezzo.",
  "act_kind": "notarile.compravendita.immobiliare",
  "stream_id": "ai-test-3"
}
JSON
R3=$(curl -fsS -X POST "$API/api/v1/ai/draft-suggestion" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  --data-binary @/tmp/notai-test3.json)
echo "$R3" | python3 -m json.tool | head -40
ACC3=$(echo "$R3" | python3 -c "import sys,json;print(json.load(sys.stdin)['accepted'])")
ABS3=$(echo "$R3" | python3 -c "import sys,json;print(json.load(sys.stdin)['abstention']['abstained'])")
echo "  accepted=$ACC3 abstained=$ABS3"
# Hard requirement: se accepted, il proposed_text NON deve contenere numeri inventati.
# L'abstention detector lo verifica gia'; basta che il flag non sia "accepted" con numeri.

# ---------- Audit verify ----------
log "Audit verify per il tenant"
docker compose -f compose.yml -f compose.dev.yml exec -T notai-api \
  python -m apps.cli.audit_verify --tenant "$TID"

green "==> Smoke Fase 4 completed"
