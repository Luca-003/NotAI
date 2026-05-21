"""Smoke test: il context manager di tenancy isola il GUC correttamente."""

from __future__ import annotations

import uuid

import pytest

from notai.shared.errors import TenantMissingError  # noqa: F401  (sanity import)
from notai.shared.tenancy import (
    TenantContext,
    current_tenant_id,
    require_tenant_id,
    set_tenant_id,
)
from notai.shared.tenancy.context import _tenant_id_var


def test_default_is_none() -> None:
    assert current_tenant_id() is None


def test_require_raises_when_unset() -> None:
    with pytest.raises(RuntimeError):
        require_tenant_id()


def test_context_manager_sets_and_restores() -> None:
    tid = uuid.uuid4()
    assert current_tenant_id() is None
    with TenantContext(tid):
        assert current_tenant_id() == tid
        assert require_tenant_id() == tid
    assert current_tenant_id() is None


def test_set_and_reset_token() -> None:
    tid = uuid.uuid4()
    token = set_tenant_id(tid)
    try:
        assert current_tenant_id() == tid
    finally:
        _tenant_id_var.reset(token)
    assert current_tenant_id() is None
