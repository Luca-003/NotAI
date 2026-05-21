"""Tenant context propagation via contextvars.

In FastAPI viene popolato da un middleware sulla base del JWT.
In Temporal viene popolato dall'header del workflow run.
"""

from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from typing import Iterator

_tenant_id_var: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "notai_tenant_id", default=None
)


def current_tenant_id() -> uuid.UUID | None:
    """Ritorna il tenant_id corrente o None se non settato."""
    return _tenant_id_var.get()


def require_tenant_id() -> uuid.UUID:
    """Come current_tenant_id ma solleva se non settato.

    Da usare nei layer di dominio dove l'assenza di tenant è un bug.
    """
    tid = _tenant_id_var.get()
    if tid is None:
        raise RuntimeError(
            "tenant_id non settato nel contesto. "
            "Probabilmente un endpoint o un worker manca della tenancy middleware."
        )
    return tid


def set_tenant_id(tenant_id: uuid.UUID) -> contextvars.Token[uuid.UUID | None]:
    """Setta il tenant_id. Ritorna un Token per ripristinare in finally."""
    return _tenant_id_var.set(tenant_id)


class TenantContext:
    """Context manager: imposta il tenant_id per la durata del blocco."""

    def __init__(self, tenant_id: uuid.UUID) -> None:
        self.tenant_id = tenant_id
        self._token: contextvars.Token[uuid.UUID | None] | None = None

    def __enter__(self) -> "TenantContext":
        self._token = set_tenant_id(self.tenant_id)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._token is not None:
            _tenant_id_var.reset(self._token)


@contextmanager
def temporary_tenant(tenant_id: uuid.UUID) -> Iterator[None]:
    """Helper compatto: `with temporary_tenant(tid): ...`."""
    with TenantContext(tenant_id):
        yield
