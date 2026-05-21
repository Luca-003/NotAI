"""NotAI - RPA worker entrypoint (Playwright headful via Xvfb).

In Fase 0 si limita a connettersi a Temporal su un task queue separato
dedicato al RPA. Le activity Playwright verranno aggiunte in Fase 2.
"""

from __future__ import annotations

import asyncio
import logging
import signal

import structlog
from temporalio.client import Client
from temporalio.worker import Worker

from notai.config import get_settings

logger = structlog.get_logger(__name__)

RPA_TASK_QUEUE = "notai-rpa"


async def _run() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    logger.info(
        "notai.rpa.starting",
        address=settings.temporal.address,
        task_queue=RPA_TASK_QUEUE,
    )
    client = await Client.connect(
        settings.temporal.address,
        namespace=settings.temporal.namespace,
    )
    worker = Worker(
        client,
        task_queue=RPA_TASK_QUEUE,
        workflows=[],
        activities=[],
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    logger.info("notai.rpa.ready")
    async with worker:
        await stop_event.wait()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
