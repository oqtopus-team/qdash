"""Per-user ChatGPT plan connections: OAuth binding, storage, refresh and sign-out."""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa

from qdash.api.lib import chatgpt_oauth as oauth
from qdash.api.services.chatgpt_connection_service import (
    REFRESH_LEASE_SECONDS,
    ChatGPTConnectionError,
    ChatGPTConnectionService,
)
from qdash.dbmodel.chatgpt_connection import ChatGPTConnectionDocument

SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ISSUED = "oaiapp_alice"


class StaticJwks:
    """Stands in for OpenAI's JWKS: one RSA public key."""

    def get_signing_key_from_jwt(self, token: str) -> Any:
        return SIGNING_KEY.public_key()


class FakeOpenAI:
    """OpenAI's token, revocation and model endpoints, recording each request."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.subject = "user-sub-1"
        self.audience = ISSUED
        self.scope = " ".join(oauth.SCOPES)
        self.key = SIGNING_KEY
        self.issuer = oauth.ISSUER
        self.refresh_response: tuple[int, dict[str, Any]] | None = None
        self.revoke_status = 200
        self.on_refresh: Any = None
        self.on_exchange: Any = None
        self.refresh_id_token: Any = None
        # An exception to raise, or a raw (status, body bytes) answer, for a refresh.
        self.refresh_raise: Exception | None = None
        self.refresh_raw: tuple[int, bytes] | None = None
        self.models: list[dict[str, str]] = [
            {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol", "visibility": "list"},
            {"slug": "hidden", "display_name": "Hidden", "visibility": "hide"},
        ]
        self.on_models: Any = None
        self.counter = 0
        self.lock = threading.Lock()

    def id_token(self, nonce: str | None, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "sub": self.subject,
            "aud": [self.audience],
            "email": "alice@example.com",
            "iat": now,
            "exp": now + 3600,
            oauth.ACCOUNT_CLAIM: {"chatgpt_account_id": "workspace-1"},
        }
        if nonce is not None:
            claims["nonce"] = nonce
        key = overrides.pop("key", self.key)
        claims.update(overrides)
        return jwt.encode(
            {k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256"
        )

    def tokens(self, nonce: str | None = None) -> dict[str, Any]:
        with self.lock:
            self.counter += 1
            n = self.counter
        body: dict[str, Any] = {
            "access_token": f"access-{n}",
            "refresh_token": f"refresh-{n}",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": self.scope,
        }
        if nonce is not None:
            body["id_token"] = self.id_token(nonce)
        return body

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.requests.append((url, form))
        if url == oauth.TOKEN_URL and form.get("grant_type") == "authorization_code":
            body = self.tokens(self.pending_nonce)
            if self.on_exchange:
                self.on_exchange()
            return httpx.Response(200, json=body)
        if url == oauth.TOKEN_URL and form.get("grant_type") == "refresh_token":
            if self.on_refresh:
                self.on_refresh()
            if self.refresh_raise is not None:
                raise self.refresh_raise
            if self.refresh_raw is not None:
                return httpx.Response(self.refresh_raw[0], content=self.refresh_raw[1])
            if self.refresh_response:
                status, body = self.refresh_response
                return httpx.Response(status, json=body)
            time.sleep(0.05)
            body = self.tokens()
            if self.refresh_id_token is not None:
                body["id_token"] = self.refresh_id_token()
            return httpx.Response(200, json=body)
        if url == oauth.REVOCATION_URL:
            return httpx.Response(self.revoke_status)
        if url == oauth.MODELS_URL:
            assert request.headers["authorization"].startswith("Bearer access-")
            # The catalog is read when the request arrives, before any hook runs.
            body = {"models": list(self.models)}
            if self.on_models:
                self.on_models()
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    pending_nonce: str = ""

    def requests_to(self, url: str, grant: str | None = None) -> list[dict[str, str]]:
        return [
            form
            for u, form in self.requests
            if u == url and (grant is None or form.get("grant_type") == grant)
        ]


@pytest.fixture
def credential_key(monkeypatch):
    monkeypatch.setenv("QDASH_CREDENTIAL_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("QDASH_CHATGPT_CALLBACK_PORT", raising=False)


@pytest.fixture
def fake(init_db, credential_key):
    return FakeOpenAI()


@pytest.fixture
def service(fake):
    client = oauth.OpenAIAccountsClient(
        http=httpx.Client(transport=httpx.MockTransport(fake.handler)),
        jwks=StaticJwks(),
        sleep=lambda _s: None,
    )
    return ChatGPTConnectionService(client=client, sleep=lambda _s: None)


def _raw(user_id: str) -> dict[str, Any]:
    doc = ChatGPTConnectionDocument.get_motor_collection().find_one({"user_id": user_id})
    assert doc is not None
    return dict(doc)


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def _nonce_of(service: ChatGPTConnectionService, user_id: str) -> str:
    from qdash.api.lib import credential_cipher

    attempt = service._attempts().find_one({"user_id": user_id})
    assert attempt is not None
    return str(json.loads(credential_cipher.decrypt(attempt["encrypted_secrets"]))["nonce"])


def _connect(service, fake, user_id: str = "alice-id", issued: str = ISSUED, **start: Any) -> str:
    started = service.start_authorization(user_id, **start)
    query = _query(started.authorization_url)
    fake.pending_nonce = _nonce_of(service, user_id)
    callback = f"{started.redirect_uri}?code=code-1&state={query['state']}"
    if query["client_id"] == oauth.DYNAMIC_CLIENT_ID:
        callback += f"&client_id={issued}"
    service.complete_authorization(user_id, callback)
    return query["state"]


def test_registration_request_follows_the_documented_parameters(service, fake):
    started = service.start_authorization("alice-id")
    query = _query(started.authorization_url)

    assert started.authorization_url.startswith(oauth.AUTHORIZE_URL + "?")
    assert started.redirect_uri == "http://127.0.0.1:1455/auth/callback"
    assert query["client_id"] == "dynamic_agent_client"
    assert query["agent_name_hint"] == "QDash"
    assert query["ext_agent_host_id"].startswith("urn:uuid:")
    assert "alice" not in query["ext_agent_host_id"]
    assert query["response_type"] == "code"
    assert query["redirect_uri"] == started.redirect_uri
    assert set(query["scope"].split()) == {
        "openid",
        "profile",
        "email",
        "offline_access",
        "resource.invoke",
        "chatgpt.tokens.use.direct",
    }
    assert query["resource"] == "https://api.openai.com/v1"
    assert query["code_challenge_method"] == "S256"
    assert query["state"] and query["nonce"]
    assert "id_token_hint" not in query
    # The host ID is chosen once and reused by later attempts.
    again = _query(service.start_authorization("alice-id").authorization_url)
    assert again["ext_agent_host_id"] == query["ext_agent_host_id"]
    assert again["state"] != query["state"]


def test_completing_exchanges_with_pkce_validates_identity_and_encrypts(service, fake):
    started = service.start_authorization("alice-id")
    query = _query(started.authorization_url)
    fake.pending_nonce = _nonce_of(service, "alice-id")
    status = service.complete_authorization(
        "alice-id",
        f"{started.redirect_uri}?code=code-1&scope=x&state={query['state']}&client_id={ISSUED}",
    )

    [exchange] = fake.requests_to(oauth.TOKEN_URL, "authorization_code")
    assert exchange["client_id"] == ISSUED
    assert exchange["code"] == "code-1"
    assert exchange["redirect_uri"] == started.redirect_uri
    assert exchange["resource"] == oauth.RESOURCE
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(exchange["code_verifier"].encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert challenge == query["code_challenge"]
    assert "client_secret" not in exchange

    assert status["status"] == "connected"
    assert status["plan_usage_enabled"] is True
    assert status["welcome_pending"] is True
    assert status["email"] == "alice@example.com"
    assert status["models"] == [{"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol"}]
    raw = _raw("alice-id")
    stored = json.dumps(raw, default=str)
    assert "access-1" not in stored and "refresh-1" not in stored
    assert raw["client_id"] == ISSUED and raw["subject"] == "user-sub-1"
    assert service.access_token("alice-id") == "access-1"


def test_a_state_is_bound_to_its_user_and_used_once(service, fake):
    started = service.start_authorization("alice-id")
    state = _query(started.authorization_url)["state"]
    fake.pending_nonce = _nonce_of(service, "alice-id")
    callback = f"{started.redirect_uri}?code=c&state={state}&client_id={ISSUED}"

    service.start_authorization("bob-id")
    with pytest.raises(ChatGPTConnectionError) as stolen:
        service.complete_authorization("bob-id", callback)
    assert stolen.value.code == "state_mismatch"

    service.complete_authorization("alice-id", callback)
    with pytest.raises(ChatGPTConnectionError) as replay:
        service.complete_authorization("alice-id", callback)
    assert replay.value.code == "no_pending_attempt"
    assert service.status("bob-id")["status"] == "not_connected"


def test_a_new_attempt_invalidates_the_previous_state(service, fake):
    first = service.start_authorization("alice-id")
    old_state = _query(first.authorization_url)["state"]
    service.start_authorization("alice-id")
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.complete_authorization(
            "alice-id", f"{first.redirect_uri}?code=c&state={old_state}&client_id={ISSUED}"
        )
    assert exc.value.code == "state_mismatch"


@pytest.mark.parametrize(
    "callback",
    [
        "http://localhost:1455/auth/callback?code=c&state=s",
        "http://127.0.0.1:1456/auth/callback?code=c&state=s",
        "http://127.0.0.1:1455/callback?code=c&state=s",
        "https://127.0.0.1:1455/auth/callback?code=c&state=s",
        "not a url",
    ],
)
def test_only_the_exact_redirect_uri_is_accepted(service, fake, callback):
    service.start_authorization("alice-id")
    with pytest.raises(ChatGPTConnectionError):
        service.complete_authorization("alice-id", callback)
    assert not fake.requests


def test_a_registration_without_an_issued_client_id_is_incomplete(service, fake):
    started = service.start_authorization("alice-id")
    state = _query(started.authorization_url)["state"]
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.complete_authorization("alice-id", f"{started.redirect_uri}?code=c&state={state}")
    assert exc.value.code == "registration_incomplete"
    assert not fake.requests


def test_declined_consent_stops_without_exchanging(service, fake):
    started = service.start_authorization("alice-id")
    state = _query(started.authorization_url)["state"]
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.complete_authorization(
            "alice-id", f"{started.redirect_uri}?error=access_denied&state={state}"
        )
    assert exc.value.code == "access_denied"
    assert not fake.requests


@pytest.mark.parametrize("problem", ["nonce", "audience", "signature", "issuer"])
def test_an_invalid_id_token_stores_nothing(service, fake, problem):
    started = service.start_authorization("alice-id")
    state = _query(started.authorization_url)["state"]
    fake.pending_nonce = "other-nonce" if problem == "nonce" else _nonce_of(service, "alice-id")
    if problem == "audience":
        fake.audience = "oaiapp_someone_else"
    if problem == "signature":
        fake.key = OTHER_KEY
    if problem == "issuer":
        fake.issuer = "https://issuer.invalid"
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.complete_authorization(
            "alice-id", f"{started.redirect_uri}?code=c&state={state}&client_id={ISSUED}"
        )
    assert exc.value.code == "invalid_id_token"
    assert service.status("alice-id")["status"] == "not_connected"


def test_without_the_plan_scope_the_sign_in_is_kept_but_not_used(service, fake):
    fake.scope = "openid profile email offline_access resource.invoke"
    _connect(service, fake)
    status = service.status("alice-id")
    assert status["status"] == "plan_disabled"
    assert status["plan_usage_enabled"] is False
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.access_token("alice-id")
    assert exc.value.code == "plan_disabled"
    # Asking again requests the full scope with consent and the issued client.
    query = _query(service.start_authorization("alice-id", enable_plan=True).authorization_url)
    assert query["client_id"] == ISSUED
    assert query["prompt"] == "consent"
    assert "chatgpt.tokens.use.direct" in query["scope"].split()


def test_reauthorization_reuses_the_client_and_rejects_another_account(service, fake):
    _connect(service, fake)
    service.disconnect("alice-id")
    started = service.start_authorization("alice-id")
    query = _query(started.authorization_url)
    assert query["client_id"] == ISSUED
    assert "agent_name_hint" not in query
    assert query["login_hint"] == "alice@example.com"

    fake.pending_nonce = _nonce_of(service, "alice-id")
    fake.subject = "someone-else"
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.complete_authorization(
            "alice-id", f"{started.redirect_uri}?code=c&state={query['state']}"
        )
    assert exc.value.code == "account_mismatch"
    assert service.status("alice-id")["status"] == "signed_out"

    # A callback naming another client is rejected rather than adopted.
    started = service.start_authorization("alice-id")
    state = _query(started.authorization_url)["state"]
    with pytest.raises(ChatGPTConnectionError) as mismatch:
        service.complete_authorization(
            "alice-id", f"{started.redirect_uri}?code=c&state={state}&client_id=oaiapp_other"
        )
    assert mismatch.value.code == "client_mismatch"


def test_adding_a_different_account_requires_signing_out_first(service, fake):
    _connect(service, fake)
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.start_authorization("alice-id", new_account=True)
    assert exc.value.status == 409


def _expire(user_id: str) -> None:
    ChatGPTConnectionDocument.get_motor_collection().update_one(
        {"user_id": user_id}, {"$set": {"access_expires_at": time.time() + 60}}
    )


def test_an_expiring_token_is_refreshed_with_the_issued_client(service, fake):
    _connect(service, fake)
    _expire("alice-id")
    token = service.access_token("alice-id")
    [refresh] = fake.requests_to(oauth.TOKEN_URL, "refresh_token")
    assert refresh == {
        "grant_type": "refresh_token",
        "client_id": ISSUED,
        "refresh_token": "refresh-1",
        "resource": oauth.RESOURCE,
    }
    assert token == "access-2"  # noqa: S105
    assert service.access_token("alice-id") == "access-2"
    _expire("alice-id")
    assert service.access_token("alice-id") == "access-3"
    assert fake.requests_to(oauth.TOKEN_URL, "refresh_token")[-1]["refresh_token"] == "refresh-2"  # noqa: S105


class _Serialized:
    """mongomock is not thread-safe; MongoDB applies each operation atomically."""

    def __init__(self, collection: Any) -> None:
        self._collection = collection
        self._lock = threading.Lock()

    def __getattr__(self, name: str) -> Any:
        method = getattr(self._collection, name)

        def call(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                return method(*args, **kwargs)

        return call


def test_concurrent_requests_refresh_a_rotating_token_once(service, fake, monkeypatch):
    _connect(service, fake)
    _expire("alice-id")
    serialized = _Serialized(ChatGPTConnectionDocument.get_motor_collection())
    monkeypatch.setattr(service, "_connections", lambda: serialized)
    results: list[str] = []
    errors: list[Exception] = []

    def use() -> None:
        try:
            results.append(service.access_token("alice-id"))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=use) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(fake.requests_to(oauth.TOKEN_URL, "refresh_token")) == 1
    assert set(results) == {"access-2"}


@pytest.mark.parametrize("code", sorted(oauth.TERMINAL_REFRESH_ERRORS))
def test_an_unusable_refresh_token_requires_signing_in_again(service, fake, code):
    _connect(service, fake)
    _expire("alice-id")
    fake.refresh_response = (400, {"error": code})
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.access_token("alice-id")
    assert exc.value.code == "reauth_required"
    raw = _raw("alice-id")
    assert raw["encrypted_tokens"] is None
    assert raw["client_id"] == ISSUED
    assert service.status("alice-id")["status"] == "reauth_required"


@pytest.mark.parametrize("code", sorted(oauth.RFC6749_REFRESH_REJECTIONS))
def test_an_rfc6749_rejection_keeps_the_credentials(service, fake, code):
    _connect(service, fake)
    _expire("alice-id")
    fake.refresh_response = (400, {"error": code, "error_description": "rejected"})
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.access_token("alice-id")
    assert exc.value.code == code
    raw = _raw("alice-id")
    assert raw["encrypted_tokens"]
    assert (raw["refresh_owner"], raw["refresh_exchange_started"]) == (None, False)
    fake.refresh_response = None
    assert service.access_token("alice-id") == "access-2"


def test_disconnect_revokes_and_clears_but_keeps_the_registration(service, fake):
    _connect(service, fake)
    host = _raw("alice-id")["host_id"]
    result = service.disconnect("alice-id")
    assert result.revocation_confirmed is True
    [revoke] = fake.requests_to(oauth.REVOCATION_URL)
    assert revoke == {
        "token": "refresh-1",
        "token_type_hint": "refresh_token",
        "client_id": ISSUED,
    }
    raw = _raw("alice-id")
    assert raw["encrypted_tokens"] is None
    assert (raw["client_id"], raw["host_id"]) == (ISSUED, host)
    status = service.status("alice-id")
    assert status["status"] == "signed_out" and status["can_reconnect"] is True
    with pytest.raises(ChatGPTConnectionError):
        service.access_token("alice-id")


def test_unconfirmed_revocation_is_reported_after_clearing(service, fake):
    _connect(service, fake)
    fake.revoke_status = 500
    result = service.disconnect("alice-id")
    assert result.revocation_confirmed is False
    assert len(fake.requests_to(oauth.REVOCATION_URL)) == 3
    assert service.status("alice-id")["status"] == "signed_out"


def test_signing_out_during_a_refresh_discards_the_new_tokens(service, fake):
    _connect(service, fake)
    _expire("alice-id")
    fake.on_refresh = lambda: service._connections().update_one(
        {"user_id": "alice-id"},
        {"$set": {"encrypted_tokens": None, "status": "signed_out"}, "$inc": {"token_version": 1}},
    )
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.access_token("alice-id")
    assert exc.value.code == "not_connected"
    # The replacement session OpenAI issued is revoked, not stored.
    assert fake.requests_to(oauth.REVOCATION_URL)[-1]["token"] == "refresh-2"  # noqa: S105
    raw = _raw("alice-id")
    assert raw["encrypted_tokens"] is None


def test_users_never_see_each_others_connections(service, fake):
    _connect(service, fake, "alice-id")
    fake.subject = "bob-sub"
    fake.audience = "oaiapp_bob"
    _connect(service, fake, "bob-id", issued="oaiapp_bob")
    alice = service.access_token("alice-id")
    bob = service.access_token("bob-id")
    assert alice != bob
    service.disconnect("bob-id")
    assert service.access_token("alice-id") == alice
    docs = list(ChatGPTConnectionDocument.get_motor_collection().find({}))
    assert len({doc["host_id"] for doc in docs}) == 2


def test_without_an_encryption_key_nothing_is_stored(service, fake, monkeypatch):
    monkeypatch.delenv("QDASH_CREDENTIAL_KEY")
    monkeypatch.delenv("QDASH_CREDENTIAL_KEY_FILE", raising=False)
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.start_authorization("alice-id")
    assert exc.value.code == "not_configured"
    assert service.status("alice-id")["available"] is False


def test_a_rotated_away_key_requires_signing_in_again(service, fake, monkeypatch):
    _connect(service, fake)
    monkeypatch.setenv("QDASH_CREDENTIAL_KEY", Fernet.generate_key().decode())
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.access_token("alice-id")
    assert exc.value.code == "reauth_required"
    assert service.status("alice-id")["status"] == "reauth_required"


# -- authorization generations: starts, callbacks and disconnects racing ------


def _start(service, fake, user_id: str = "alice-id", **start: Any) -> str:
    """Start an attempt and return the callback URL its browser would land on."""
    started = service.start_authorization(user_id, **start)
    query = _query(started.authorization_url)
    fake.pending_nonce = _nonce_of(service, user_id)
    callback = f"{started.redirect_uri}?code=code-x&state={query['state']}"
    if query["client_id"] == oauth.DYNAMIC_CLIENT_ID:
        callback += f"&client_id={ISSUED}"
    return callback


def _stored_refresh_token(user_id: str) -> str:
    from qdash.api.lib import credential_cipher

    return str(
        json.loads(credential_cipher.decrypt(_raw(user_id)["encrypted_tokens"]))["refresh_token"]
    )


def test_disconnecting_during_a_callback_discards_its_tokens(service, fake):
    callback = _start(service, fake)
    fake.on_exchange = lambda: service.disconnect("alice-id")
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.complete_authorization("alice-id", callback)
    assert exc.value.code == "superseded"
    raw = _raw("alice-id")
    assert raw["encrypted_tokens"] is None
    assert service.status("alice-id")["status"] == "not_connected"
    # The session OpenAI issued for the stale callback is revoked, not stored.
    assert fake.requests_to(oauth.REVOCATION_URL)[-1]["token"] == "refresh-1"  # noqa: S105


def test_a_newer_start_during_a_callback_keeps_the_stored_tokens(service, fake):
    _connect(service, fake)
    stale = _start(service, fake)
    newer: list[str] = []
    fake.on_exchange = lambda: newer.append(_start(service, fake))
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.complete_authorization("alice-id", stale)
    assert exc.value.code == "superseded"
    # The existing connection is untouched and the stale session is revoked.
    assert _stored_refresh_token("alice-id") == "refresh-1"
    assert service.access_token("alice-id") == "access-1"
    assert fake.requests_to(oauth.REVOCATION_URL)[-1]["token"] == "refresh-2"  # noqa: S105

    fake.on_exchange = None
    service.complete_authorization("alice-id", newer[0])
    assert service.access_token("alice-id") == "access-3"


def test_a_superseded_attempt_is_rejected_before_exchanging(service, fake):
    stale = _start(service, fake)
    service.disconnect("alice-id")
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.complete_authorization("alice-id", stale)
    assert exc.value.code == "no_pending_attempt"
    assert not fake.requests_to(oauth.TOKEN_URL)


def test_a_slower_start_never_deletes_a_newer_attempt(service, fake):
    service.start_authorization("alice-id")
    newer = {
        "user_id": "alice-id",
        "state_hash": "newer",
        "encrypted_secrets": "x",
        "client_id": oauth.DYNAMIC_CLIENT_ID,
        "registration": True,
        "redirect_uri": oauth.redirect_uri(),
        "host_id": "urn:uuid:x",
        "generation": 99,
        "expires_epoch": time.time() + 600,
    }
    service._attempts().insert_one(newer)
    service.start_authorization("alice-id")
    hashes = {a["state_hash"] for a in service._attempts().find({"user_id": "alice-id"})}
    assert "newer" in hashes
    assert len(hashes) == 2


def test_simultaneous_callbacks_exchange_the_code_once(service, fake, monkeypatch):
    callback = _start(service, fake)
    connections = _Serialized(ChatGPTConnectionDocument.get_motor_collection())
    attempts = _Serialized(service._attempts())
    monkeypatch.setattr(service, "_connections", lambda: connections)
    monkeypatch.setattr(service, "_attempts", lambda: attempts)
    codes: list[str] = []

    def complete() -> None:
        try:
            service.complete_authorization("alice-id", callback)
            codes.append("ok")
        except ChatGPTConnectionError as exc:
            codes.append(exc.code)

    threads = [threading.Thread(target=complete) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert codes.count("ok") == 1
    assert len(fake.requests_to(oauth.TOKEN_URL, "authorization_code")) == 1
    assert service.access_token("alice-id") == "access-1"


def test_another_account_on_reauthorization_keeps_the_connection(service, fake):
    _connect(service, fake)
    callback = _start(service, fake)
    fake.subject = "someone-else"
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.complete_authorization("alice-id", callback)
    assert exc.value.code == "account_mismatch"
    assert service.access_token("alice-id") == "access-1"
    assert fake.requests_to(oauth.REVOCATION_URL)[-1]["token"] == "refresh-2"  # noqa: S105


# -- refreshed ID tokens -------------------------------------------------------


def test_a_refresh_without_an_id_token_keeps_the_original(service, fake):
    _connect(service, fake)
    from qdash.api.lib import credential_cipher

    before = json.loads(credential_cipher.decrypt(_raw("alice-id")["encrypted_tokens"]))
    _expire("alice-id")
    assert service.access_token("alice-id") == "access-2"
    after = json.loads(credential_cipher.decrypt(_raw("alice-id")["encrypted_tokens"]))
    assert after["id_token"] == before["id_token"]


@pytest.mark.parametrize("nonce", ["absent", "original"])
def test_a_valid_refreshed_id_token_is_stored(service, fake, nonce):
    _connect(service, fake)
    original = fake.pending_nonce
    fake.refresh_id_token = lambda: fake.id_token(original if nonce == "original" else None)
    _expire("alice-id")
    assert service.access_token("alice-id") == "access-2"
    raw = _raw("alice-id")
    assert raw["subject"] == "user-sub-1"
    assert raw["status"] == "connected"


@pytest.mark.parametrize(
    "problem", ["subject", "signature", "audience", "issuer", "nonce", "workspace"]
)
def test_a_refreshed_id_token_cannot_change_the_account(service, fake, problem):
    _connect(service, fake)
    cases: dict[str, dict[str, Any]] = {
        "subject": {"sub": "someone-else"},
        "signature": {"key": OTHER_KEY},
        "audience": {"aud": ["oaiapp_other"]},
        "issuer": {"iss": "https://issuer.invalid"},
        "nonce": {"nonce": "another-nonce"},
        "workspace": {oauth.ACCOUNT_CLAIM: {"chatgpt_account_id": "workspace-2"}},
    }
    overrides = dict(cases[problem])
    nonce = overrides.pop("nonce", None)
    fake.refresh_id_token = lambda: fake.id_token(nonce, **overrides)
    _expire("alice-id")
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.access_token("alice-id")
    assert exc.value.code == "reauth_required"
    raw = _raw("alice-id")
    assert raw["encrypted_tokens"] is None
    assert (raw["subject"], raw["client_id"]) == ("user-sub-1", ISSUED)
    assert raw["refresh_owner"] is None
    # The rotated session OpenAI issued is revoked, not kept.
    assert fake.requests_to(oauth.REVOCATION_URL)[-1]["token"] == "refresh-2"  # noqa: S105


class _UnreachableJwks(StaticJwks):
    def get_signing_keys(self) -> Any:
        raise jwt.PyJWKClientConnectionError("down")


def test_unreachable_keys_stop_the_refresh_before_rotating(fake):
    client = oauth.OpenAIAccountsClient(
        http=httpx.Client(transport=httpx.MockTransport(fake.handler)),
        jwks=StaticJwks(),
        sleep=lambda _s: None,
    )
    service = ChatGPTConnectionService(client=client, sleep=lambda _s: None)
    _connect(service, fake)
    client._jwks = _UnreachableJwks()
    _expire("alice-id")
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.access_token("alice-id")
    assert exc.value.code == "temporarily_unavailable"
    assert not fake.requests_to(oauth.TOKEN_URL, "refresh_token")
    assert _stored_refresh_token("alice-id") == "refresh-1"
    assert _raw("alice-id")["refresh_lock_until"] == 0.0


# -- one refresh token is sent at most once ------------------------------------


class FakeClock:
    """Service time that only moves when a test or the service's wait moves it."""

    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def timed(fake, clock) -> ChatGPTConnectionService:
    """A service whose clock and waits are driven by ``clock``."""
    client = oauth.OpenAIAccountsClient(
        http=httpx.Client(transport=httpx.MockTransport(fake.handler)),
        jwks=StaticJwks(),
        sleep=lambda _s: None,
    )
    return ChatGPTConnectionService(client=client, clock=clock, sleep=clock.advance)


