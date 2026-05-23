#!/usr/bin/env bash
# Smoke E2E del nuovo flow workspace + preparation:
#   1. workspace/tree popolato dopo create
#   2. preparation status iniziale ha can_execute=false
#   3. Workflow start senza consolidate -> 409
#   4. acquire-visure salva Document kind=visura_auto
#   5. consolidate -> can_execute=true
#   6. Workflow start funziona
set -eo pipefail

API="${API:-http://localhost:8000}"
NOW=$(date +%s)
SLUG="prep-$NOW"

c_red()   { printf "\e[31m%s\e[0m" "$*"; }
c_green() { printf "\e[32m%s\e[0m" "$*"; }
c_yel()   { printf "\e[33m%s\e[0m" "$*"; }
section() { echo; c_yel "==> $*"; echo; }

section "Bootstrap"
BOOT=$(curl -fsS -X POST "$API/api/v1/dev/bootstrap" -H "Content-Type: application/json" \
  -d "{\"slug\":\"$SLUG\",\"name\":\"P\",\"kind\":\"misto\",\"admin_email\":\"a@$SLUG.test\",\"admin_display_name\":\"A\"}")
JWT=$(echo "$BOOT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
H="Authorization: Bearer $JWT"

section "Crea pratica + atto + verifica workspace tree"
PR=$(curl -fsS -X POST "$API/api/v1/practices" -H "$H" -H "Content-Type: application/json" \
  -d '{"code":"PR-1","kind":"notarile.compravendita.immobiliare","title":"Test prep"}')
PR_ID=$(echo "$PR" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
A=$(curl -fsS -X POST "$API/api/v1/acts" -H "$H" -H "Content-Type: application/json" \
  -d "{\"practice_id\":\"$PR_ID\",\"kind\":\"notarile.compravendita.immobiliare\",\"title\":\"Atto prep\"}")
ACT_ID=$(echo "$A" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

TREE=$(curl -fsS -H "$H" "$API/api/v1/workspace/tree")
echo "$TREE" | python3 -c '
import sys,json
d=json.load(sys.stdin)
print("  practice_count:", d["practice_count"])
print("  acts in first practice:", len(d["practices"][0]["acts"]))
assert d["practice_count"] == 1
assert len(d["practices"][0]["acts"]) == 1
print("  OK tree popolato")'

section "TEST 1: preparation status iniziale, can_execute=false"
PREP=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/preparation")
echo "$PREP" | python3 -c '
import sys,json
d=json.load(sys.stdin)
print("  template_known:", d["template_known"])
print("  catalog status:", d["step1_catalog"]["status"])
print("  expected types:", d["step2_visure_needed"]["expected_document_types"])
print("  consolidated:", d["step4_consolidation"]["consolidated"])
print("  can_execute:", d["can_execute"])
assert d["template_known"]
assert d["can_execute"] is False
print("  OK can_execute=false su atto vuoto")'

section "TEST 2: workflow start senza consolidate -> 409"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"template_id":"notarile.compravendita.immobiliare:v1","base_imponibile":100,"is_prima_casa":false,"parties":[]}' \
  "$API/api/v1/acts/$ACT_ID/workflow/start")
[ "$HTTP" = "409" ] && echo "  OK 409 sul gate" || { c_red "FAIL: expected 409 got $HTTP"; exit 1; }

section "TEST 3: acquire-visure (ANPR) salva Document kind=visura_auto"
R=$(curl -fsS -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"adapter":"anpr","party_fiscal_code":"RSSMRA70A01F205X"}' \
  "$API/api/v1/acts/$ACT_ID/preparation/acquire-visure")
DOC_ID=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["document_id"])')
echo "  acquired doc_id=$DOC_ID"

# Verifica che appaia nel tree come visura_auto
TREE=$(curl -fsS -H "$H" "$API/api/v1/workspace/tree")
echo "$TREE" | python3 -c '
import sys,json
d=json.load(sys.stdin)
visure = d["practices"][0]["acts"][0]["documents"]["visure_auto"]
print("  visure_auto in tree:", len(visure))
assert len(visure) == 1
print("  OK Document visura_auto creato e visibile in tree")'

section "TEST 4: consolidate -> can_execute=true"
curl -fsS -X POST -H "$H" "$API/api/v1/acts/$ACT_ID/preparation/consolidate" >/dev/null
PREP=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/preparation")
echo "$PREP" | python3 -c '
import sys,json
d=json.load(sys.stdin)
print("  consolidated:", d["step4_consolidation"]["consolidated"])
print("  can_execute:", d["can_execute"])
assert d["step4_consolidation"]["consolidated"] is True
assert d["can_execute"] is True
print("  OK consolidate sblocca can_execute")'

section "TEST 5: workflow start ora passa (202)"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"template_id":"notarile.compravendita.immobiliare:v1","base_imponibile":250000,"is_prima_casa":true,"parties":[{"role":"venditore","kind":"PF","fiscal_code":"RSSMRA70A01F205X"},{"role":"acquirente","kind":"PF","fiscal_code":"BNCLCA85B05H501Y"}]}' \
  "$API/api/v1/acts/$ACT_ID/workflow/start")
[ "$HTTP" = "202" ] && echo "  OK 202 dopo consolidate" || { c_red "FAIL: expected 202 got $HTTP"; exit 1; }

section "TEST 6: tree mostra workflow_status aggiornato"
sleep 3
TREE=$(curl -fsS -H "$H" "$API/api/v1/workspace/tree")
echo "$TREE" | python3 -c '
import sys,json
d=json.load(sys.stdin)
a=d["practices"][0]["acts"][0]
print("  workflow_status:", a["workflow_status"])
print("  workflow_run_id:", a["workflow_run_id"][:12] if a["workflow_run_id"] else "")
assert a["workflow_run_id"] is not None
print("  OK workflow run_id presente in tree")'

c_green "==> Smoke preparation PASSED"
echo
