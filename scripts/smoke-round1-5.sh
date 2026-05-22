#!/usr/bin/env bash
# Smoke test mirato a verificare i fix dei round 1-5 post code-review:
#   - GET /api/v1/documents/{id}/lineage           (block 9)
#   - GET /api/v1/documents/{id}/reverse-provenance-counts  (round 1 H1)
#   - PUT /api/v1/documents/provenance/{id}/confirm (block 8)
#   - DELETE /api/v1/documents/provenance/{id}     (block 8)
#   - audit_logger.append via stream_heads         (round 3 H3)
set -eo pipefail

API="${API:-http://localhost:8000}"
NOW=$(date +%s)
SLUG="r15-$NOW"

c_red()   { printf "\e[31m%s\e[0m" "$*"; }
c_green() { printf "\e[32m%s\e[0m" "$*"; }
c_yel()   { printf "\e[33m%s\e[0m" "$*"; }
section() { echo; c_yel "==> $*"; echo; }

section "Bootstrap tenant $SLUG"
BOOT=$(curl -fsS -X POST "$API/api/v1/dev/bootstrap" -H "Content-Type: application/json" \
  -d "{\"slug\":\"$SLUG\",\"name\":\"R15\",\"kind\":\"notarile\",\"admin_email\":\"a@$SLUG.test\",\"admin_display_name\":\"A\"}")
