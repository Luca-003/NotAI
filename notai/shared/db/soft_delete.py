"""Helpers per il pattern soft-delete (deleted_at IS NULL)."""

from __future__ import annotations

import uuid
from typing import Generic, Sequence, TypeVar

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


def not_deleted(model: type[T]) -> ColumnElement[bool]:
    """Predicato SQL: model.deleted_at IS NULL.

    Centralizza il check soft-delete duplicato 7+ volte nei router/repo.
    Se in futuro cambiamo la semantica di "non eliminato" (es. nuova
    enum), modifichiamo solo qui.
    """
    return getattr(model, "deleted_at").is_(None)


class SoftDeleteRepository(Generic[T]):
    """Base per repository che operano su modelli soft-deletable.

    Espone get/list/create di base con il filtro deleted_at applicato.
    I subclass possono aggiungere query specifiche del dominio.
    """

    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: uuid.UUID) -> T | None:
        id_col = getattr(self.model, "id")
        return (
            await self.session.execute(
                select(self.model).where(id_col == entity_id, not_deleted(self.model))
            )
        ).scalar_one_or_none()

    async def list_all(self, *, limit: int = 50, offset: int = 0) -> Sequence[T]:
        created_at = getattr(self.model, "created_at", None)
        stmt = select(self.model).where(not_deleted(self.model))
        if created_at is not None:
            stmt = stmt.order_by(created_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        return (await self.session.execute(stmt)).scalars().all()


__all__ = ["SoftDeleteRepository", "not_deleted"]
