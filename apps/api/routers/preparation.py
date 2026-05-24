"""Endpoint /api/v1/acts/{id}/preparation - fase 'pre-workflow' esplicita.

Modello: prima di avviare il workflow Temporal (draft+tax+review), il notaio
passa per 4 step espliciti:
  1. CATALOGO: i documenti caricati sono ingeriti + classificati
  2. VISURE NEEDED: cosa manca rispetto al template
  3. VISURE ACQUIRED: visure auto-acquisite (mock adapter -> Document)
  4. CONSOLIDA: notaio approva, l'atto puo' passare a draft

Solo dopo consolidate() il workflow puo' partire (`can_execute=true`).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from apps.api.bg import background_safe
from apps.api.deps import DbDep, TenantDep
from notai.contexts.audit.logger import audit_logger
from notai.contexts.audit.streams import stream_for_act
from notai.contexts.documents.ingestion import ingest_document
from notai.contexts.documents.models import Document, DocumentChunk
from notai.contexts.documents.storage import put_blob
from notai.contexts.drafting.registry import get_template
from notai.contexts.integrations.anpr import AnprAdapter
from notai.contexts.integrations.telemaco import TelemacoAdapter
from notai.contexts.practices.acts_repository import ActRepository
from notai.shared.db.soft_delete import not_deleted

router = APIRouter(prefix="/acts", tags=["preparation"])


# ---------------------------------------------------------------------------
# GET status
# ---------------------------------------------------------------------------


def _template_expected_doc_types(slot_schema: dict[str, Any]) -> set[str]:
    """Per ogni slot del template, raccoglie i document_type elencati in
    `extract_from`. Risultato: set di tipi attesi (es. {visura_catastale, ...}).
    """
    types: set[str] = set()
    for spec in (slot_schema or {}).values():
        if isinstance(spec, dict):
            for t in spec.get("extract_from", []) or []:
                types.add(str(t))
    return types


@router.get("/{act_id}/preparation")
async def get_preparation_status(
    act_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> dict:
    """Stato dei 4 step pre-workflow per un atto."""
    del principal
    act = await ActRepository(session).get(act_id)
    if act is None:
        raise HTTPException(status_code=404, detail="act not found")

    template_id = act.kind + ":v1"  # convenzione: kind->template
    tpl = get_template(template_id)
    expected_types = _template_expected_doc_types(tpl.slot_schema if tpl else {})

    # Documenti dell'atto
    docs = (
        await session.execute(
            select(Document)
            .where(Document.act_id == act_id, not_deleted(Document))
            .order_by(Document.created_at.asc())
        )
    ).scalars().all()

    inputs = [d for d in docs if d.kind in ("input_source", "allegato")]
    visure_auto = [d for d in docs if d.kind == "visura_auto"]

    # Step 1: catalogo
    docs_total = len(inputs) + len(visure_auto)
    docs_classified = sum(
        1 for d in (inputs + visure_auto) if d.ingestion_status == "done"
    )
    chunks_rows = (
        await session.execute(
            select(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                Document.act_id == act_id,
                Document.kind.in_(["input_source", "allegato", "visura_auto"]),
                not_deleted(Document),
            )
        )
    ).scalars().all()
    chunks_total = len(chunks_rows)
    chunks_classified = sum(
        1 for c in chunks_rows if c.classification_status == "done"
    )

    # Breakdown per status (utile alla progress bar nel FE)
    chunk_status_breakdown: dict[str, int] = {
        "pending": 0, "in_progress": 0, "done": 0, "abstained": 0, "failed": 0,
    }
    last_activity_at: str | None = None
    for c in chunks_rows:
        st = c.classification_status or "pending"
        if st in chunk_status_breakdown:
            chunk_status_breakdown[st] += 1
        if c.classified_at is not None:
            iso = c.classified_at.isoformat()
            if last_activity_at is None or iso > last_activity_at:
                last_activity_at = iso

    catalog_status = (
        "ready"
        if docs_total > 0 and docs_total == docs_classified and chunks_total == chunks_classified and chunks_total > 0
        else "pending"
    )

    # Step 2: tipi documento mancanti rispetto al template
    classified_types: set[str] = set()
    for c in chunks_rows:
        cls = c.classification or {}
        dt = cls.get("document_type")
        if dt and dt != "indeterminato":
            classified_types.add(dt)

    covered = expected_types & classified_types
    missing = expected_types - classified_types

    # Step 3: visure gia' auto-acquisite
    visure_acquired = [
        {
            "id": str(d.id),
            "filename": d.filename,
            "source": (d.extra or {}).get("source_adapter", "?"),
            "ingestion_status": d.ingestion_status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in visure_auto
    ]

    # Step 4: consolidamento - leggi flag dall'extra dell'atto
    extra = act.extra or {}
    prep = extra.get("preparation") or {}
    consolidated_at = prep.get("consolidated_at")
    consolidated = consolidated_at is not None

    # can_execute: il notaio ha esplicitamente consolidato e il workflow
    # non e' gia' partito. Il catalog status e' informativo: il notaio puo'
    # consolidare anche con ingestion in corso (la slot_extract poi
    # vedra' i chunk che ci sono).
    can_execute = consolidated and not act.workflow_run_id

    # Preview slot extraction (se gia' calcolato via /extract-preview)
    preview = extra.get("preview_slots")

    return {
        "act_id": str(act_id),
        "template_id": template_id,
        "template_known": tpl is not None,
        "step1_catalog": {
            "documents_total": docs_total,
            "documents_classified": docs_classified,
            "chunks_total": chunks_total,
            "chunks_classified": chunks_classified,
            "chunk_status_breakdown": chunk_status_breakdown,
            "last_activity_at": last_activity_at,
            "status": catalog_status,
        },
        "step2_visure_needed": {
            "expected_document_types": sorted(expected_types),
            "classified_document_types": sorted(classified_types),
            "covered": sorted(covered),
            "missing": sorted(missing),
            "available_adapters": ["telemaco", "anpr"],
        },
        "step3_visure_acquired": {
            "count": len(visure_acquired),
            "items": visure_acquired,
        },
        "step4_consolidation": {
            "consolidated": consolidated,
            "consolidated_at": consolidated_at,
        },
        "preview_slots": preview,  # null se /extract-preview non ancora chiamato
        "can_execute": can_execute,
        "workflow_run_id": act.workflow_run_id,
    }


# ---------------------------------------------------------------------------
# POST acquire-visure
# ---------------------------------------------------------------------------


class AcquireVisureRequest(BaseModel):
    adapter: str  # "telemaco" | "anpr"
    party_fiscal_code: str | None = None
    party_vat: str | None = None


def _render_visura_markdown(adapter: str, payload: dict) -> str:
    """Stampa un .md leggibile (e classificabile come document_type)
    dalla risposta JSON di un adapter mock.
    """
    if adapter == "telemaco":
        sede = payload.get("sede_legale") or {}
        amms = payload.get("amministratori") or []
        amms_md = "\n".join(
            f"  - {a.get('nome','')} {a.get('cognome','')} - {a.get('ruolo','')} (CF: {a.get('fiscal_code','-')})"
            for a in amms
        )
        return (
            f"# Visura camerale (acquisita automaticamente via Telemaco)\n\n"
            f"**Denominazione**: {payload.get('denominazione','?')}\n"
            f"**P.IVA**: {payload.get('vat_number','-')}\n"
            f"**Codice fiscale**: {payload.get('fiscal_code','-')}\n"
            f"**Forma giuridica**: {payload.get('forma_giuridica','?')}\n"
            f"**Data costituzione**: {payload.get('data_costituzione','?')}\n"
            f"**Sede legale**: {sede.get('via','?')}, {sede.get('cap','')} {sede.get('comune','')} ({sede.get('provincia','')})\n"
            f"**Capitale sociale**: EUR {payload.get('capitale_sociale','-')}\n"
            f"**Stato**: {payload.get('stato','-')}\n"
            f"**Iscrizione REA**: {payload.get('iscrizione_rea','-')}\n\n"
            f"## Amministratori\n{amms_md or '_(nessuno)_'}\n"
        )
    if adapter == "anpr":
        nascita = payload.get("luogo_nascita") or {}
        residenza = payload.get("residenza") or {}
        return (
            f"# Visura anagrafica ANPR (acquisita automaticamente)\n\n"
            f"**Cognome e nome**: {payload.get('cognome','')} {payload.get('nome','')}\n"
            f"**CF**: {payload.get('fiscal_code','-')}\n"
            f"**Sesso**: {payload.get('sesso','-')}\n"
            f"**Data nascita**: {payload.get('data_nascita','-')}\n"
            f"**Luogo nascita**: {nascita.get('comune','?')} ({nascita.get('provincia','-')})\n"
            f"**Residenza**: {residenza.get('via','?')}, {residenza.get('cap','')} {residenza.get('comune','')} ({residenza.get('provincia','')})\n"
            f"**Stato civile**: {payload.get('stato_civile','-')}\n"
            f"**Cittadinanza**: {payload.get('cittadinanza','-')}\n"
        )
    raise ValueError(f"adapter sconosciuto: {adapter}")


@background_safe("notai.preparation.acquire_ingest")
async def _ingest_acquired(doc_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await ingest_document(doc_id, tenant_id)


@router.post(
    "/{act_id}/preparation/acquire-visure",
    status_code=status.HTTP_201_CREATED,
)
async def acquire_visure(
    act_id: uuid.UUID,
    payload: AcquireVisureRequest,
    principal: TenantDep,
    session: DbDep,
    background: BackgroundTasks,
) -> dict:
    """Chiama l'adapter mock + salva il risultato come Document kind=visura_auto.

    Il nuovo Document parte in ingestion (parse + chunks + embed + classify)
    in background, quindi appare nell'albero come visura_acquisita e finisce
    nello slot_extract al prossimo run del workflow.
    """
    act = await ActRepository(session).get(act_id)
    if act is None:
        raise HTTPException(status_code=404, detail="act not found")

    if payload.adapter == "telemaco":
        adapter = TelemacoAdapter()
        key = payload.party_vat or payload.party_fiscal_code or ""
        raw = await adapter.fetch_company_data(vat_or_fiscal=key)
    elif payload.adapter == "anpr":
        adapter_a = AnprAdapter()
        raw = await adapter_a.fetch_person_data(fiscal_code=payload.party_fiscal_code or "")
    else:
        raise HTTPException(status_code=400, detail=f"adapter sconosciuto: {payload.adapter}")

    if not raw:
        raise HTTPException(
            status_code=502,
            detail=f"adapter {payload.adapter} non ha trovato dati per la chiave fornita",
        )

    md_text = _render_visura_markdown(payload.adapter, raw)
    data = md_text.encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    doc_id = uuid.uuid4()
    filename = f"{payload.adapter}-auto-{doc_id.hex[:8]}.md"
    key_path = (
        f"input/{principal.tenant_id}/act/{act_id}/{doc_id}/{filename}"
    )
    bucket = "notai-documents"
    storage_uri, _ = await put_blob(bucket, key_path, data, "text/markdown")

    doc = Document(
        id=doc_id,
        tenant_id=principal.tenant_id,
        practice_id=act.practice_id,
        act_id=act_id,
        kind="visura_auto",
        filename=filename,
        mime_type="text/markdown",
        size_bytes=len(data),
        storage_uri=storage_uri,
        sha256=sha,
        retention_class="nessuna",
        extra={
            "source_adapter": payload.adapter,
            "adapter_payload_keys": sorted(list(raw.keys())),
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    session.add(doc)
    await session.flush()

    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=stream_for_act(act_id),
        type="preparation.visura_acquired",
        payload={
            "document_id": str(doc_id),
            "adapter": payload.adapter,
            "filename": filename,
            "sha256": sha,
            "payload_keys": sorted(list(raw.keys())),
        },
        actor=principal.as_actor(),
    )

    await session.commit()
    background.add_task(_ingest_acquired, doc_id, principal.tenant_id)

    return {
        "document_id": str(doc_id),
        "filename": filename,
        "adapter": payload.adapter,
        "ingestion_status": "pending",
    }


# ---------------------------------------------------------------------------
# POST extract-preview
# ---------------------------------------------------------------------------


@router.post("/{act_id}/preparation/extract-preview")
async def extract_preview(
    act_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> dict:
    """Esegue lo slot extractor LLM SUBITO (fuori dal workflow Temporal) e
    salva il risultato su act.extra.preview_slots per anteprima nella UI.

    Idempotente: ri-eseguibile, sovrascrive il preview precedente.
    Quando il workflow Temporal parte, lo slot_extract gira di nuovo dentro
    (per la durable history). I due risultati dovrebbero coincidere, ma il
    workflow e' la fonte autoritativa.
    """
    from notai.contexts.drafting.registry import get_template
    from notai.contexts.drafting.slot_extractor import extract_slots

    act = await ActRepository(session).get(act_id)
    if act is None:
        raise HTTPException(status_code=404, detail="act not found")

    template_id = act.kind + ":v1"
    tpl = get_template(template_id)
    if tpl is None:
        raise HTTPException(
            status_code=400,
            detail=f"template '{template_id}' non trovato nel registry",
        )

    extraction = await extract_slots(
        act_id=act_id,
        tenant_id=principal.tenant_id,
        template_id=template_id,
        slot_schema=tpl.slot_schema,
    )

    slots: dict[str, object] = {}
    provenance: dict[str, dict] = {}
    abstained: list[str] = []
    for s in extraction.slots:
        if s.abstain:
            abstained.append(s.name)
            continue
        slots[s.name] = s.value
        provenance[s.name] = {
            "chunk_id": s.source_chunk_id,
            "char_start": s.source_char_start,
            "char_end": s.source_char_end,
            "confidence": s.confidence,
        }

    extra = dict(act.extra or {})
    extra["preview_slots"] = {
        "slots": slots,
        "provenance": provenance,
        "abstained": abstained,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "template_id": template_id,
    }
    act.extra = extra

    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=stream_for_act(act_id),
        type="preparation.slots_previewed",
        payload={
            "template_id": template_id,
            "slots_extracted": list(slots.keys()),
            "slots_abstained": abstained,
        },
        actor=principal.as_actor(),
    )

    return {
        "act_id": str(act_id),
        "template_id": template_id,
        "slots": slots,
        "provenance": provenance,
        "abstained": abstained,
    }


# ---------------------------------------------------------------------------
# POST consolidate
# ---------------------------------------------------------------------------


@router.post("/{act_id}/preparation/consolidate")
async def consolidate_preparation(
    act_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> dict:
    """Notaio dichiara 'i documenti di input sono pronti'. Sblocca il workflow.

    Pre-condizione consigliata: tutti i docs classificati. Non rigida: il notaio
    puo' procedere comunque (responsabilita' sua).
    """
    act = await ActRepository(session).get(act_id)
    if act is None:
        raise HTTPException(status_code=404, detail="act not found")
    if act.workflow_run_id:
        raise HTTPException(
            status_code=409, detail="workflow gia' avviato, consolidamento non ha senso"
        )

    extra = dict(act.extra or {})
    prep = dict(extra.get("preparation") or {})
    now_iso = datetime.now(timezone.utc).isoformat()
    prep["consolidated_at"] = now_iso
    prep["consolidated_by"] = principal.as_actor()
    extra["preparation"] = prep
    act.extra = extra

    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=stream_for_act(act_id),
        type="preparation.consolidated",
        payload={"consolidated_at": now_iso},
        actor=principal.as_actor(),
    )

    return {
        "act_id": str(act_id),
        "consolidated_at": now_iso,
        "can_execute": True,
    }


__all__ = ["router"]
