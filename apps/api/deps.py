"""FastAPI dependencies riusabili.

Estrae i pattern usati ripetutamente nei router: estrazione tenant_id dal
JWT (popolato dalla TenancyMiddleware), apertura di sessione DB tenant-scoped,
controllo modulo abilitato per il tenant.
"""

from __future__ import annotations

import uuid
from typing import Annotated, AsyncIterator, TypeVar

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notai.shared.tenancy.session import scoped_session

T = TypeVar("T")


class TenantPrincipal:
    """Identita' "minima" estratta dal JWT: chi sta chiamando e per quale studio."""

    def __init__(self, tenant_id: uuid.UUID, user_id: str | None) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id

    def as_actor(self) -> str | None:
        return self.user_id


def get_tenant_principal(request: Request) -> TenantPrincipal:
    """Dependency: estrae tenant_id dal request.state (popolato da TenancyMiddleware).

    Solleva 401 se assente o invalido.
    """
    tid = getattr(request.state, "tenant_id", None)
    if tid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid JWT",
        )
    return TenantPrincipal(tenant_id=tid, user_id=getattr(request.state, "user_id", None))


async def get_db_session(
    principal: Annotated[TenantPrincipal, Depends(get_tenant_principal)],
) -> AsyncIterator[AsyncSession]:
    """Dependency: apre una sessione SQLAlchemy con SET LOCAL app.tenant_id."""
    async with scoped_session(principal.tenant_id) as session:
        yield session


# Type aliases per i type hint nei router
TenantDep = Annotated[TenantPrincipal, Depends(get_tenant_principal)]
DbDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_or_404(
    session: AsyncSession,
    model: type[T],
    entity_id: uuid.UUID,
    *,
    name: str | None = None,
) -> T:
    """Carica un'entita' per ID o solleva 404.

    Rimpiazza il pattern ripetuto:
        e = await repo.get(id); if e is None: raise HTTPException(404, "X not found")
    presente in 13+ posti tra acts/practices/documents/examples.

    NB: assume che il modello abbia un attributo `id`. Tutti i nostri modelli
    ereditano da IdMixin, quindi vero ovunque.
    """
    id_col = getattr(model, "id")
    obj = (await session.execute(select(model).where(id_col == entity_id))).scalar_one_or_none()
    if obj is None:
        raise HTTPException(
            status_code=404,
            detail=f"{name or model.__name__.lower()} not found",
        )
    return obj
