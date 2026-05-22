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
from notai.contexts.audit.streams import stream_for_act
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
            stream_id=stream_for_act(ctx.act_id),
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
    payload["_summary"] = TelemacoAdapter.summarize(payload)
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
    payload["_summary"] = AnprAdapter.summarize(payload)
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


def _build_act_sections(template_id: str, slots: dict) -> list[dict]:
    """Genera la struttura dell'atto dal template registry (file YAML).

    Il template definisce sezioni, titoli, testo, relies_on. Se il template_id
    non e' nel registry, ritorna fallback minimo (header + parti) per non
    bloccare il workflow ma segnalando errore in audit.
    """
    from notai.contexts.drafting.registry import get_template

    enriched = dict(slots)
    enriched["template_id"] = template_id
    enriched["today"] = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    tpl = get_template(template_id)
    if tpl is not None:
        return tpl.render_sections(enriched)

    logger.warning("notai.draft.template_not_found", template_id=template_id)
    return [
        {
            "id": "header",
            "title": "Intestazione",
            "text": (
                f"**Bozza atto** — `{template_id}` (template non trovato nel registry).\n\n"
                "Il documento verra' completato manualmente."
            ),
            "relies_on": [],
        },
        {
            "id": "parties",
            "title": "Parti",
            "text": "\n".join(
                f"- **{p.get('role','-')}**: {p.get('fiscal_code') or p.get('vat') or '—'}"
                for p in (slots.get("parties") or [])
            ) or "_(nessuna parte)_",
            "relies_on": ["person_name", "fiscal_code", "company_name", "vat_number"],
        },
    ]


def _sections_to_markdown(sections: list[dict]) -> str:
    """Render markdown delle sezioni per il viewer."""
    blocks = []
    for s in sections:
        blocks.append(f"## {s['title']}\n\n{s['text']}")
    return "\n\n---\n\n".join(blocks)


@activity.defn(name="draft.generate")
async def draft_generate(req: DraftRequest) -> DraftResult:
    """Genera bozza atto da template + provenance euristica dai chunk input."""
    from minio.error import S3Error
    from sqlalchemy import select as sa_select

    from notai.contexts.documents.kinds import INPUT_SOURCE
    from notai.contexts.documents.models import (
        Document,
        DocumentChunk,
        ProvenanceLink,
    )
    from notai.contexts.documents.storage import put_text
    from notai.shared.db.soft_delete import not_deleted

    activity.heartbeat("rendering draft")
    sections = _build_act_sections(req.template_id, req.slots)
    text_content = _sections_to_markdown(sections)
    tenant_uuid = uuid.UUID(req.ctx.tenant_id)
    act_uuid = uuid.UUID(req.ctx.act_id)
    doc_id = uuid.uuid4()
    key = f"draft/{req.ctx.tenant_id}/{req.ctx.act_id}/{doc_id}.md"
    bucket = "notai-documents"

    try:
        storage_uri, sha = await put_text(bucket, key, text_content)
        upload_ok = True
    except S3Error as e:
        logger.warning("notai.draft.storage_failed", error=str(e))
        storage_uri = f"s3://{bucket}/{key}"
        sha = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
        upload_ok = False

    provenance_count = 0
    async with scoped_session(tenant_uuid) as session:
        # 1) Carica i chunks classificati dei documenti di input dell'atto
        chunk_rows = (
            await session.execute(
                sa_select(DocumentChunk, Document.id.label("doc_id"))
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(
                    Document.act_id == act_uuid,
                    Document.kind == INPUT_SOURCE,
                    not_deleted(Document),
                )
            )
        ).all()

        # Indice: per ogni "relies_on" type, lista di (chunk, source_doc_id)
        chunks_by_entity_type: dict[str, list] = {}
        chunks_by_doc_type: dict[str, list] = {}
        for row in chunk_rows:
            chunk = row[0]
            doc_id_src = row[1]
            cls = chunk.classification or {}
            if cls.get("abstained") or "error" in cls:
                continue
            doc_type = cls.get("document_type")
            if doc_type:
                chunks_by_doc_type.setdefault(doc_type, []).append((chunk, doc_id_src))
            for ent in cls.get("entities") or []:
                etype = ent.get("type")
                if etype:
                    chunks_by_entity_type.setdefault(etype, []).append((chunk, doc_id_src))

        # 2) Per ogni sezione, deduce provenance dai relies_on
        provenance_records: list[ProvenanceLink] = []
        sections_with_sources: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()
        for section in sections:
            section_sources: list[dict] = []
            for relies in section.get("relies_on", []):
                candidates = chunks_by_entity_type.get(relies, [])
                for chunk, src_doc_id in candidates:
                    pair = (section["id"], str(chunk.id))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    section_sources.append({
                        "chunk_id": str(chunk.id),
                        "source_document_id": str(src_doc_id),
                        "entity_type": relies,
                    })
                    provenance_records.append(
                        ProvenanceLink(
                            tenant_id=tenant_uuid,
                            output_document_id=doc_id,
                            output_section_id=section["id"],
                            source_chunk_id=chunk.id,
                            source_document_id=src_doc_id,
                            relation="uses_entity",
                            rationale=(
                                f"sezione '{section['title']}' usa entita' di tipo "
                                f"'{relies}' estratte dal chunk #{chunk.ordering}"
                            ),
                            confidence=0.85,
                        )
                    )
            # Anche provenance per document_type esplicito (visure -> sezione visure/art_1)
            if section["id"] in ("visure", "art_1") and "visura_catastale" in chunks_by_doc_type:
                for chunk, src_doc_id in chunks_by_doc_type["visura_catastale"]:
                    pair = (section["id"], str(chunk.id))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    section_sources.append({
                        "chunk_id": str(chunk.id),
                        "source_document_id": str(src_doc_id),
                        "document_type": "visura_catastale",
                    })
                    provenance_records.append(
                        ProvenanceLink(
                            tenant_id=tenant_uuid,
                            output_document_id=doc_id,
                            output_section_id=section["id"],
                            source_chunk_id=chunk.id,
                            source_document_id=src_doc_id,
                            relation="derived_from",
                            rationale=(
                                f"sezione '{section['title']}' deriva dalla visura "
                                f"catastale (chunk #{chunk.ordering})"
                            ),
                            confidence=0.9,
                        )
                    )

            section_with_meta = {**section, "sources": section_sources}
            sections_with_sources.append(section_with_meta)

        # 3) Persisti Document + sections + provenance
        doc = Document(
            id=doc_id,
            tenant_id=tenant_uuid,
            act_id=act_uuid,
            practice_id=uuid.UUID(req.ctx.practice_id),
            kind="bozza_atto",
            filename=f"bozza-{doc_id}.md",
            mime_type="text/markdown",
            size_bytes=len(text_content.encode("utf-8")),
            storage_uri=storage_uri,
            sha256=sha,
            retention_class="nessuna",
            extra={"template_id": req.template_id, "upload_ok": upload_ok},
            sections=sections_with_sources,
        )
        session.add(doc)
        if provenance_records:
            session.add_all(provenance_records)
            provenance_count = len(provenance_records)
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
            "sections_count": len(sections_with_sources),
            "provenance_links_count": provenance_count,
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
