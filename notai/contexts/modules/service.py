"""Service per la gestione dei feature flag (moduli per tenant)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notai.contexts.audit.logger import audit_logger
from notai.contexts.modules.models import FeatureFlag
from notai.contexts.modules.registry import (
    Module,
    all_modules,
    essential_module_ids,
    get_module,
)
from notai.shared.errors import NotAIError, NotFoundError


class ModuleConfigError(NotAIError):
    """Tentativo di disattivare un modulo essenziale o sconosciuto."""


@dataclass(frozen=True)
class ModuleStatus:
    """Stato runtime di un modulo per un tenant."""

    module: Module
    enabled: bool
    note: str | None
    changed_at: datetime | None
    changed_by: uuid.UUID | None
    source: str  # "tenant-override" | "default"


async def _flags_by_module(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, FeatureFlag]:
    rows = await session.execute(
        select(FeatureFlag).where(FeatureFlag.tenant_id == tenant_id)
    )
    return {ff.module_id: ff for ff in rows.scalars().all()}


async def list_modules(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[ModuleStatus]:
    """Ritorna lo stato di TUTTI i moduli per il tenant (default + override)."""
    flags = await _flags_by_module(session, tenant_id)
    statuses: list[ModuleStatus] = []
    for m in all_modules():
        ff = flags.get(m.id)
        if ff is not None:
            statuses.append(
                ModuleStatus(
                    module=m,
                    enabled=ff.enabled or m.essential,
                    note=ff.note,
                    changed_at=ff.updated_at,
                    changed_by=ff.changed_by,
                    source="tenant-override",
                )
            )
        else:
            statuses.append(
                ModuleStatus(
                    module=m,
                    enabled=m.essential or m.default_enabled,
                    note=None,
                    changed_at=None,
                    changed_by=None,
                    source="default",
                )
            )
    return statuses


async def is_enabled(
    session: AsyncSession, tenant_id: uuid.UUID, module_id: str
) -> bool:
    """Ritorna True se il modulo e' attivo per il tenant."""
    module = get_module(module_id)
    if module is None:
        raise NotFoundError(f"unknown module: {module_id}")
    if module.essential:
        return True
    ff = (
        await session.execute(
            select(FeatureFlag).where(
                FeatureFlag.tenant_id == tenant_id, FeatureFlag.module_id == module_id
            )
        )
    ).scalar_one_or_none()
    if ff is not None:
        return ff.enabled
    return module.default_enabled


async def set_enabled(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    module_id: str,
    enabled: bool,
    actor: str | None,
    note: str | None = None,
) -> ModuleStatus:
    """Attiva o disattiva un modulo. I core (essential=True) non sono disattivabili."""
    module = get_module(module_id)
    if module is None:
        raise NotFoundError(f"unknown module: {module_id}")
    if module.essential and not enabled:
        raise ModuleConfigError(
            f"module '{module_id}' is essential and cannot be disabled"
        )

    changed_by = uuid.UUID(actor) if actor and len(actor) == 36 else None

    ff = (
        await session.execute(
            select(FeatureFlag).where(
                FeatureFlag.tenant_id == tenant_id, FeatureFlag.module_id == module_id
            )
        )
    ).scalar_one_or_none()

    if ff is None:
        ff = FeatureFlag(
            tenant_id=tenant_id,
            module_id=module_id,
            enabled=enabled,
            note=note,
            changed_by=changed_by,
        )
        session.add(ff)
    else:
        ff.enabled = enabled
        ff.note = note
        ff.changed_by = changed_by

    await session.flush()
    # Ricarica i campi server-side (updated_at e' server_default=now())
    await session.refresh(ff)

    await audit_logger.append(
        session=session,
        tenant_id=tenant_id,
        stream_id=f"tenant-config:{tenant_id}",
        type="module.toggled",
        payload={"module_id": module_id, "enabled": enabled, "note": note},
        actor=actor,
    )

    return ModuleStatus(
        module=module,
        enabled=enabled or module.essential,
        note=note,
        changed_at=ff.updated_at,
        changed_by=changed_by,
        source="tenant-override",
    )


async def seed_defaults(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Inizializza i feature flag con i default del manifest per un nuovo tenant.

    Idempotente: non riscrive flag esistenti. Ritorna il numero di nuovi flag inseriti.
    """
    existing = await _flags_by_module(session, tenant_id)
    inserted = 0
    for m in all_modules():
        if m.id in existing:
            continue
        session.add(
            FeatureFlag(
                tenant_id=tenant_id,
                module_id=m.id,
                enabled=m.essential or m.default_enabled,
                note="seeded with manifest defaults",
            )
        )
        inserted += 1
    if inserted:
        await session.flush()
    return inserted


__all__ = [
    "ModuleConfigError",
    "ModuleStatus",
    "essential_module_ids",
    "is_enabled",
    "list_modules",
    "seed_defaults",
    "set_enabled",
]
