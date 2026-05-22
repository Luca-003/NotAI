"""document_chunks + ingestion_status su documents

Revision ID: 0004_document_chunks
Revises: 0003_feature_flags
Create Date: 2026-05-22 11:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_document_chunks"
down_revision: Union[str, None] = "0003_feature_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ingestion_status su documents: pending|in_progress|done|failed|skipped
    op.add_column(
        "documents",
        sa.Column(
            "ingestion_status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "documents",
        sa.Column("ingestion_error", sa.Text, nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordering", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=False),
        sa.Column("char_end", sa.Integer, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        # Vettore embedding (se inserito anche in Qdrant lo marchiamo qui)
        sa.Column("embedding_indexed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "ordering", name="uq_document_chunks_doc_order"),
    )
    op.create_index("ix_document_chunks_tenant_id", "document_chunks", ["tenant_id"])
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    op.execute("SELECT public.enable_tenant_rls('public.document_chunks'::regclass)")


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_column("documents", "ingested_at")
    op.drop_column("documents", "ingestion_error")
    op.drop_column("documents", "ingestion_status")
