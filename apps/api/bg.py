"""Helpers per FastAPI BackgroundTasks.

`add_task` non gestisce errori: se la coroutine fa raise, l'errore viene
loggato dal logger di FastAPI ma non in modo strutturato, e in alcuni casi
il task viene marcato come "done" silenziosamente. Wrappiamo con cattura
esplicita + log strutturato.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import structlog

logger = structlog.get_logger(__name__)


def background_safe(label: str) -> Callable[[Callable[..., Awaitable[None]]], Callable[..., Awaitable[None]]]:
    """Decorator factory: wrappa una coroutine in un try/except che logga.

    Uso:
        @background_safe("notai.ingest.background")
        async def run_ingest(doc_id, tenant_id):
            await ingest_document(doc_id, tenant_id)

        background.add_task(run_ingest, doc_id, tenant_id)
    """

    def decorator(fn: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        async def wrapper(*args, **kwargs) -> None:
            try:
                await fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    f"{label}.failed",
                    error=str(e),
                    args=[str(a) for a in args],
                )

        wrapper.__name__ = getattr(fn, "__name__", label)
        return wrapper

    return decorator


__all__ = ["background_safe"]
