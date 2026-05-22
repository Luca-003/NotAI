"""audit.audit_stream_heads: head cache per la catena hash.

Ogni append in audit.audit_events fa oggi:
    1) pg_advisory_xact_lock(hashtext(tenant_id || stream_id))
    2) SELECT ... ORDER BY seq DESC LIMIT 1 (index seek su audit_events)
    3) INSERT INTO audit_events

Con stream_heads:
    1) SELECT last_seq, last_hash FROM audit_stream_heads WHERE pk=... FOR UPDATE
       (PK seek + row-level lock, no advisory lock globale)
    2) UPDATE audit_stream_heads SET last_seq=...+1, last_hash=...
    3) INSERT INTO audit_events
La row-level lock garantisce serializzazione per-stream senza contention globale.

Revision ID: 0009_audit_stream_heads
Revises: 0008_pg_trgm
Create Date: 2026-05-22 17:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009_audit_stream_heads"
down_revision: Union[str, None] = "0008_pg_trgm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_stream_heads",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stream_id", sa.String(128), nullable=False),
        sa.Column("last_seq", sa.BigInteger, nullable=False),
        sa.Column("last_hash", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "stream_id", name="pk_audit_stream_heads"),
        schema="audit",
    )

    # Backfill: per ogni stream esistente in audit_events, popola la head con
    # l'ultimo evento. Usa DISTINCT ON che e' Postgres-specific ma e' l'unica
    # via efficiente per ottenere "ultimo per gruppo" senza una subquery
    # correlata.
    op.execute(
        """
        INSERT INTO audit.audit_stream_heads (tenant_id, stream_id, last_seq, last_hash)
        SELECT DISTINCT ON (tenant_id, stream_id) tenant_id, stream_id, seq, hash
        FROM audit.audit_events
        ORDER BY tenant_id, stream_id, seq DESC
        ON CONFLICT (tenant_id, stream_id) DO NOTHING
        """
    )

    # A differenza di audit_events, qui UPDATE e' necessario (la testa cambia
    # ad ogni append). Le default privileges in audit/ grants solo SELECT/INSERT.
    # Aggiungiamo esplicitamente UPDATE su questa singola tabella.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON audit.audit_stream_heads TO notai_app, notai_audit_writer"
    )


def downgrade() -> None:
    op.drop_table("audit_stream_heads", schema="audit")
