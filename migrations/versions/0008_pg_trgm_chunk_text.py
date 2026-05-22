"""pg_trgm + GIN index su document_chunks.text per ILIKE search veloce.

La search in atto (/v1/acts/{id}/search) usa ILIKE su chunk.text. Senza
indice trigram fa sequential scan: a 50k+ chunk/tenant diventa lento.
Con pg_trgm + GIN, ILIKE '%...%' usa l'indice.

Revision ID: 0008_pg_trgm
Revises: 0007_act_examples
Create Date: 2026-05-22 16:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0008_pg_trgm"
down_revision: Union[str, None] = "0007_act_examples"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_text_trgm "
        "ON document_chunks USING gin (text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_text_trgm")
    # Lasciamo pg_trgm installato: e' un'estensione condivisa, altre query
    # potrebbero gia' dipenderne in futuro.
