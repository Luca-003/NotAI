"""act_examples: wiki/RAG di atti reali catalogati per template_id

Revision ID: 0007_act_examples
Revises: 0006_provenance
Create Date: 2026-05-22 14:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_act_examples"
down_revision: Union[str, None] = "0006_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "act_examples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # tenant_id NULLABLE: NULL = esempio globale (condiviso tra tutti i tenant);
        # !NULL = esempio privato del tenant.
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("template_id", sa.String(128), nullable=True),  # es. notarile.compravendita.immobiliare:v1
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("full_text", sa.Text, nullable=False),
        # sezioni dell'esempio se gia' strutturate (id, title, text)
        sa.Column("sections", postgresql.JSONB, nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="[]"),

        # Provenance dell'esempio (chi/come l'ha caricato)
        sa.Column("source", sa.String(64), nullable=False, server_default="manual_upload"),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),

        # Legal/privacy
        # public | internal_only | consent_given | anonymized
        sa.Column("license", sa.String(32), nullable=False, server_default="internal_only"),
        sa.Column("is_anonymized", sa.Boolean, nullable=False, server_default=sa.text("false")),

        # Tecnici
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("embedding_indexed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("chunks_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_act_examples_tenant_id", "act_examples", ["tenant_id"])
    op.create_index("ix_act_examples_template_id", "act_examples", ["template_id"])
    op.create_index("ix_act_examples_tags_gin", "act_examples", ["tags"], postgresql_using="gin")

    # NB: NIENTE RLS standard sulla tabella perche' supporta record GLOBAL
    # (tenant_id NULL). Le query API filtreranno esplicitamente con:
    #   WHERE (tenant_id IS NULL OR tenant_id = current_tenant)
    # Aggiungiamo una policy custom che permette SELECT su global + own tenant.
    op.execute("ALTER TABLE public.act_examples ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.act_examples FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_or_global_select ON public.act_examples
          FOR SELECT
          USING (
            tenant_id IS NULL
            OR tenant_id::text = current_setting('app.tenant_id', true)
          )
    """)
    op.execute("""
        CREATE POLICY tenant_only_modify ON public.act_examples
          FOR ALL
          USING (tenant_id::text = current_setting('app.tenant_id', true))
          WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))
    """)


def downgrade() -> None:
    op.drop_table("act_examples")