JWT=$(echo "$BOOT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
TENANT=$(echo "$BOOT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["tenant_id"])')
echo "  tenant=$TENANT"
H="Authorization: Bearer $JWT"

section "Crea pratica + atto"
PR=$(curl -fsS -X POST "$API/api/v1/practices" -H "$H" -H "Content-Type: application/json" \
  -d '{"code":"R15-1","kind":"notarile.compravendita.immobiliare","title":"Test R15"}')
PR_ID=$(echo "$PR" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
A=$(curl -fsS -X POST "$API/api/v1/acts" -H "$H" -H "Content-Type: application/json" \
  -d "{\"practice_id\":\"$PR_ID\",\"kind\":\"notarile.compravendita.immobiliare\",\"title\":\"Atto R15\"}")
ACT_ID=$(echo "$A" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "  act_id=$ACT_ID"

section "Upload documento input"
DOC=$(curl -fsS -X POST "$API/api/v1/documents" \
  -H "$H" \
  -F "act_id=$ACT_ID" \
  -F "kind=input_source" \
  -F "file=@demostuff/case-studies/compravendita-prima-casa/visura-catastale.md;type=text/markdown")
IN_DOC_ID=$(echo "$DOC" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "  input_doc=$IN_DOC_ID"

section "Attende ingestion (max 30s)"
for i in $(seq 1 30); do
  STATUS=$(curl -fsS -H "$H" "$API/api/v1/documents/$IN_DOC_ID" | python3 -c 'import sys,json;print(json.load(sys.stdin)["ingestion_status"])')
  echo "  [$i] ingestion_status=$STATUS"
  if [ "$STATUS" = "done" ] || [ "$STATUS" = "failed" ]; then break; fi
  sleep 1
done

section "Attende classificazione LLM (max 120s)"
# La classificazione e' un LLM call per chunk (~30-70s con qwen2.5-7b locale).
# Il workflow ha bisogno di entities classificate per generare i provenance link.
for i in $(seq 1 120); do
  CL=$(curl -fsS -H "$H" "$API/api/v1/documents/$IN_DOC_ID/classification")
  PENDING=$(echo "$CL" | python3 -c 'import sys,json
d=json.load(sys.stdin)
s=d.get("status_counts") or {}
print((s.get("pending") or 0) + (s.get("in_progress") or 0))')
  echo "  [$i] classification pending=$PENDING"
  if [ "$PENDING" = "0" ]; then break; fi
  sleep 2
done

section "Start workflow"
curl -fsS -X POST "$API/api/v1/acts/$ACT_ID/workflow/start" -H "$H" -H "Content-Type: application/json" \
  -d '{"template_id":"notarile.compravendita.immobiliare:v1","base_imponibile":250000,"is_prima_casa":true,"parties":[{"role":"venditore","kind":"PF","fiscal_code":"RSSMRA70A01F205X"},{"role":"acquirente","kind":"PF","fiscal_code":"BNCLCA85B05H501Y"}]}' >/dev/null

section "Attende review_requested (max 60s)"
DRAFT_DOC=""
for i in $(seq 1 60); do
  S=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/workflow/status")
  ST=$(echo "$S" | python3 -c 'import sys,json;print(json.load(sys.stdin)["state"]["status"])')
  echo "  [$i] wf=$ST"
  if [ "$ST" = "review_requested" ]; then
    DRAFT_DOC=$(echo "$S" | python3 -c 'import sys,json;d=json.load(sys.stdin)["state"]["draft"];print(d["document_id"] if d else "")')
    break
  fi
  sleep 1
done
if [ -z "$DRAFT_DOC" ]; then c_red "draft non generato"; exit 1; fi
echo "  draft_doc=$DRAFT_DOC"

section "TEST 1: GET /documents/{id}/lineage (block 9)"
LIN=$(curl -fsS -H "$H" "$API/api/v1/documents/$DRAFT_DOC/lineage")
echo "$LIN" | python3 -c 'import sys,json
d=json.load(sys.stdin)
print("  input_documents:", len(d["input_documents"]))
print("  chunks:", len(d["chunks"]))
print("  output_sections:", len(d["output_sections"]))
print("  edges:", len(d["edges"]))
assert len(d["edges"]) > 0, "no edges - lineage broken"
assert len(d["input_documents"]) > 0, "no input docs"
print("  OK lineage popolato")'

section "TEST 2: GET /documents/{id}/reverse-provenance-counts (round 1 H1)"
RC=$(curl -fsS -H "$H" "$API/api/v1/documents/$IN_DOC_ID/reverse-provenance-counts")
echo "$RC" | python3 -c 'import sys,json
d=json.load(sys.stdin)
counts=d["counts_by_chunk"]
print("  chunks with links:", len(counts))
print("  total link references:", sum(counts.values()))
assert len(counts) > 0, "batch counts empty"
print("  OK batch reverse counts")'

section "TEST 3: PUT /documents/provenance/{id}/confirm (block 8)"
PV=$(curl -fsS -H "$H" "$API/api/v1/documents/$DRAFT_DOC/provenance")
LINK_ID=$(echo "$PV" | python3 -c 'import sys,json
d=json.load(sys.stdin)
for sec in d["links_by_section"].values():
    for l in sec: print(l["id"]); sys.exit(0)')
echo "  link to confirm: $LINK_ID"
RES=$(curl -fsS -X PUT "$API/api/v1/documents/provenance/$LINK_ID/confirm" -H "$H" -H "Content-Type: application/json" -d '{"confirmed":true}')
echo "$RES" | python3 -c 'import sys,json
d=json.load(sys.stdin)
assert d["confidence"] == 1.0, "expected 1.0 got " + str(d["confidence"])
print("  OK confirm -> confidence 1.0")'

section "TEST 4: DELETE /documents/provenance/{id} (block 8)"
PV2=$(curl -fsS -H "$H" "$API/api/v1/documents/$DRAFT_DOC/provenance")
LINK_RM=$(echo "$PV2" | python3 -c 'import sys,json
d=json.load(sys.stdin)
for sec in d["links_by_section"].values():
    for l in sec:
        if l["id"] != "'"$LINK_ID"'":
            print(l["id"]); sys.exit(0)')
echo "  link to delete: $LINK_RM"
curl -fsS -X DELETE "$API/api/v1/documents/provenance/$LINK_RM" -H "$H" -o /dev/null -w "  http=%{http_code}\n"
curl -fsS -H "$H" "$API/api/v1/documents/$DRAFT_DOC/provenance" | python3 -c 'import sys,json
d=json.load(sys.stdin)
all_ids=[l["id"] for sec in d["links_by_section"].values() for l in sec]
assert "'"$LINK_RM"'" not in all_ids, "link not deleted"
print("  OK link rimosso")'

section "TEST 5: audit chain integrita' (round 3 H3 stream_heads + hash)"
# Verify via CLI (non c'e' un endpoint HTTP; il check viaggia su DB direttamente).
docker compose exec -T notai-api python -m apps.cli.audit_verify --tenant "$TENANT" --stream "act:$ACT_ID" 2>&1 | tail -3

section "TEST 6: search ILIKE su chunk text (round 1 H5 - pg_trgm)"
SR=$(curl -fsS -H "$H" "$API/api/v1/acts/$ACT_ID/search?q=Garibaldi&limit=5")
echo "$SR" | python3 -c 'import sys,json
d=json.load(sys.stdin)
print("  input_hits:", len(d["input_hits"]), "| output_hits:", len(d["output_hits"]))
assert d["total"] > 0, "search returned 0 results"
print("  OK search trgm-indexed")'

c_green "==> Smoke round 1-5 PASSED"
echo