def _refreshes(fake) -> list[str]:
    """The refresh tokens sent to OpenAI's token endpoint, in order."""
    return [form["refresh_token"] for form in fake.requests_to(oauth.TOKEN_URL, "refresh_token")]


def _revoked(fake) -> list[str]:
    return [form["token"] for form in fake.requests_to(oauth.REVOCATION_URL)]


def _assert_retired(user_id: str = "alice-id") -> None:
    raw = _raw(user_id)
    assert raw["encrypted_tokens"] is None
    assert raw["status"] == "reauth_required"
    assert raw["client_id"] == ISSUED
    assert (raw["refresh_owner"], raw["refresh_exchange_started"]) == (None, False)


def test_a_response_slower_than_the_lease_never_lets_another_worker_resend(timed, fake, clock):
    _connect(timed, fake)
    _expire("alice-id")
    other: list[ChatGPTConnectionError] = []

    def lease_expires_while_in_flight() -> None:
        # Another request arrives after the whole lease elapsed; the first
        # request has not returned, so nothing proves it ended.
        clock.advance(REFRESH_LEASE_SECONDS + 1)
        with pytest.raises(ChatGPTConnectionError) as exc:
            timed.access_token("alice-id")
        other.append(exc.value)

    fake.on_refresh = lease_expires_while_in_flight
    with pytest.raises(ChatGPTConnectionError) as late:
        timed.access_token("alice-id")
    assert [error.code for error in other] == ["reauth_required"]
    # The late successful result does not resurrect the retired session.
    assert late.value.code == "reauth_required"
    assert _refreshes(fake) == ["refresh-1"]
    _assert_retired()
    assert _raw("alice-id")["last_error_code"] == "refresh_outcome_unknown"
    # The retired token and the late session OpenAI issued are both revoked.
    assert _revoked(fake) == ["refresh-1", "refresh-2"]
    with pytest.raises(ChatGPTConnectionError):
        timed.access_token("alice-id")
    assert _refreshes(fake) == ["refresh-1"]


