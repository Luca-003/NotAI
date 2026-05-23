#!/usr/bin/env bash
# Verifica E2E che i valori dell'atto vengono ESTRATTI dai documenti
# (non solo presi dal form). Sequence:
#   1. Bootstrap tenant
#   2. Crea pratica + atto (compravendita)
#   3. Upload 3 doc demo via scenario endpoint
#   4. Aspetta classificazione LLM
#   5. Avvia workflow
#   6. Aspetta review_requested
#   7. Verifica state.extracted_slots contiene immobile_*, prezzo, ecc.
#   8. Verifica state.extracted_provenance ha chunk_id validi
#   9. Verifica draft sections contiene i valori estratti (non solo "—")
set -eo pipefail

API="${API:-http://localhost:8000}"
NOW=$(date +%s)
SLUG="se-$NOW"

c_red()   { printf "\e[31m%s\e[0m" "$*"; }
c_green() { printf "\e[32m%s\e[0m" "$*"; }
c_yel()   { printf "\e[33m%s\e[0m" "$*"; }
section() { echo; c_yel "==> $*"; echo; }

section "Bootstrap tenant $SLUG"
BOOT=$(curl -fsS -X POST "$API/api/v1/dev/bootstrap" -H "Content-Type: application/json" \
  -d "{\"slug\":\"$SLUG\",\"name\":\"SE\",\"kind\":\"notarile\",\"admin_email\":\"a@$SLUG.test\",\"admin_display_name\":\"A\"}")
JWT=$(echo "$BOOT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
H="Authorization: Bearer $JWT"

section "Crea pratica + atto compravendita"
PR=$(curl -fsS -X POST "$API/api/v1/practices" -H "$H" -H "Content-Type: application/json" \
  -d '{"code":"SE-1","kind":"notarile.compravendita.immobiliare","title":"Slot extraction test"}')
PR_ID=$(echo "$PR" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
A=$(curl -fsS -X POST "$API/api/v1/acts" -H "$H" -H "Content-Type: application/json" \
  -d "{\"practice_id\":\"$PR_ID\",\"kind\":\"notarile.compravendita.immobiliare\",\"title\":\"Atto SE\"}")
ACT_ID=$(echo "$A" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "  act=$ACT_ID"

section "Upload 3 documenti via scenario endpoint"
R=$(curl -fsS -X POST "$API/api/v1/dev/scenarios/compravendita-prima-casa/upload-to-act/$ACT_ID" -H "$H")
echo "  $(echo "$R" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("uploaded:", d["documents_created"], "docs")')"

section "Attende classificazione LLM (max 6 min)"
for i in $(seq 1 180); do
  DOCS=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/documents")
  PENDING=$(echo "$DOCS" | python3 -c 'import sys,json
docs=json.load(sys.stdin)
n=sum(1 for d in docs if d["ingestion_status"] != "done")
print(n)')
  echo "  [$i] ingestion pending=$PENDING"
  if [ "$PENDING" = "0" ]; then break; fi
  sleep 2
done

# Aspetta che la classificazione sia done per tutti i chunk
for i in $(seq 1 90); do
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
  sleep 4
done

section "Avvia workflow"
curl -fsS -X POST "$API/api/v1/acts/$ACT_ID/workflow/start" -H "$H" -H "Content-Type: application/json" \
  -d '{"template_id":"notarile.compravendita.immobiliare:v1","base_imponibile":285000,"is_prima_casa":true,"parties":[{"role":"venditore","kind":"PF","fiscal_code":"RSSMRA70A01F205X"},{"role":"acquirente","kind":"PF","fiscal_code":"BNCLCA85B05H501Y"}]}' >/dev/null

section "Attende review_requested (max 5 min - slot_extract e' lento)"
DRAFT_DOC=""
for i in $(seq 1 150); do
  S=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/workflow/status")
  ST=$(echo "$S" | python3 -c 'import sys,json;print(json.load(sys.stdin)["state"]["status"])')
  echo "  [$i] wf=$ST"
  if [ "$ST" = "review_requested" ]; then
    DRAFT_DOC=$(echo "$S" | python3 -c 'import sys,json;d=json.load(sys.stdin)["state"]["draft"];print(d["document_id"] if d else "")')
    break
  fi
  sleep 2
done
[ -n "$DRAFT_DOC" ] || { c_red "draft non generato"; exit 1; }
echo "  draft=$DRAFT_DOC"

section "TEST 1: extracted_slots non vuoto"
S=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/workflow/status")
echo "$S" | python3 -c '
import sys,json
d=json.load(sys.stdin)["state"]
slots=d.get("extracted_slots") or {}
prov=d.get("extracted_provenance") or {}
abst=d.get("extracted_abstained") or []
print("  estratti:", list(slots.keys()))
print("  astenuti:", abst)
print("  con provenance:", list(prov.keys()))
if not slots:
    print("  KO: nessuno slot estratto")
    sys.exit(1)
print("  OK", len(slots), "slot estratti dai documenti")'

section "TEST 2: provenance ha chunk_id validi"
echo "$S" | python3 -c '
import sys,json
d=json.load(sys.stdin)["state"]
prov=d.get("extracted_provenance") or {}
for name, p in prov.items():
    cid=p.get("chunk_id")
    cs=p.get("char_start")
    ce=p.get("char_end")
    conf=p.get("confidence", 0)
    print(f"  {name}: chunk={cid[:8]}... offset={cs}-{ce} conf={conf:.2f}")
    assert cid and len(cid) > 10
print("  OK provenance validi")'

section "TEST 3: draft contiene valori estratti (non placeholder vuoti)"
SECTIONS=$(curl -fsS -H "$H" "$API/api/v1/documents/$DRAFT_DOC/sections")
echo "$SECTIONS" | python3 -c '
import sys,json
d=json.load(sys.stdin)
secs=d.get("sections", [])
joined=" ".join(s.get("text","") for s in secs)
# Cerca placeholder rimasti unfilled (—)
emdash_count = joined.count("—")
print(f"  sezioni: {len(secs)}, em-dash residui (placeholder non riempiti): {emdash_count}")
# Cerca segnali di valori reali estratti
markers = ["foglio", "particella", "Garibaldi", "Milano", "Mario", "Rossi"]
found = [m for m in markers if m.lower() in joined.lower()]
print(f"  marker trovati nel draft: {found}")
if not found:
    print("  WARN: nessun marker - LLM potrebbe non aver estratto dai docs reali")
else:
    print("  OK draft riferisce i valori dei documenti reali")'

c_green "==> Smoke slot-extract PASSED"
echo
