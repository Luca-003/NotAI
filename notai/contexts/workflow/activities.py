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
import json
import uuid
from datetime import datetime, timezone

import structlog
from temporalio import activity

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
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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


@activity.defn(name="visura.telemaco")
async def visura_telemaco(req: VisuraRequest) -> VisuraResult:
    """Visura camerale tramite InfoCamere/Telemaco. Mock in Fase 2."""
    activity.heartbeat("starting telemaco visura")
    adapter = TelemacoAdapter()
    payload = await adapter.fetch_company_data(
        vat_or_fiscal=req.party_vat or req.party_fiscal_code or "",
    )
    h = _hash_payload(payload)
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


@activity.defn(name="draft.generate")
async def draft_generate(req: DraftRequest) -> DraftResult:
    """Genera bozza atto da template. Mock in Fase 2: solo stub (real engine in Fase 4)."""
    activity.heartbeat("rendering draft")
    # Stub: il rendering Jinja vero arriva in Fase 4 con il drafting context.
    # Qui creiamo un Document fittizio (testo placeholder) e registriamo l'audit.
    text_content = (
        f"# ATTO {req.template_id}\n\n"
        f"Slot ricevuti:\n{json.dumps(req.slots, indent=2, ensure_ascii=False)}\n"
    )
    sha = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
    doc_id = str(uuid.uuid4())
    storage_uri = f"s3://notai-documents/draft/{req.ctx.tenant_id}/{doc_id}.md"

    await _audit(
        req.ctx,
        event_type="draft.generated",
        payload={
            "document_id": doc_id,
            "template_id": req.template_id,
            "slots_keys": sorted(req.slots.keys()),
            "sha256": sha,
            "storage_uri": storage_uri,
            "stub": True,
        },
    )
    return DraftResult(document_id=doc_id, storage_uri=storage_uri, sha256=sha)


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
