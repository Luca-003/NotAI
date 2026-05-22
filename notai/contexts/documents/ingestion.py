"""Pipeline di ingestion documenti: parsing -> chunking -> embeddings -> store.

Pattern:
    1. Carica il blob da MinIO via storage.get_blob
    2. Estrae testo per mime type (PDF: pypdf, DOCX: python-docx, text/md: raw)
    3. Chunking per paragrafi con offset (char_start, char_end, page_number)
    4. Calcola embeddings via LLM gateway (bge-m3 / Ollama)
    5. Persiste DocumentChunk + upsert in Qdrant
    6. Aggiorna ingestion_status del Document
    7. Audit event per ogni step

Mime types supportati (Fase 4):
    - application/pdf -> pypdf
    - application/vnd.openxmlformats-officedocument.wordprocessingml.document (docx)
    - text/*  (markdown, plain)

NON supportati (rimandati a blocco OCR Fase 5+):
    - image/*  (richiede Tesseract sull'immagine API)
    - application/msword (.doc binario)
"""

from __future__ import annotations

import io
import re
import uuid
from datetime import datetime, timezone

import structlog
from qdrant_client.http import models as qm
from sqlalchemy import delete, select

from notai.contexts.audit.logger import audit_logger
from notai.contexts.audit.streams import stream_for_document
from notai.contexts.documents.models import Document, DocumentChunk
from notai.contexts.documents.storage import get_blob, parse_storage_uri
from notai.shared.tenancy.session import scoped_session

logger = structlog.get_logger(__name__)

CHUNK_MAX_CHARS = 1200
CHUNK_OVERLAP_CHARS = 100

# Mime classes
_PDF_MIME = "application/pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_TEXT_PREFIX = "text/"


# ---------------------------------------------------------------------------
# Estrattori per mime type
# ---------------------------------------------------------------------------


