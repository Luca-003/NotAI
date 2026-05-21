"""IAM models: Tenant, User, Role, Permission, UserRole."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from notai.shared.domain.base import (
    Base,
    IdMixin,
    SoftDeleteMixin,
    TimestampsMixin,
)


class Tenant(IdMixin, TimestampsMixin, SoftDeleteMixin, Base):
    """Studio notarile/legale. Root della multi-tenancy."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # Tipologia: notarile | legale | misto
    kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="misto")
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class User(IdMixin, TimestampsMixin, SoftDeleteMixin, Base):
    """Utente dello studio.

    NB: tenant_id qui NON e' nullable e DEVE matchare quello di ogni risorsa
    a cui l'utente accede. RLS lo enforce.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Hash password (passlib bcrypt). NULL = solo SSO/SAML.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # MFA TOTP secret (opzionale, cifrato a livello applicativo in Fase 2+).
    mfa_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Professional details
    professional_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)  # notaio|avvocato|collab
    professional_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # iscrizione albo

    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Role(IdMixin, TimestampsMixin, Base):
    """Ruolo applicativo (per-tenant)."""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Permission(IdMixin, TimestampsMixin, Base):
    """Permessi globali (NON tenant-scoped, sono codici applicativi)."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class RolePermission(Base):
    """N:N Role <-> Permission."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class UserRole(Base):
    """N:N User <-> Role."""

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )


__all__ = ["Permission", "Role", "RolePermission", "Tenant", "User", "UserRole"]
