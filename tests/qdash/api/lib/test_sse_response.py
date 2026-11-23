"""A disconnected response releases its subscription without relying on garbage collection."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import anyio
import pytest
from starlette.requests import ClientDisconnect

from qdash.api.lib.sse import ClosingStreamingResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from starlette.types import Message, Scope


def scope(version: str = "2.4") -> Scope:
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": version}}


async def receive() -> Message:
    await asyncio.Event().wait()
    raise AssertionError("the response does not receive a disconnect in this test")


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [OSError("client disconnected"), RuntimeError("send failed")])
async def test_send_error_closes_subscriber_even_while_response_and_traceback_are_retained(
    error: Exception,
) -> None:
    subscribed: set[str] = set()
    cleanup_finished = asyncio.Event()
    release_turn = asyncio.Event()
    turn = asyncio.create_task(release_turn.wait())

    async def subscriber() -> AsyncGenerator[str, None]:
        subscribed.add("browser")
        try:
            yield "data: one\n\n"
            await release_turn.wait()
        finally:
            await anyio.sleep(0)
            subscribed.clear()
            cleanup_finished.set()

    response = ClosingStreamingResponse(subscriber())

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise error

    expected = ClientDisconnect if isinstance(error, OSError) else RuntimeError
    try:
        # Keep both the response and exception traceback alive: neither gc nor a
        # later event from the independent turn may be needed to unsubscribe.
        with pytest.raises(expected) as raised:
            await response(scope(), receive, send)
        assert raised.value is not None
        if isinstance(error, RuntimeError):
            assert raised.value is error
        assert not subscribed
        assert cleanup_finished.is_set()
        assert not turn.done()
        assert not turn.cancelled()
    finally:
        release_turn.set()
        await turn


@pytest.mark.asyncio
async def test_normal_end_finishes_generator_cleanup() -> None:
    cleanup_finished = asyncio.Event()
    messages: list[Message] = []

    async def subscriber() -> AsyncGenerator[str, None]:
        try:
            yield "one"
        finally:
            await anyio.sleep(0)
            cleanup_finished.set()

    async def send(message: Message) -> None:
        messages.append(message)

    response = ClosingStreamingResponse(subscriber())
    await response(scope(), receive, send)
    assert cleanup_finished.is_set()
    assert messages[-1] == {"type": "http.response.body", "body": b"", "more_body": False}


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["2.3", "2.4"])
async def test_request_cancellation_closes_suspended_subscriber(version: str) -> None:
    sending = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def subscriber() -> AsyncGenerator[str, None]:
        try:
            yield "one"
        finally:
            # A cancellation scope must not interrupt an asynchronous finalizer.
            await anyio.sleep(0)
            cleanup_finished.set()

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            sending.set()
            await asyncio.Event().wait()

    response = ClosingStreamingResponse(subscriber())
    request = asyncio.create_task(response(scope(version), receive, send))
    await asyncio.wait_for(sending.wait(), timeout=5)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert cleanup_finished.is_set()


@pytest.mark.asyncio
async def test_legacy_disconnect_closes_suspended_subscriber() -> None:
    gone = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def subscriber() -> AsyncGenerator[str, None]:
        try:
            yield "one"
        finally:
            await anyio.sleep(0)
            cleanup_finished.set()

    async def disconnected() -> Message:
        await gone.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            gone.set()
            await asyncio.Event().wait()

    response = ClosingStreamingResponse(subscriber())
    await asyncio.wait_for(response(scope("2.3"), disconnected, send), timeout=5)
    assert cleanup_finished.is_set()
