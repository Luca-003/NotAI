"""Repository per Act."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from notai.shared.db.soft_delete import SoftDeleteRepository, not_deleted

from .models import Act


class ActRepository(SoftDeleteRepository[Act]):
    """CRUD su Act. Eredita get() da SoftDeleteRepository."""

    model = Act

    async def list_by_practice(self, practice_id: uuid.UUID) -> Sequence[Act]:
        rows = await self.session.execute(
            select(Act)
            .where(Act.practice_id == practice_id, not_deleted(Act))
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
