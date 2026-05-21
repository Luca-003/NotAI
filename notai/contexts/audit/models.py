"""Audit event store: append-only su schema 'audit'.

Tabelle:
    audit.audit_events    - evento generico (catena hash per stream_id+tenant_id)
    audit.llm_invocations - record specifico di ogni call LLM (sottocaso ricercabile)
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from notai.shared.domain.base import Base, IdMixin

AUDIT_SCHEMA = "audit"


class AuditEvent(IdMixin, Base):
    """Evento audit immutabile.

    Indici:
      - (tenant_id, stream_id, seq) UNIQUE: catena per-stream
      - (tenant_id, ts) per query temporali
      - (tenant_id, type) per filtro tipologia
      - GIN su payload per ricerche dentro il JSON
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "stream_id", "seq", name="uq_audit_events_stream_seq"),
        Index("ix_audit_events_tenant_ts", "tenant_id", "ts"),
        Index("ix_audit_events_tenant_type", "tenant_id", "type"),
        Index("ix_audit_events_payload_gin", "payload", postgresql_using="gin"),
        {"schema": AUDIT_SCHEMA},
    )

    # Tenant - non e' TenantMixin standard perche' RLS sull'audit ha policy
    # diversa (gli admin del singolo studio devono poter LEGGERE tutto l'audit
    # del proprio tenant, niente filtri soft-delete).
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Stream = aggregate (es. practice:<uuid> o act:<uuid>). Tutti gli eventi
    # dello stesso stream formano una catena ordinata da `seq`.
    stream_id: Mapped[str] = mapped_column(String(128), nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)

    ts: Mapped[__import__("datetime").datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # Tipologia evento (es. practice.created, act.draft_submitted, llm.invoked, ...)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    # Identita': user UUID o nome service ('temporal-worker', 'rpa-worker', ...)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Payload strutturato: snapshot dell'input/output dell'azione
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Hash chain
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Firma del singolo evento (opzionale - usata se firmiamo per-evento invece che la testa)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Marca temporale RFC 3161 (token base64) - settata solo per "checkpoint" periodici
    # o eventi di particolare rilevanza giuridica (firma atto, registrazione).
    timestamp_token: Mapped[str | None] = mapped_column(Text, nullable=True)


class LLMInvocation(IdMixin, Base):
    """Record dettagliato di ogni call LLM. Cross-referenced da AuditEvent.

    Tutti i campi sono essenziali per AI Act art. 11 (documentazione tecnica)
    e art. 50 (trasparenza). Conservare in append-only.
    """

    __tablename__ = "llm_invocations"
    __table_args__ = (
        Index("ix_llm_inv_tenant_ts", "tenant_id", "ts"),
        Index("ix_llm_inv_audit_event", "audit_event_id"),
        {"schema": AUDIT_SCHEMA},
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    # Riferimento bidirezionale all'evento audit corrispondente
    audit_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{AUDIT_SCHEMA}.audit_events.id", ondelete="RESTRICT"),
        nullable=True,
    )

    ts: Mapped[__import__("datetime").datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Modello: alias (es. local/qwen2.5-7b) e identificativo backend (es. ollama/qwen2.5:7b)
    model_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    model_backend: Mapped[str] = mapped_column(String(64), nullable=False)
    # SHA-256 dei pesi del modello (se ricavabile) per riproducibilita'
    model_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Prompt template + version (riferimenti) + prompt finale renderizzato
    prompt_template_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_rendered: Mapped[str] = mapped_column(Text, nullable=False)

    # Risposta raw + risposta strutturata (se schema-enforced)
    response_raw: Mapped[str] = mapped_column(Text, nullable=False)
    response_structured: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Parametri inferenza
    temperature: Mapped[float] = mapped_column(nullable=False, server_default="0")
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Metriche
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Output di abstention detector
    # decision: produced | abstained
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    abstain_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    # Citation grounding: array di {ref_id, score, chunk_ref}
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Hash dell'input snapshot (riferimento al payload audit) e dell'output
    input_snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Rationale testuale (opzionale): perche' l'AI ha prodotto/abstain
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["AUDIT_SCHEMA", "AuditEvent", "LLMInvocation"]