def test_a_waiter_during_an_exchange_in_flight_waits_and_never_sends(timed, fake, clock):
    _connect(timed, fake)
    _expire("alice-id")
    waited: list[ChatGPTConnectionError] = []

    def another_request_waits() -> None:
        with pytest.raises(ChatGPTConnectionError) as exc:
            timed.access_token("alice-id")
        waited.append(exc.value)

    fake.on_refresh = another_request_waits
    assert timed.access_token("alice-id") == "access-2"
    # The waiter gave up within the lease and left the exchange to its holder.
    assert [error.code for error in waited] == ["temporarily_unavailable"]
    assert _refreshes(fake) == ["refresh-1"]
    fake.on_refresh = None
    assert timed.access_token("alice-id") == "access-2"
    assert _stored_refresh_token("alice-id") == "refresh-2"


def _leave_exchange(user_id: str, owner: str, *, started: bool, lock_until: float) -> None:
    """Leave the record as a worker that stopped at that point would."""
    ChatGPTConnectionDocument.get_motor_collection().update_one(
        {"user_id": user_id},
        {
            "$set": {
                "refresh_owner": owner,
                "refresh_exchange_started": started,
                "refresh_lock_until": lock_until,
            }
        },
    )


def test_a_worker_that_crashed_after_sending_is_never_retried(timed, fake, clock):
    _connect(timed, fake)
    _expire("alice-id")
    _leave_exchange("alice-id", "crashed-worker", started=True, lock_until=clock.now + 60)
    # While its lease runs, other requests wait for it and send nothing.
    with pytest.raises(ChatGPTConnectionError) as waiting:
        timed.access_token("alice-id")
    assert waiting.value.code == "temporarily_unavailable"
    assert _raw("alice-id")["refresh_owner"] == "crashed-worker"
    clock.advance(60)
    with pytest.raises(ChatGPTConnectionError) as retired:
        timed.access_token("alice-id")
    assert retired.value.code == "reauth_required"
    assert not _refreshes(fake)
    _assert_retired()
    assert _revoked(fake) == ["refresh-1"]


