"""Helper per la creazione di un Temporal Client riutilizzabile dall'API."""

from __future__ import annotations

import asyncio

import structlog
from temporalio.client import Client

from notai.config import get_settings

logger = structlog.get_logger(__name__)

_client: Client | None = None
_lock = asyncio.Lock()


async def get_temporal_client() -> Client:
    """Singleton lazy. Riconnette se la connessione viene chiusa."""
    global _client
    async with _lock:
        if _client is None:
            settings = get_settings()
            logger.info(
                "notai.workflow.client.connect",
                address=settings.temporal.address,
                namespace=settings.temporal.namespace,
            )
            _client = await Client.connect(
                settings.temporal.address,
                namespace=settings.temporal.namespace,
            )
        return _client
