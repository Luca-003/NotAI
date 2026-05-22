"""Endpoint /api/v1/act-examples - wiki di atti reali per il RAG."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from notai.contexts.audit.streams import stream_for_act_example
from notai.shared.db.soft_delete import not_deleted
from notai.shared.domain.identifiers import as_uuid_or_none

from apps.api.bg import background_safe
from apps.api.deps import DbDep, TenantDep
from notai.contexts.audit.logger import audit_logger
from notai.contexts.drafting.examples import (
    index_example_in_qdrant,
    search_examples,
)
from notai.contexts.drafting.examples_models import ActExample

router = APIRouter(prefix="/act-examples", tags=["wiki-examples"])

MAX_EXAMPLE_BYTES = 5 * 1024 * 1024


class ActExampleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    template_id: str | None
    title: str
    description: str | None
    tags: list
    source: str
    license: str
    is_anonymized: bool
    sha256: str
    size_bytes: int
    embedding_indexed: bool
    chunks_count: int
    created_at: datetime


class ActExampleDetail(ActExampleRead):
    full_text: str
    sections: list | None


@background_safe("notai.examples.index_background")
async def _index_safely(example_id: uuid.UUID, tenant_id: uuid.UUID | None) -> None:
    await index_example_in_qdrant(example_id, tenant_id)


@router.post("", response_model=ActExampleRead, status_code=status.HTTP_201_CREATED)
async def upload_example(
    principal: TenantDep,
    session: DbDep,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    template_id: str | None = Form(None),
    description: str | None = Form(None),
    tags: str = Form(""),
    license: str = Form("internal_only"),
    is_anonymized: bool = Form(False),
    is_global: bool = Form(False),
    source_url: str | None = Form(None),
) -> ActExampleRead:
    """Carica un esempio di atto.

    Accetta solo text/markdown/plain (in Fase 7+ PDF/DOCX con parsing).
    `is_global=true` rende l'esempio visibile a tutti i tenant (richiede
    license=public o is_anonymized=true; check applicato a runtime).
    """
    if not (file.content_type or "").startswith(("text/", "application/markdown")):
        raise HTTPException(
            status_code=415,
            detail="upload solo text/markdown per ora (PDF/DOCX coming soon)",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="file vuoto")
    if len(data) > MAX_EXAMPLE_BYTES:
        raise HTTPException(status_code=413, detail="file troppo grande (max 5 MB)")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    sha = hashlib.sha256(data).hexdigest()

    if is_global and license not in ("public",) and not is_anonymized:
        raise HTTPException(
            status_code=400,
            detail="is_global richiede license=public oppure is_anonymized=true",
        )

    tags_list = [t.strip() for t in tags.split(",") if t.strip()]

    example = ActExample(
        id=uuid.uuid4(),
        tenant_id=None if is_global else principal.tenant_id,
        template_id=template_id,
        title=title,
        description=description,
        full_text=text,
        tags=tags_list,
        source="manual_upload",
        source_url=source_url,
        uploaded_by=as_uuid_or_none(principal.user_id),
        license=license,
        is_anonymized=is_anonymized,
        sha256=sha,
        size_bytes=len(data),
    )
    session.add(example)
    await session.flush()

    await audit_logger.append(
        session=session,
        tenant_id=principal.tenant_id,
        stream_id=stream_for_act_example(example.id),
        type="act_example.uploaded",
        payload={
            "example_id": str(example.id),
            "title": title,
            "template_id": template_id,
            "sha256": sha,
            "size_bytes": len(data),
            "tags": tags_list,
            "is_global": is_global,
            "license": license,
        },
        actor=principal.as_actor(),
    )
    await session.commit()

    # Indicizza embeddings in background
    background.add_task(
        _index_safely,
        example.id,
        None if is_global else principal.tenant_id,
    )

    return ActExampleRead.model_validate(example)


@router.get("", response_model=list[ActExampleRead])
async def list_examples(
    principal: TenantDep,
    session: DbDep,
    template_id: str | None = Query(None),
    tag: str | None = Query(None),
    limit: int = Query(50, le=200),
) -> list[ActExampleRead]:
    """Elenca esempi visibili al tenant corrente (global + own)."""
    del principal
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB

    stmt = select(ActExample).where(not_deleted(ActExample))
    if template_id:
        stmt = stmt.where(ActExample.template_id == template_id)
    if tag:
        stmt = stmt.where(cast(ActExample.tags, JSONB).contains([tag]))
    stmt = stmt.order_by(ActExample.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [ActExampleRead.model_validate(r) for r in rows]


@router.get("/search")
async def search(
    principal: TenantDep,
    session: DbDep,
    q: str,
    template_id: str | None = Query(None),
    limit: int = Query(10, le=50),
) -> dict:
    """Ricerca ibrida (semantic + text) sugli esempi."""
    del session
    hits = await search_examples(
        q,
        template_id=template_id,
        tenant_id=principal.tenant_id,
        limit=limit,
    )
    return {"query": q, "template_id": template_id, "hits": hits, "count": len(hits)}


@router.get("/{example_id}", response_model=ActExampleDetail)
async def get_example(
    example_id: uuid.UUID, principal: TenantDep, session: DbDep
) -> ActExampleDetail:
    del principal
    ex = (
        await session.execute(select(ActExample).where(ActExample.id == example_id))
    ).scalar_one_or_none()
    if ex is None:
        raise HTTPException(status_code=404, detail="example not found")
    return ActExampleDetail.model_validate(ex)


@router.delete("/{example_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_example(
    example_id: uuid.UUID, principal: TenantDep, session: DbDep
):
    ex = (
        await session.execute(select(ActExample).where(ActExample.id == example_id))
    ).scalar_one_or_none()
    if ex is None:
        raise HTTPException(status_code=404, detail="example not found")
    if ex.deleted_at is None:
        ex.deleted_at = datetime.now(timezone.utc)
        await audit_logger.append(
            session=session,
            tenant_id=principal.tenant_id,
            stream_id=stream_for_act_example(example_id),
            type="act_example.deleted",
            payload={"example_id": str(example_id), "title": ex.title},
            actor=principal.as_actor(),
        )
    from fastapi import Response
    return Response(status_code=204)