def _extract_pdf(blob: bytes) -> list[tuple[int, str]]:
    """Ritorna lista (page_number, page_text)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(blob))
    out: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            txt = ""
        if txt.strip():
            out.append((i, txt))
    return out


def _extract_docx(blob: bytes) -> list[tuple[int, str]]:
    """DOCX -> lista di (None, paragraph_text). Niente pagine native in docx."""
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(blob))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    if not paragraphs:
        return []
    # Aggreghiamo i paragrafi in un'unica "pagina" virtuale 1
    full = "\n\n".join(paragraphs)
    return [(1, full)]


def _extract_text(blob: bytes) -> list[tuple[int, str]]:
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        text = blob.decode("latin-1", errors="replace")
    return [(1, text)] if text.strip() else []


def _extract(mime: str, blob: bytes) -> list[tuple[int, str]]:
    if mime == _PDF_MIME:
        return _extract_pdf(blob)
    if mime == _DOCX_MIME:
        return _extract_docx(blob)
    if mime.startswith(_TEXT_PREFIX):
        return _extract_text(blob)
    raise ValueError(f"unsupported mime for ingestion: {mime}")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _chunk_text(
    text: str, *, page: int | None, max_chars: int = CHUNK_MAX_CHARS
) -> list[dict]:
    """Split per paragrafi, accorpati fino a max_chars. Ritorna chunk con offset
    nel testo originale della pagina (non globale).
    """
    # Split su blank lines (almeno 1 newline tra paragrafi)
    parts = re.split(r"\n\s*\n+", text)
    chunks: list[dict] = []
    buf: list[str] = []
    buf_chars = 0
    # offset del prossimo chunk nel testo originale
    cursor = 0
    chunk_start = 0

    for part in parts:
        if not part.strip():
            cursor += len(part) + 2  # +2 stima per i separatori
            continue
        if buf_chars + len(part) > max_chars and buf:
            chunk_text = "\n\n".join(buf)
            chunks.append({
                "text": chunk_text,
                "char_start": chunk_start,
                "char_end": chunk_start + len(chunk_text),
                "page_number": page,
            })
            buf = []
            buf_chars = 0
            chunk_start = cursor
        if not buf:
            chunk_start = cursor
        buf.append(part)
        buf_chars += len(part) + 2
        cursor += len(part) + 2

    if buf:
        chunk_text = "\n\n".join(buf)
        chunks.append({
            "text": chunk_text,
            "char_start": chunk_start,
            "char_end": chunk_start + len(chunk_text),
            "page_number": page,
        })

    return chunks


# ---------------------------------------------------------------------------
# Persistenza chunks + Qdrant
# ---------------------------------------------------------------------------


async def _index_chunks_in_qdrant(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    chunks: list[DocumentChunk],
    texts: list[str],
) -> list[bool]:
    """Calcola embedding + upsert in Qdrant. Ritorna lista di flag indexed per chunk."""
    from notai.contexts.ai.llm_gateway import embed_texts
    from notai.contexts.ai.rag import ensure_collection, get_qdrant

    collection = f"notai-{tenant_id}-doc-chunks"
    try:
        embeddings = await embed_texts(texts)
    except Exception as e:  # noqa: BLE001
        logger.warning("notai.ingest.embed_failed", error=str(e))
        return [False] * len(chunks)

    if not embeddings:
        return [False] * len(chunks)

    await ensure_collection(collection)

    points = [
        qm.PointStruct(
            id=str(c.id),
            vector=emb,
            payload={
                "tenant_id": str(tenant_id),
                "document_id": str(document_id),
                "chunk_id": str(c.id),
                "ordering": c.ordering,
                "page_number": c.page_number,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "text": c.text[:500],  # solo preview per facet/scroll, full text e' in DB
            },
        )
        for c, emb in zip(chunks, embeddings, strict=True)
    ]
    try:
        await get_qdrant().upsert(collection_name=collection, points=points)
        return [True] * len(chunks)
    except Exception as e:  # noqa: BLE001
        logger.warning("notai.ingest.qdrant_upsert_failed", error=str(e))
        return [False] * len(chunks)


# ---------------------------------------------------------------------------
# Pipeline principale
# ---------------------------------------------------------------------------


async def ingest_document(document_id: uuid.UUID, tenant_id: uuid.UUID) -> dict:
    """Pipeline completa: parse -> chunk -> embed -> store.

    Sicuro per retry: prima di partire, marchia ingestion_status='in_progress' e
    rimuove eventuali chunk precedenti. Sempre idempotente sul Document.
    """
    actor = "ingestion-pipeline"
    stream_id = f"document:{document_id}"

    async with scoped_session(tenant_id) as session:
        doc = (
            await session.execute(select(Document).where(Document.id == document_id))
        ).scalar_one_or_none()
        if doc is None:
            raise ValueError(f"document {document_id} not found")
        if doc.ingestion_status == "in_progress":
            logger.info("notai.ingest.already_in_progress", document_id=str(document_id))
            return {"skipped": True}
        doc.ingestion_status = "in_progress"
        doc.ingestion_error = None
        # Cleanup eventuali chunks da run precedenti (best-effort)
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await audit_logger.append(
            session=session,
            tenant_id=tenant_id,
            stream_id=stream_id,
            type="document.ingestion_started",
            payload={"document_id": str(document_id), "mime": doc.mime_type},
            actor=actor,
        )
        mime = doc.mime_type
        storage_uri = doc.storage_uri

    # Scarica blob (fuori dalla session per non tenere connessione)
    try:
        bucket, key = parse_storage_uri(storage_uri)
        blob = await get_blob(bucket, key)
    except Exception as e:  # noqa: BLE001
        await _mark_failed(document_id, tenant_id, f"download_failed: {e}")
        raise

    # Estrai testo
    try:
        pages = _extract(mime, blob)
    except ValueError as e:
        await _mark_failed(document_id, tenant_id, f"unsupported_mime: {mime}", skipped=True)
        return {"skipped": True, "reason": str(e)}
    except Exception as e:  # noqa: BLE001
        await _mark_failed(document_id, tenant_id, f"extraction_failed: {e}")
        raise

    if not pages:
        await _mark_failed(document_id, tenant_id, "no_text_extracted", skipped=True)
        return {"skipped": True, "reason": "no_text"}

    # Chunking per pagina
    all_chunks: list[dict] = []
    for page_num, page_text in pages:
        all_chunks.extend(_chunk_text(page_text, page=page_num))

    if not all_chunks:
        await _mark_failed(document_id, tenant_id, "no_chunks", skipped=True)
        return {"skipped": True, "reason": "no_chunks"}

    # Persisti su DB
    async with scoped_session(tenant_id) as session:
        chunk_models = [
            DocumentChunk(
                tenant_id=tenant_id,
                document_id=document_id,
                ordering=i,
                text=c["text"],
                char_start=c["char_start"],
                char_end=c["char_end"],
                page_number=c["page_number"],
                token_count=len(c["text"]) // 4,  # stima grossolana (~4 chars / token)
            )
            for i, c in enumerate(all_chunks)
        ]
        session.add_all(chunk_models)
        await session.flush()

        # Index in Qdrant
        indexed_flags = await _index_chunks_in_qdrant(
            tenant_id=tenant_id,
            document_id=document_id,
            chunks=chunk_models,
            texts=[c.text for c in chunk_models],
        )
        for chunk, indexed in zip(chunk_models, indexed_flags, strict=True):
            chunk.embedding_indexed = indexed

        # Finalizza
        doc = (
            await session.execute(select(Document).where(Document.id == document_id))
        ).scalar_one()
        doc.ingestion_status = "done"
        doc.ingested_at = datetime.now(timezone.utc)

        await audit_logger.append(
            session=session,
            tenant_id=tenant_id,
            stream_id=stream_id,
            type="document.ingested",
            payload={
                "document_id": str(document_id),
                "chunks_count": len(chunk_models),
                "pages_count": len(pages),
                "indexed_count": sum(1 for f in indexed_flags if f),
                "mime": mime,
            },
            actor=actor,
        )

    logger.info(
        "notai.ingest.done",
        document_id=str(document_id),
        chunks=len(all_chunks),
        indexed=sum(1 for f in indexed_flags if f),
    )

    # Errori della classificazione non bloccano l'ingestion (valore aggiunto, non critico).
    # Import locale: classification importa rag/gateway, lasciamo il confine pulito.
    try:
        from notai.contexts.documents.classification import classify_document_chunks

        await classify_document_chunks(document_id, tenant_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("notai.ingest.classification_failed", error=str(e))

    return {
        "document_id": str(document_id),
        "chunks_count": len(all_chunks),
        "pages_count": len(pages),
        "indexed_count": sum(1 for f in indexed_flags if f),
    }


async def _mark_failed(
    document_id: uuid.UUID,
    tenant_id: uuid.UUID,
    error: str,
    *,
    skipped: bool = False,
) -> None:
    async with scoped_session(tenant_id) as session:
        doc = (
            await session.execute(select(Document).where(Document.id == document_id))
        ).scalar_one_or_none()
        if doc is None:
            return
        doc.ingestion_status = "skipped" if skipped else "failed"
        doc.ingestion_error = error
        doc.ingested_at = datetime.now(timezone.utc)
        await audit_logger.append(
            session=session,
            tenant_id=tenant_id,
            stream_id=stream_for_document(document_id),
            type="document.ingestion_failed" if not skipped else "document.ingestion_skipped",
            payload={"document_id": str(document_id), "error": error},
            actor="ingestion-pipeline",
        )


__all__ = ["ingest_document"]
