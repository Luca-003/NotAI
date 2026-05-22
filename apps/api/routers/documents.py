"""Endpoint /api/v1/documents/* - upload, metadata, contenuto blob da MinIO."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select

from apps.api.deps import DbDep, TenantDep, get_or_404
from notai.contexts.audit.logger import audit_logger
from notai.contexts.documents.ingestion import ingest_document
from notai.contexts.documents.models import Document, DocumentChunk, ProvenanceLink
from notai.contexts.documents.storage import get_blob, parse_storage_uri, put_blob

router = APIRouter(prefix="/documents", tags=["documents"])

DEFAULT_BUCKET = "notai-documents"

# Mime type accettati in upload (whitelist per evitare blob arbitrari)
ALLOWED_MIME_PREFIXES = (
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats",
    "application/vnd.oasis.opendocument",
    "text/",
    "image/",
)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024   # 50 MB


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    practice_id: uuid.UUID | None
    act_id: uuid.UUID | None
    kind: str
    filename: str
    mime_type: str
    size_bytes: int
    storage_uri: str
    sha256: str
    version: int
    created_at: datetime
    ingestion_status: str
    ingestion_error: str | None
    ingested_at: datetime | None


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    ordering: int
    text: str
    char_start: int
    char_end: int
    page_number: int | None
    embedding_indexed: bool
    token_count: int | None
    classification: dict | None
    classification_status: str
    classified_at: datetime | None


async def _run_ingestion_safely(document_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Wrapper sicuro per BackgroundTasks: cattura errori per non far crashare il worker."""
    import structlog

    log = structlog.get_logger(__name__)
    try:
        await ingest_document(document_id, tenant_id)
    except Exception as e:  # noqa: BLE001
        log.exception("notai.ingest.background_failed", document_id=str(document_id), error=str(e))


async def _load_doc(session, doc_id: uuid.UUID) -> Document:
    return await get_or_404(session, Document, doc_id, name="document")


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    principal: TenantDep,
    session: DbDep,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    kind: str = Form("input_source"),
    practice_id: uuid.UUID | None = Form(None),
    act_id: uuid.UUID | None = Form(None),
) -> DocumentRead:
    """Upload di un documento di input nel fascicolo.

    `kind` consigliato:
      - "input_source"  -> documento fornito dal notaio per generare l'atto
      - "allegato"      -> allegato non sostanziale
      - "atto_firmato"  -> versione firmata (riservato; verra' validato altrove)
    """
    mime = file.content_type or "application/octet-stream"
    if not any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        raise HTTPException(
            status_code=415,
            detail=f"mime type non consentito: {mime}",
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="file vuoto")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file troppo grande (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )

    if act_id is None and practice_id is None:
        raise HTTPException(
            status_code=400,
            detail="serve almeno uno tra act_id e practice_id",
        )

    doc_id = uuid.uuid4()
    safe_name = (file.filename or "doc").replace("/", "_").replace("\\", "_")
    key_scope = f"act/{act_id}" if act_id else f"practice/{practice_id}"
    key = f"input/{principal.tenant_id}/{key_scope}/{doc_id}/{safe_name}"

    storage_uri, sha = await put_blob(DEFAULT_BUCKET, key, data, mime)

    doc = Document(
        id=doc_id,
        tenant_id=principal.tenant_id,
        practice_id=practice_id,
        act_id=act_id,
        kind=kind,
        filename=safe_name,
        mime_type=mime,
        size_bytes=len(data),
        storage_uri=storage_uri,
        sha256=sha,
        retention_class="nessuna",
        extra={"uploaded_at": datetime.now(timezone.utc).isoformat()},
    )
    session.add(doc)
    await session.flush()

    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=f"act:{act_id}" if act_id else f"practice:{practice_id}",
        type="document.uploaded",
        payload={
            "document_id": str(doc_id),
            "filename": safe_name,
            "mime_type": mime,
            "size_bytes": len(data),
            "sha256": sha,
            "kind": kind,
        },
        actor=principal.as_actor(),
    )

    # COMMIT esplicito PRIMA di schedulare il background: FastAPI esegue le
    # BackgroundTasks dopo che la response e' stata inviata, ma il cleanup
    # delle dependency con `yield` avviene a sua volta dopo la response, quindi
    # il commit di `DbDep` non e' garantito che preceda il background task.
    # Senza questo commit, il background apre una nuova session e non vede il
    # documento appena inserito (RLS non c'entra: il problema e' transazionale).
    await session.commit()

    background.add_task(_run_ingestion_safely, doc_id, principal.tenant_id)

    return DocumentRead.model_validate(doc)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document_meta(
    document_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> DocumentRead:
    del principal
    doc = await _load_doc(session, document_id)
    return DocumentRead.model_validate(doc)


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> Response:
    """Stream del contenuto del documento da MinIO. Supporta qualsiasi mime."""
    del principal
    doc = await _load_doc(session, document_id)
    try:
        bucket, key = parse_storage_uri(doc.storage_uri)
        content = await get_blob(bucket, key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"storage backend unavailable: {type(e).__name__}",
        ) from e

    # `inline` per i tipi visualizzabili nel browser (pdf, img, text/md);
    # `attachment` per gli altri (download forzato).
    inline_mimes = ("application/pdf", "image/", "text/")
    disposition = "inline" if any(doc.mime_type.startswith(p) for p in inline_mimes) else "attachment"

    return Response(
        content=content,
        media_type=doc.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{doc.filename}"',
            "X-Sha256": doc.sha256,
        },
    )


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------


