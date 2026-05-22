"""Endpoint /api/v1/templates - registry dei template di atto disponibili."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from notai.contexts.drafting.registry import (
    all_templates,
    get_template,
    reload_templates,
)

router = APIRouter(prefix="/templates", tags=["templates"])


def _serialize(t) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "category": t.category,
        "subcategory": t.subcategory,
        "description": t.description,
        "requires_modules": list(t.requires_modules),
        "tags": list(t.tags),
        "section_count": len(t.sections),
        "slot_schema": t.slot_schema,
        "workflow_skip_steps": list(t.workflow_skip_steps),
    }


@router.get("")
async def list_templates(category: str | None = Query(None)) -> dict:
    """Elenca i template disponibili, opzionalmente filtrati per categoria
    (es. `notarile`, `legale`). Pubblico (no tenant required) - i template
    sono parte del codebase, non sono dati per-tenant.
    """
    templates = all_templates()
    if category:
        templates = [t for t in templates if t.category == category]
    grouped: dict[str, list[dict]] = {}
    for t in templates:
        grouped.setdefault(t.category, []).append(_serialize(t))
    return {
        "templates": [_serialize(t) for t in templates],
        "grouped": grouped,
        "count": len(templates),
    }


@router.get("/{template_id:path}")
async def get_template_detail(template_id: str) -> dict:
    """Dettaglio di un singolo template (sezioni complete con text_template)."""
    t = get_template(template_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"template '{template_id}' not found")
    return {
        **_serialize(t),
        "sections": [
            {
                "id": s.id,
                "title": s.title,
                "text_template": s.text_template,
                "relies_on": list(s.relies_on),
            }
            for s in t.sections
        ],
    }


@router.post("/reload")
async def reload_registry() -> dict:
    """Forza il ricaricamento dei template dal filesystem (per dev / dopo upload).

    In produzione richiedera' permesso admin (Fase 5+).
    """
    n = reload_templates()
    return {"count": n}
