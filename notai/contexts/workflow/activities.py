"""Temporal activities: chiamate "lato server" non-deterministiche.

Ogni activity:
  - apre una sessione DB tenant-scoped
  - chiama l'adapter di integrazione (in Fase 2: mock)
  - scrive un AuditEvent per ogni passo significativo
  - ritorna un dataclass serializzabile

Temporal gestisce retry/timeout. Le activity sono idempotenti dove possibile.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import structlog
from temporalio import activity

from notai.contexts.audit.hash_chain import canonical_json
from notai.contexts.audit.logger import audit_logger
from notai.contexts.integrations.anpr import AnprAdapter
from notai.contexts.integrations.telemaco import TelemacoAdapter
from notai.shared.tenancy.session import scoped_session

from .common import (
    DraftRequest,
    DraftResult,
    HumanReviewRequest,
    HumanReviewResponse,
    TaxCalculationRequest,
    TaxCalculationResult,
    VisuraRequest,
    VisuraResult,
    WorkflowContext,
)

logger = structlog.get_logger(__name__)


def _hash_payload(payload: dict) -> str:
    """SHA-256 del payload usando la stessa canonicalization RFC 8785 dell'audit chain."""
    return hashlib.sha256(canonical_json(payload)).hexdigest()


async def _audit(
    ctx: WorkflowContext,
    *,
    event_type: str,
    payload: dict,
) -> None:
    tenant_uuid = uuid.UUID(ctx.tenant_id)
    async with scoped_session(tenant_uuid) as session:
        await audit_logger.append(
            session=session,
            tenant_id=tenant_uuid,
            stream_id=f"act:{ctx.act_id}",
            type=event_type,
            payload=payload,
            actor=ctx.actor or "temporal-worker",
        )


def _summarize_telemaco(payload: dict) -> str:
    if not payload:
        return "nessun risultato"
    den = payload.get("denominazione", "?")
    sede = payload.get("sede_legale") or {}
    citta = sede.get("comune", "?")
    return f"{den} (sede {citta})"


def _summarize_anpr(payload: dict) -> str:
    if not payload:
        return "nessun risultato"
    nome = f"{payload.get('nome', '')} {payload.get('cognome', '')}".strip()
    nascita = payload.get("luogo_nascita") or {}
    return f"{nome}, nato/a a {nascita.get('comune', '?')} il {payload.get('data_nascita', '?')}"


@activity.defn(name="visura.telemaco")
async def visura_telemaco(req: VisuraRequest) -> VisuraResult:
    """Visura camerale tramite InfoCamere/Telemaco. Mock in Fase 2."""
    activity.heartbeat("starting telemaco visura")
    adapter = TelemacoAdapter()
    payload = await adapter.fetch_company_data(
        vat_or_fiscal=req.party_vat or req.party_fiscal_code or "",
    )
    h = _hash_payload(payload)
    payload["_summary"] = _summarize_telemaco(payload)
    result = VisuraResult(
        source="telemaco",
        found=bool(payload),
        payload=payload,
        hash=h,
        fetched_at=datetime.now(timezone.utc),
    )
    await _audit(
        req.ctx,
        event_type="visura.fetched",
        payload={
            "source": "telemaco",
            "input": {"vat": req.party_vat, "fiscal": req.party_fiscal_code},
            "found": result.found,
            "payload_sha256": h,
        },
    )
    logger.info("notai.activity.visura.telemaco", found=result.found, hash=h[:12])
    return result


@activity.defn(name="visura.anpr")
async def visura_anpr(req: VisuraRequest) -> VisuraResult:
    """Verifica anagrafica ANPR. Mock in Fase 2."""
    activity.heartbeat("starting anpr lookup")
    adapter = AnprAdapter()
    payload = await adapter.fetch_person_data(fiscal_code=req.party_fiscal_code or "")
    h = _hash_payload(payload)
    payload["_summary"] = _summarize_anpr(payload)
    result = VisuraResult(
        source="anpr",
        found=bool(payload),
        payload=payload,
        hash=h,
        fetched_at=datetime.now(timezone.utc),
    )
    await _audit(
        req.ctx,
        event_type="visura.fetched",
        payload={
            "source": "anpr",
            "input": {"fiscal_code": req.party_fiscal_code},
            "found": result.found,
            "payload_sha256": h,
        },
    )
    return result


