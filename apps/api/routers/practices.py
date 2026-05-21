"""Endpoint /practices - CRUD minimo con audit-on-write."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status

from notai.contexts.audit.logger import audit_logger
from notai.contexts.practices.repository import PracticeRepository
from notai.contexts.practices.schemas import PracticeCreate, PracticeRead
from notai.shared.tenancy.session import scoped_session

router = APIRouter(prefix="/practices", tags=["practices"])


def _require_tenant(request: Request) -> tuple[uuid.UUID, str | None]:
    tid = getattr(request.state, "tenant_id", None)
    if tid is None:
        raise HTTPException(status_code=401, detail="missing or invalid JWT")
    return tid, getattr(request.state, "user_id", None)


@router.post("", response_model=PracticeRead, status_code=status.HTTP_201_CREATED)
async def create_practice(payload: PracticeCreate, request: Request) -> PracticeRead:
    tenant_id, actor = _require_tenant(request)

    async with scoped_session(tenant_id) as session:
        repo = PracticeRepository(session)
        try:
            practice = await repo.create(
                tenant_id=tenant_id,
                code=payload.code,
                kind=payload.kind,
                title=payload.title,
                description=payload.description,
                responsible_user_id=payload.responsible_user_id,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        # Audit append nella stessa transazione: se la write della pratica viene
        # rollbackata, il record audit non viene committato.
        await audit_logger.append(
            session=session,
            tenant_id=tenant_id,
            stream_id=f"practice:{practice.id}",
            type="practice.created",
            payload={
                "practice_id": str(practice.id),
                "code": practice.code,
                "kind": practice.kind,
                "title": practice.title,
            },
            actor=actor,
        )
        # scoped_session committa al __aexit__
        return PracticeRead.model_validate(practice)


@router.get("", response_model=list[PracticeRead])
async def list_practices(request: Request, limit: int = 50, offset: int = 0) -> list[PracticeRead]:
    tenant_id, _ = _require_tenant(request)
    async with scoped_session(tenant_id) as session:
        repo = PracticeRepository(session)
        items = await repo.list(limit=limit, offset=offset)
        return [PracticeRead.model_validate(p) for p in items]


@router.get("/{practice_id}", response_model=PracticeRead)
async def get_practice(practice_id: uuid.UUID, request: Request) -> PracticeRead:
    tenant_id, _ = _require_tenant(request)
    async with scoped_session(tenant_id) as session:
        repo = PracticeRepository(session)
        p = await repo.get(practice_id)
        if p is None:
            raise HTTPException(status_code=404, detail="practice not found")
        return PracticeRead.model_validate(p)
