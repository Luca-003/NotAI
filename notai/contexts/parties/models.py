"""Parti (Party): anagrafiche persone fisiche e giuridiche, KYC/AML."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from notai.shared.domain.base import (
    Base,
    IdMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampsMixin,
)


class Party(IdMixin, TenantMixin, TimestampsMixin, SoftDeleteMixin, Base):
    """Persona fisica o persona giuridica coinvolta in una pratica."""

    __tablename__ = "parties"

    # PF (persona fisica) | PG (persona giuridica)
    kind: Mapped[str] = mapped_column(String(2), nullable=False)
    # Dati anagrafici strutturati (varia tra PF/PG): nome/cognome o ragione_sociale,
    # luogo/data nascita o sede, ecc.
    anagrafica: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    fiscal_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    vat_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # KYC: pending | verified | rejected
    kyc_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    # Beneficiari effettivi (per PG): array di party_id riferiti
    beneficial_owners: Mapped[list | None] = mapped_column(JSONB, nullable=True)


class AMLAssessment(IdMixin, TenantMixin, TimestampsMixin, Base):
    """Adeguata verifica D.Lgs 231/2007 - cronologia per parte."""

    __tablename__ = "aml_assessments"

    party_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("parties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # ordinaria | rafforzata | semplificata
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)  # basso|medio|alto
    factors: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # Esito: ok | sospetto | sos_inviata
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    operator_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["AMLAssessment", "Party"]
