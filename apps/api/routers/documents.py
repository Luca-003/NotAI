"""Endpoint /api/v1/documents/* - upload, metadata, contenuto blob da MinIO."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from apps.api.deps import DbDep, TenantDep
from notai.contexts.audit.logger import audit_logger
from notai.contexts.documents.ingestion import ingest_document
from notai.contexts.documents.models import Document, DocumentChunk
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


async def _run_ingestion_safely(document_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Wrapper sicuro per BackgroundTasks: cattura errori per non far crashare il worker."""
    import structlog

    log = structlog.get_logger(__name__)
    try:
        await ingest_document(document_id, tenant_id)
    except Exception as e:  # noqa: BLE001
        log.exception("notai.ingest.background_failed", document_id=str(document_id), error=str(e))


async def _load_doc(session, doc_id: uuid.UUID) -> Document:
    doc = (
        await session.execute(select(Document).where(Document.id == doc_id))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc


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
