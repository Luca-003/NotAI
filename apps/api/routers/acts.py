"""Endpoint /acts - creazione atti + workflow Temporal."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from sqlalchemy import select

from apps.api.deps import DbDep, TenantDep
from apps.api.deps_modules import module_required
from apps.api.routers.documents import DocumentRead
from notai.contexts.audit.logger import audit_logger
from notai.contexts.audit.streams import stream_for_act
from notai.contexts.documents.kinds import INPUT_SOURCE
from notai.contexts.documents.models import Document
from notai.contexts.practices.acts_repository import ActRepository
from notai.contexts.workflow.client import get_temporal_client
from notai.contexts.workflow.common import (
    HumanReviewDecision,
    HumanReviewResponse,
    WorkflowContext,
    make_workflow_id,
)
from notai.contexts.workflow.workflows import (
    AtoWorkflow,
    AtoWorkflowInput,
    AtoWorkflowState,
)

router = APIRouter(prefix="/acts", tags=["acts"])

WORKFLOW_TASK_QUEUE = "notai-main"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ActCreate(BaseModel):
    practice_id: uuid.UUID
    kind: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=512)


class ActRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    practice_id: uuid.UUID
    kind: str
    title: str
    workflow_status: str
    workflow_run_id: str | None


class PartyInput(BaseModel):
    role: str
    kind: str = "PF"            # PF | PG
    fiscal_code: str | None = None
    vat: str | None = None


class StartWorkflowRequest(BaseModel):
    template_id: str = Field(..., max_length=128)
    base_imponibile: float
    is_prima_casa: bool = False
    parties: list[PartyInput] = Field(default_factory=list)


class HumanReviewSignal(BaseModel):
    decision: str = Field(..., pattern=r"^(approved|rejected|changed)$")
    notes: str | None = None
    modifications: dict | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ActRead, status_code=status.HTTP_201_CREATED)
async def create_act(
    payload: ActCreate, principal: TenantDep, session: DbDep
) -> ActRead:
    repo = ActRepository(session)
    act = await repo.create(
        tenant_id=principal.tenant_id,
        practice_id=payload.practice_id,
        kind=payload.kind,
        title=payload.title,
    )
    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=stream_for_act(act.id),
        type="act.created",
        payload={
            "act_id": str(act.id),
            "practice_id": str(act.practice_id),
            "kind": act.kind,
            "title": act.title,
        },
        actor=principal.as_actor(),
    )
    return ActRead.model_validate(act)


@router.get("/{act_id}", response_model=ActRead)
async def get_act(act_id: uuid.UUID, principal: TenantDep, session: DbDep) -> ActRead:
    del principal
    act = await ActRepository(session).get(act_id)
    if act is None:
        raise HTTPException(status_code=404, detail="act not found")
    return ActRead.model_validate(act)


@router.post(
    "/{act_id}/workflow/start",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[module_required("notaio.workflow")],
)
async def start_workflow(
    act_id: uuid.UUID,
    payload: StartWorkflowRequest,
    principal: TenantDep,
    session: DbDep,
) -> dict:
    repo = ActRepository(session)
    act = await repo.get(act_id)
    if act is None:
        raise HTTPException(status_code=404, detail="act not found")

    wf_id = make_workflow_id(act_id)
    ctx = WorkflowContext(
        tenant_id=str(principal.tenant_id),
        act_id=str(act_id),
        practice_id=str(act.practice_id),
        actor=principal.as_actor(),
    )
    wf_input = AtoWorkflowInput(
        ctx=ctx,
        template_id=payload.template_id,
        base_imponibile=payload.base_imponibile,
        is_prima_casa=payload.is_prima_casa,
        parties=[p.model_dump() for p in payload.parties],
    )

    client = await get_temporal_client()
    handle = await client.start_workflow(
        AtoWorkflow.run,
        wf_input,
        id=wf_id,
        task_queue=WORKFLOW_TASK_QUEUE,
    )

    await repo.update_workflow(
        act_id,
        workflow_run_id=handle.first_execution_run_id or wf_id,
        status="running",
    )
    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=stream_for_act(act_id),
        type="workflow.started",
        payload={
            "workflow_id": wf_id,
            "template_id": payload.template_id,
            "base_imponibile": payload.base_imponibile,
        },
        actor=principal.as_actor(),
    )

    return {"workflow_id": wf_id, "run_id": handle.first_execution_run_id}


@router.get(
    "/{act_id}/workflow/status",
    dependencies=[module_required("notaio.workflow")],
)
async def get_workflow_status(
    act_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> dict:
    del principal
    act = await ActRepository(session).get(act_id)
    if act is None:
        raise HTTPException(status_code=404, detail="act not found")

    wf_id = make_workflow_id(act_id)
    client = await get_temporal_client()
    try:
        handle = client.get_workflow_handle(wf_id)
        state: AtoWorkflowState = await handle.query(
            "state", result_type=AtoWorkflowState
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=404, detail=f"workflow state unavailable: {e}"
        ) from e
    try:
        desc = await handle.describe()
        status_temporal = desc.status.name if desc.status else None
    except Exception:  # noqa: BLE001
        status_temporal = None
    return {
        "workflow_id": wf_id,
        "status_temporal": status_temporal,
        "state": {
            "status": state.status,
            "visure": state.visure,
            "draft": state.draft,
            "tax": state.tax,
            "review": state.review,
        },
    }


@router.post(
    "/{act_id}/workflow/human-review",
    dependencies=[module_required("notaio.workflow")],
)
async def signal_human_review(
    act_id: uuid.UUID,
    payload: HumanReviewSignal,
    principal: TenantDep,
    session: DbDep,
) -> dict:
    """Invia un signal al workflow per chiudere il HumanTask di review."""
    if (await ActRepository(session).get(act_id)) is None:
        raise HTTPException(status_code=404, detail="act not found")
    # Valida la decision contro l'Enum (defense in depth oltre al regex Pydantic)
    HumanReviewDecision(payload.decision)

    response = HumanReviewResponse(
        decision=payload.decision,
        notes=payload.notes,
        user_id=principal.as_actor(),
        completed_at=datetime.now(timezone.utc),
        modifications=payload.modifications,
    )

    wf_id = make_workflow_id(act_id)
    client = await get_temporal_client()
    handle = client.get_workflow_handle(wf_id)
    await handle.signal("human_review_response", response)

    return {"signaled": True, "workflow_id": wf_id}


@router.get("/{act_id}/documents", response_model=list[DocumentRead])
async def list_documents_of_act(
    act_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> list[DocumentRead]:
    """Lista documenti dell'atto (input + output), ordine cronologico ascendente."""
    del principal
    if (await ActRepository(session).get(act_id)) is None:
        raise HTTPException(status_code=404, detail="act not found")
    rows = await session.execute(
        select(Document)
        .where(Document.act_id == act_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.asc())
    )
    return [DocumentRead.model_validate(d) for d in rows.scalars().all()]