def _render_act_markdown(template_id: str, slots: dict) -> str:
    """Renderer markdown di una bozza notarile.

    NON e' ancora un vero motore Jinja (arriva in Fase 4). Produce un atto
    "credibile" che il notaio puo' leggere e su cui chiedere modifiche.
    Tutti i numeri (importi, date) provengono dagli slots - mai inventati.
    """
    parties = slots.get("parties") or []
    base = slots.get("base_imponibile")
    visure_summaries = slots.get("visure_summaries") or []

    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    parties_md = "\n".join(
        f"- **{p.get('role','-')}** (`{p.get('kind','-')}`): "
        f"CF/PIVA `{p.get('fiscal_code') or p.get('vat') or '—'}`"
        for p in parties
    ) or "_(nessuna parte indicata)_"

    visure_md = "\n".join(
        f"- **{v.get('source')}** — {v.get('summary') or '(dati non disponibili)'} "
        f"`hash: {(v.get('hash') or '')[:12]}…`"
        for v in visure_summaries
    ) or "_(nessuna visura)_"

    return f"""# Bozza atto — {template_id}

> **Stato:** bozza in attesa di review del notaio.
> **Data redazione:** {today}
> **Template:** `{template_id}`

---

## Parti
{parties_md}

## Visure pre-atto acquisite automaticamente
{visure_md}

## Premesso che

a) Le parti dichiarano di essere a conoscenza dei reciproci dati anagrafici come
   risultanti dalle visure di cui sopra, acquisite a cura del notaio rogante
   nelle competenti banche dati (ANPR, Registro Imprese, ove applicabile);

b) il presente atto e' redatto in conformita' al modello standard
   `{template_id}` e dovra' essere riletto, integrato e firmato in presenza
   del notaio rogante;

c) il corrispettivo / valore di riferimento e' pari a EUR
   **{f'{base:,.2f}'.replace(',', '.') if isinstance(base, (int, float)) else '—'}**
   come dichiarato dalle parti.

## Articolo 1 — Oggetto

[Da completare in fase di review: descrizione dell'oggetto dell'atto.]

## Articolo 2 — Prezzo / valore

Le parti dichiarano che il valore di riferimento e' quello indicato in
premessa.

## Articolo 3 — Garanzie e dichiarazioni

I dichiaranti, ai sensi e per gli effetti di cui all'art. 1490 c.c. e
seguenti, garantiscono la conformita' del bene oggetto del presente atto.
La parte trasferente dichiara che il bene e' libero da pesi pregiudizievoli,
salvo quanto eventualmente risultante dalle visure ipo-catastali allegate.

## Articolo 4 — Trascrizione

Il presente atto sara' trascritto nei pubblici registri ai sensi dell'art.
2643 c.c. a cura del notaio rogante.

## Articolo 5 — Imposte

Per gli aspetti fiscali si rinvia al prospetto di calcolo delle imposte
allegato (registro / ipotecaria / catastale), determinate ai sensi del
DPR 131/1986 e del D.Lgs 347/1990.

---

**Note tecniche per il notaio**

Questo testo e' una **bozza preliminare** prodotta da NotAI sulla base del
template `{template_id}` e dei dati raccolti tramite visure automatiche.
Le parti sostanziali (oggetto, prezzo definitivo, clausole specifiche) DEVONO
essere completate e validate dal notaio prima della firma.

Provenienza clausole: `template` (nessuna porzione generata da AI in questa
versione). Eventuali suggerimenti AI futuri verranno marcati con
`generated_by: llm` e accompagnati dal riferimento normativo cited.
"""


