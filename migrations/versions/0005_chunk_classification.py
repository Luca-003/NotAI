"""chunk_classification: campi classification + classification_status su document_chunks

Aggiunge:
- classification (JSONB): output completo del classificatore LLM
- classification_status (str): pending|done|abstained|skipped|failed

Revision ID: 0005_chunk_classification
Revises: 0004_document_chunks
Create Date: 2026-05-22 12:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_chunk_classification"
down_revision: Union[str, None] = "0004_document_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("classification", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "classification_status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "document_chunks",
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # GIN su classification per query JSONB (es. WHERE classification->>'document_type' = ...)
    op.create_index(
        "ix_document_chunks_classification_gin",
        "document_chunks",
        ["classification"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_classification_gin", table_name="document_chunks")
    op.drop_column("document_chunks", "classified_at")
    op.drop_column("document_chunks", "classification_status")
    op.drop_column("document_chunks", "classification")
