"""Endpoint /api/v1/modules - gestione moduli per il tenant corrente."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from apps.api.deps import DbDep, TenantDep
from notai.contexts.modules.service import (
    ModuleConfigError,
    list_modules,
    set_enabled,
)
from notai.shared.errors import NotFoundError

router = APIRouter(prefix="/modules", tags=["modules"])


class ModuleToggleRequest(BaseModel):
    enabled: bool
    note: str | None = Field(None, max_length=512)


@router.get("")
async def list_all_modules(principal: TenantDep, session: DbDep) -> dict:
    """Elenca TUTTI i moduli con stato corrente (override + default)."""
    statuses = await list_modules(session, principal.tenant_id)
    return {
        "modules": [
            {
                "id": s.module.id,
                "name": s.module.name,
                "category": s.module.category,
                "description": s.module.description,
                "requires": list(s.module.requires),
                "essential": s.module.essential,
                "default_enabled": s.module.default_enabled,
                "tags": list(s.module.tags),
                "enabled": s.enabled,
                "source": s.source,
                "note": s.note,
                "changed_at": s.changed_at.isoformat() if s.changed_at else None,
                "changed_by": str(s.changed_by) if s.changed_by else None,
            }
            for s in statuses
        ],
        "count": len(statuses),
    }


@router.put("/{module_id}")
async def toggle_module(
    module_id: str,
    payload: ModuleToggleRequest,
    principal: TenantDep,
    session: DbDep,
) -> dict:
    """Attiva o disattiva un modulo per il tenant. I core sono essential e
    non disattivabili (HTTP 409)."""
    try:
        new_status = await set_enabled(
            session,
            tenant_id=principal.tenant_id,
            module_id=module_id,
            enabled=payload.enabled,
            actor=principal.as_actor(),
            note=payload.note,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ModuleConfigError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    return {
        "id": new_status.module.id,
        "enabled": new_status.enabled,
        "note": new_status.note,
        "source": new_status.source,
    }
