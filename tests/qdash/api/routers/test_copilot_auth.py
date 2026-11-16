"""Copilot forwards the authenticated user's credentials to Pi on every turn."""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qdash.api.dependencies import get_copilot_runtime
from qdash.api.lib import auth
from qdash.api.routers import copilot
from qdash.api.schemas.auth import UserInDB
from qdash.api.services import pi_chat_service
from qdash.api.services.copilot_chat_session_service import RuntimeTarget
from qdash.copilot.config import CopilotConfig
from qdash.copilot.contracts import TaskContext, TaskContextBundle


@pytest.fixture(autouse=True)
def _chats_never_branched(monkeypatch):
    """These tests run without MongoDB: every chat is its own store's root, as one never branched."""

    async def target(_username, session_id):
        return RuntimeTarget(session_id)

    monkeypatch.setattr(pi_chat_service, "runtime_target", target)


@pytest.mark.parametrize("with_task", [False, True])
@pytest.mark.parametrize("selected_project", [None, "selected-project"])
def test_pi_receives_current_user_token_and_project(monkeypatch, with_task, selected_project):
    captured = []
    user = UserInDB(
        user_id="alice-id",
        username="alice",
        access_token="alice-token",
        hashed_password="unused",
        default_project_id="default-project",
    )
    monkeypatch.setattr(
        auth, "get_user_by_token", lambda token: user if token == user.access_token else None
    )
    monkeypatch.setattr(copilot, "load_copilot_config", lambda: CopilotConfig(enabled=True))

    async def stream(*args, **kwargs):
        captured.append(kwargs)
        yield 'event: result\ndata: {"blocks": []}\n\n'

    monkeypatch.setattr(pi_chat_service, "stream", stream)
    app = FastAPI()
    app.include_router(copilot.router)
    app.dependency_overrides[get_copilot_runtime] = lambda: SimpleNamespace(
        build_task_context=lambda **kwargs: TaskContextBundle(
            context=TaskContext(task_knowledge_prompt="", chip_id="chip", qid="0"),
            image_base64=None,
            expected_images=[],
        ),
    )
    body: dict[str, object] = {"message": "Analyze", "session_id": "s1"}
    if with_task:
        body["task"] = {
            "task_name": "CheckRabi",
            "chip_id": "chip",
            "qid": "0",
            "execution_id": "e1",
            "task_id": "t1",
        }
    headers = {"Authorization": "Bearer alice-token"}
    if selected_project:
        headers["X-Project-Id"] = selected_project
    with TestClient(app) as client:
        response = client.post("/chat/stream", json=body, headers=headers)
        assert response.status_code == 200
        assert captured[0]["username"] == "alice"
        assert captured[0]["auth"] == pi_chat_service.QDashAuth(
            "alice-token", selected_project or "default-project"
        )
        assert (captured[0]["task"] is not None) is with_task
        assert "alice-token" not in response.text
        # A later request must supply valid credentials again, including approvals.
        body["approval"] = {"id": "write-1", "approve": True}
        rejected = client.post(
            "/chat/stream", json=body, headers={"Authorization": "Bearer revoked-token"}
        )
        assert rejected.status_code == 401
        assert len(captured) == 1
        user.disabled = True
        assert client.post("/chat/stream", json=body, headers=headers).status_code == 403
        assert len(captured) == 1


@pytest.mark.asyncio
async def test_bridge_sends_credentials_in_headers_only(monkeypatch):
    import httpx

    captured = []

    def handle(request):
        captured.append(request)
        return httpx.Response(200, text=json.dumps({"type": "done", "text": "ok"}) + "\n")

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "internal-token")
    credentials = pi_chat_service.QDashAuth("alice-token", "selected-project")
    payload = {"owner_id": "alice", "conversation_id": "s1", "message": "hello"}
    events = [
        event
        async for event in pi_chat_service.stream_payload(
            payload, step="run_chat", auth=credentials
        )
    ]
    request = captured[0]
    assert request.headers["Authorization"] == "Bearer internal-token"
    assert request.headers["X-QDash-Token"] == "alice-token"
    assert request.headers["X-QDash-Project-Id"] == "selected-project"
    assert json.loads(request.content) == payload
    assert "alice-token" not in repr(credentials)
    assert "alice-token" not in "".join(events)


