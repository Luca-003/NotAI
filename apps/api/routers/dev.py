"""Endpoint di dev: creazione tenant + emissione JWT senza login.

ATTENZIONE: disponibile SOLO se NOTAI_ENV=dev. In prod e' montato come 404.
In Fase 2 verra' sostituito da un vero flow di registrazione/SSO con MFA.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from jose import jwt
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from apps.api.bg import background_safe
from apps.api.deps import DbDep, TenantDep
from notai.config import get_settings
from notai.contexts.audit.logger import audit_logger
from notai.contexts.audit.streams import stream_for_act
from notai.contexts.documents.ingestion import ingest_document
from notai.contexts.documents.kinds import INPUT_SOURCE
from notai.contexts.documents.models import Document
from notai.contexts.documents.storage import put_blob
from notai.contexts.iam.models import Tenant, User
from notai.contexts.modules.service import seed_defaults
from notai.contexts.practices.acts_repository import ActRepository
from notai.shared.tenancy.session import get_session_factory

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
    factory = get_session_factory()
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

        # Seed feature flags con i default del manifest
        await seed_defaults(session, tenant.id)

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


# ---------------------------------------------------------------------------
# Demo guidata: upload predefinito dei documenti di case-study per uno scenario.
# Legge i .md dalla cartella demostuff/case-studies/<scenario_id>/ del filesystem
# del container API e li uploada come Document associati all'atto indicato.
# ---------------------------------------------------------------------------

# Cartella case-studies bind-mounted via compose.dev.yml (./demostuff -> /app/demostuff).
DEMOSTUFF_ROOT = Path("/app/demostuff/case-studies")

# Scenario_id -> nome cartella (1:1 con demostuff/case-studies/<id>/).
ALLOWED_SCENARIOS = {
    "compravendita-prima-casa",
    "donazione-genitore-figlio",
    "costituzione-srl",
    "citazione-recupero-credito",
    "decreto-ingiuntivo-commerciale",
    "separazione-consensuale",
}


class ScenarioUploadResponse(BaseModel):
    scenario_id: str
    act_id: str
    documents_created: int
    document_ids: list[str]


@background_safe("notai.dev.scenario_ingest")
async def _ingest_in_background(doc_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await ingest_document(doc_id, tenant_id)


@router.post(
    "/scenarios/{scenario_id}/upload-to-act/{act_id}",
    response_model=ScenarioUploadResponse,
)
async def upload_scenario_documents(
    scenario_id: str,
    act_id: uuid.UUID,
    principal: TenantDep,
    session: DbDep,
    background: BackgroundTasks,
) -> ScenarioUploadResponse:
    """Uploada i documenti di un case-study sotto un atto esistente.

    Pensato per la demo guidata: il notaio non deve drag&drop nulla,
    NotAI legge i .md da demostuff/case-studies/<scenario>/ e li ingerisce.
    Solo dev.
    """
    settings = get_settings()
    if settings.env != "dev":
        raise HTTPException(status_code=404, detail="not found")

    if scenario_id not in ALLOWED_SCENARIOS:
        raise HTTPException(
            status_code=400, detail=f"scenario sconosciuto: {scenario_id}"
        )

    folder = DEMOSTUFF_ROOT / scenario_id
    if not folder.is_dir():
        raise HTTPException(
            status_code=500,
            detail=(
                f"cartella demostuff non trovata in container: {folder}. "
                "Verifica il bind-mount in compose.dev.yml."
            ),
        )

    # Verifica esistenza atto + tenant scoping (RLS gia' attiva sulla session).
    act = await ActRepository(session).get(act_id)
    if act is None:
        raise HTTPException(status_code=404, detail="act not found")

    md_files = sorted(folder.glob("*.md"))
    if not md_files:
        raise HTTPException(
            status_code=500, detail=f"nessun .md nello scenario {scenario_id}"
        )

    created_ids: list[uuid.UUID] = []
    bucket = "notai-documents"

    for path in md_files:
        data = path.read_bytes()
        if not data:
            continue
        doc_id = uuid.uuid4()
        key = f"input/{principal.tenant_id}/act/{act_id}/{doc_id}/{path.name}"
        storage_uri, sha = await put_blob(bucket, key, data, "text/markdown")
        doc = Document(
            id=doc_id,
            tenant_id=principal.tenant_id,
            practice_id=act.practice_id,
            act_id=act_id,
            kind=INPUT_SOURCE,
            filename=path.name,
            mime_type="text/markdown",
            size_bytes=len(data),
            storage_uri=storage_uri,
            sha256=sha,
            retention_class="nessuna",
            extra={
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "source": f"demostuff:{scenario_id}",
            },
        )
        session.add(doc)
        await session.flush()
        await audit_logger.append(
            session=session,
            tenant_id=principal.tenant_id,
            stream_id=stream_for_act(act_id),
            type="document.uploaded",
            payload={
                "document_id": str(doc_id),
                "filename": path.name,
                "source": f"demostuff:{scenario_id}",
                "sha256": sha,
            },
            actor=principal.as_actor(),
        )
        created_ids.append(doc_id)

    # Commit prima di schedulare il background (stesso pattern di documents.py).
    await session.commit()
    for doc_id in created_ids:
        background.add_task(_ingest_in_background, doc_id, principal.tenant_id)

    return ScenarioUploadResponse(
        scenario_id=scenario_id,
        act_id=str(act_id),
        documents_created=len(created_ids),
        document_ids=[str(i) for i in created_ids],
    )
