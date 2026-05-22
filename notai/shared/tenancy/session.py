"""DB session scoped al tenant: applica SET LOCAL app.tenant_id in ogni sessione.

L'engine globale è creato lazy. Le sessioni vengono create da `scoped_session()`
e applicano il GUC immediatamente.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from notai.config import get_settings

from .context import current_tenant_id


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    return create_async_engine(
        get_settings().postgres.dsn,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


# Alias deprecati per compatibilita' (rimuovere in Fase 5+)
_engine = get_engine
_session_factory = get_session_factory


@asynccontextmanager
async def scoped_session(
    tenant_id: uuid.UUID | None = None,
) -> AsyncIterator[AsyncSession]:
    """Apre una sessione e applica `SET LOCAL app.tenant_id`.

    Se `tenant_id` non passato, usa quello del contextvar. Senza tenant, le query
    RLS-protette restituiranno set vuoti — è voluto.
    """
    tid = tenant_id or current_tenant_id()
    factory = get_session_factory()

    async with factory() as session:
        if tid is not None:
            # set_config(name, value, is_local=true) e' l'equivalente parametrizzabile
            # di SET LOCAL: il GUC dura il tempo della transazione corrente.
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tid)},
            )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