@activity.defn(name="draft.generate")
async def draft_generate(req: DraftRequest) -> DraftResult:
    """Genera bozza atto da template e la salva su MinIO + Document su DB."""
    from minio.error import S3Error

    from notai.contexts.documents.models import Document
    from notai.contexts.documents.storage import put_text

    activity.heartbeat("rendering draft")
    text_content = _render_act_markdown(req.template_id, req.slots)
    tenant_uuid = uuid.UUID(req.ctx.tenant_id)
    doc_id = uuid.uuid4()
    key = f"draft/{req.ctx.tenant_id}/{req.ctx.act_id}/{doc_id}.md"
    bucket = "notai-documents"

    try:
        storage_uri, sha = await put_text(bucket, key, text_content)
        upload_ok = True
    except S3Error as e:
        # Se MinIO non risponde, manteniamo lo stub: il workflow puo' andare avanti
        # ma marchiamo l'evento per troubleshooting.
        logger.warning("notai.draft.storage_failed", error=str(e))
        storage_uri = f"s3://{bucket}/{key}"
        sha = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
        upload_ok = False

    # Persisti Document nel DB (sessione tenant-scoped per RLS)
    async with scoped_session(tenant_uuid) as session:
        doc = Document(
            id=doc_id,
            tenant_id=tenant_uuid,
            act_id=uuid.UUID(req.ctx.act_id),
            practice_id=uuid.UUID(req.ctx.practice_id),
            kind="bozza_atto",
            filename=f"bozza-{doc_id}.md",
            mime_type="text/markdown",
            size_bytes=len(text_content.encode("utf-8")),
            storage_uri=storage_uri,
            sha256=sha,
            retention_class="nessuna",
            extra={"template_id": req.template_id, "upload_ok": upload_ok},
        )
        session.add(doc)
        await session.flush()

    await _audit(
        req.ctx,
        event_type="draft.generated",
        payload={
            "document_id": str(doc_id),
            "template_id": req.template_id,
            "slots_keys": sorted(req.slots.keys()),
            "sha256": sha,
            "storage_uri": storage_uri,
            "upload_ok": upload_ok,
            "size_bytes": len(text_content.encode("utf-8")),
        },
    )
    return DraftResult(document_id=str(doc_id), storage_uri=storage_uri, sha256=sha)


@activity.defn(name="tax.calculate")
async def tax_calculate(req: TaxCalculationRequest) -> TaxCalculationResult:
    """Calcolo imposte. In Fase 2 e' un rule engine MOLTO semplificato per
    compravendita immobiliare. Real coverage (registro/ipo/cat/INVIM) in Fase 2.5.

    Rules:
      - prima casa: imposta registro 2% (min 1000 EUR), ipotecaria 50 EUR, catastale 50 EUR
      - seconda casa: registro 9% (min 1000 EUR), ipo 50, cat 50

    Riferimento normativo: DPR 131/86 (registro) - tariffa parte I art. 1.
    """
    items: list[dict] = []
    if req.is_prima_casa:
        registro = max(req.base_imponibile * 0.02, 1000.0)
        items.append({
            "tipo": "registro_prima_casa",
            "aliquota": 0.02,
            "base_imponibile": req.base_imponibile,
            "importo": registro,
            "norm_ref": "dpr.131-1986.tariffa.parte_I.art.1.nota_II_bis",
        })
    else:
        registro = max(req.base_imponibile * 0.09, 1000.0)
        items.append({
            "tipo": "registro_ordinaria",
            "aliquota": 0.09,
            "base_imponibile": req.base_imponibile,
            "importo": registro,
            "norm_ref": "dpr.131-1986.tariffa.parte_I.art.1",
        })
    items.append({"tipo": "ipotecaria", "importo": 50.0, "norm_ref": "dlgs.347-1990.art.1"})
    items.append({"tipo": "catastale", "importo": 50.0, "norm_ref": "dlgs.347-1990.art.10"})
    total = sum(i["importo"] for i in items)

    await _audit(
        req.ctx,
        event_type="tax.calculated",
        payload={
            "act_kind": req.act_kind,
            "base_imponibile": req.base_imponibile,
            "is_prima_casa": req.is_prima_casa,
            "items": items,
            "total": total,
        },
    )
    return TaxCalculationResult(items=items, total=total)


@activity.defn(name="human.review_requested")
async def human_review_requested(req: HumanReviewRequest) -> None:
    """Registra l'apertura di un HumanTask. La risposta arriva via signal,
    non come ritorno di questa activity."""
    await _audit(
        req.ctx,
        event_type="human_task.opened",
        payload={
            "title": req.title,
            "description": req.description,
            "candidates_count": len(req.candidates),
        },
    )


@activity.defn(name="human.review_completed")
async def human_review_completed(
    ctx: WorkflowContext, response: HumanReviewResponse
) -> None:
    """Registra l'esito di un HumanTask completato (chiamata dal workflow dopo signal)."""
    await _audit(
        ctx,
        event_type="human_task.completed",
        payload={
            "decision": response.decision,
            "notes": response.notes,
            "user_id": response.user_id,
            "modifications_keys": (
                sorted(response.modifications.keys())
                if response.modifications else []
            ),
        },
    )


ALL_ACTIVITIES = [
    visura_telemaco,
    visura_anpr,
    draft_generate,
    tax_calculate,
    human_review_requested,
    human_review_completed,
]
