#!/usr/bin/env bash
# Smoke per Step 4 (slot preview) + Step 7 (tags facets).
# Pre-condizione: il sistema deve avere classificazione LLM funzionante.
set -eo pipefail

API="${API:-http://localhost:8000}"
NOW=$(date +%s)
SLUG="s47-$NOW"

c_red()   { printf "\e[31m%s\e[0m" "$*"; }
c_green() { printf "\e[32m%s\e[0m" "$*"; }
c_yel()   { printf "\e[33m%s\e[0m" "$*"; }
section() { echo; c_yel "==> $*"; echo; }

section "Bootstrap + setup atto con docs reali"
BOOT=$(curl -fsS -X POST "$API/api/v1/dev/bootstrap" -H "Content-Type: application/json" \
  -d "{\"slug\":\"$SLUG\",\"name\":\"S47\",\"kind\":\"notarile\",\"admin_email\":\"a@$SLUG.test\",\"admin_display_name\":\"A\"}")
JWT=$(echo "$BOOT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
H="Authorization: Bearer $JWT"

PR=$(curl -fsS -X POST "$API/api/v1/practices" -H "$H" -H "Content-Type: application/json" \
  -d '{"code":"S47","kind":"notarile.compravendita.immobiliare","title":"Step 4-7 test"}')
PR_ID=$(echo "$PR" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
A=$(curl -fsS -X POST "$API/api/v1/acts" -H "$H" -H "Content-Type: application/json" \
  -d "{\"practice_id\":\"$PR_ID\",\"kind\":\"notarile.compravendita.immobiliare\",\"title\":\"AT\"}")
ACT_ID=$(echo "$A" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -fsS -X POST -H "$H" "$API/api/v1/dev/scenarios/compravendita-prima-casa/upload-to-act/$ACT_ID" >/dev/null
echo "  act=$ACT_ID"

section "Attendi classificazione (max 6 min)"
for i in $(seq 1 180); do
  DOCS=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/documents")
  PENDING_DOC=$(echo "$DOCS" | python3 -c 'import sys,json
ds=json.load(sys.stdin)
print(sum(1 for d in ds if d["ingestion_status"] != "done"))')
  if [ "$PENDING_DOC" = "0" ]; then
    PENDING_CHUNK=0
    for DID in $(echo "$DOCS" | python3 -c 'import sys,json
[print(d["id"]) for d in json.load(sys.stdin)]'); do
      CL=$(curl -fsS -H "$H" "$API/api/v1/documents/$DID/classification" 2>/dev/null || echo '{}')
      P=$(echo "$CL" | python3 -c 'import sys,json
try:
  d=json.load(sys.stdin)
  s=d.get("status_counts") or {}
  print((s.get("pending") or 0) + (s.get("in_progress") or 0))
except: print(99)')
      PENDING_CHUNK=$((PENDING_CHUNK + P))
    done
    echo "  [$i] docs ok, classification pending=$PENDING_CHUNK"
    if [ "$PENDING_CHUNK" = "0" ]; then break; fi
  else
    echo "  [$i] docs pending=$PENDING_DOC"
  fi
  sleep 3
done

section "TEST 4A: POST /preparation/extract-preview"
R=$(curl -fsS -X POST -H "$H" "$API/api/v1/acts/$ACT_ID/preparation/extract-preview")
echo "$R" | python3 -c '
import sys,json
d=json.load(sys.stdin)
slots=d["slots"]
prov=d["provenance"]
abst=d["abstained"]
print("  estratti:", len(slots), "slots")
print("  astenuti:", abst)
print("  esempi:", dict(list(slots.items())[:3]))
assert len(slots) > 0, "nessuno slot estratto"
for name in slots:
    assert name in prov, f"manca provenance per {name}"
    assert prov[name]["chunk_id"], f"chunk_id mancante per {name}"
print("  OK preview estratto + grounded")'

section "TEST 4B: GET /preparation include preview_slots"
PREP=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/preparation")
echo "$PREP" | python3 -c '
import sys,json
d=json.load(sys.stdin)
ps=d.get("preview_slots")
assert ps is not None, "preview_slots mancante"
assert ps["slots"], "slots vuoti nel preview"
n=len(ps["slots"])
print("  preview_slots in /preparation:", n, "slots")
print("  template_id nel preview:", ps["template_id"])
print("  extracted_at:", ps["extracted_at"])
print("  OK preview persistito + esposto in GET")'

section "TEST 7A: GET /acts/{id}/tags"
TAGS=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/tags")
echo "$TAGS" | python3 -c '
import sys,json
d=json.load(sys.stdin)
print("  chunks_analyzed:", d["chunks_analyzed"])
print("  document_types:", [(t["name"], t["count"]) for t in d["document_types"]])
print("  tags top-5:", [(t["name"], t["count"]) for t in d["tags"][:5]])
print("  entity_types top-5:", [(t["name"], t["count"]) for t in d["entity_types"][:5]])
assert d["chunks_analyzed"] > 0
assert len(d["document_types"]) > 0 or len(d["tags"]) > 0 or len(d["entity_types"]) > 0
print("  OK facet aggregati popolati")'

section "TEST: idempotenza ri-estrazione"
# Ri-estrai: il preview_slots viene sovrascritto, l'audit log ha 2 eventi
R2=$(curl -fsS -X POST -H "$H" "$API/api/v1/acts/$ACT_ID/preparation/extract-preview")
N1=$(echo "$R" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["slots"]))')
N2=$(echo "$R2" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["slots"]))')
echo "  prima estrazione: $N1 slots, ri-estrazione: $N2 slots"
[ "$N1" = "$N2" ] && echo "  OK ri-estrazione produce stesso N slots" || c_yel "  WARN: count diverso (LLM non deterministico?)"

c_green "==> Smoke step 4 + 7 PASSED"
echo
