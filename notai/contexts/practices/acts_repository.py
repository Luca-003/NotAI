"""Repository per Act."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Act


class ActRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, act_id: uuid.UUID) -> Act | None:
        return (
            await self.session.execute(
                select(Act).where(Act.id == act_id, Act.deleted_at.is_(None))
            )
        ).scalar_one_or_none()

    async def list_by_practice(self, practice_id: uuid.UUID) -> Sequence[Act]:
        rows = await self.session.execute(
            select(Act)
            .where(Act.practice_id == practice_id, Act.deleted_at.is_(None))
            .order_by(Act.created_at.desc())
        )
        return rows.scalars().all()

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        practice_id: uuid.UUID,
        kind: str,
        title: str,
    ) -> Act:
        act = Act(
            tenant_id=tenant_id,
            practice_id=practice_id,
            kind=kind,
            title=title,
        )
        self.session.add(act)
        await self.session.flush()
        return act

    async def update_workflow(
        self, act_id: uuid.UUID, *, workflow_run_id: str, status: str
    ) -> None:
        act = await self.get(act_id)
        if act is None:
            return
        act.workflow_run_id = workflow_run_id
        act.workflow_status = status
