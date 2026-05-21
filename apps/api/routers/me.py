"""Endpoint placeholder /me: ritorna info sul JWT decodificato."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def me(request: Request) -> dict[str, Any]:
    tid = getattr(request.state, "tenant_id", None)
    uid = getattr(request.state, "user_id", None)
    if tid is None:
        raise HTTPException(status_code=401, detail="missing or invalid JWT")
    return {
        "tenant_id": str(tid),
        "user_id": uid,
    }
