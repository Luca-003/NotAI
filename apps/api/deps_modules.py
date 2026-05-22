"""Dependency FastAPI per gating endpoint su moduli abilitati.

Uso:
    from apps.api.deps_modules import module_required

    @router.post("", dependencies=[module_required("ai.classify_clause")])
    async def classify(...):
        ...

Se il modulo non e' abilitato per il tenant corrente -> HTTP 403 con detail
strutturato (module_id + reason). L'UI puo' mostrare un CTA per attivarlo.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from apps.api.deps import DbDep, TenantDep
from notai.contexts.modules.service import is_enabled


def module_required(module_id: str):
    """Factory: ritorna una FastAPI dependency che 403-a se il modulo non e' attivo."""

    async def _check(principal: TenantDep, session: DbDep) -> None:
        if not await is_enabled(session, principal.tenant_id, module_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "module_disabled",
                    "module_id": module_id,
                    "message": (
                        f"Modulo '{module_id}' non attivo per questo studio. "
                        "Un amministratore puo' attivarlo da Impostazioni > Moduli."
                    ),
                },
            )

    return Depends(_check)


# Variante "informativa": come dependency restituisce True/False senza alzare,
# utile per endpoint che vogliono comportarsi diversamente in base al modulo.
def get_module_enabled(module_id: str):
    async def _check(principal: TenantDep, session: DbDep) -> bool:
        return await is_enabled(session, principal.tenant_id, module_id)

    return Depends(_check)


ModuleEnabledDep = Annotated[bool, "use get_module_enabled(<id>)"]
