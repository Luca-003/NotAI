"""Repository pattern per Practice. La sessione (con tenant scoping RLS) e' iniettata."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Practice


class PracticeRepository:
    """CRUD su Practice. Tutte le query passano per RLS (SET LOCAL app.tenant_id)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, practice_id: uuid.UUID) -> Practice | None:
        return (
            await self.session.execute(
                select(Practice).where(
                    Practice.id == practice_id, Practice.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[Practice]:
        rows = await self.session.execute(
            select(Practice)
            .where(Practice.deleted_at.is_(None))
            .order_by(Practice.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return rows.scalars().all()

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        code: str,
        kind: str,
        title: str,
        description: str | None = None,
        responsible_user_id: uuid.UUID | None = None,
    ) -> Practice:
        p = Practice(
            tenant_id=tenant_id,
            code=code,
            kind=kind,
            title=title,
            description=description,
            responsible_user_id=responsible_user_id,
        )
        self.session.add(p)
        await self.session.flush()
        return p


__all__ = ["PracticeRepository"]
