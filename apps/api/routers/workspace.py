"""Endpoint /api/v1/workspace - vista ad albero del tenant.

Sostituisce il pattern "lista flat" con una struttura gerarchica usata dalla
sidebar tree del frontend:
    tenant
      practice (cartella cliente)
        act (cartella atto)
          documents (input_source + visura_auto + bozze)

Tutto tenant-scoped via RLS (sessione gia' setta app.tenant_id).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from apps.api.deps import DbDep, TenantDep
from notai.contexts.documents.models import Document
from notai.contexts.practices.models import Act, Practice
from notai.shared.db.soft_delete import not_deleted

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/tree")
async def get_workspace_tree(principal: TenantDep, session: DbDep) -> dict:
    """Albero practices -> acts -> documents per il tenant corrente.

    Una query per livello (3 query in tutto), poi assemblaggio in memoria.
    Per studi con migliaia di atti, in Fase 5 paginiamo / lazy-load i figli.
    """
    del principal  # RLS scopa via session

    pr_rows = (
        await session.execute(
            select(Practice).where(not_deleted(Practice)).order_by(Practice.created_at.desc())
        )
    ).scalars().all()
    practices = list(pr_rows)
    practice_ids = [p.id for p in practices]

    acts_by_practice: dict[uuid.UUID, list[Act]] = {}
    if practice_ids:
        act_rows = (
            await session.execute(
                select(Act)
                .where(Act.practice_id.in_(practice_ids), not_deleted(Act))
                .order_by(Act.created_at.asc())
            )
        ).scalars().all()
        for a in act_rows:
            acts_by_practice.setdefault(a.practice_id, []).append(a)

    act_ids = [a.id for ps in acts_by_practice.values() for a in ps]
    docs_by_act: dict[uuid.UUID, list[Document]] = {}
    if act_ids:
        doc_rows = (
            await session.execute(
                select(Document)
                .where(Document.act_id.in_(act_ids), not_deleted(Document))
                .order_by(Document.created_at.asc())
            )
        ).scalars().all()
        for d in doc_rows:
            if d.act_id is None:
                continue
            docs_by_act.setdefault(d.act_id, []).append(d)

    tree = []
    for p in practices:
        p_node = {
            "kind": "practice",
            "id": str(p.id),
            "label": p.title,
            "code": p.code,
            "practice_kind": p.kind,
            "status": p.status,
            "acts": [],
        }
        for a in acts_by_practice.get(p.id, []):
            a_docs = docs_by_act.get(a.id, [])
            inputs = [d for d in a_docs if d.kind in ("input_source", "allegato")]
            visure = [d for d in a_docs if d.kind == "visura_auto"]
            outputs = [d for d in a_docs if d.kind not in ("input_source", "allegato", "visura_auto")]
            a_node = {
                "kind": "act",
                "id": str(a.id),
                "label": a.title,
                "act_kind": a.kind,
                "workflow_status": a.workflow_status,
                "workflow_run_id": a.workflow_run_id,
                "documents": {
                    "inputs": [_doc_node(d) for d in inputs],
                    "visure_auto": [_doc_node(d) for d in visure],
                    "outputs": [_doc_node(d) for d in outputs],
                },
                "counts": {
                    "inputs": len(inputs),
                    "visure_auto": len(visure),
                    "outputs": len(outputs),
                },
            }
            p_node["acts"].append(a_node)
        tree.append(p_node)

    return {"practices": tree, "practice_count": len(practices)}


def _doc_node(d: Document) -> dict:
    return {
        "kind": "document",
        "id": str(d.id),
        "label": d.filename,
        "doc_kind": d.kind,
        "mime_type": d.mime_type,
        "ingestion_status": d.ingestion_status,
        "size_bytes": d.size_bytes,
    }


__all__ = ["router"]
