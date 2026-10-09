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
from qdash.api.services import pi_analysis_service, pi_chat_service
from qdash.copilot.config import CopilotConfig
from qdash.copilot.contracts import AnalysisContextResult, TaskAnalysisContext


@pytest.mark.parametrize("path", ["/chat/stream", "/analyze/stream"])
@pytest.mark.parametrize("selected_project", [None, "selected-project"])
def test_pi_receives_current_user_token_and_project(monkeypatch, path, selected_project):
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
    monkeypatch.setattr(
        copilot, "load_copilot_config", lambda: CopilotConfig(enabled=True, copilot_backend="pi")
    )

    async def stream(*args, **kwargs):
        captured.append(kwargs)
        yield 'event: result\ndata: {"blocks": []}\n\n'

    monkeypatch.setattr(pi_chat_service, "stream", stream)
    monkeypatch.setattr(pi_analysis_service, "stream", stream)
    app = FastAPI()
    app.include_router(copilot.router)
    app.dependency_overrides[get_copilot_runtime] = lambda: SimpleNamespace(
        build_analysis_context=lambda **kwargs: AnalysisContextResult(
            context=TaskAnalysisContext(task_knowledge_prompt="", chip_id="chip", qid="0"),
            image_base64=None,
            expected_images=[],
        ),
    )
    body: dict[str, object] = {
        "message": "Analyze",
        "session_id": "s1",
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
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 200
        assert captured[0]["username"] == "alice"
        assert captured[0]["auth"] == pi_chat_service.QDashAuth(
            "alice-token", selected_project or "default-project"
        )
        assert "alice-token" not in response.text
        # A later request must supply valid credentials again, including approvals.
        body["approval"] = {"id": "write-1", "approve": True}
        rejected = client.post(path, json=body, headers={"Authorization": "Bearer revoked-token"})
        assert rejected.status_code == 401
        assert len(captured) == 1
        user.disabled = True
        assert client.post(path, json=body, headers=headers).status_code == 403
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