def test_a_worker_that_stalled_before_sending_can_be_taken_over(timed, fake, clock):
    _connect(timed, fake)
    _expire("alice-id")
    _leave_exchange("alice-id", "stalled-worker", started=False, lock_until=clock.now - 1)
    assert timed.access_token("alice-id") == "access-2"
    assert _refreshes(fake) == ["refresh-1"]


def test_a_holder_that_lost_its_lease_before_sending_sends_nothing(timed, fake, clock):
    _connect(timed, fake)
    _expire("alice-id")

    def taken_over_while_loading_keys() -> None:
        _leave_exchange("alice-id", "newer-worker", started=True, lock_until=clock.now + 60)

    timed.client.warm_signing_keys = taken_over_while_loading_keys
    with pytest.raises(ChatGPTConnectionError) as exc:
        timed.access_token("alice-id")
    assert exc.value.code == "temporarily_unavailable"
    assert not _refreshes(fake)
    raw = _raw("alice-id")
    assert (raw["refresh_owner"], raw["refresh_exchange_started"]) == ("newer-worker", True)
    assert _stored_refresh_token("alice-id") == "refresh-1"


@pytest.mark.parametrize(
    "outcome",
    [
        {"refresh_raise": httpx.ReadTimeout("no response")},
        {"refresh_raise": httpx.RemoteProtocolError("connection dropped")},
        {"refresh_response": (500, {"error": "server_error"})},
        {"refresh_response": (502, {"detail": "bad gateway"})},
        {"refresh_response": (503, {"detail": "unavailable"})},
        {"refresh_response": (503, {"error": "temporarily_unavailable"})},
        {"refresh_response": (504, {"detail": "gateway timeout"})},
        {"refresh_raw": (500, b"<html>proxy error</html>")},
        {"refresh_response": (429, {"error": "rate_limited"})},
        {"refresh_raw": (403, b"forbidden by proxy")},
        {"refresh_response": (400, {"error": {"code": "invalid_request"}})},
        {"refresh_raw": (200, b"not json")},
        {"refresh_response": (200, {"access_token": "partial"})},
    ],
    ids=[
        "read-timeout",
        "dropped",
        "500",
        "502",
        "503",
        "503-oauth-body",
        "504",
        "500-html",
        "429",
        "403-unstructured",
        "400-not-rfc6749",
        "200-not-json",
        "200-incomplete",
    ],
)
def test_an_unknown_refresh_outcome_retires_the_session(timed, fake, outcome):
    _connect(timed, fake)
    _expire("alice-id")
    for name, value in outcome.items():
        setattr(fake, name, value)
    with pytest.raises(ChatGPTConnectionError) as exc:
        timed.access_token("alice-id")
    assert exc.value.code == "reauth_required"
    _assert_retired()
    assert _raw("alice-id")["last_error_code"] == "refresh_outcome_unknown"
    for name in outcome:
        setattr(fake, name, None)
    with pytest.raises(ChatGPTConnectionError) as again:
        timed.access_token("alice-id")
    assert again.value.code == "reauth_required"
    assert _refreshes(fake) == ["refresh-1"]
    assert _revoked(fake) == ["refresh-1"]


