"""Endpoint per il management dei modelli LLM.

GET  /api/v1/llm/models      -> elenca modelli scoperti su LiteLLM + Ollama
GET  /api/v1/llm/routing     -> mappa attuale ruolo -> alias modello
PUT  /api/v1/llm/routing     -> aggiorna mappa (Fase 0: solo in-process; Fase 1: DB-persisted)

Nota: in Fase 0 il PUT modifica una mappa runtime non persistita - utile per testare,
ma al restart torna ai default da env. In Fase 1 verra' persistita per-tenant su DB.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from notai.contexts.ai.registry import current_routing, discover_all

router = APIRouter(prefix="/llm", tags=["llm"])


class RoutingUpdate(BaseModel):
    generation: str | None = None
    extraction: str | None = None
    embeddings: str | None = None
    verifier: str | None = None
    classification: str | None = None


# Override runtime (in-memory). Sostituisce per-ruolo i default da env.
# Volutamente semplice: in Fase 1 sostituiamo con repository DB-backed.
_runtime_overrides: dict[str, str] = {}


def _effective_routing() -> dict[str, str]:
    base = current_routing().as_dict()
    base.update(_runtime_overrides)
    return base


@router.get("/models")
async def list_models() -> dict[str, Any]:
    """Elenca modelli disponibili (sia su LiteLLM gateway che su Ollama host)."""
    models = await discover_all()
    return {
        "count": len(models),
        "models": [m.to_public() for m in models],
    }


@router.get("/routing")
async def get_routing() -> dict[str, Any]:
    """Mappa attuale ruolo -> alias modello (env default + override runtime)."""
    base = current_routing().as_dict()
    return {
        "routing": _effective_routing(),
        "defaults_from_env": base,
        "runtime_overrides": dict(_runtime_overrides),
    }


@router.put("/routing")
async def update_routing(payload: RoutingUpdate) -> dict[str, Any]:
    """Aggiorna la mappa ruolo -> modello (override in-memory, non persistente).

    In Fase 1 questo PUT diventera' DB-persisted per-tenant + audit-logged.
    """
    valid_roles = set(current_routing().as_dict().keys())
    updates = payload.model_dump(exclude_none=True)

    unknown = set(updates) - valid_roles
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown roles: {sorted(unknown)}")

    _runtime_overrides.update(updates)
    return {"routing": _effective_routing(), "updated": updates}


@router.delete("/routing/overrides")
async def clear_overrides() -> dict[str, Any]:
    """Rimuove tutti gli override runtime, torna ai default da env."""
    _runtime_overrides.clear()
    return {"routing": _effective_routing(), "cleared": True}
