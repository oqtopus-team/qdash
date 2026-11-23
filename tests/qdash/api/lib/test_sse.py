"""A closing streaming response runs its generator's cleanup when it ends.

The response is driven through its ASGI interface with no garbage collection,
so each test shows the cleanup ran because the response closed the generator.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, MutableMapping
from typing import Any

import pytest
from starlette.requests import ClientDisconnect

from qdash.api.lib.sse import ClosingStreamingResponse

Message = MutableMapping[str, Any]


def _scope(spec_version: str) -> dict[str, Any]:
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": spec_version}}


class Body:
    """A body that yields chunks until told to stop, and records its cleanup."""

    def __init__(self) -> None:
        self.cleaned_up = False

    async def chunks(self) -> AsyncGenerator[str, None]:
        try:
            while True:
                yield "data: x\n\n"
                await asyncio.sleep(0)
        finally:
            self.cleaned_up = True


@pytest.mark.asyncio
async def test_a_disconnect_reported_on_send_closes_the_generator() -> None:
    body = Body()
    sent: list[Message] = []

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and sent:
            # What an ASGI 2.4 server does once the client closed the connection.
            raise OSError("client disconnected")
        sent.append(message)

    async def receive() -> Message:
        raise AssertionError("an ASGI 2.4 response does not listen for the disconnect")

    response = ClosingStreamingResponse(body.chunks(), media_type="text/event-stream")
    with pytest.raises(ClientDisconnect):
        await response(_scope("2.4"), receive, send)
    assert body.cleaned_up


@pytest.mark.asyncio
async def test_a_disconnect_reported_on_receive_closes_the_generator() -> None:
    body = Body()
    gone = asyncio.Event()

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            # The server is slow to write, so the cancel lands in ``send``.
            await asyncio.sleep(3600)

    async def receive() -> Message:
        await gone.wait()
        return {"type": "http.disconnect"}

    response = ClosingStreamingResponse(body.chunks(), media_type="text/event-stream")
    task = asyncio.create_task(response(_scope("2.3"), receive, send))
    await asyncio.sleep(0.01)
    gone.set()
    await asyncio.wait_for(task, 5)
    assert body.cleaned_up


@pytest.mark.asyncio
async def test_a_finished_response_leaves_its_ended_generator_alone() -> None:
    async def chunks() -> AsyncGenerator[str, None]:
        yield "data: x\n\n"

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    async def receive() -> Message:
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    response = ClosingStreamingResponse(chunks(), media_type="text/event-stream")
    await response(_scope("2.4"), receive, send)
    assert [m.get("body") for m in sent[1:]] == [b"data: x\n\n", b""]
