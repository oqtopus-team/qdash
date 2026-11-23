"""A chat turn runs to its end and is saved after its HTTP stream disconnects.

These tests drive the copilot router through its ASGI interface: the chat's
``/chat/stream`` response is opened, read, and then disconnected the way a
server reports a closed browser tab, and the saved chat is read back through
the authenticated session endpoint. Only the agent runtime is faked.
"""

from __future__ import annotations

import asyncio
import contextlib
import gc
import json
from collections.abc import AsyncGenerator, Awaitable, Callable, MutableMapping
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from qdash.api.dependencies import (
    get_copilot_investigation_service,
    get_copilot_runtime,
    get_evaluation_service,
)
from qdash.api.lib import auth
from qdash.api.lib.sse import sse_event
from qdash.api.routers import copilot
from qdash.api.schemas.auth import UserInDB
from qdash.api.services import chat_turn_runs, pi_chat_service
from qdash.api.services.chat_transcript import transcript_digest
from qdash.copilot.config import CopilotConfig
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.copilot_chat_session import CopilotChatMessage
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument

Message = MutableMapping[str, Any]

ALICE = {"Authorization": "Bearer alice-token", "X-Project-Id": "p1"}
BOB = {"Authorization": "Bearer bob-token", "X-Project-Id": "p1"}
HISTORY = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]


class Runtime:
    """The agent runtime: the test releases each turn's events one by one."""

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.queues: dict[str, asyncio.Queue[str | None]] = {}

    def queue(self, request_id: str) -> asyncio.Queue[str | None]:
        return self.queues.setdefault(request_id, asyncio.Queue())

    def send(self, request_id: str, event: str, data: dict[str, Any]) -> None:
        self.queue(request_id).put_nowait(sse_event(event, data))

    def end(self, request_id: str) -> None:
        self.queue(request_id).put_nowait(None)

    async def stream(self, request: Any, *_args: Any, **_kwargs: Any) -> AsyncGenerator[str, None]:
        self.opened.append(request.request_id)
        queue = self.queue(request.request_id)
        while (chunk := await queue.get()) is not None:
            yield chunk


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> Runtime:
    users = {
        f"{name}-token": UserInDB(
            user_id=f"{name}-id",
            username=name,
            access_token=f"{name}-token",
            hashed_password="unused",
            default_project_id="p1",
        )
        for name in ("alice", "bob")
    }
    monkeypatch.setattr(auth, "get_user_by_token", users.get)
    monkeypatch.setattr(copilot, "load_copilot_config", lambda: CopilotConfig(enabled=True))
    monkeypatch.setattr(chat_turn_runs, "PROGRESS_INTERVAL", 0.0)
    fake = Runtime()
    monkeypatch.setattr(pi_chat_service, "stream", fake.stream)

    async def not_running(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"running": False}

    monkeypatch.setattr(pi_chat_service, "active_runtime_turn", not_running)
    return fake


def _projects() -> None:
    """Projects p1 and p2 with alice a member of both; p3, of which she is not."""
    for project_id in ("p1", "p2", "p3"):
        ProjectDocument(
            project_id=project_id,
            name=project_id,
            owner_user_id="carol-id",
            owner_username="carol",
        ).insert()
    for project_id in ("p1", "p2"):
        ProjectMembershipDocument(
            project_id=project_id,
            user_id="alice-id",
            username="alice",
            role=ProjectRole.VIEWER,
            status="active",
        ).insert()


def _unused() -> SimpleNamespace:
    """A service the chat's turns here never use."""
    return SimpleNamespace()


@pytest.fixture
def app(runtime: Runtime) -> FastAPI:
    app = FastAPI()
    app.include_router(copilot.router)
    app.dependency_overrides[get_copilot_runtime] = _unused
    app.dependency_overrides[get_evaluation_service] = lambda: SimpleNamespace(
        chat_turn_recorder=lambda **_kwargs: None
    )
    app.dependency_overrides[get_copilot_investigation_service] = _unused
    return app


class Stream:
    """One ``/chat/stream`` response over raw ASGI, which the test can disconnect."""

    def __init__(self, app: FastAPI, body: dict[str, Any], spec_version: str) -> None:
        self.messages: asyncio.Queue[Message] = asyncio.Queue()
        self.gone = asyncio.Event()
        self._body_sent = False
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": spec_version},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/chat/stream",
            "raw_path": b"/chat/stream",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"content-type", b"application/json"),
                *((k.lower().encode(), v.encode()) for k, v in ALICE.items()),
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
        self._payload = json.dumps(body).encode()
        self.task = asyncio.create_task(app(scope, self._receive, self._send))

    async def _receive(self) -> Message:
        if not self._body_sent:
            self._body_sent = True
            return {"type": "http.request", "body": self._payload, "more_body": False}
        await self.gone.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: Message) -> None:
        if self.gone.is_set():
            # What a server does once the client closed the connection (ASGI 2.4).
            raise OSError("client disconnected")
        await self.messages.put(message)

    async def next_event(self) -> tuple[str, dict[str, Any]]:
        while True:
            message = await asyncio.wait_for(self.messages.get(), 5)
            if message["type"] != "http.response.body" or not message.get("body"):
                continue
            lines = dict(
                line.split(": ", 1)
                for line in message["body"].decode().strip().splitlines()
                if ": " in line
            )
            if "event" in lines:
                return lines["event"], json.loads(lines["data"])

    async def disconnect(self) -> None:
        self.gone.set()

    async def closed(self) -> None:
        """Wait for the app to finish the response, and drop it as a server does.

        An ASGI 2.4 app ends with ``ClientDisconnect``; the server logs and drops
        it, which lets the response's generator be finalized.
        """
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.task, 5)
        del self.task
        gc.collect()


