"""provenance graph: tabella provenance_links + Document.sections JSONB

- documents.sections (JSONB): struttura del documento di output in sezioni
- provenance_links: ogni riga mappa una sezione dell'output a un chunk sorgente

Revision ID: 0006_provenance
Revises: 0005_chunk_classification
Create Date: 2026-05-22 13:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_provenance"
down_revision: Union[str, None] = "0005_chunk_classification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("sections", postgresql.JSONB, nullable=True),
    )

    op.create_table(
        "provenance_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("output_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("output_section_id", sa.String(128), nullable=False),
        sa.Column("source_chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        # derived_from | cites | uses_entity | uses_norm
        sa.Column("relation", sa.String(32), nullable=False, server_default="derived_from"),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("llm_invocation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["output_document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_chunk_id"], ["document_chunks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["documents.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_provenance_tenant_id", "provenance_links", ["tenant_id"])
    op.create_index(
        "ix_provenance_output_section",
        "provenance_links",
        ["output_document_id", "output_section_id"],
    )
    op.create_index(
        "ix_provenance_source_chunk", "provenance_links", ["source_chunk_id"]
    )
    op.create_index(
        "ix_provenance_source_doc", "provenance_links", ["source_document_id"]
    )

    op.execute("SELECT public.enable_tenant_rls('public.provenance_links'::regclass)")


def downgrade() -> None:
    op.drop_table("provenance_links")
    op.drop_column("documents", "sections")
