"""Practice (Fascicolo) e Act (Atto): aggregate root del dominio."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


class Practice(IdMixin, TenantMixin, TimestampsMixin, SoftDeleteMixin, Base):
    """Fascicolo / Pratica - contenitore principale del lavoro."""

    __tablename__ = "practices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_practices_tenant_code"),
    )

    # Codice pratica leggibile (es. "2026/0123") - generato dall'app per tenant.
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Tipo: notarile.compravendita | legale.civile.contenzioso | ...
    kind: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stato: bozza | attiva | in_attesa_firma | conclusa | archiviata
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="bozza")
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    main_client_party_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("parties.id", ondelete="SET NULL"),
        nullable=True,
    )
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class Act(IdMixin, TenantMixin, TimestampsMixin, SoftDeleteMixin, Base):
    """Atto: documento giuridico principale di una pratica.

    Es. compravendita, mutuo, statuto, donazione, atto di citazione, decreto ingiuntivo.
    """

    __tablename__ = "acts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "repertorio_year", "repertorio_number",
            name="uq_acts_tenant_repertorio",
        ),
    )

    practice_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Tipo atto (es. notarile.compravendita.immobiliare). Mappa al template_id.
    kind: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    # Numerazione repertoriale (notarile). NULL finche' non e' assegnata alla firma.
    repertorio_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repertorio_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raccolta_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Stato workflow Temporal: bozza | in_redazione | review | firmato | registrato | archiviato
    workflow_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="bozza")
    workflow_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Template di riferimento (se generato da template). NULL = redatto manualmente.
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stipulation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notary_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class PartyRole(IdMixin, TenantMixin, TimestampsMixin, Base):
    """N:N Party <-> Act con qualificazione del ruolo nell'atto.

    Es. (party=Mario Rossi, act=compravendita-123, role=venditore, quota=1.0).
    """

    __tablename__ = "party_roles"
    __table_args__ = (
        UniqueConstraint("act_id", "party_id", "role", name="uq_party_roles_act_party_role"),
    )

    act_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("parties.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Es: venditore, acquirente, mutuante, mutuatario, donante, donatario, attore,
    # convenuto, mandante, mandatario, ...
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    # Quota di partecipazione (per comproprieta', diritti reali, ecc.) - 0..1.
    quota: Mapped[float | None] = mapped_column(nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


__all__ = ["Act", "PartyRole", "Practice"]