@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ConnectTimeout("no route")])
def test_a_refresh_that_never_reached_openai_keeps_the_credentials(timed, fake, error):
    _connect(timed, fake)
    _expire("alice-id")
    fake.refresh_raise = error
    with pytest.raises(ChatGPTConnectionError) as exc:
        timed.access_token("alice-id")
    assert exc.value.code == "temporarily_unavailable"
    raw = _raw("alice-id")
    assert raw["encrypted_tokens"]
    assert (raw["refresh_owner"], raw["refresh_exchange_started"]) == (None, False)
    fake.refresh_raise = None
    # The mock records the attempt, but httpx raises these before sending a request.
    assert timed.access_token("alice-id") == "access-2"
    assert _refreshes(fake) == ["refresh-1", "refresh-1"]


def test_a_late_refresh_never_disturbs_a_new_sign_in(timed, fake, clock):
    _connect(timed, fake)
    _expire("alice-id")

    def retired_and_signed_in_again() -> None:
        clock.advance(REFRESH_LEASE_SECONDS + 1)
        with pytest.raises(ChatGPTConnectionError):
            timed.access_token("alice-id")
        fake.on_refresh = None
        _connect(timed, fake)

    fake.on_refresh = retired_and_signed_in_again
    # The late response is dropped and the request uses the new sign-in.
    assert timed.access_token("alice-id") == "access-2"
    raw = _raw("alice-id")
    assert raw["status"] == "connected"
    assert _stored_refresh_token("alice-id") == "refresh-2"
    assert _refreshes(fake) == ["refresh-1"]
    assert _revoked(fake) == ["refresh-1", "refresh-3"]


