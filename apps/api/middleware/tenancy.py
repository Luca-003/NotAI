"""Middleware che estrae il tenant_id dal JWT e lo mette nel contextvar.

In Fase 0 il JWT è opzionale (per consentire le probe /health). In Fase 1, gli
endpoint sotto /api/v1/* richiederanno autenticazione obbligatoria via dependency.
"""

from __future__ import annotations

import uuid

from fastapi import Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from notai.config import get_settings
from notai.shared.tenancy import set_tenant_id


class TenancyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        token: contextvars_Token | None = None  # type: ignore[name-defined]  # noqa: F821
        settings = get_settings()

        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            jwt_token = auth.split(" ", 1)[1]
            try:
                claims = jwt.decode(
                    jwt_token,
                    settings.jwt_secret.get_secret_value(),
                    algorithms=[settings.jwt_algo],
                )
                tid_str = claims.get("tenant_id")
                if tid_str:
                    token = set_tenant_id(uuid.UUID(tid_str))
                    request.state.tenant_id = uuid.UUID(tid_str)
                    request.state.user_id = claims.get("sub")
            except (JWTError, ValueError):
                # JWT malformato: lasciamo passare ma senza tenant.
                # Gli endpoint protetti rifiuteranno con 401.
                pass

        try:
            response = await call_next(request)
        finally:
            if token is not None:
                from notai.shared.tenancy.context import _tenant_id_var  # noqa: PLC0415

                _tenant_id_var.reset(token)

        return response
