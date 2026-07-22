"""Real NATS/JetStream ``EventBus`` implementation.

Imported and exercised ONLY under ``@pytest.mark.integration`` (the repo conftest
auto-skips unless ``RUN_INTEGRATION=1``); unit tests use ``InMemoryEventBus``.
Connection settings are read straight from the environment (see ``.env.example``:
``NATS_URL``, ``NATS_STREAM``) to avoid editing the shared ``app.config`` module.

``nats-py`` is async; this wraps the async client behind the synchronous
``EventBus`` surface via a private event loop so callers stay transport-agnostic.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from typing import Any

from app.workflow.engine import EventBus

NATS_URL_ENV = "NATS_URL"
NATS_STREAM_ENV = "NATS_STREAM"


def _nats_url() -> str:
    return os.environ.get(NATS_URL_ENV, "nats://localhost:4222")


def _stream() -> str:
    return os.environ.get(NATS_STREAM_ENV, "accounting-intents")


class NatsEventBus(EventBus):
    """JetStream-backed bus. Durable, at-least-once delivery of intents."""

    def __init__(self, url: str | None = None, stream: str | None = None) -> None:
        self._url = url or _nats_url()
        self._stream = stream or _stream()
        self._loop = asyncio.new_event_loop()
        self._nc: Any = None
        self._js: Any = None

    def _connect(self) -> None:
        if self._nc is not None:
            return

        async def _do() -> None:
            import nats

            self._nc = await nats.connect(self._url)
            self._js = self._nc.jetstream()
            # Idempotent stream creation; the subject wildcard captures all intents.
            try:
                await self._js.add_stream(name=self._stream, subjects=["intents.>"])
            except Exception:  # noqa: BLE001 - stream may already exist
                pass

        self._loop.run_until_complete(_do())

    def publish(self, subject: str, payload: dict[str, Any]) -> None:
        self._connect()
        data = json.dumps(payload, default=str).encode("utf-8")

        async def _do() -> None:
            await self._js.publish(subject, data)

        self._loop.run_until_complete(_do())

    def subscribe(self, subject: str, handler: Callable[[dict[str, Any]], None]) -> None:
        self._connect()

        async def _do() -> None:
            async def _cb(msg: Any) -> None:
                handler(json.loads(msg.data.decode("utf-8")))
                await msg.ack()

            await self._js.subscribe(subject, cb=_cb)

        self._loop.run_until_complete(_do())

    def close(self) -> None:
        if self._nc is not None:
            self._loop.run_until_complete(self._nc.drain())
            self._nc = None
        self._loop.close()
