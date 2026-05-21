"""Tag (faceted + gerarchici) e NormativeReference (riferimenti normativi).

Tag namespace+key+value formano un identificatore unico per-tenant. Possono
essere gerarchici via parent_id (closure table opzionale in Fase 2).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from notai.shared.domain.base import (
    Base,
    IdMixin,
    TenantMixin,
    TimestampsMixin,
)


class Tag(IdMixin, TenantMixin, TimestampsMixin, Base):
    """Tag con namespace+key+value. Per-tenant (anche se molti sono gli stessi
    cross-tenant, manteniamo isolamento totale).

    Es. (namespace='act_type', key='notarile.compravendita.immobiliare', value=None)
    Es. (namespace='norm', key='cc.art.2643', value=None)
    Es. (namespace='party_role', key='venditore', value=None)
    """

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "namespace", "key", "value",
            name="uq_tags_tenant_ns_key_value",
        ),
    )

    namespace: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    display_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="RESTRICT"),
        nullable=True,
    )
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)


class NormativeReference(IdMixin, TimestampsMixin, Base):
    """Riferimenti normativi (NON tenant-scoped: e' patrimonio comune).

    Es. CC art. 2643 c.c. (trascrizione), DPR 131/86 art. 19 c. 1, ecc.

    `vigenza_da` e `vigenza_a` permettono di tracciare le modifiche normative
    (es. norma abrogata dal 2024-01-01). Indicizzato per ricerca veloce.
    """

    __tablename__ = "normative_references"
    __table_args__ = (
        UniqueConstraint(
            "fonte", "anno", "numero", "articolo", "comma", "vigenza_da",
            name="uq_normative_ref",
        ),
    )

    # cc | cpc | cp | cpp | dpr | dlgs | l | reg_ue | dl | dm | dpcm | ...
    fonte: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    anno: Mapped[int | None] = mapped_column(Integer, nullable=True)
    numero: Mapped[str | None] = mapped_column(String(64), nullable=True)
    articolo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comma: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Identificativo human-readable canonico (es. "art. 2643 c.c.")
    citation: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    vigenza_da: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vigenza_a: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Link al testo ufficiale (Normattiva, gazzetta)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class Clause(IdMixin, TenantMixin, TimestampsMixin, Base):
    """Clausola di un atto. Unita' di indicizzazione/ricerca/tagging.

    Ogni clausola sara' indicizzata in OpenSearch (BM25) e Qdrant (embedding).
    """

    __tablename__ = "clauses"

    act_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordering: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Provenienza: template | llm | manual
    generated_by: Mapped[str] = mapped_column(String(16), nullable=False)
    # Se generated_by=llm, riferimento all'LLMInvocation (auditing AI Act art. 50).
    llm_invocation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )
    # Confidence calibrata (0..1). NULL per provenienze non-AI.
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    # Revisione/approvazione professionista
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Tag IDs e normative_reference IDs - JSONB di UUID per query GIN flessibili
    tag_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    normative_refs: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class TaggedItem(IdMixin, TenantMixin, TimestampsMixin, Base):
    """Polymorphic tagging: applica un Tag a un'entita' qualsiasi.

    item_type: 'practice' | 'act' | 'document' | 'clause' | 'party'.
    """

    __tablename__ = "tagged_items"
    __table_args__ = (
        UniqueConstraint(
            "tag_id", "item_type", "item_id",
            name="uq_tagged_items_tag_item",
        ),
    )

    tag_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)


__all__ = ["Clause", "NormativeReference", "Tag", "TaggedItem"]
