"""RAG minimale: Qdrant come vector store, bge-m3 (via Ollama) come embedder.

Collection convention: `notai-{tenant_id}-normative` (per la normativa)
                       `notai-{tenant_id}-clauses`   (per le clausole interne)
                       `notai-global-normative`       (normativa cross-tenant)

Per ora usiamo SOLO la collection global-normative; il fork per-tenant
arriva in Fase 5.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from notai.config import get_settings
from notai.contexts.ai.llm_gateway import embed_texts

logger = structlog.get_logger(__name__)

GLOBAL_NORMATIVE_COLLECTION = "notai-global-normative"

# bge-m3 produce embedding di dimensione 1024 (vedi card del modello).
# Verifichiamo all'avvio della prima ingestion.
_EMBEDDING_DIM = 1024


@dataclass
class RetrievedChunk:
    chunk_id: str
    citation: str           # es. "art. 2643 c.c."
    text: str
    score: float


_client: AsyncQdrantClient | None = None


def get_qdrant() -> AsyncQdrantClient:
    """Singleton lazy del client async Qdrant (riusato tra moduli)."""
    global _client
    if _client is None:
        s = get_settings()
        _client = AsyncQdrantClient(
            host=s.qdrant.host,
            port=s.qdrant.port,
            api_key=s.qdrant.api_key.get_secret_value(),
            https=False,
            timeout=30,
        )
    return _client


# Alias retro-compatibile (le call interne lo usano ancora)
_qdrant = get_qdrant


def _stable_chunk_id(citation: str, text: str) -> int:
    """Qdrant accetta point id come int o UUID. Usiamo hash 63-bit dell'identita'."""
    return int.from_bytes(
        hashlib.sha256(f"{citation}::{text}".encode("utf-8")).digest()[:8],
        "big",
    ) & ((1 << 63) - 1)


async def ensure_collection(collection: str = GLOBAL_NORMATIVE_COLLECTION) -> None:
    """Crea la collection se non esiste. Idempotente."""
    client = _qdrant()
    cols = await client.get_collections()
    if any(c.name == collection for c in cols.collections):
        return
    await client.create_collection(
        collection_name=collection,
        vectors_config=qm.VectorParams(size=_EMBEDDING_DIM, distance=qm.Distance.COSINE),
    )
    logger.info("notai.rag.collection_created", collection=collection, dim=_EMBEDDING_DIM)


@dataclass
class IngestItem:
    citation: str            # es. "art. 2643 c.c."
    text: str                # testo del comma/articolo
    kind: str = "normative"
    extra: dict | None = None


async def ingest(
    items: list[IngestItem],
    collection: str = GLOBAL_NORMATIVE_COLLECTION,
) -> int:
    """Ingest batch in Qdrant. Idempotente (point id stabile da hash)."""
    if not items:
        return 0
    global _EMBEDDING_DIM

    embeddings = await embed_texts([i.text for i in items])
    if embeddings:
        actual_dim = len(embeddings[0])
        if actual_dim != _EMBEDDING_DIM:
            logger.warning("notai.rag.dim_mismatch", expected=_EMBEDDING_DIM, actual=actual_dim)
            _EMBEDDING_DIM = actual_dim

    await ensure_collection(collection)

    points = [
        qm.PointStruct(
            id=_stable_chunk_id(item.citation, item.text),
            vector=embedding,
            payload={
                "citation": item.citation,
                "text": item.text,
                "kind": item.kind,
                **(item.extra or {}),
            },
        )
        for item, embedding in zip(items, embeddings, strict=True)
    ]
    await _qdrant().upsert(collection_name=collection, points=points)
    logger.info("notai.rag.ingested", count=len(points), collection=collection)
    return len(points)


async def retrieve(
    query: str,
    *,
    top_k: int = 5,
    collection: str = GLOBAL_NORMATIVE_COLLECTION,
    min_score: float = 0.3,
) -> list[RetrievedChunk]:
    embeddings = await embed_texts([query])
    if not embeddings:
        return []
    await ensure_collection(collection)
    # qdrant-client v1.18: search e' deprecato, usiamo query_points.
    response = await _qdrant().query_points(
        collection_name=collection,
        query=embeddings[0],
        limit=top_k,
        score_threshold=min_score,
        with_payload=True,
    )
    return [
        RetrievedChunk(
            chunk_id=str(h.id),
            citation=(h.payload or {}).get("citation", ""),
            text=(h.payload or {}).get("text", ""),
            score=float(h.score or 0.0),
        )
        for h in response.points
    ]


async def known_citations(
    collection: str = GLOBAL_NORMATIVE_COLLECTION,
    limit: int = 1000,
) -> set[str]:
    """Ritorna l'insieme delle citation presenti nella collection.

    Usata dall'abstention detector per validare che le citation dell'AI esistano davvero.
    """
    try:
        await ensure_collection(collection)
        points, _ = await _qdrant().scroll(
            collection_name=collection,
            limit=limit,
            with_payload=True,
        )
        return {
            (p.payload or {}).get("citation", "")
            for p in points
            if (p.payload or {}).get("citation")
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("notai.rag.known_citations_failed", error=str(e))
        return set()


__all__ = [
    "GLOBAL_NORMATIVE_COLLECTION",
    "IngestItem",
    "RetrievedChunk",
    "ensure_collection",
    "ingest",
    "known_citations",
    "retrieve",
]
