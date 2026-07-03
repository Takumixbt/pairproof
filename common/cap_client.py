from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, TypeVar

from croo import AgentClient, Config, Event, EventStream

from .config import AgentConfig

T = TypeVar("T")


async def poll_until(
    get_fn: Callable[[], Awaitable[T]],
    predicate: Callable[[T], bool],
    timeout: float,
    interval: float = 3.0,
) -> T:
    """Repeatedly calls get_fn() until predicate(result) is true or timeout
    elapses. Used for driving one-shot negotiations (Builder-as-requester,
    test scripts) where polling is simpler and more robust than depending on
    unconfirmed websocket event-field semantics.
    """
    deadline = time.monotonic() + timeout
    while True:
        value = await get_fn()
        if predicate(value):
            return value
        if time.monotonic() >= deadline:
            raise TimeoutError("timed out waiting for condition")
        await asyncio.sleep(interval)


def make_client(cfg: AgentConfig) -> AgentClient:
    return AgentClient(
        Config(base_url=cfg.base_url, ws_url=cfg.ws_url, rpc_url=cfg.rpc_url),
        cfg.sdk_key,
    )


class EventWaiter:
    """Resolves once a matching event arrives on an already-connected EventStream.

    Register the waiter *before* the action that triggers the event (e.g. before
    accepting a negotiation), since the stream only delivers events going forward.
    """

    def __init__(self, stream: EventStream, event_type: str, predicate: Callable[[Event], bool] | None = None) -> None:
        self._future: asyncio.Future[Event] = asyncio.get_event_loop().create_future()

        def handler(event: Event) -> None:
            if self._future.done():
                return
            if predicate is not None and not predicate(event):
                return
            self._future.set_result(event)

        stream.on(event_type, handler)

    async def wait(self, timeout: float) -> Event:
        return await asyncio.wait_for(self._future, timeout=timeout)