@pytest.mark.parametrize("selected_project", [None, "selected-project"])
def test_a_steer_is_sent_for_the_current_user_and_project(monkeypatch, selected_project):
    captured = []
    user = UserInDB(
        user_id="alice-id",
        username="alice",
        access_token="alice-token",
        hashed_password="unused",
        default_project_id="default-project",
    )
    monkeypatch.setattr(
        auth, "get_user_by_token", lambda token: user if token == user.access_token else None
    )

    async def steer(username, session_id, **kwargs):
        captured.append({"username": username, "session_id": session_id, **kwargs})
        if kwargs["auth"].project_id == "other-project":
            raise pi_chat_service.SteerRefusedError(403, "other project")
        return {"status": "queued", "reason": None, "entry_id": None}

    monkeypatch.setattr(pi_chat_service, "steer_runtime_turn", steer)
    app = FastAPI()
    app.include_router(copilot.router)
    body = {"session_id": "s1", "request_id": "r1", "message": "Use Q5"}
    headers = {"Authorization": "Bearer alice-token"}
    if selected_project:
        headers["X-Project-Id"] = selected_project
    with TestClient(app) as client:
        response = client.post("/chat/steer", json=body, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"status": "queued", "reason": None, "entry_id": None}
        assert captured[0]["username"] == "alice"
        assert captured[0]["auth"] == pi_chat_service.QDashAuth(
            "alice-token", selected_project or "default-project"
        )
        assert captured[0]["request_id"] == "r1"
        # Another project's running answer is refused by the runtime and reported as such.
        refused = client.post(
            "/chat/steer",
            json=body,
            headers={"Authorization": "Bearer alice-token", "X-Project-Id": "other-project"},
        )
        assert refused.status_code == 403
        assert client.post("/chat/steer", json=body).status_code in (401, 403)
        assert (
            client.post(
                "/chat/steer", json=body, headers={"Authorization": "Bearer revoked-token"}
            ).status_code
            == 401
        )
        assert (
            client.post("/chat/steer", json={**body, "message": ""}, headers=headers).status_code
            == 422
        )
        assert len(captured) == 2


def test_a_steer_status_is_read_for_the_current_user_and_project(monkeypatch):
    captured = []
    user = UserInDB(
        user_id="alice-id",
        username="alice",
        access_token="alice-token",
        hashed_password="unused",
        default_project_id="default-project",
    )
    monkeypatch.setattr(
        auth, "get_user_by_token", lambda token: user if token == user.access_token else None
    )

    async def status(username, session_id, **kwargs):
        captured.append({"username": username, "session_id": session_id, **kwargs})
        if kwargs["auth"].project_id == "other-project":
            raise pi_chat_service.SteerRefusedError(403, "another project")
        return {"status": "applied", "reason": None, "entry_id": "12"}

    async def never_send(*_args, **_kwargs):
        raise AssertionError("a status lookup must not send the message")

    monkeypatch.setattr(pi_chat_service, "steer_runtime_status", status)
    monkeypatch.setattr(pi_chat_service, "steer_runtime_turn", never_send)
    app = FastAPI()
    app.include_router(copilot.router)
    body = {"session_id": "s1", "request_id": "r1"}
    headers = {"Authorization": "Bearer alice-token", "X-Project-Id": "p1"}
    with TestClient(app) as client:
        response = client.post("/chat/steer/status", json=body, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"status": "applied", "reason": None, "entry_id": "12"}
        assert captured[0]["username"] == "alice"
        assert captured[0]["auth"] == pi_chat_service.QDashAuth("alice-token", "p1")
        refused = client.post(
            "/chat/steer/status",
            json=body,
            headers={"Authorization": "Bearer alice-token", "X-Project-Id": "other-project"},
        )
        assert refused.status_code == 403
        assert client.post("/chat/steer/status", json=body).status_code in (401, 403)
        assert (
            client.post(
                "/chat/steer/status", json={"session_id": "s1"}, headers=headers
            ).status_code
            == 422
        )


def test_a_continue_does_not_rebuild_the_opening_context(monkeypatch):
    captured = []
    user = UserInDB(
        user_id="alice-id",
        username="alice",
        access_token="alice-token",
        hashed_password="unused",
        default_project_id="default-project",
    )
    monkeypatch.setattr(
        auth, "get_user_by_token", lambda token: user if token == user.access_token else None
    )
    monkeypatch.setattr(copilot, "load_copilot_config", lambda: CopilotConfig(enabled=True))

    async def stream(*args, **kwargs):
        captured.append(kwargs)
        yield 'event: result\ndata: {"blocks": []}\n\n'

    def no_context(**_kwargs):
        raise AssertionError("a continue must not rebuild the task context")

    monkeypatch.setattr(pi_chat_service, "stream", stream)
    app = FastAPI()
    app.include_router(copilot.router)
    app.dependency_overrides[get_copilot_runtime] = lambda: SimpleNamespace(
        build_task_context=no_context
    )
    body = {
        "message": "",
        "session_id": "s1",
        "continue_run": True,
        "task": {
            "task_name": "CheckRabi",
            "chip_id": "chip",
            "qid": "0",
            "execution_id": "e1",
            "task_id": "t1",
        },
    }
    with TestClient(app) as client:
        response = client.post(
            "/chat/stream", json=body, headers={"Authorization": "Bearer alice-token"}
        )
        assert response.status_code == 200
    assert captured[0]["task"] is None


