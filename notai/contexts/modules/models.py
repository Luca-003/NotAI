"""Tabella feature_flags: stato attivo/disattivo dei moduli per tenant."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from notai.shared.domain.base import (
    Base,
    IdMixin,
    TenantMixin,
    TimestampsMixin,
)


class FeatureFlag(IdMixin, TenantMixin, TimestampsMixin, Base):
    """Stato di attivazione di un modulo per uno specifico tenant.

    Se manca un record per (tenant_id, module_id), si applica il default del
    manifest (module.default_enabled OR module.essential).
    """

    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("tenant_id", "module_id", name="uq_feature_flags_tenant_module"),
    )

    module_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Nota libera (es. motivazione disattivazione)
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Chi ha effettuato l'ultima modifica
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )


__all__ = ["FeatureFlag"]
