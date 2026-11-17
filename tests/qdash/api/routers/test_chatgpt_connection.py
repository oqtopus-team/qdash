"""ChatGPT plan connection routes and their use in chat, per authenticated user."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet

from qdash.api.dependencies import get_chatgpt_connection_service
from qdash.api.lib import chatgpt_oauth as oauth
from qdash.api.routers import copilot
from qdash.api.services import pi_chat_service
from qdash.api.services.chatgpt_connection_service import ChatGPTConnectionService
from qdash.copilot.config import CopilotConfig
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument
from tests.qdash.api.services.test_chatgpt_connection_service import FakeOpenAI, StaticJwks
from tests.qdash.api.services.test_chatgpt_connection_service import _connect as _connect_service


def _user(username: str) -> dict[str, str]:
    UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=f"{username}-token",
        system_info=SystemInfoModel(),
    ).insert()
    return {"Authorization": f"Bearer {username}-token"}


def _user_id(username: str) -> str:
    user = UserDocument.find_one({"username": username}).run()
    assert user is not None
    return user.user_id


@pytest.fixture
def setup(test_client, monkeypatch):
    monkeypatch.setenv("QDASH_CREDENTIAL_KEY", Fernet.generate_key().decode())
    fake = FakeOpenAI()
    service = ChatGPTConnectionService(
        client=oauth.OpenAIAccountsClient(
            http=httpx.Client(transport=httpx.MockTransport(fake.handler)),
            jwks=StaticJwks(),
            sleep=lambda _s: None,
        ),
        sleep=lambda _s: None,
    )
    test_client.app.dependency_overrides[get_chatgpt_connection_service] = lambda: service

    async def plan_model_ids() -> frozenset[str]:
        return frozenset({"gpt-6.1-sol"})

    monkeypatch.setattr(pi_chat_service, "plan_model_ids", plan_model_ids)
    yield test_client, fake, service
    test_client.app.dependency_overrides.pop(get_chatgpt_connection_service, None)


def _connect(client, fake, service, headers, username: str, issued: str) -> dict[str, Any]:
    started = client.post("/copilot/chatgpt/authorize", headers=headers, json={})
    assert started.status_code == 200
    body = started.json()
    state = parse_qs(urlsplit(body["authorization_url"]).query)["state"][0]
    from qdash.api.lib import credential_cipher

    attempt = service._attempts().find_one({"user_id": _user_id(username)})
    fake.pending_nonce = json.loads(credential_cipher.decrypt(attempt["encrypted_secrets"]))[
        "nonce"
    ]
    fake.audience = issued
    done = client.post(
        "/copilot/chatgpt/callback",
        headers=headers,
        json={"callback_url": f"{body['redirect_uri']}?code=c&state={state}&client_id={issued}"},
    )
    assert done.status_code == 200, done.text
    result: dict[str, Any] = done.json()
    return result


def test_routes_require_a_signed_in_user(setup):
    client, _fake, _service = setup
    assert client.get("/copilot/chatgpt/connection").status_code in {401, 403}
    assert client.post("/copilot/chatgpt/authorize", json={}).status_code in {401, 403}
    assert client.delete("/copilot/chatgpt/connection").status_code in {401, 403}


def test_connect_status_and_disconnect_never_return_tokens(setup):
    client, fake, service = setup
    alice = _user("alice")
    bob = _user("bob")

    status = _connect(client, fake, service, alice, "alice", "oaiapp_alice")
    assert status["status"] == "connected"
    assert status["models"] == [
        {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol", "supported": True}
    ]
    assert status["usage_url"] == "https://chatgpt.com/settings/usage"
    text = json.dumps(status)
    assert "access-" not in text and "refresh-" not in text and "id_token" not in text

    # Bob sees only his own (absent) connection.
    assert client.get("/copilot/chatgpt/connection", headers=bob).json()["status"] == (
        "not_connected"
    )
    # Bob cannot finish Alice's attempt, even with her callback address.
    started = client.post("/copilot/chatgpt/authorize", headers=alice, json={}).json()
    state = parse_qs(urlsplit(started["authorization_url"]).query)["state"][0]
    stolen = client.post(
        "/copilot/chatgpt/callback",
        headers=bob,
        json={"callback_url": f"{started['redirect_uri']}?code=c&state={state}"},
    )
    assert stolen.status_code == 400

    welcome = client.post("/copilot/chatgpt/welcome", headers=alice).json()
    assert welcome["welcome_pending"] is False

    result = client.delete("/copilot/chatgpt/connection", headers=alice)
    assert result.json() == {"revocation_confirmed": True}
    after = client.get("/copilot/chatgpt/connection", headers=alice).json()
    assert after["status"] == "signed_out" and after["can_reconnect"] is True


def _chat(client, headers, model: str = "gpt-6.1-sol") -> str:
    response = client.post(
        "/copilot/chat/stream",
        headers=headers,
        json={
            "message": "hi",
            "session_id": "s1",
            "model_override": {"provider": "chatgpt", "name": model},
        },
    )
    assert response.status_code == 200
    return str(response.text)


@pytest.fixture
def chat_capture(monkeypatch):
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(copilot, "load_copilot_config", lambda: CopilotConfig(enabled=True))

    async def stream(*args, **kwargs):
        captured.append(kwargs)
        yield 'event: result\ndata: {"blocks": []}\n\n'

    monkeypatch.setattr(pi_chat_service, "stream", stream)
    return captured


def test_a_chatgpt_chat_uses_only_the_signed_in_users_plan(setup, chat_capture):
    client, fake, service = setup
    alice = _user("alice")
    bob = _user("bob")
    _connect(client, fake, service, alice, "alice", "oaiapp_alice")

    service.record_inference_error(
        _user_id("alice"),
        service.turn_token(_user_id("alice")).token_version,
        "subscription_sharing_usage_limit_exceeded",
        "limit",
    )
    text = _chat(client, alice)
    assert len(chat_capture) == 1
    # A completed plan turn clears the earlier limit from Settings.
    assert client.get("/copilot/chatgpt/connection", headers=alice).json()["last_error"] is None
    auth = chat_capture[0]["auth"]
    assert auth.chatgpt_access_token == "access-1"  # noqa: S105
    assert "access-1" not in text
    assert chat_capture[0]["on_plan_error"] is not None

    # Bob is not connected: the turn fails instead of using Alice's plan or an operator key.
    text = _chat(client, bob)
    assert len(chat_capture) == 1
    assert '"code": "not_connected"' in text

    # A model the account does not offer is refused.
    text = _chat(client, alice, model="gpt-unknown")
    assert len(chat_capture) == 1
    assert "model_unavailable" in text

    # After disconnecting, Alice's next turn does not run either.
    client.delete("/copilot/chatgpt/connection", headers=alice)
    text = _chat(client, alice)
    assert len(chat_capture) == 1


def _stream_that(monkeypatch, during_turn, *, plan_error: str | None) -> None:
    """A turn that runs ``during_turn`` and then fails on the plan or completes."""
    monkeypatch.setattr(copilot, "load_copilot_config", lambda: CopilotConfig(enabled=True))

    async def stream(*args, on_plan_error=None, **kwargs):
        during_turn()
        if plan_error is not None:
            on_plan_error(plan_error, "limit")
            yield "event: error\ndata: {}\n\n"
            return
        yield 'event: result\ndata: {"blocks": []}\n\n'

    monkeypatch.setattr(pi_chat_service, "stream", stream)


def _reconnect(service, fake, user_id: str) -> None:
    service.disconnect(user_id)
    _connect_service(service, fake, user_id, issued="oaiapp_alice")


def test_a_plan_failure_is_recorded_on_the_turns_token_set(setup, monkeypatch):
    client, fake, service = setup
    alice = _user("alice")
    _connect(client, fake, service, alice, "alice", "oaiapp_alice")
    _stream_that(monkeypatch, lambda: None, plan_error="usage_limit_reached")
    _chat(client, alice)
    status = client.get("/copilot/chatgpt/connection", headers=alice).json()
    assert status["last_error"]["code"] == "usage_limit_reached"


def test_a_failed_turn_on_an_old_session_leaves_the_new_one_unchanged(setup, monkeypatch):
    client, fake, service = setup
    alice = _user("alice")
    _connect(client, fake, service, alice, "alice", "oaiapp_alice")
    uid = _user_id("alice")
    _stream_that(monkeypatch, lambda: _reconnect(service, fake, uid), plan_error="usage_limit")
    _chat(client, alice)
    status = client.get("/copilot/chatgpt/connection", headers=alice).json()
    assert status["status"] == "connected"
    assert status["last_error"] is None


def test_a_finished_turn_on_an_old_session_keeps_the_new_ones_error(setup, monkeypatch):
    client, fake, service = setup
    alice = _user("alice")
    _connect(client, fake, service, alice, "alice", "oaiapp_alice")
    uid = _user_id("alice")

    def reconnect_and_fail() -> None:
        _reconnect(service, fake, uid)
        version = service.turn_token(uid).token_version
        service.record_inference_error(uid, version, "usage_limit_reached", "new session")

    _stream_that(monkeypatch, reconnect_and_fail, plan_error=None)
    _chat(client, alice)
    status = client.get("/copilot/chatgpt/connection", headers=alice).json()
    assert status["last_error"]["code"] == "usage_limit_reached"


def test_local_models_send_no_plan_token(setup, chat_capture):
    client, fake, service = setup
    alice = _user("alice")
    _connect(client, fake, service, alice, "alice", "oaiapp_alice")
    response = client.post(
        "/copilot/chat/stream",
        headers=alice,
        json={
            "message": "hi",
            "session_id": "s1",
            "model_override": {"provider": "openai-compatible", "name": "qwen"},
        },
    )
    assert response.status_code == 200
    assert chat_capture[0]["auth"].chatgpt_access_token is None
    assert chat_capture[0]["on_plan_error"] is None


@pytest.mark.asyncio
async def test_plan_usage_errors_are_explained_and_recorded():
    recorded: list[tuple[str, str]] = []

    async def lines():
        yield json.dumps(
            {
                "type": "error",
                "message": "conversation was not answered: error: 429 "
                "subscription_sharing_usage_limit_exceeded",
            }
        )

    events = [
        event
        async for event in pi_chat_service.translate(
            lines(), on_plan_error=lambda code, message: recorded.append((code, message))
        )
    ]
    assert recorded and recorded[0][0] == "subscription_sharing_usage_limit_exceeded"
    payload = json.loads(events[0].split("data: ", 1)[1])
    assert payload["code"] == "subscription_sharing_usage_limit_exceeded"
    assert payload["usage_url"] == "https://chatgpt.com/settings/usage"


@pytest.mark.asyncio
async def test_the_plan_token_travels_in_an_internal_header_only(monkeypatch):
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text=json.dumps({"type": "done", "text": "ok"}) + "\n")

    transport = httpx.MockTransport(handle)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "runtime-secret")
    auth = pi_chat_service.QDashAuth("alice-token", "p1", chatgpt_access_token="plan-token")
    assert "plan-token" not in repr(auth)
    _ = [
        event
        async for event in pi_chat_service.stream_payload(
            {"message": "hi", "model": {"provider": "chatgpt", "name": "gpt-6.1-sol"}},
            step="run_chat",
            auth=auth,
        )
    ]
    [request] = captured
    assert request.headers["x-qdash-chatgpt-token"] == "plan-token"
    assert b"plan-token" not in request.content
