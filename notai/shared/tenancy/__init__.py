"""Tenancy primitives — context propagation and DB session scoping.

Tutto l'accesso al database deve passare attraverso una sessione su cui è stato
fatto `SET LOCAL app.tenant_id = '<uuid>'`. Le policy RLS in Postgres filtrano
tutte le query sulla GUC; senza GUC settata, le query non vedono nulla.
"""

from .context import (
    TenantContext,
    current_tenant_id,
    require_tenant_id,
    set_tenant_id,
)
from .session import scoped_session

__all__ = [
    "TenantContext",
    "current_tenant_id",
    "require_tenant_id",
    "scoped_session",
    "set_tenant_id",
]
