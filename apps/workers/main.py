"""NotAI - Temporal worker entrypoint.

In Fase 0 il worker si connette a Temporal e resta in ascolto sul task queue
configurato. Workflow e activity verranno registrati nei sprint successivi.

Avvio: `python -m apps.workers.main`.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Sequence

import structlog
from temporalio.client import Client
from temporalio.worker import Worker

from notai.config import get_settings

logger = structlog.get_logger(__name__)


from notai.contexts.workflow.activities import ALL_ACTIVITIES
from notai.contexts.workflow.workflows import ALL_WORKFLOWS

WORKFLOWS: Sequence[type] = tuple(ALL_WORKFLOWS)
ACTIVITIES: Sequence = tuple(ALL_ACTIVITIES)


async def _run() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    logger.info(
        "notai.workers.starting",
        address=settings.temporal.address,
        namespace=settings.temporal.namespace,
        task_queue=settings.temporal.task_queue,
    )

    client = await Client.connect(
        settings.temporal.address,
        namespace=settings.temporal.namespace,
    )

    worker = Worker(
        client,
        task_queue=settings.temporal.task_queue,
        workflows=list(WORKFLOWS),
        activities=list(ACTIVITIES),
    )

    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        logger.info("notai.workers.signal_received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows non supporta add_signal_handler con ProactorEventLoop.
            pass

    logger.info("notai.workers.ready")
    async with worker:
        await stop_event.wait()
    logger.info("notai.workers.stopped")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