def test_a_branch_is_made_for_the_users_own_chat_in_a_project_they_can_use(init_db, monkeypatch):
    from fastapi import Header, HTTPException

    from qdash.api.lib.project import get_project_context
    from qdash.api.schemas.copilot_chat_session import CreateCopilotChatSessionRequest
    from qdash.api.services.copilot_chat_session_service import (
        CopilotChatSessionService,
        ForkedBranch,
        ForkSettledError,
        RuntimeTarget,
    )
    from qdash.dbmodel.copilot_chat_session import CopilotChatSessionDocument

    user = UserInDB(
        user_id="alice-id",
        username="alice",
        access_token="alice-token",
        hashed_password="unused",
        default_project_id="default-project",
    )
    monkeypatch.setattr(
        auth, "get_user_by_token", lambda token: user if token == user.access_token else None
    )
    forks = []
    deleted = []
    failing = {"on": False}

    stopped = []

    async def fork(username, store, source, entry_id, target, *, auth):
        forks.append((username, store, source, entry_id, target, auth))
        if failing["on"]:
            # As fork_runtime_branch reports a runtime it could not reach.
            raise ForkSettledError("runtime down")
        return ForkedBranch("7", True)

    refusing = {"on": False}

    async def delete(username, store):
        if refusing["on"]:
            return False
        deleted.append((username, store))
        return True

    async def abort(username, session_id, target=None):
        stopped.append((username, session_id, target))
        return False

    monkeypatch.setattr(pi_chat_service, "fork_runtime_branch", fork)
    monkeypatch.setattr(pi_chat_service, "delete_runtime_session_state", delete)
    monkeypatch.setattr(pi_chat_service, "abort_runtime_turn", abort)

    def project_context(x_project_id: str | None = Header(default=None)):
        # Membership, as get_project_context checks it: "other-project" is not the user's.
        if x_project_id == "other-project":
            raise HTTPException(status_code=403, detail="not a member")
        return SimpleNamespace(project_id=x_project_id or "default-project")

    CopilotChatSessionService().create_session(
        username="alice",
        request=CreateCopilotChatSessionRequest.model_validate(
            {
                "session_id": "s1",
                "messages": [
                    {"role": "user", "content": "Q1"},
                    {"role": "assistant", "content": "A1", "entry_id": "5"},
                ],
            }
        ),
    )
    app = FastAPI()
    app.include_router(copilot.router)
    app.dependency_overrides[get_project_context] = project_context
    headers = {"Authorization": "Bearer alice-token", "X-Project-Id": "p1"}
    body = {"entry_id": "5", "target_session_id": "b1"}
    with TestClient(app) as client:
        assert (
            client.post(
                "/chat/sessions/s1/branches",
                json=body,
                headers={**headers, "X-Project-Id": "other-project"},
            ).status_code
            == 403
        )
        assert client.post("/chat/sessions/s1/branches", json=body).status_code in (401, 403)
        assert forks == []
        # The runtime could not be reached: the branch waits, hidden, for the retry.
        failing["on"] = True
        response = client.post("/chat/sessions/s1/branches", json=body, headers=headers)
        assert response.status_code == 502
        pending = CopilotChatSessionDocument.find_one({"session_id": "b1"}).run()
        assert pending is not None
        assert pending.branch is not None
        assert pending.branch.status == "pending"
        failing["on"] = False
        response = client.post("/chat/sessions/s1/branches", json=body, headers=headers)
        assert response.status_code == 200
        assert response.json()["branch"] == {"source_session_id": "s1", "source_entry_id": "5"}
        assert [m["content"] for m in response.json()["messages"]] == ["Q1", "A1"]
        username, store, source, entry_id, target, sent_auth = forks[-1]
        assert (username, store, source, entry_id, target) == ("alice", "s1", None, "5", "b1")
        assert sent_auth == pi_chat_service.QDashAuth("alice-token", "p1")
        # Deleting the source stops only its own turn and keeps the store its branch uses;
        # deleting the branch then removes it.
        assert client.delete("/chat/sessions/s1", headers=headers).status_code == 200
        assert deleted == []
        assert stopped == [("alice", "s1", RuntimeTarget("s1"))]
        assert client.delete("/chat/sessions/b1", headers=headers).status_code == 200
        assert deleted == [("alice", "s1")]
        assert stopped[-1] == ("alice", "b1", RuntimeTarget("s1", "7"))
        assert client.delete("/chat/sessions/b1", headers=headers).status_code == 404
        # The runtime cannot remove a store yet: the deleted chat is kept, hidden, and the
        # next listing of the user's chats removes the store.
        CopilotChatSessionService().create_session(
            username="alice",
            request=CreateCopilotChatSessionRequest.model_validate({"session_id": "solo"}),
        )
        refusing["on"] = True
        assert client.delete("/chat/sessions/solo", headers=headers).status_code == 200
        assert ("alice", "solo") not in deleted
        refusing["on"] = False
        assert client.get("/chat/sessions", headers=headers).json() == {"sessions": []}
        assert deleted[-1] == ("alice", "solo")
        assert CopilotChatSessionDocument.find({"username": "alice"}).to_list() == []
