"""Endpoint /practices - CRUD minimo con audit-on-write."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from apps.api.deps import DbDep, TenantDep
from apps.api.routers.acts import ActRead
from notai.contexts.audit.logger import audit_logger
from notai.contexts.audit.streams import stream_for_practice
from notai.contexts.practices.acts_repository import ActRepository
from notai.contexts.practices.repository import PracticeRepository
from notai.contexts.practices.schemas import PracticeCreate, PracticeRead

router = APIRouter(prefix="/practices", tags=["practices"])


@router.post("", response_model=PracticeRead, status_code=status.HTTP_201_CREATED)
async def create_practice(
    payload: PracticeCreate, principal: TenantDep, session: DbDep
) -> PracticeRead:
    repo = PracticeRepository(session)
    try:
        practice = await repo.create(
            tenant_id=principal.tenant_id,
            code=payload.code,
            kind=payload.kind,
            title=payload.title,
            description=payload.description,
            responsible_user_id=payload.responsible_user_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=stream_for_practice(practice.id),
        type="practice.created",
        payload={
            "practice_id": str(practice.id),
            "code": practice.code,
            "kind": practice.kind,
            "title": practice.title,
        },
        actor=principal.as_actor(),
    )
    return PracticeRead.model_validate(practice)


@router.get("", response_model=list[PracticeRead])
async def list_practices(
    principal: TenantDep, session: DbDep, limit: int = 50, offset: int = 0
) -> list[PracticeRead]:
    del principal  # tenant scoping via RLS sulla sessione iniettata
    repo = PracticeRepository(session)
    items = await repo.list(limit=limit, offset=offset)
    return [PracticeRead.model_validate(p) for p in items]


@router.get("/{practice_id}", response_model=PracticeRead)
async def get_practice(
    practice_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> PracticeRead:
    del principal
    repo = PracticeRepository(session)
    p = await repo.get(practice_id)
    if p is None:
        raise HTTPException(status_code=404, detail="practice not found")
    return PracticeRead.model_validate(p)


@router.get("/{practice_id}/acts", response_model=list[ActRead])
async def list_acts_of_practice(
    practice_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> list[ActRead]:
    del principal
    p_repo = PracticeRepository(session)
    if (await p_repo.get(practice_id)) is None:
        raise HTTPException(status_code=404, detail="practice not found")
    acts = await ActRepository(session).list_by_practice(practice_id)
    return [ActRead.model_validate(a) for a in acts]
