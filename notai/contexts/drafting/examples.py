"""Service di gestione esempi di atto (wiki/RAG).

Pipeline upload esempio:
  1. Calcola sha256 + size
  2. Crea ActExample su DB (sessione tenant-scoped o globale)
  3. In background: chunking + embeddings + index in collection Qdrant
     `notai-act-examples` (globale, perche' alcuni esempi sono shared)

Ricerca:
  - text ILIKE su title/full_text/tags (sempre disponibile)
  - dense retrieval via Qdrant se embedding_indexed=True (semantic search)
"""

from __future__ import annotations

import re
import uuid
from typing import Sequence

import structlog
from qdrant_client.http import models as qm
from sqlalchemy import or_, select

from notai.contexts.drafting.examples_models import ActExample
from notai.shared.tenancy.session import scoped_session

logger = structlog.get_logger(__name__)

EXAMPLES_COLLECTION = "notai-act-examples"


def _chunk_text(text: str, max_chars: int = 1200) -> list[dict]:
    """Split per paragrafi + accorpamento (riusa la stessa euristica
    di ingestion.py per coerenza)."""
    parts = re.split(r"\n\s*\n+", text)
    chunks: list[dict] = []
    buf: list[str] = []
    buf_chars = 0
    cursor = 0
    chunk_start = 0
    for part in parts:
        if not part.strip():
            cursor += len(part) + 2
            continue
        if buf_chars + len(part) > max_chars and buf:
            ch = "\n\n".join(buf)
            chunks.append({"text": ch, "char_start": chunk_start, "char_end": chunk_start + len(ch)})
            buf = []
            buf_chars = 0
            chunk_start = cursor
        if not buf:
            chunk_start = cursor
        buf.append(part)
        buf_chars += len(part) + 2
        cursor += len(part) + 2
    if buf:
        ch = "\n\n".join(buf)
        chunks.append({"text": ch, "char_start": chunk_start, "char_end": chunk_start + len(ch)})
    return chunks


