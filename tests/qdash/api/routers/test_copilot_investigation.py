"""The chat opens an investigation from project-scoped logs; source routes are read-only and authenticated."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from qdash.api.dependencies import (
    get_copilot_investigation_service,
    get_copilot_runtime,
    get_source_access_service,
)
from qdash.api.lib import auth
from qdash.api.routers import copilot
from qdash.api.schemas.auth import UserInDB
from qdash.api.services import pi_chat_service
from qdash.api.services.copilot_investigation_service import (
    InvestigationContext,
    InvestigationNotFoundError,
)
from qdash.api.services.source_access_service import SourceAccessService, SourceRoot
from qdash.copilot.config import CopilotConfig

HEADERS = {"Authorization": "Bearer alice-token", "X-Project-Id": "proj"}


@pytest.fixture
def user(monkeypatch):
    user = UserInDB(
        user_id="alice-id",
        username="alice",
        access_token="alice-token",
        hashed_password="",
        default_project_id="default-project",
    )
    monkeypatch.setattr(
        auth, "get_user_by_token", lambda token: user if token == user.access_token else None
    )
    monkeypatch.setattr(copilot, "load_copilot_config", lambda: CopilotConfig(enabled=True))
    return user


class _Investigations:
    def __init__(self, missing=False):
        self.calls = []
        self.missing = missing

    def build(self, **kwargs):
        self.calls.append(kwargs)
        if self.missing:
            raise InvestigationNotFoundError(kwargs["target"].execution_id)
        return InvestigationContext(
            opening_message=f"OPENING for {kwargs['target'].execution_id}",
            has_task_result=False,
            has_logs=True,
        )


def _app(investigations, source=None):
    app = FastAPI()
    app.include_router(copilot.router)
    app.dependency_overrides[get_copilot_runtime] = lambda: SimpleNamespace()  # noqa: PLW0108
    app.dependency_overrides[get_copilot_investigation_service] = lambda: investigations
    if source is not None:
        app.dependency_overrides[get_source_access_service] = lambda: source
    return app


def _capture_stream(monkeypatch):
    captured = []

    async def stream(*args, **kwargs):
        captured.append(kwargs)
        yield 'event: result\ndata: {"blocks": []}\n\n'

    monkeypatch.setattr(pi_chat_service, "stream", stream)
    return captured


def test_investigation_opens_with_server_built_context(monkeypatch, user):
    captured = _capture_stream(monkeypatch)
    checked = []

    def project_context(current_user, project_id):
        checked.append((current_user.username, project_id))
        return SimpleNamespace(project_id=project_id)

    monkeypatch.setattr(copilot, "get_project_context", project_context)
    investigations = _Investigations()
    body = {
        "message": "Investigate why execution e1 failed.",
        "session_id": "s1",
        "investigation": {"execution_id": "e1"},
    }
    with TestClient(_app(investigations)) as client:
        response = client.post("/chat/stream", json=body, headers=HEADERS)
    assert response.status_code == 200
    assert checked == [("alice", "proj")]
    assert investigations.calls[0]["project_id"] == "proj"
    assert investigations.calls[0]["target"].task_id is None
    assert captured[0]["opening_message"] == "OPENING for e1"
    assert captured[0]["task"] is None


def test_ordinary_chat_builds_no_investigation(monkeypatch, user):
    captured = _capture_stream(monkeypatch)
    investigations = _Investigations()
    with TestClient(_app(investigations)) as client:
        response = client.post(
            "/chat/stream", json={"message": "hi", "session_id": "s1"}, headers=HEADERS
        )
    assert response.status_code == 200
    assert investigations.calls == []
    assert captured[0]["opening_message"] is None


def test_investigation_respects_project_access_and_existence(monkeypatch, user):
    captured = _capture_stream(monkeypatch)

    def forbidden(current_user, project_id):
        raise HTTPException(status_code=403, detail="No access")

    body = {"message": "m", "session_id": "s1", "investigation": {"execution_id": "e1"}}
    monkeypatch.setattr(copilot, "get_project_context", forbidden)
    investigations = _Investigations()
    with TestClient(_app(investigations)) as client:
        assert client.post("/chat/stream", json=body, headers=HEADERS).status_code == 403
    assert investigations.calls == []

    monkeypatch.setattr(copilot, "get_project_context", lambda u, p: SimpleNamespace(project_id=p))
    with TestClient(_app(_Investigations(missing=True))) as client:
        assert client.post("/chat/stream", json=body, headers=HEADERS).status_code == 404
        both = {
            **body,
            "task": {
                "task_name": "CheckRabi",
                "chip_id": "c",
                "qid": "0",
                "execution_id": "e1",
                "task_id": "t1",
            },
        }
        assert client.post("/chat/stream", json=both, headers=HEADERS).status_code == 400
    assert captured == []


def test_source_routes_are_authenticated_and_bounded(tmp_path: Path, user):
    (tmp_path / "workflow").mkdir()
    (tmp_path / "workflow" / "task.py").write_text("def run():\n    raise KeyError('qid')\n")
    source = SourceAccessService(
        (SourceRoot(name="qdash", path=tmp_path.resolve(), kind="qdash", revision="abc"),)
    )
    with TestClient(_app(_Investigations(), source)) as client:
        assert client.get("/source/roots").status_code == 401
        roots = client.get("/source/roots", headers=HEADERS).json()
        assert roots["roots"][0]["name"] == "qdash"
        assert roots["execution_revision_recorded"] is False

        found = client.get("/source/search", params={"query": "KeyError"}, headers=HEADERS)
        assert found.json()["matches"] == [
            {
                "root": "qdash",
                "path": "workflow/task.py",
                "line": 2,
                "text": "raise KeyError('qid')",
            }
        ]
        read = client.get(
            "/source/file", params={"path": "/app/qdash/workflow/task.py"}, headers=HEADERS
        ).json()
        assert (read["path"], read["revision"], read["total_lines"]) == (
            "workflow/task.py",
            "abc",
            2,
        )
        refused = client.get(
            "/source/file", params={"root": "qdash", "path": "../secret.py"}, headers=HEADERS
        )
        assert refused.status_code == 400
        assert (
            client.get("/source/search", params={"query": "x", "limit": 1000}, headers=HEADERS)
        ).status_code == 422
