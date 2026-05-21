"""SQLAlchemy Base + mixin condivisi."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Convenzione di naming uniforme per i constraint - utile per Alembic autogenerate.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base SQLAlchemy per tutti i modelli."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class IdMixin:
    """Primary key UUID v4."""

    @declared_attr
    def id(cls) -> Mapped[uuid.UUID]:
        return _uuid_pk()


class TimestampsMixin:
    """created_at / updated_at gestiti dal DB."""

    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )


class SoftDeleteMixin:
    """Soft delete: invece di DELETE, settiamo deleted_at."""

    @declared_attr
    def deleted_at(cls) -> Mapped[datetime | None]:
        return mapped_column(DateTime(timezone=True), nullable=True)


class TenantMixin:
    """Tutte le entita' di dominio sono tenant-scoped.

    La colonna tenant_id e' SEMPRE NOT NULL e indicizzata; le policy RLS la usano
    per filtrare sull'apposito GUC `app.tenant_id`.
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)


def utcnow() -> datetime:
    """datetime.utcnow() naive evitato: usiamo timezone-aware."""
    from datetime import timezone

    return datetime.now(timezone.utc)


__all__ = [
    "Base",
    "IdMixin",
    "SoftDeleteMixin",
    "TenantMixin",
    "TimestampsMixin",
    "utcnow",
]


# Re-export utili per i moduli che fanno `from notai.shared.domain.base import Any`
_ = Any
