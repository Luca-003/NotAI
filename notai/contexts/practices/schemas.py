"""Pydantic schemas per il contesto Practice (request/response API)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PracticeCreate(BaseModel):
    """Payload per POST /practices."""

    code: str = Field(..., min_length=1, max_length=64)
    kind: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=512)
    description: str | None = None
    responsible_user_id: uuid.UUID | None = None


class PracticeRead(BaseModel):
    """Risposta /practices/*."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    kind: str
    title: str
    description: str | None
    status: str
    responsible_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