@pytest.mark.parametrize("status", [500, 503])
def test_a_server_error_after_a_new_sign_in_leaves_it_untouched(timed, fake, status):
    _connect(timed, fake)
    _expire("alice-id")

    def signed_in_again() -> None:
        fake.on_refresh = None
        timed.disconnect("alice-id")
        _connect(timed, fake)

    fake.on_refresh = signed_in_again
    fake.refresh_response = (status, {"detail": "unavailable"})
    with pytest.raises(ChatGPTConnectionError) as exc:
        timed.access_token("alice-id")
    assert exc.value.code == "reauth_required"
    raw = _raw("alice-id")
    assert raw["status"] == "connected"
    assert raw["last_error_code"] is None
    assert (raw["refresh_owner"], raw["refresh_exchange_started"]) == (None, False)
    assert _stored_refresh_token("alice-id") == "refresh-2"
    fake.refresh_response = None
    assert timed.access_token("alice-id") == "access-2"
    # Only the old, possibly rotated token was sent and then revoked.
    assert _refreshes(fake) == ["refresh-1"]
    assert "refresh-2" not in _revoked(fake)


def test_stale_cleanup_never_touches_a_newer_token_set(timed, fake, clock):
    _connect(timed, fake)
    _leave_exchange("alice-id", "crashed-worker", started=True, lock_until=clock.now - 1)
    stale = _raw("alice-id")
    # The user signed in again after the stale worker's state was observed.
    _connect(timed, fake)
    timed._retire_unfinished_exchange("alice-id", stale, clock.now)
    raw = _raw("alice-id")
    assert raw["status"] == "connected"
    assert _stored_refresh_token("alice-id") == "refresh-2"
    assert not _revoked(fake)


