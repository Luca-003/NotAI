"""Endpoint /api/v1/documents/* - metadata + contenuto blob da MinIO."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from apps.api.deps import DbDep, TenantDep
from notai.contexts.documents.models import Document
from notai.contexts.documents.storage import get_text, parse_storage_uri

router = APIRouter(prefix="/documents", tags=["documents"])


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


async def _load_doc(session, doc_id: uuid.UUID) -> Document:
    doc = (
        await session.execute(select(Document).where(Document.id == doc_id))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc


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
    """Stream del contenuto del documento da MinIO. Per ora solo text/markdown."""
    del principal
    doc = await _load_doc(session, document_id)
    try:
        bucket, key = parse_storage_uri(doc.storage_uri)
        content = await get_text(bucket, key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"storage backend unavailable: {type(e).__name__}",
        ) from e
    return Response(
        content=content,
        media_type=doc.mime_type or "text/plain",
        headers={
            "Content-Disposition": f'inline; filename="{doc.filename}"',
            "X-Sha256": doc.sha256,
        },
    )
