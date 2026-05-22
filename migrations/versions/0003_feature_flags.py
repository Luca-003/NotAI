"""feature_flags: tabella per attivare/disattivare moduli per tenant

Revision ID: 0003_feature_flags
Revises: 0002_core_schema
Create Date: 2026-05-22 10:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_feature_flags"
down_revision: Union[str, None] = "0002_core_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("module_id", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("note", sa.String(512), nullable=True),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "module_id", name="uq_feature_flags_tenant_module"),
    )
    op.create_index("ix_feature_flags_tenant_id", "feature_flags", ["tenant_id"])
    op.create_index("ix_feature_flags_module_id", "feature_flags", ["module_id"])

    op.execute("SELECT public.enable_tenant_rls('public.feature_flags'::regclass)")


def downgrade() -> None:
    op.drop_table("feature_flags")
