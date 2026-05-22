"""Endpoint /acts - creazione atti + workflow Temporal."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from notai.contexts.audit.logger import audit_logger
from notai.contexts.practices.acts_repository import ActRepository
from notai.contexts.workflow.client import get_temporal_client
from notai.contexts.workflow.common import WorkflowContext, make_workflow_id
from notai.contexts.workflow.workflows import AtoWorkflow, AtoWorkflowInput
from notai.shared.tenancy.session import scoped_session

router = APIRouter(prefix="/acts", tags=["acts"])

WORKFLOW_TASK_QUEUE = "notai-main"


def _require_tenant(request: Request) -> tuple[uuid.UUID, str | None]:
    tid = getattr(request.state, "tenant_id", None)
    if tid is None:
        raise HTTPException(status_code=401, detail="missing or invalid JWT")
    return tid, getattr(request.state, "user_id", None)


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
async def create_act(payload: ActCreate, request: Request) -> ActRead:
    tenant_id, actor = _require_tenant(request)
    async with scoped_session(tenant_id) as session:
        repo = ActRepository(session)
        act = await repo.create(
            tenant_id=tenant_id,
            practice_id=payload.practice_id,
            kind=payload.kind,
            title=payload.title,
        )
        await audit_logger.append(
            session=session,
            tenant_id=tenant_id,
            stream_id=f"act:{act.id}",
            type="act.created",
            payload={
                "act_id": str(act.id),
                "practice_id": str(act.practice_id),
                "kind": act.kind,
                "title": act.title,
            },
            actor=actor,
        )
        return ActRead.model_validate(act)


@router.get("/{act_id}", response_model=ActRead)
async def get_act(act_id: uuid.UUID, request: Request) -> ActRead:
    tenant_id, _ = _require_tenant(request)
    async with scoped_session(tenant_id) as session:
        act = await ActRepository(session).get(act_id)
        if act is None:
            raise HTTPException(status_code=404, detail="act not found")
        return ActRead.model_validate(act)


@router.post("/{act_id}/workflow/start", status_code=status.HTTP_202_ACCEPTED)
async def start_workflow(
    act_id: uuid.UUID, payload: StartWorkflowRequest, request: Request
) -> dict:
    tenant_id, actor = _require_tenant(request)

    async with scoped_session(tenant_id) as session:
        repo = ActRepository(session)
        act = await repo.get(act_id)
        if act is None:
            raise HTTPException(status_code=404, detail="act not found")

    wf_id = make_workflow_id(act_id)
    ctx = WorkflowContext(
        tenant_id=str(tenant_id),
        act_id=str(act_id),
        practice_id=str(act.practice_id),
        actor=actor,
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

    async with scoped_session(tenant_id) as session:
        repo = ActRepository(session)
        await repo.update_workflow(
            act_id,
            workflow_run_id=handle.first_execution_run_id or wf_id,
            status="running",
        )
        await audit_logger.append(
            session=session,
            tenant_id=tenant_id,
            stream_id=f"act:{act_id}",
            type="workflow.started",
            payload={
                "workflow_id": wf_id,
                "template_id": payload.template_id,
                "base_imponibile": payload.base_imponibile,
            },
            actor=actor,
        )

    return {"workflow_id": wf_id, "run_id": handle.first_execution_run_id}


@router.get("/{act_id}/workflow/status")
async def get_workflow_status(act_id: uuid.UUID, request: Request) -> dict:
    tenant_id, _ = _require_tenant(request)
    async with scoped_session(tenant_id) as session:
        act = await ActRepository(session).get(act_id)
        if act is None:
            raise HTTPException(status_code=404, detail="act not found")

    wf_id = make_workflow_id(act_id)
    client = await get_temporal_client()
    from notai.contexts.workflow.workflows import AtoWorkflowState
    try:
        handle = client.get_workflow_handle(wf_id)
        # Specifichiamo result_type per la deserializzazione del dataclass.
        state: AtoWorkflowState = await handle.query("state", result_type=AtoWorkflowState)
    except Exception as e:  # noqa: BLE001
        # Stato non disponibile (workflow non esiste o handle invalido)
        raise HTTPException(status_code=404, detail=f"workflow state unavailable: {e}") from e
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


@router.post("/{act_id}/workflow/human-review")
async def signal_human_review(
    act_id: uuid.UUID, payload: HumanReviewSignal, request: Request
) -> dict:
    """Invia un signal al workflow per chiudere il HumanTask di review."""
    tenant_id, actor = _require_tenant(request)
    # Verifica esistenza atto (RLS guard)
    async with scoped_session(tenant_id) as session:
        if (await ActRepository(session).get(act_id)) is None:
            raise HTTPException(status_code=404, detail="act not found")

    from datetime import datetime, timezone

    from notai.contexts.workflow.common import HumanReviewResponse

    response = HumanReviewResponse(
        decision=payload.decision,
        notes=payload.notes,
        user_id=actor,
        completed_at=datetime.now(timezone.utc),
        modifications=payload.modifications,
    )

    wf_id = make_workflow_id(act_id)
    client = await get_temporal_client()
    handle = client.get_workflow_handle(wf_id)
    await handle.signal("human_review_response", response)

    return {"signaled": True, "workflow_id": wf_id}
