"""Repository pattern per Practice. La sessione (con tenant scoping RLS) e' iniettata."""

from __future__ import annotations

import uuid
from typing import Sequence

from notai.shared.db.soft_delete import SoftDeleteRepository

from .models import Practice


class PracticeRepository(SoftDeleteRepository[Practice]):
    """CRUD su Practice. Tutte le query passano per RLS (SET LOCAL app.tenant_id).

    Eredita get() e list_all() da SoftDeleteRepository; aggiunge create().
    """

    model = Practice

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[Practice]:
        return await self.list_all(limit=limit, offset=offset)

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
