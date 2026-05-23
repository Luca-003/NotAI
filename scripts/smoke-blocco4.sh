#!/usr/bin/env bash
# Smoke blocco 4: end-to-end traceability output->input.
set -euo pipefail
API="${API:-http://localhost:8000}"

green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
log()   { printf "\033[33m==> %s\033[0m\n" "$*"; }

NOW=$(date +%s)
SLUG="blocco4-$NOW"

log "Bootstrap + pratica + atto"
BOOT=$(curl -fsS -X POST "$API/api/v1/dev/bootstrap" -H "Content-Type: application/json" \
  --data-binary @- <<JSON
{"slug":"$SLUG","name":"X","kind":"notarile","admin_email":"a@$SLUG.test","admin_display_name":"A"}
JSON
)
TOK=$(echo "$BOOT" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
PR=$(curl -fsS -X POST "$API/api/v1/practices" -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"code":"P/B4/001","kind":"notarile.compravendita.immobiliare","title":"Compravendita test b4"}')
PID=$(echo "$PR" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
ACT=$(curl -fsS -X POST "$API/api/v1/acts" -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d "{\"practice_id\":\"$PID\",\"kind\":\"notarile.compravendita.immobiliare\",\"title\":\"Atto test\"}")
AID=$(echo "$ACT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  act=$AID"

log "Upload visura catastale"
cat > /tmp/visura.txt <<'EOF'
VISURA CATASTALE - IMMOBILE
Comune: Milano (MI)
Foglio: 412, Particella: 88, Subalterno: 3
Categoria: A/2, Classe: 4
Indirizzo: Via Garibaldi 12, scala A interno 4
Intestatari: Rossi Mario, CF RSSMRA70A01F205X, piena proprieta'.
Rendita catastale: 1.234,56 EUR.
EOF
DOC=$(curl -fsS -X POST "$API/api/v1/documents" -H "Authorization: Bearer $TOK" \
  -F "file=@/tmp/visura.txt" -F "kind=input_source" -F "act_id=$AID")
DID=$(echo "$DOC" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "  doc=$DID"

log "Attendo ingestion + classification (max 5 min - LLM locale puo' essere lento)"
for i in $(seq 1 150); do
  sleep 2
  CS=$(curl -fsS "$API/api/v1/documents/$DID/chunks" -H "Authorization: Bearer $TOK" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['classification_status'] if d else '-')")
  echo "  $i: class=$CS"
  if [ "$CS" = "done" ] || [ "$CS" = "abstained" ]; then break; fi
done

log "Consolida (sblocca il workflow gate)"
curl -fsS -X POST "$API/api/v1/acts/$AID/preparation/consolidate" -H "Authorization: Bearer $TOK" >/dev/null

log "Avvia workflow atto"
curl -fsS -X POST "$API/api/v1/acts/$AID/workflow/start" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"template_id":"notarile.compravendita.immobiliare:v1","base_imponibile":285000,"is_prima_casa":true,"parties":[{"role":"venditore","kind":"PF","fiscal_code":"RSSMRA70A01F205X"},{"role":"acquirente","kind":"PF","fiscal_code":"BNCLCA85B05H501Y"}]}' >/dev/null

log "Attendo draft generato"
for i in $(seq 1 30); do
  sleep 2
  ST=$(curl -fsS "$API/api/v1/acts/$AID/workflow/status" -H "Authorization: Bearer $TOK" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);s=(d.get('state') or {});dr=s.get('draft');print(dr['document_id'] if dr else '-')")
  echo "  $i: draft=$ST"
  if [ "$ST" != "-" ]; then BOZZA_ID=$ST; break; fi
done

if [ -z "${BOZZA_ID:-}" ]; then
  red "[KO] draft non generato"; exit 1
fi
green "  bozza_id=$BOZZA_ID"

log "Verifica sezioni bozza"
SEC=$(curl -fsS "$API/api/v1/documents/$BOZZA_ID/sections" -H "Authorization: Bearer $TOK")
N_SEC=$(echo "$SEC" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['sections']))")
echo "  $N_SEC sezioni"
if [ "$N_SEC" -lt 5 ]; then red "  [KO] poche sezioni"; exit 1; fi
green "  [ok] sezioni strutturate"

log "Verifica provenance"
PROV=$(curl -fsS "$API/api/v1/documents/$BOZZA_ID/provenance" -H "Authorization: Bearer $TOK")
echo "$PROV" | python3 -m json.tool | head -50
TOTAL=$(echo "$PROV" | python3 -c "import sys,json;print(json.load(sys.stdin)['total_links'])")
echo "  total provenance links: $TOTAL"
if [ "$TOTAL" -lt 1 ]; then
  red "  [KO] nessun link di provenance generato"; exit 1
fi
green "  [ok] $TOTAL link generati"

log "Reverse provenance: dato un chunk del documento input, in quali sezioni di output viene usato?"
CHUNK_ID=$(curl -fsS "$API/api/v1/documents/$DID/chunks" -H "Authorization: Bearer $TOK" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
echo "  chunk_id=$CHUNK_ID"
REV=$(curl -fsS "$API/api/v1/documents/chunks/$CHUNK_ID/reverse-provenance" -H "Authorization: Bearer $TOK")
echo "$REV" | python3 -m json.tool | head -20

green "==> Smoke blocco 4 PASSED"
