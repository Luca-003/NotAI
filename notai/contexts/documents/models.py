"""Document model: blob su MinIO + metadata su Postgres + firma + marca temporale."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


class Document(IdMixin, TenantMixin, TimestampsMixin, SoftDeleteMixin, Base):
    """Documento generico (bozza, allegato, atto firmato, ricevuta, ecc.)."""

    __tablename__ = "documents"

    practice_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    act_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # Tipo documento: bozza_atto | atto_firmato | visura | allegato | ricevuta | ...
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # MinIO storage location: s3://bucket/key
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Hash SHA-256 del contenuto (64 hex chars) - usato per verifica integrita'.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Versioning: parent_version_id punta alla versione precedente (catena).
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # Firma digitale: payload JSON con dettagli (firmatario CF, alg, validita', cert chain)
    signature: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Marca temporale qualificata RFC 3161 (base64 token)
    timestamp_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Classificazione conservazione: nessuna | a_norma | confidenziale
    retention_class: Mapped[str] = mapped_column(String(32), nullable=False, server_default="nessuna")
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Ingestion pipeline (parsing + chunking + embeddings)
    # Stato: pending | in_progress | done | failed | skipped
    ingestion_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    ingestion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DocumentChunk(IdMixin, TenantMixin, TimestampsMixin, Base):
    """Chunk testuale estratto da un Document - unita' di ricerca e provenance."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordering", name="uq_document_chunks_doc_order"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordering: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # True quando il chunk e' stato anche caricato nel vector store
    embedding_indexed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Classificazione LLM (Fase 3 - blocco 3 visione workspace)
    classification: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    classification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    classified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["Document", "DocumentChunk"]