def _turn_body(request_id: str, text: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    prefix = [CopilotChatMessage.model_validate(m) for m in history]
    own = CopilotChatMessage(role="user", content=text)
    return {
        "message": text,
        "session_id": "s1",
        "request_id": request_id,
        "turn_start": {
            "index": len(history),
            "digest": transcript_digest([*prefix, own]),
        },
    }


def _answer(text: str) -> dict[str, Any]:
    return {"blocks": [{"type": "text", "content": text, "chart": None}], "entry_id": "17"}


async def _until(check: Callable[[], Awaitable[bool]]) -> None:
    for _ in range(200):
        if await check():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the condition was never met")


@pytest.mark.asyncio
@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_a_turn_whose_stream_disconnects_is_saved_complete_for_the_owner(
    init_db: Any, app: FastAPI, runtime: Runtime, spec_version: str
) -> None:
    _projects()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    async with client:
        created = await client.post(
            "/chat/sessions", json={"session_id": "s1", "messages": HISTORY}, headers=ALICE
        )
        assert created.status_code == 200

        stream = Stream(app, _turn_body("r1", "What is T1?", HISTORY), spec_version)
        start = await asyncio.wait_for(stream.messages.get(), 5)
        assert start["type"] == "http.response.start"
        assert start["status"] == 200
        runtime.send("r1", "delta", {"text": "T1 is "})
        assert await stream.next_event() == ("delta", {"text": "T1 is "})

        # The browser tab closes: the server reports the disconnect to the app.
        await stream.disconnect()
        runtime.send("r1", "delta", {"text": "40 "})
        await stream.closed()
        run = chat_turn_runs.running("alice", "s1", "r1")
        assert run is not None and run.task is not None

        async def unsubscribed() -> bool:
            # ASGI 2.4 servers report the disconnect on the next send; the closed
            # response's generator is finalized after the app returns.
            return not run.subscribers

        await _until(unsubscribed)
        assert not run.task.done()

        # The turn goes on with nobody listening: its progress is saved...
        runtime.send("r1", "delta", {"text": "us."})

        async def progress_saved() -> bool:
            got = (await client.get("/chat/sessions/s1", headers=ALICE)).json()
            last = got["messages"][-1]
            return bool(
                len(got["messages"]) == 4
                and json.loads(last["content"]).get("in_progress")
                and "T1 is 40 us." in last["content"]
            )

        await _until(progress_saved)
        # The session names the turn it records, so a reloaded page finds it by request ID.
        running = (await client.get("/chat/sessions/s1", headers=ALICE)).json()["turn"]
        assert running["request_id"] == "r1"
        assert running["status"] == "running"
        assert running["start_index"] == 2
        assert running["continuing"] is False
        assert running["project_id"] == "p1"

        # ...and so is its end.
        runtime.send("r1", "result", _answer("T1 is 40 us."))
        runtime.end("r1")
        await asyncio.wait_for(run.task, 5)
        assert not run.task.cancelled()
        assert chat_turn_runs.running("alice", "s1", "r1") is None
        assert runtime.opened == ["r1"]

        saved = await client.get("/chat/sessions/s1", headers=ALICE)
        assert saved.status_code == 200
        messages = saved.json()["messages"]
        assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
        assert [m["turn_request_id"] for m in messages] == [None, None, "r1", "r1"]
        assert messages[2]["content"] == "What is T1?"
        answer = json.loads(messages[3]["content"])
        assert answer["blocks"][0]["content"] == "T1 is 40 us."
        assert "in_progress" not in answer
        assert "stopped" not in answer
        assert messages[3]["entry_id"] == "17"
        assert saved.json()["turn"]["status"] == "completed"

        # Only the owner reads the chat.
        assert (await client.get("/chat/sessions/s1", headers=BOB)).status_code == 404
        assert (await client.get("/chat/sessions/s1")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_only_an_explicit_stop_ends_a_disconnected_turn_as_stopped(
    init_db: Any, app: FastAPI, runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    aborted: list[dict[str, Any]] = []

    async def abort(username: str, session_id: str, *_args: Any, **kwargs: Any) -> str:
        aborted.append({"username": username, "session_id": session_id, **kwargs})
        if username != "alice":
            # The runtime keeps each user's chats apart.
            return "not_running"
        runtime.send(
            kwargs["turn_request_id"],
            "error",
            {"step": "run_chat", "detail": "conversation was not answered: aborted"},
        )
        runtime.end(kwargs["turn_request_id"])
        return "stopped"

    monkeypatch.setattr(pi_chat_service, "abort_runtime_turn", abort)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    async with client:
        await client.post(
            "/chat/sessions", json={"session_id": "s1", "messages": HISTORY}, headers=ALICE
        )
        stream = Stream(app, _turn_body("r1", "What is T1?", HISTORY), "2.3")
        runtime.send("r1", "delta", {"text": "Partial"})
        assert await stream.next_event() == ("delta", {"text": "Partial"})
        await stream.disconnect()
        await stream.closed()
        run = chat_turn_runs.running("alice", "s1", "r1")
        assert run is not None and run.task is not None
        assert not run.task.done()

        # A request of the turn from another project is refused, and stops nothing.
        other = await client.post(
            "/chat/stream",
            json={**_turn_body("r1", "What is T1?", HISTORY), "reattach": True},
            headers={**ALICE, "X-Project-Id": "p2"},
        )
        assert '"code": "wrong_project"' in other.text
        # Another user cannot stop it: their stop names their own chat.
        await client.post(
            "/chat/stop", json={"session_id": "s1", "turn_request_id": "r1"}, headers=BOB
        )
        assert not run.task.done()

        # The owner's Stop ends the turn, and it is saved as stopped, not as failed.
        stopped = await client.post(
            "/chat/stop", json={"session_id": "s1", "turn_request_id": "r1"}, headers=ALICE
        )
        assert stopped.json() == {"stopped": True}
        await asyncio.wait_for(run.task, 5)
        assert aborted[-1]["username"] == "alice"

        messages = (await client.get("/chat/sessions/s1", headers=ALICE)).json()["messages"]
        payload = json.loads(messages[-1]["content"])
        assert payload["stopped"] is True
        assert payload["blocks"][0]["content"] == "Partial"


@pytest.mark.asyncio
async def test_the_recorded_turn_is_named_only_in_the_project_it_was_sent_from(
    init_db: Any, app: FastAPI, runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _projects()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    async with client:
        await client.post(
            "/chat/sessions", json={"session_id": "s1", "messages": HISTORY}, headers=ALICE
        )
        stream = Stream(app, _turn_body("r1", "What is T1?", HISTORY), "2.3")
        runtime.send("r1", "delta", {"text": "Partial"})
        assert await stream.next_event() == ("delta", {"text": "Partial"})

        async def read(headers: dict[str, str]) -> httpx.Response:
            got = await client.get("/chat/sessions/s1", headers=headers)
            assert got.status_code == 200
            # The chat itself is the owner's in every project; only the turn is masked.
            assert len(got.json()["messages"]) >= 3
            return got

        async def recorded() -> bool:
            return (await read(ALICE)).json()["turn"] is not None

        await _until(recorded)
        named = await read(ALICE)
        assert named.json()["turn"]["request_id"] == "r1"
        assert named.json()["turn"]["project_id"] == "p1"
        # The reply depends on the project asked from: no cache serves it to another.
        assert "no-store" in named.headers["cache-control"]
        assert "X-Project-Id" in named.headers["vary"]

        token = {"Authorization": ALICE["Authorization"]}
        # Without X-Project-Id the user's default project (p1) is the one asked from.
        assert (await read(token)).json()["turn"]["request_id"] == "r1"
        # Another project she is a member of, one she is not, one that does not exist.
        for project in ("p2", "p3", "missing"):
            assert (await read({**token, "X-Project-Id": project})).json()["turn"] is None
        # Asked from p1 again (A -> B -> A), the turn is named again.
        assert (await read(ALICE)).json()["turn"]["request_id"] == "r1"

        # A user with no default project and no header is in no project: no turn.
        no_default = UserInDB(
            user_id="alice-id",
            username="alice",
            access_token="alice-bare-token",
            hashed_password="unused",
            default_project_id=None,
        )
        known = auth.get_user_by_token
        monkeypatch.setattr(
            auth,
            "get_user_by_token",
            lambda t: no_default if t == "alice-bare-token" else known(t),
        )
        bare = await read({"Authorization": "Bearer alice-bare-token"})
        assert bare.json()["turn"] is None

        # Her membership of p1 ends: the turn is no longer named to her there.
        membership = ProjectMembershipDocument.find_one(
            {"project_id": "p1", "username": "alice"}
        ).run()
        assert membership is not None
        membership.status = "removed"
        membership.save()
        assert (await read(ALICE)).json()["turn"] is None

        # Another user never reads the chat at all.
        assert (await client.get("/chat/sessions/s1", headers=BOB)).status_code == 404

        runtime.send("r1", "result", _answer("Done."))
        runtime.end("r1")
        await stream.disconnect()
        await stream.closed()
        run = chat_turn_runs.running("alice", "s1", "r1")
        if run is not None and run.task is not None:
            await asyncio.wait_for(run.task, 5)
