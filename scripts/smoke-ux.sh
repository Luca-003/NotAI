#!/usr/bin/env bash
# Verifica E2E del round UX:
#   1. Bootstrap (1 click "Accedi dev")
#   2. Crea pratica + atto (come fa il DemoLoader)
#   3. Hit nuovo endpoint /api/v1/dev/scenarios/{id}/upload-to-act/{act} con
#      tutti e 6 gli scenari
#   4. Verifica che i documenti siano stati creati e siano in ingestion
#   5. Verifica deep-link URL: /api/v1/practices/{id} risponde
set -eo pipefail

API="${API:-http://localhost:8000}"
NOW=$(date +%s)
SLUG="ux-$NOW"

c_red()   { printf "\e[31m%s\e[0m" "$*"; }
c_green() { printf "\e[32m%s\e[0m" "$*"; }
c_yel()   { printf "\e[33m%s\e[0m" "$*"; }
section() { echo; c_yel "==> $*"; echo; }

section "Bootstrap tenant"
BOOT=$(curl -fsS -X POST "$API/api/v1/dev/bootstrap" -H "Content-Type: application/json" \
  -d "{\"slug\":\"$SLUG\",\"name\":\"UX\",\"kind\":\"misto\",\"admin_email\":\"a@$SLUG.test\",\"admin_display_name\":\"A\"}")
JWT=$(echo "$BOOT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
TENANT=$(echo "$BOOT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["tenant_id"])')
H="Authorization: Bearer $JWT"
echo "  tenant=$TENANT"

section "Crea 2 pratiche (1 notarile + 1 legale) con 1 atto ciascuna"

# Notarile
PR1=$(curl -fsS -X POST "$API/api/v1/practices" -H "$H" -H "Content-Type: application/json" \
  -d '{"code":"UX-NOT-1","kind":"notarile.compravendita.immobiliare","title":"UX Compravendita"}')
PR1_ID=$(echo "$PR1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
A1=$(curl -fsS -X POST "$API/api/v1/acts" -H "$H" -H "Content-Type: application/json" \
  -d "{\"practice_id\":\"$PR1_ID\",\"kind\":\"notarile.compravendita.immobiliare\",\"title\":\"Atto notarile UX\"}")
A1_ID=$(echo "$A1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "  notarile: practice=$PR1_ID act=$A1_ID"

# Legale
PR2=$(curl -fsS -X POST "$API/api/v1/practices" -H "$H" -H "Content-Type: application/json" \
  -d '{"code":"UX-LEG-1","kind":"legale.atto_citazione","title":"UX Citazione"}')
PR2_ID=$(echo "$PR2" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
A2=$(curl -fsS -X POST "$API/api/v1/acts" -H "$H" -H "Content-Type: application/json" \
  -d "{\"practice_id\":\"$PR2_ID\",\"kind\":\"legale.atto_citazione\",\"title\":\"Atto legale UX\"}")
A2_ID=$(echo "$A2" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "  legale:   practice=$PR2_ID act=$A2_ID"

section "TEST 1: scenario notarile -> upload-to-act/compravendita-prima-casa"
R1=$(curl -fsS -X POST "$API/api/v1/dev/scenarios/compravendita-prima-casa/upload-to-act/$A1_ID" -H "$H")
echo "$R1" | python3 -c 'import sys,json
d=json.load(sys.stdin)
print("  documents_created:", d["documents_created"])
assert d["documents_created"] == 3, "expected 3 docs, got " + str(d["documents_created"])
print("  OK 3 documenti caricati")'

section "TEST 2: scenario legale -> upload-to-act/citazione-recupero-credito"
R2=$(curl -fsS -X POST "$API/api/v1/dev/scenarios/citazione-recupero-credito/upload-to-act/$A2_ID" -H "$H")
echo "$R2" | python3 -c 'import sys,json
d=json.load(sys.stdin)
print("  documents_created:", d["documents_created"])
assert d["documents_created"] == 3, "expected 3 docs, got " + str(d["documents_created"])
print("  OK 3 documenti caricati")'

section "TEST 3: tutti i documenti hanno ingestion_status legittimo"
DOCS1=$(curl -fsS -H "$H" "$API/api/v1/acts/$A1_ID/documents")
echo "$DOCS1" | python3 -c 'import sys,json
docs=json.load(sys.stdin)
assert len(docs) == 3, "expected 3 docs in notarile act"
for d in docs:
    s = d["ingestion_status"]
    assert s in ("pending", "in_progress", "done"), "unexpected status: " + s
    print("  -", d["filename"], "·", s)
print("  OK 3 documenti notarile in stato valido")'

section "TEST 4: deep-link target URLs (sanity check API)"
# /api/v1/practices/{id} risponde 200 (deep-link sara' #/practices/{id})
curl -fsS -H "$H" "$API/api/v1/practices/$PR1_ID" >/dev/null && echo "  OK practice GET"
curl -fsS -H "$H" "$API/api/v1/acts/$A1_ID" >/dev/null && echo "  OK act GET"

section "TEST 5: scenario id non valido -> 400"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/api/v1/dev/scenarios/inesistente/upload-to-act/$A1_ID" -H "$H")
if [ "$HTTP" = "400" ]; then
  echo "  OK 400 su scenario sconosciuto"
else
  c_red "FAIL: expected 400 got $HTTP"; exit 1
fi

section "TEST 6: act_id sbagliato -> 404"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/api/v1/dev/scenarios/compravendita-prima-casa/upload-to-act/00000000-0000-0000-0000-000000000000" -H "$H")
if [ "$HTTP" = "404" ]; then
  echo "  OK 404 su act inesistente"
else
  c_red "FAIL: expected 404 got $HTTP"; exit 1
fi

section "TEST 7: idempotenza relativa (re-upload stesso scenario)"
# Ri-uploadare lo stesso scenario sullo stesso atto crea ALTRI 3 documenti
# (e' INSERT, non upsert). Verifichiamo che almeno non crashi.
R3=$(curl -fsS -X POST "$API/api/v1/dev/scenarios/compravendita-prima-casa/upload-to-act/$A1_ID" -H "$H")
echo "$R3" | python3 -c 'import sys,json
d=json.load(sys.stdin)
print("  re-upload documents_created:", d["documents_created"])
assert d["documents_created"] == 3
print("  OK re-upload non crasha (crea duplicati - comportamento atteso)")'

DOCS_AFTER=$(curl -fsS -H "$H" "$API/api/v1/acts/$A1_ID/documents" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))')
echo "  totale docs sull'atto ora: $DOCS_AFTER"

section "TEST 8: scenari validi (sanity sulla whitelist)"
for SC in donazione-genitore-figlio costituzione-srl decreto-ingiuntivo-commerciale separazione-consensuale; do
  # Creo un nuovo atto vuoto per ognuno
  AN=$(curl -fsS -X POST "$API/api/v1/acts" -H "$H" -H "Content-Type: application/json" \
    -d "{\"practice_id\":\"$PR1_ID\",\"kind\":\"notarile.compravendita.immobiliare\",\"title\":\"Atto $SC\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
  RR=$(curl -fsS -X POST "$API/api/v1/dev/scenarios/$SC/upload-to-act/$AN" -H "$H")
  N=$(echo "$RR" | python3 -c 'import sys,json;print(json.load(sys.stdin)["documents_created"])')
  echo "  $SC -> $N documenti"
  [ "$N" -gt 0 ] || { c_red "FAIL: 0 docs per $SC"; exit 1; }
done

c_green "==> Smoke UX PASSED"
echo