def _make_snippet(text: str, lower_needle: str, needle_len: int) -> str:
    """Estrae ~160 char attorno al needle (case-insensitive), con ellipsi."""
    if not text:
        return ""
    idx = text.lower().find(lower_needle)
    if idx < 0:
        return text[:160] + ("…" if len(text) > 160 else "")
    start = max(0, idx - 60)
    end = min(len(text), idx + needle_len + 100)
    return (
        ("…" if start > 0 else "")
        + text[start:end]
        + ("…" if end < len(text) else "")
    )


async def _search_input_chunks(
    session, act_id: uuid.UUID, pattern: str, lower_needle: str, needle_len: int, limit: int
) -> list[dict]:
    import sqlalchemy as sa
    from sqlalchemy import or_
    from notai.contexts.documents.models import DocumentChunk

    rows = await session.execute(
        select(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            Document.act_id == act_id,
            Document.kind == INPUT_SOURCE,
            Document.deleted_at.is_(None),
            or_(
                DocumentChunk.text.ilike(pattern),
                DocumentChunk.classification.cast(sa.String).ilike(pattern),
            ),
        )
        .limit(limit)
    )
    return [
        {
            "kind": "input_chunk",
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "filename": doc.filename,
            "ordering": chunk.ordering,
            "page_number": chunk.page_number,
            "document_type": (chunk.classification or {}).get("document_type"),
            "snippet": _make_snippet(chunk.text, lower_needle, needle_len),
        }
        for chunk, doc in rows.all()
    ]


async def _search_output_sections(
    session, act_id: uuid.UUID, lower_needle: str, needle_len: int, limit: int
) -> list[dict]:
    docs = (
        await session.execute(
            select(Document).where(
                Document.act_id == act_id,
                Document.kind != INPUT_SOURCE,
                Document.deleted_at.is_(None),
                Document.sections.is_not(None),
            )
        )
    ).scalars().all()

    hits: list[dict] = []
    for d in docs:
        for section in d.sections or []:
            text = section.get("text") or ""
            title = section.get("title") or ""
            if lower_needle in (text + " " + title).lower():
                hits.append({
                    "kind": "output_section",
                    "document_id": str(d.id),
                    "filename": d.filename,
                    "section_id": section.get("id"),
                    "section_title": section.get("title"),
                    "snippet": _make_snippet(text, lower_needle, needle_len),
                })
                if len(hits) >= limit:
                    return hits
    return hits


@router.get("/{act_id}/search")
async def search_in_act(
    act_id: uuid.UUID,
    principal: TenantDep,
    session: DbDep,
    q: str,
    limit: int = 20,
) -> dict:
    """Ricerca testuale (case-insensitive) su input chunks + output sections.

    In Fase 5 ILIKE su Postgres (con indice pg_trgm); in fasi successive
    aggiungeremo dense retrieval via Qdrant + BM25 via OpenSearch.
    """
    del principal
    if (await ActRepository(session).get(act_id)) is None:
        raise HTTPException(status_code=404, detail="act not found")
    needle = (q or "").strip()
    if len(needle) < 2:
        return {"query": q, "input_hits": [], "output_hits": [], "total": 0}

    lower_needle = needle.lower()
    pattern = f"%{lower_needle}%"
    nlen = len(needle)

    input_hits = await _search_input_chunks(session, act_id, pattern, lower_needle, nlen, limit)
    output_hits = await _search_output_sections(session, act_id, lower_needle, nlen, limit)

    return {
        "query": q,
        "input_hits": input_hits,
        "output_hits": output_hits,
        "total": len(input_hits) + len(output_hits),
    }