async def index_example_in_qdrant(example_id: uuid.UUID, tenant_id: uuid.UUID | None) -> bool:
    """Calcola embeddings dei chunks dell'esempio e li carica in Qdrant.

    L'example_id viene usato come point id (con suffisso ordering); il payload
    include template_id + tags per il filtering.
    """
    from notai.contexts.ai.llm_gateway import embed_texts
    from notai.contexts.ai.rag import ensure_collection, get_qdrant

    async with scoped_session(tenant_id) as session:
        example = (
            await session.execute(select(ActExample).where(ActExample.id == example_id))
        ).scalar_one_or_none()
        if example is None:
            return False

        chunks = _chunk_text(example.full_text)
        if not chunks:
            example.embedding_indexed = False
            example.chunks_count = 0
            return False

        try:
            embeddings = await embed_texts([c["text"] for c in chunks])
        except Exception as e:  # noqa: BLE001
            logger.warning("notai.examples.embed_failed", error=str(e))
            example.embedding_indexed = False
            example.chunks_count = len(chunks)
            return False

        await ensure_collection(EXAMPLES_COLLECTION)

        points = [
            qm.PointStruct(
                # id deterministico: hash(example_id + ordering)
                id=int.from_bytes(
                    (str(example_id) + str(i)).encode("utf-8"), "big", signed=False
                ) & ((1 << 63) - 1),
                vector=emb,
                payload={
                    "example_id": str(example_id),
                    "tenant_id": str(tenant_id) if tenant_id else None,
                    "template_id": example.template_id,
                    "title": example.title,
                    "tags": example.tags or [],
                    "ordering": i,
                    "text": c["text"][:600],
                    "char_start": c["char_start"],
                    "char_end": c["char_end"],
                    "license": example.license,
                    "is_anonymized": example.is_anonymized,
                },
            )
            for i, (c, emb) in enumerate(zip(chunks, embeddings, strict=True))
        ]
        try:
            await get_qdrant().upsert(collection_name=EXAMPLES_COLLECTION, points=points)
            example.embedding_indexed = True
            example.chunks_count = len(chunks)
            logger.info(
                "notai.examples.indexed",
                example_id=str(example_id),
                chunks=len(chunks),
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("notai.examples.qdrant_upsert_failed", error=str(e))
            example.embedding_indexed = False
            example.chunks_count = len(chunks)
            return False


async def search_examples(
    query: str,
    *,
    template_id: str | None = None,
    tenant_id: uuid.UUID | None = None,
    limit: int = 10,
) -> list[dict]:
    """Hybrid search: dense (Qdrant) + text fallback (ILIKE).

    Filtra per template_id se fornito; include esempi globali + del tenant.
    """
    if not query or len(query.strip()) < 2:
        return []

    from notai.contexts.ai.llm_gateway import embed_texts
    from notai.contexts.ai.rag import ensure_collection, get_qdrant

    # 1) Dense retrieval (best effort)
    dense_hits: list[dict] = []
    try:
        embeddings = await embed_texts([query])
        if embeddings:
            await ensure_collection(EXAMPLES_COLLECTION)
            qfilter = None
            if template_id:
                qfilter = qm.Filter(
                    must=[qm.FieldCondition(key="template_id", match=qm.MatchValue(value=template_id))]
                )
            response = await get_qdrant().query_points(
                collection_name=EXAMPLES_COLLECTION,
                query=embeddings[0],
                query_filter=qfilter,
                limit=limit,
                with_payload=True,
            )
            for h in response.points:
                payload = h.payload or {}
                # Filtra per visibilita': global (tenant_id=None) o stesso tenant
                example_tenant = payload.get("tenant_id")
                if example_tenant is not None and str(tenant_id) != example_tenant:
                    continue
                dense_hits.append({
                    "kind": "semantic",
                    "example_id": payload.get("example_id"),
                    "title": payload.get("title"),
                    "template_id": payload.get("template_id"),
                    "tags": payload.get("tags") or [],
                    "score": float(h.score or 0.0),
                    "snippet": payload.get("text", "")[:300],
                    "ordering": payload.get("ordering"),
                })
    except Exception as e:  # noqa: BLE001
        logger.warning("notai.examples.search_dense_failed", error=str(e))

    # 2) Text fallback (sempre)
    text_hits: list[dict] = []
    pattern = f"%{query.strip().lower()}%"
    async with scoped_session(tenant_id) as session:
        stmt = select(ActExample).where(
            ActExample.deleted_at.is_(None),
            or_(
                ActExample.title.ilike(pattern),
                ActExample.full_text.ilike(pattern),
            ),
        )
        if template_id:
            stmt = stmt.where(ActExample.template_id == template_id)
        rows = (await session.execute(stmt.limit(limit))).scalars().all()
        for ex in rows:
            text = ex.full_text
            idx = text.lower().find(query.strip().lower())
            if idx < 0:
                snippet = text[:200]
            else:
                start = max(0, idx - 60)
                end = min(len(text), idx + len(query) + 140)
                snippet = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
            text_hits.append({
                "kind": "text",
                "example_id": str(ex.id),
                "title": ex.title,
                "template_id": ex.template_id,
                "tags": ex.tags or [],
                "score": None,
                "snippet": snippet,
                "ordering": None,
            })

    # Merge + dedup per example_id (priorita' al dense con score piu' alto)
    seen: dict[str, dict] = {}
    for hit in dense_hits + text_hits:
        eid = hit["example_id"]
        if eid not in seen or (hit.get("score") or 0) > (seen[eid].get("score") or -1):
            seen[eid] = hit
    out = sorted(seen.values(), key=lambda h: -(h.get("score") or 0))
    return out[:limit]


__all__ = [
    "EXAMPLES_COLLECTION",
    "index_example_in_qdrant",
    "search_examples",
]
