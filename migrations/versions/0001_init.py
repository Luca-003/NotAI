"""init - bootstrap schemi NotAI

Crea lo schema 'audit' (gia' creato dall'init script Postgres ma idempotente)
e una tabella `_alembic_marker` per dimostrare che la migration ha girato.

I modelli reali verranno introdotti nelle migration successive nei sprint di
Fase 1+.

Revision ID: 0001_init
Revises:
Create Date: 2026-05-21 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")

    op.create_table(
        "_alembic_marker",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("note", sa.Text, nullable=False, server_default="bootstrap"),
    )


def downgrade() -> None:
    op.drop_table("_alembic_marker")