@router.get("/{document_id}/chunks", response_model=list[ChunkRead])
async def list_document_chunks(
    document_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> list[ChunkRead]:
    """Ritorna i chunk testuali estratti dalla pipeline di ingestion."""
    del principal
    await _load_doc(session, document_id)
    rows = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.ordering.asc())
    )
    return [ChunkRead.model_validate(c) for c in rows.scalars().all()]


@router.get("/{document_id}/sections")
async def get_document_sections(
    document_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> dict:
    """Sezioni strutturate del documento di output (es. bozza atto)."""
    del principal
    doc = await _load_doc(session, document_id)
    return {
        "document_id": str(document_id),
        "filename": doc.filename,
        "kind": doc.kind,
        "sections": doc.sections or [],
    }


@router.delete("/provenance/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provenance_link(
    link_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> Response:
    """Rimuove un link di provenance (il notaio lo ha valutato come errato)."""
    link = (
        await session.execute(select(ProvenanceLink).where(ProvenanceLink.id == link_id))
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="provenance link not found")
    section_id = link.output_section_id
    out_doc_id = link.output_document_id
    source_chunk_id = link.source_chunk_id
    rationale = link.rationale
    await session.execute(
        delete(ProvenanceLink).where(ProvenanceLink.id == link_id)
    )
    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=f"provenance:{out_doc_id}",
        type="provenance.link_removed",
        payload={
            "link_id": str(link_id),
            "section_id": section_id,
            "source_chunk_id": str(source_chunk_id),
            "rationale": rationale,
        },
        actor=principal.as_actor(),
    )
    return Response(status_code=204)


class ProvenanceConfirm(BaseModel):
    confirmed: bool


@router.put("/provenance/{link_id}/confirm")
async def confirm_provenance_link(
    link_id: uuid.UUID,
    payload: ProvenanceConfirm,
    principal: TenantDep,
    session: DbDep,
) -> dict:
    """Notaio valida (confidence 1.0) o smarca (0.0) un link automatico.

    Il link resta in DB (utile per training futuro / audit) ma viene
    nascosto dall'UI quando confidence == 0.
    """
    link = (
        await session.execute(select(ProvenanceLink).where(ProvenanceLink.id == link_id))
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="provenance link not found")
    link.confidence = 1.0 if payload.confirmed else 0.0
    extra = dict(link.extra or {})
    extra["confirmed_by_user"] = payload.confirmed
    extra["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    link.extra = extra
    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=f"provenance:{link.output_document_id}",
        type="provenance.link_confirmed" if payload.confirmed else "provenance.link_rejected",
        payload={"link_id": str(link_id), "section_id": link.output_section_id},
        actor=principal.as_actor(),
    )
    return {
        "id": str(link.id),
        "confidence": link.confidence,
        "confirmed": payload.confirmed,
    }


@router.get("/{document_id}/provenance")
async def get_document_provenance(
    document_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> dict:
    """Mappa output_section_id -> lista di source chunks.

    Usato dall'UI per mostrare, accanto a ogni sezione dell'atto, da quali
    chunk dei documenti di input il sistema ha preso le informazioni.
    """
    del principal
    await _load_doc(session, document_id)
    rows = await session.execute(
        select(ProvenanceLink).where(
            ProvenanceLink.output_document_id == document_id
        )
    )
    by_section: dict[str, list[dict]] = {}
    for link in rows.scalars().all():
        by_section.setdefault(link.output_section_id, []).append({
            "id": str(link.id),
            "source_chunk_id": str(link.source_chunk_id),
            "source_document_id": str(link.source_document_id),
            "relation": link.relation,
            "rationale": link.rationale,
            "confidence": link.confidence,
        })
    return {
        "document_id": str(document_id),
        "links_by_section": by_section,
        "total_links": sum(len(v) for v in by_section.values()),
    }


@router.get("/{document_id}/lineage")
async def get_document_lineage_graph(
    document_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> dict:
    """Restituisce il grafo di lineage completo per un documento di output.

    Output: nodi (input documents + chunks + output sections) e archi
    (chunk -> section). Il frontend usa questi dati per disegnare un SVG.
    """
    del principal
    out_doc = await _load_doc(session, document_id)

    links_rows = await session.execute(
        select(ProvenanceLink).where(
            ProvenanceLink.output_document_id == document_id,
            ProvenanceLink.confidence > 0,
        )
    )
    links = list(links_rows.scalars().all())

    source_chunk_ids = {link.source_chunk_id for link in links}
    chunks_by_id: dict[uuid.UUID, DocumentChunk] = {}
    input_doc_ids: set[uuid.UUID] = set()
    if source_chunk_ids:
        chunk_rows = await session.execute(
            select(DocumentChunk).where(DocumentChunk.id.in_(source_chunk_ids))
        )
        for c in chunk_rows.scalars().all():
            chunks_by_id[c.id] = c
            input_doc_ids.add(c.document_id)

    input_docs: list[dict] = []
    if input_doc_ids:
        doc_rows = await session.execute(
            select(Document).where(Document.id.in_(input_doc_ids))
        )
        for d in doc_rows.scalars().all():
            input_docs.append({
                "id": str(d.id),
                "filename": d.filename,
                "kind": d.kind,
            })

    chunks_payload = [
        {
            "id": str(c.id),
            "document_id": str(c.document_id),
            "ordering": c.ordering,
            "page_number": c.page_number,
            "preview": (c.text or "")[:120],
            "entity_type": (c.classification or {}).get("entity_type"),
            "document_type": (c.classification or {}).get("document_type"),
        }
        for c in chunks_by_id.values()
    ]

    referenced_section_ids = {link.output_section_id for link in links}
    all_sections = [
        {"id": s.get("id") or "", "title": s.get("title") or ""}
        for s in (out_doc.sections or [])
    ]
    referenced_only = [s for s in all_sections if s["id"] in referenced_section_ids]
    sections_payload = referenced_only or all_sections

    edges = [
        {
            "id": str(link.id),
            "source_chunk_id": str(link.source_chunk_id),
            "output_section_id": link.output_section_id,
            "relation": link.relation,
            "confidence": link.confidence,
            "rationale": link.rationale,
        }
        for link in links
    ]

    return {
        "document_id": str(document_id),
        "input_documents": input_docs,
        "chunks": chunks_payload,
        "output_sections": sections_payload,
        "edges": edges,
    }


@router.get("/{document_id}/reverse-provenance-counts")
async def get_document_reverse_provenance_counts(
    document_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> dict:
    """Per ciascun chunk del documento di input, quanti link in uscita ha.

    Rimpiazza la chiamata N-volte di /chunks/{id}/reverse-provenance
    (una per chunk) con UNA query GROUP BY. Usato dal ChunkLineageBadge
    nel workspace.
    """
    del principal
    import sqlalchemy as sa

    rows = await session.execute(
        sa.select(
            ProvenanceLink.source_chunk_id,
            sa.func.count(ProvenanceLink.id).label("n"),
        )
        .join(DocumentChunk, DocumentChunk.id == ProvenanceLink.source_chunk_id)
        .where(
            DocumentChunk.document_id == document_id,
            ProvenanceLink.confidence > 0,
        )
        .group_by(ProvenanceLink.source_chunk_id)
    )
    counts = {str(chunk_id): n for chunk_id, n in rows.all()}
    return {"document_id": str(document_id), "counts_by_chunk": counts}


@router.get("/chunks/{chunk_id}/reverse-provenance")
async def get_chunk_reverse_provenance(
    chunk_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> dict:
    """Reverse: dato un chunk di input, in quali documenti/sezioni di output e' stato usato.

    Permette al notaio di partire da un dato (es. "questa visura catastale")
    e vedere TUTTI gli atti che lo hanno usato.
    """
    del principal
    rows = await session.execute(
        select(ProvenanceLink).where(ProvenanceLink.source_chunk_id == chunk_id)
    )
    items: list[dict] = []
    for link in rows.scalars().all():
        items.append({
            "id": str(link.id),
            "output_document_id": str(link.output_document_id),
            "output_section_id": link.output_section_id,
            "relation": link.relation,
            "rationale": link.rationale,
            "confidence": link.confidence,
        })
    return {"chunk_id": str(chunk_id), "uses": items, "count": len(items)}


@router.get("/{document_id}/classification")
async def get_document_classification_summary(
    document_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> dict:
    """Aggregato della classificazione di tutti i chunk del documento.

    Restituisce:
      - document_type "dominante" (piu' frequente tra i chunk classificati)
      - lista unica di entita' estratte (dedup per (type,value))
      - tag aggregati
      - statistiche per stato
    """
    del principal
    await _load_doc(session, document_id)
    rows = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.ordering.asc())
    )
    chunks = list(rows.scalars().all())

    status_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    entities: dict[tuple[str, str], dict] = {}
    tags: set[str] = set()
    summaries: list[str] = []

    for c in chunks:
        status_counts[c.classification_status] = status_counts.get(c.classification_status, 0) + 1
        cls = c.classification or {}
        if cls.get("abstained") or "error" in cls:
            continue
        dt = cls.get("document_type")
        if dt:
            type_counts[dt] = type_counts.get(dt, 0) + 1
        for e in cls.get("entities") or []:
            key = (e.get("type", "?"), e.get("value", ""))
            if key[1] and key not in entities:
                entities[key] = e
        for t in cls.get("suggested_tags") or []:
            if t:
                tags.add(t)
        if cls.get("summary"):
            summaries.append(cls["summary"])

    dominant = max(type_counts.items(), key=lambda kv: kv[1])[0] if type_counts else None

    return {
        "document_id": str(document_id),
        "chunks_count": len(chunks),
        "status_counts": status_counts,
        "document_type": dominant,
        "document_type_distribution": type_counts,
        "entities": list(entities.values()),
        "tags": sorted(tags),
        "summaries": summaries,
    }


@router.post("/{document_id}/reingest", status_code=status.HTTP_202_ACCEPTED)
async def reingest_document(
    document_id: uuid.UUID,
    principal: TenantDep,
    session: DbDep,
    background: BackgroundTasks,
) -> dict:
    """Forza un re-run della pipeline (utile dopo cambio modello embeddings)."""
    await _load_doc(session, document_id)
    background.add_task(_run_ingestion_safely, document_id, principal.tenant_id)
    return {"scheduled": True, "document_id": str(document_id)}


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> Response:
    doc = await _load_doc(session, document_id)
    if doc.deleted_at is not None:
        return Response(status_code=204)
    doc.deleted_at = datetime.now(timezone.utc)
    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=f"act:{doc.act_id}" if doc.act_id else f"practice:{doc.practice_id}",
        type="document.deleted",
        payload={"document_id": str(document_id), "filename": doc.filename},
        actor=principal.as_actor(),
    )
    return Response(status_code=204)
