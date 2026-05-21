"""Endpoint di dev: creazione tenant + emissione JWT senza login.

ATTENZIONE: disponibile SOLO se NOTAI_ENV=dev. In prod e' montato come 404.
In Fase 2 verra' sostituito da un vero flow di registrazione/SSO con MFA.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, HTTPException
from jose import jwt
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from notai.config import get_settings
from notai.contexts.iam.models import Tenant, User
from notai.shared.tenancy.session import _session_factory

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/dev", tags=["dev"])


class TenantBootstrap(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(..., min_length=1, max_length=255)
    kind: str = Field("misto", max_length=32)
    admin_email: str = Field(..., min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    admin_display_name: str = Field(..., min_length=1, max_length=255)


class TenantBootstrapResponse(BaseModel):
    tenant_id: str
    user_id: str
    token: str


@router.post("/bootstrap", response_model=TenantBootstrapResponse)
async def bootstrap_tenant(payload: TenantBootstrap) -> TenantBootstrapResponse:
    """Crea (upsert) un tenant + un utente admin e ritorna un JWT.

    Idempotente sullo slug del tenant. Solo dev.
    """
    settings = get_settings()
    if settings.env != "dev":
        raise HTTPException(status_code=404, detail="not found")

    # La tabella `tenants` non ha RLS (e' la root); l'inserimento e' libero.
    # `users` invece ha RLS, quindi prima di insertare un user dobbiamo settare
    # SET LOCAL app.tenant_id = <tenant.id>.
    factory = _session_factory()
    async with factory() as session:
        # Upsert tenant
        stmt = (
            insert(Tenant)
            .values(slug=payload.slug, name=payload.name, kind=payload.kind)
            .on_conflict_do_update(
                index_elements=["slug"],
                set_={"name": payload.name, "kind": payload.kind},
            )
            .returning(Tenant)
        )
        tenant = (await session.execute(stmt)).scalar_one()

        # Setta il GUC per soddisfare le policy RLS sulle tabelle tenant-aware
        # (in primis `users`). set_config(name, value, is_local=true) e'
        # l'equivalente parametrizzabile di SET LOCAL.
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant.id)},
        )

        # Upsert admin user
        await session.execute(
            insert(User)
            .values(
                tenant_id=tenant.id,
                email=payload.admin_email,
                display_name=payload.admin_display_name,
                professional_kind="notaio" if payload.kind == "notarile" else None,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "email"])
        )

        user = (
            await session.execute(
                select(User).where(
                    User.tenant_id == tenant.id, User.email == payload.admin_email
                )
            )
        ).scalar_one()

        await session.commit()

    # Genera JWT
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user.id),
        "tenant_id": str(tenant.id),
        "email": payload.admin_email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_ttl_seconds)).timestamp()),
    }
    token = jwt.encode(
        claims, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algo
    )

    logger.info("notai.dev.bootstrap", tenant_id=str(tenant.id), user_id=str(user.id))
    return TenantBootstrapResponse(
        tenant_id=str(tenant.id),
        user_id=str(user.id),
        token=token,
    )