def test_concurrent_refreshes_after_an_unknown_outcome_never_resend(fake, monkeypatch):
    client = oauth.OpenAIAccountsClient(
        http=httpx.Client(transport=httpx.MockTransport(fake.handler)),
        jwks=StaticJwks(),
        sleep=lambda _s: None,
    )
    service = ChatGPTConnectionService(client=client, sleep=lambda _s: time.sleep(0.01))
    _connect(service, fake)
    _expire("alice-id")
    serialized = _Serialized(ChatGPTConnectionDocument.get_motor_collection())
    monkeypatch.setattr(service, "_connections", lambda: serialized)
    fake.refresh_raise = httpx.ReadTimeout("no response")
    codes: list[str] = []

    def use() -> None:
        try:
            service.access_token("alice-id")
        except ChatGPTConnectionError as exc:
            codes.append(exc.code)

    threads = [threading.Thread(target=use) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert _refreshes(fake) == ["refresh-1"]
    assert codes == ["reauth_required"] * 5
    _assert_retired()


def test_a_late_model_list_never_overwrites_a_new_connections_catalog(timed, fake):
    _connect(timed, fake)
    new_catalog = [{"slug": "gpt-7", "display_name": "GPT-7", "visibility": "list"}]

    def reconnected_meanwhile() -> None:
        fake.on_models = None
        timed.disconnect("alice-id")
        fake.models = new_catalog
        _connect(timed, fake)

    fake.on_models = reconnected_meanwhile
    old = timed.list_models("alice-id")
    assert old == [{"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol"}]
    assert timed.cached_models("alice-id") == [{"slug": "gpt-7", "display_name": "GPT-7"}]


def test_an_attempt_from_an_older_generation_never_exchanges(service, fake):
    callback = _start(service, fake)
    # A concurrent start claimed a newer generation but has not replaced the attempt yet.
    service._connections().update_one({"user_id": "alice-id"}, {"$inc": {"auth_generation": 1}})
    with pytest.raises(ChatGPTConnectionError) as exc:
        service.complete_authorization("alice-id", callback)
    assert exc.value.code == "superseded"
    assert not fake.requests_to(oauth.TOKEN_URL)


def test_a_turns_status_writes_apply_only_to_its_own_token_set(service, fake):
    _connect(service, fake)
    turn = service.turn_token("alice-id")
    assert turn.access_token == "access-1"  # noqa: S105
    assert "access-1" not in repr(turn)
    service.record_inference_error("alice-id", turn.token_version, "usage_limit_reached", "x")
    assert _raw("alice-id")["last_error_code"] == "usage_limit_reached"
    service.clear_inference_error("alice-id", turn.token_version)
    assert _raw("alice-id")["last_error_code"] is None


@pytest.mark.parametrize("change", ["refresh", "new-session"])
def test_a_stale_turn_never_records_or_clears_a_newer_token_sets_error(service, fake, change):
    _connect(service, fake)
    old = service.turn_token("alice-id")
    if change == "refresh":
        _expire("alice-id")
        new = service.turn_token("alice-id")
    else:
        service.disconnect("alice-id")
        _connect(service, fake)
        new = service.turn_token("alice-id")
    assert new.token_version != old.token_version

    # A stale failure leaves the newer token set without an error.
    service.record_inference_error("alice-id", old.token_version, "usage_limit_reached", "old")
    assert _raw("alice-id")["last_error_code"] is None

    # A stale success leaves the newer token set's own error in place.
    service.record_inference_error("alice-id", new.token_version, "usage_limit_reached", "new")
    service.clear_inference_error("alice-id", old.token_version)
    raw = _raw("alice-id")
    assert (raw["last_error_code"], raw["last_error_message"]) == ("usage_limit_reached", "new")
    service.clear_inference_error("alice-id", new.token_version)
    assert _raw("alice-id")["last_error_code"] is None
