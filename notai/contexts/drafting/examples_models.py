"""Modello ActExample: esempio di atto reale catalogato per il RAG/wiki."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from notai.shared.domain.base import (
    Base,
    IdMixin,
    SoftDeleteMixin,
    TimestampsMixin,
)


class ActExample(IdMixin, TimestampsMixin, SoftDeleteMixin, Base):
    """Esempio di atto reale (storico, anonimizzato o public). Usato dal RAG
    per:
      - validare la struttura di una bozza generata
      - suggerire clausole simili durante review
      - estrarre template da esempi (Fase 5+)
    """

    __tablename__ = "act_examples"

    # NULLABLE: NULL = globale (cross-tenant); ID = privato di un tenant.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )
    template_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    source: Mapped[str] = mapped_column(String(64), nullable=False, server_default="manual_upload")
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # public | internal_only | consent_given | anonymized
    license: Mapped[str] = mapped_column(String(32), nullable=False, server_default="internal_only")
    is_anonymized: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    chunks_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


__all__ = ["ActExample"]
