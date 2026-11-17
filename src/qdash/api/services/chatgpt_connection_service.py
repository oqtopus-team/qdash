"""Per-user ChatGPT plan connections for Copilot chat.

Each QDash user connects their own ChatGPT account with Sign in with ChatGPT
(see ``qdash.api.lib.chatgpt_oauth``). The connection is keyed by the
authenticated user's internal ``user_id``; callers pass that ID from the
verified QDash session, never from the browser.

QDash runs on a server, so the documented ``127.0.0.1`` callback reaches the
user's own computer rather than QDash. The user copies the address their
browser landed on back into Settings; the server, which alone holds the PKCE
verifier and nonce, validates the state against the same user's pending
attempt, consumes the attempt once, and exchanges the code.

Tokens are stored encrypted (``credential_cipher``) and never leave the server
except as the per-turn bearer the chat runtime sends to OpenAI.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pymongo import ReturnDocument

from qdash.api.lib import chatgpt_oauth as oauth
from qdash.api.lib import credential_cipher
from qdash.dbmodel.chatgpt_connection import (
    ChatGPTAuthorizationAttemptDocument,
    ChatGPTConnectionDocument,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

ATTEMPT_TTL_SECONDS = 10 * 60
# Hand the runtime a token that outlives a long chat turn.
ACCESS_TOKEN_MARGIN_SECONDS = 10 * 60
# The refresh lease. Before the refresh token is sent, an expired lease may be
# taken over. Once the holder has recorded that it is sending the token, no
# other worker sends it again: an expired lease in that state retires the
# session, because only OpenAI knows whether the token was rotated.
REFRESH_LEASE_SECONDS = 60
REFRESH_WAIT_SECONDS = 25.0
REFRESH_POLL_SECONDS = 0.25
OUTCOME_UNKNOWN = "refresh_outcome_unknown"
OUTCOME_UNKNOWN_MESSAGE = (
    "QDash could not confirm a ChatGPT token refresh, so it ended the session; connect again"
)
# Resets every refresh-lease field.
_NO_LEASE: dict[str, Any] = {
    "refresh_lock_until": 0.0,
    "refresh_owner": None,
    "refresh_exchange_started": False,
}

STATUS_CONNECTED = "connected"
STATUS_PLAN_DISABLED = "plan_disabled"
STATUS_REAUTH_REQUIRED = "reauth_required"
STATUS_SIGNED_OUT = "signed_out"
STATUS_NOT_CONNECTED = "not_connected"


class ChatGPTConnectionError(Exception):
    """A user-facing failure with a stable code and an HTTP status for the API."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class AuthorizationStart:
    authorization_url: str
    redirect_uri: str
    expires_at: datetime


@dataclass(frozen=True)
class PlanTurnToken:
    """A turn's access token and the ``token_version`` of the token set it came from."""

    access_token: str = field(repr=False)
    token_version: int


@dataclass(frozen=True)
class DisconnectResult:
    revocation_confirmed: bool


def _now_dt(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, tz=UTC)


def _superseded() -> ChatGPTConnectionError:
    return ChatGPTConnectionError(
        "superseded",
        "A newer sign-in or a disconnect replaced this attempt; start again from Settings",
        409,
    )


class ChatGPTConnectionService:
    """Connect, refresh, use and disconnect one QDash user's ChatGPT plan."""

    def __init__(
        self,
        client: oauth.OpenAIAccountsClient | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._clock = clock
        self._sleep = sleep

    @property
    def client(self) -> oauth.OpenAIAccountsClient:
        if self._client is None:
            self._client = oauth.OpenAIAccountsClient()
        return self._client

    # -- storage helpers ---------------------------------------------------

    @staticmethod
    def _connections() -> Any:
        return ChatGPTConnectionDocument.get_motor_collection()

    @staticmethod
    def _attempts() -> Any:
        return ChatGPTAuthorizationAttemptDocument.get_motor_collection()

    def _find(self, user_id: str) -> dict[str, Any] | None:
        doc: dict[str, Any] | None = self._connections().find_one({"user_id": user_id})
        return doc

    def _ensure(self, user_id: str) -> dict[str, Any]:
        """The user's record, created with a fresh host ID before the first sign-in."""
        existing = self._find(user_id)
        if existing is not None:
            return existing
        record = ChatGPTConnectionDocument(user_id=user_id, host_id=oauth.new_host_id())
        data = record.model_dump(exclude={"id", "revision_id"})
        # Upsert so two first sign-ins of one user agree on a single host ID.
        self._connections().update_one({"user_id": user_id}, {"$setOnInsert": data}, upsert=True)
        stored = self._find(user_id)
        assert stored is not None
        return stored

    @staticmethod
    def _require_cipher() -> None:
        if not credential_cipher.cipher_available():
            raise ChatGPTConnectionError(
                "not_configured",
                "ChatGPT connections are not configured on this QDash server",
                503,
            )

    def _set_error(
        self, user_id: str, code: str, message: str, *, version: int | None = None, **fields: Any
    ) -> None:
        """Record a failure; with ``version``, only on that token set."""
        query: dict[str, Any] = {"user_id": user_id}
        if version is not None:
            query["token_version"] = version
        self._connections().update_one(
            query,
            {
                "$set": {
                    "last_error_code": code,
                    "last_error_message": message[:300],
                    "last_error_at": _now_dt(self._clock()),
                    "updated_at": _now_dt(self._clock()),
                    **fields,
                }
            },
        )

    # -- status ------------------------------------------------------------

    def status(self, user_id: str) -> dict[str, Any]:
        """What Settings shows; never includes tokens."""
        doc = self._find(user_id)
        available = credential_cipher.cipher_available()
        if doc is None:
            return {
                "available": available,
                "status": STATUS_NOT_CONNECTED,
                "can_reconnect": False,
                "plan_usage_enabled": False,
                "welcome_pending": False,
                "email": None,
                "connected_at": None,
                "last_error": None,
                "models": [],
            }
        status = doc.get("status") or STATUS_SIGNED_OUT
        has_tokens = bool(doc.get("encrypted_tokens"))
        if not has_tokens and status in (STATUS_CONNECTED, STATUS_PLAN_DISABLED):
            status = STATUS_REAUTH_REQUIRED
        last_error = (
            {
                "code": doc.get("last_error_code"),
                "message": doc.get("last_error_message") or "",
                "at": doc.get("last_error_at"),
            }
            if doc.get("last_error_code")
            else None
        )
        return {
            "available": available,
            "status": status if doc.get("client_id") else STATUS_NOT_CONNECTED,
            "can_reconnect": bool(doc.get("client_id")),
            "plan_usage_enabled": status == STATUS_CONNECTED,
            "welcome_pending": bool(doc.get("welcome_pending")) and status == STATUS_CONNECTED,
            "email": doc.get("email"),
            "connected_at": doc.get("connected_at"),
            "last_error": last_error,
            "models": list(doc.get("models") or []) if status == STATUS_CONNECTED else [],
        }

    # -- authorization -----------------------------------------------------

    def start_authorization(
        self, user_id: str, *, new_account: bool = False, enable_plan: bool = False
    ) -> AuthorizationStart:
        """Create a pending attempt bound to this user and return the authorize URL.

        A saved registration is reauthorized with its issued client ID. A new
        registration uses ``dynamic_agent_client``; it is refused while the
        current registration still holds tokens, so one registration's tokens
        are never replaced by another's without a sign-out.
        """
        self._require_cipher()
        self._ensure(user_id)
        # Claim a new generation atomically: every older attempt, including one
        # whose callback is already exchanging its code, can no longer store tokens.
        doc = self._connections().find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"auth_generation": 1}},
            return_document=ReturnDocument.AFTER,
        )
        assert doc is not None
        generation = int(doc["auth_generation"])
        registered = bool(doc.get("client_id"))
        if new_account and doc.get("encrypted_tokens"):
            raise ChatGPTConnectionError(
                "connected",
                "Disconnect the current ChatGPT account before adding a different one",
                409,
            )
        registration = new_account or not registered
        client_id = oauth.DYNAMIC_CLIENT_ID if registration else str(doc["client_id"])
        state = oauth.random_value()
        nonce = oauth.random_value()
        verifier = oauth.random_value()
        redirect = oauth.redirect_uri()
        now = self._clock()
        # One pending attempt per user: starting again invalidates the previous
        # one. Only older generations are deleted, so a slower concurrent start
        # never deletes the newer attempt.
        self._attempts().delete_many(
            {
                "user_id": user_id,
                "$or": [
                    {"generation": {"$lt": generation}},
                    {"generation": {"$exists": False}},
                ],
            }
        )
        attempt = ChatGPTAuthorizationAttemptDocument(
            user_id=user_id,
            state_hash=oauth.state_hash(state),
            encrypted_secrets=credential_cipher.encrypt(
                json.dumps({"verifier": verifier, "nonce": nonce})
            ),
            client_id=client_id,
            registration=registration,
            redirect_uri=redirect,
            host_id=str(doc["host_id"]),
            expected_subject=None if registration else doc.get("subject"),
            generation=generation,
            expires_at=_now_dt(now + ATTEMPT_TTL_SECONDS),
            expires_epoch=now + ATTEMPT_TTL_SECONDS,
        )
        self._attempts().insert_one(attempt.model_dump(exclude={"id", "revision_id"}))
        url = oauth.authorization_url(
            client_id=client_id,
            host_id=str(doc["host_id"]),
            redirect=redirect,
            state=state,
            nonce=nonce,
            verifier=verifier,
            login_hint=None if registration else doc.get("email"),
            force_consent=enable_plan and not registration,
        )
        return AuthorizationStart(
            authorization_url=url,
            redirect_uri=redirect,
            expires_at=_now_dt(now + ATTEMPT_TTL_SECONDS),
        )

    def complete_authorization(self, user_id: str, callback_url: str) -> dict[str, Any]:
        """Validate the pasted redirect, exchange the code, validate identity and store."""
        self._require_cipher()
        # The redirect URI is fixed per deployment; parse against any of this user's attempts.
        pending = self._attempts().find_one({"user_id": user_id})
        if pending is None:
            raise ChatGPTConnectionError(
                "no_pending_attempt", "Start the connection again from Settings", 400
            )
        try:
            callback = oauth.parse_callback(callback_url, str(pending["redirect_uri"]))
        except oauth.OAuthError as exc:
            raise ChatGPTConnectionError(exc.code, str(exc), 400) from exc
        # Consume the attempt once, and only when the state belongs to this user.
        attempt = self._attempts().find_one_and_delete(
            {"user_id": user_id, "state_hash": oauth.state_hash(callback.state)}
        )
        if attempt is None or float(attempt["expires_epoch"]) < self._clock():
            raise ChatGPTConnectionError(
                "state_mismatch",
                "This sign-in attempt expired, was already used or belongs to another session",
                400,
            )
        generation = attempt.get("generation")
        if not isinstance(generation, int) or not self._is_current(user_id, generation):
            raise _superseded()
        if callback.error:
            if callback.error == "access_denied":
                raise ChatGPTConnectionError(
                    "access_denied",
                    "ChatGPT was not connected because access was declined",
                    400,
                )
            raise ChatGPTConnectionError(
                "authorization_failed", f"ChatGPT authorization failed: {callback.error}", 400
            )
        if not callback.code:
            raise ChatGPTConnectionError("invalid_callback", "The address has no code", 400)
        client_id = str(attempt["client_id"])
        if attempt["registration"]:
            issued = callback.client_id
            if not issued or issued == oauth.DYNAMIC_CLIENT_ID:
                raise ChatGPTConnectionError(
                    "registration_incomplete",
                    "ChatGPT did not return an issued client ID; start again",
                    400,
                )
            client_id = issued
        elif callback.client_id and callback.client_id != client_id:
            raise ChatGPTConnectionError(
                "client_mismatch", "ChatGPT returned a different client registration", 400
            )
        secrets_ = json.loads(credential_cipher.decrypt(str(attempt["encrypted_secrets"])))
        try:
            tokens = self.client.exchange_code(
                client_id=client_id,
                code=callback.code,
                verifier=secrets_["verifier"],
                redirect=str(attempt["redirect_uri"]),
            )
        except oauth.TemporaryOAuthError as exc:
            raise ChatGPTConnectionError(
                "temporarily_unavailable", "OpenAI could not be reached; try again", 503
            ) from exc
        except oauth.OAuthError as exc:
            if exc.code == "invalid_grant":
                raise ChatGPTConnectionError(
                    "invalid_grant", "The sign-in code was rejected; start again", 400
                ) from exc
            raise ChatGPTConnectionError(exc.code, f"Token exchange failed: {exc}", 400) from exc
        assert tokens.id_token is not None
        try:
            claims = self.client.verify_id_token(
                tokens.id_token, client_id=client_id, nonce=secrets_["nonce"]
            )
        except oauth.OAuthError as exc:
            self._discard(client_id, tokens)
            raise ChatGPTConnectionError(exc.code, str(exc), 400) from exc
        expected = attempt.get("expected_subject")
        if expected and claims["sub"] != expected:
            # Never put another account's tokens on this registration.
            self._discard(client_id, tokens)
            raise ChatGPTConnectionError(
                "account_mismatch",
                "You signed in with a different ChatGPT account than this connection uses",
                400,
            )
        if not self._store_new_tokens(user_id, generation, client_id, claims, tokens):
            # A newer sign-in or a sign-out happened while this code was being
            # exchanged: keep whatever is stored now and drop this session.
            self._discard(client_id, tokens)
            raise _superseded()
        self._refresh_models_best_effort(user_id)
        return self.status(user_id)

    def _is_current(self, user_id: str, generation: int) -> bool:
        doc = self._find(user_id)
        return doc is not None and int(doc.get("auth_generation") or 0) == generation

    def _discard(self, client_id: str, tokens: oauth.TokenSet) -> None:
        """Revoke a freshly issued session that QDash will not store."""
        if not self.client.revoke(client_id=client_id, refresh_token=tokens.refresh_token):
            logger.warning("An unused ChatGPT session could not be revoked")

    def _store_new_tokens(
        self,
        user_id: str,
        generation: int,
        client_id: str,
        claims: dict[str, Any],
        tokens: oauth.TokenSet,
    ) -> bool:
        """Store a sign-in's tokens if its attempt is still the newest; True when stored."""
        now = self._clock()
        plan = tokens.plan_usage_granted
        current = self._find(user_id) or {}
        welcome_shown = bool(current.get("welcome_shown")) and current.get("client_id") == client_id
        result = self._connections().update_one(
            {"user_id": user_id, "auth_generation": generation},
            {
                "$set": {
                    "client_id": client_id,
                    "issuer": claims.get("iss"),
                    "subject": claims["sub"],
                    "email": claims.get("email") if isinstance(claims.get("email"), str) else None,
                    "scopes": list(tokens.scopes),
                    "status": STATUS_CONNECTED if plan else STATUS_PLAN_DISABLED,
                    "encrypted_tokens": self._encrypt_tokens(tokens, None),
                    "access_expires_at": now + tokens.expires_in,
                    "saved_at": _now_dt(now),
                    **_NO_LEASE,
                    "models": [],
                    "last_error_code": None if plan else "plan_not_enabled",
                    "last_error_message": None
                    if plan
                    else "ChatGPT plan usage was not granted. Enable it to use your plan.",
                    "last_error_at": None if plan else _now_dt(now),
                    "welcome_pending": plan and not welcome_shown,
                    "welcome_shown": welcome_shown,
                    "connected_at": _now_dt(now),
                    "updated_at": _now_dt(now),
                },
                "$inc": {"token_version": 1},
            },
        )
        return bool(result.matched_count == 1)

    @staticmethod
    def _encrypt_tokens(tokens: oauth.TokenSet, previous_id_token: str | None) -> str:
        return credential_cipher.encrypt(
            json.dumps(
                {
                    "access_token": tokens.access_token,
                    "refresh_token": tokens.refresh_token,
                    "id_token": tokens.id_token or previous_id_token,
                }
            )
        )

    def _decrypt_tokens(self, user_id: str, doc: dict[str, Any]) -> dict[str, str]:
        try:
            data: dict[str, str] = json.loads(
                credential_cipher.decrypt(str(doc["encrypted_tokens"]))
            )
        except credential_cipher.CredentialDecryptError as exc:
            # Fenced on the token version: never erase a newer token set.
            self._connections().update_one(
                {"user_id": user_id, "token_version": int(doc.get("token_version") or 0)},
                {
                    "$set": {
                        "status": STATUS_REAUTH_REQUIRED,
                        "encrypted_tokens": None,
                        "last_error_code": "credentials_unreadable",
                        "last_error_message": (
                            "Stored ChatGPT credentials cannot be read; connect again"
                        ),
                        "last_error_at": _now_dt(self._clock()),
                        "updated_at": _now_dt(self._clock()),
                    },
                    "$inc": {"token_version": 1},
                },
            )
            raise ChatGPTConnectionError(
                STATUS_REAUTH_REQUIRED, "Connect ChatGPT again in Settings", 409
            ) from exc
        return data

    def acknowledge_welcome(self, user_id: str) -> None:
        self._connections().update_one(
            {"user_id": user_id},
            {"$set": {"welcome_pending": False, "welcome_shown": True}},
        )

    # -- token use ---------------------------------------------------------

    def access_token(self, user_id: str) -> str:
        """A valid access token for this user's plan, refreshed when close to expiry.

        Raises ``ChatGPTConnectionError`` instead of returning anything else:
        there is no fallback to another credential or another user.
        """
        token, _version = self._access_token(user_id)
        return token

    def turn_token(self, user_id: str) -> PlanTurnToken:
        """The access token for one chat turn with the ``token_version`` it belongs to.

        Both come from the same read or refresh, so the version identifies the
        exact token set the turn uses; later writes about the turn are fenced on it.
        """
        token, version = self._access_token(user_id)
        return PlanTurnToken(access_token=token, token_version=version)

    def _access_token(self, user_id: str) -> tuple[str, int]:
        """The access token and the ``token_version`` of the token set it belongs to."""
        self._require_cipher()
        doc = self._find(user_id)
        if doc is None or not doc.get("client_id"):
            raise ChatGPTConnectionError(
                STATUS_NOT_CONNECTED, "Connect your ChatGPT account in Settings first", 409
            )
        status = doc.get("status")
        if status == STATUS_PLAN_DISABLED:
            raise ChatGPTConnectionError(
                STATUS_PLAN_DISABLED,
                "ChatGPT plan usage is not enabled for this connection; enable it in Settings",
                409,
            )
        if status != STATUS_CONNECTED or not doc.get("encrypted_tokens"):
            raise ChatGPTConnectionError(
                STATUS_REAUTH_REQUIRED, "Connect ChatGPT again in Settings", 409
            )
        tokens = self._decrypt_tokens(user_id, doc)
        version = int(doc.get("token_version") or 0)
        expires = float(doc.get("access_expires_at") or 0)
        if expires - self._clock() > ACCESS_TOKEN_MARGIN_SECONDS:
            return tokens["access_token"], version
        return self._refresh(user_id, version)

    def _refresh(self, user_id: str, version: int) -> tuple[str, int]:
        """Refresh under an owned lease so one refresh token is sent at most once.

        A lease can be taken when it is free, or when it expired before its
        holder recorded ``refresh_exchange_started``. After that point the
        token is never sent again: a waiter that finds the lease expired with
        the exchange started retires the session instead of retrying it.
        """
        deadline = self._clock() + REFRESH_WAIT_SECONDS
        while True:
            now = self._clock()
            owner = uuid.uuid4().hex
            leased = self._connections().find_one_and_update(
                {
                    "user_id": user_id,
                    "token_version": version,
                    "refresh_lock_until": {"$lt": now},
                    "refresh_exchange_started": {"$ne": True},
                },
                {
                    "$set": {
                        "refresh_lock_until": now + REFRESH_LEASE_SECONDS,
                        "refresh_owner": owner,
                        "refresh_exchange_started": False,
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
            if leased is not None:
                return self._refresh_leased(user_id, leased, version, owner)
            current = self._find(user_id)
            if current is None or int(current.get("token_version") or 0) != version:
                # Another worker refreshed or retired the session, or the user
                # signed out or in again, meanwhile.
                return self._access_token(user_id)
            if current.get("refresh_exchange_started") and (
                float(current.get("refresh_lock_until") or 0) < now
            ):
                # The holder sent the token but never finished: it crashed or
                # its request outlived the lease. Its outcome is unknown.
                self._retire_unfinished_exchange(user_id, current, now)
                continue
            if now >= deadline:
                raise ChatGPTConnectionError(
                    "temporarily_unavailable", "ChatGPT token refresh is taking too long", 503
                )
            self._sleep(REFRESH_POLL_SECONDS)

    @staticmethod
    def _lease_filter(user_id: str, version: int, owner: str) -> dict[str, Any]:
        return {"user_id": user_id, "token_version": version, "refresh_owner": owner}

    def _release(self, user_id: str, version: int, owner: str) -> None:
        """Free the lease when the refresh token was not spent; fenced on the owner."""
        self._connections().update_one(
            self._lease_filter(user_id, version, owner), {"$set": dict(_NO_LEASE)}
        )

    def _start_exchange(self, user_id: str, version: int, owner: str) -> bool:
        """Record, before sending, that the refresh token is about to be sent.

        True only while this worker still owns the lease; after that, no other
        worker can take the lease over until the session is retired.
        """
        result = self._connections().update_one(
            {**self._lease_filter(user_id, version, owner), "refresh_exchange_started": False},
            {
                "$set": {
                    "refresh_exchange_started": True,
                    "refresh_lock_until": self._clock() + REFRESH_LEASE_SECONDS,
                }
            },
        )
        return bool(result.modified_count == 1)

    def _session_ended(self, code: str, message: str) -> dict[str, Any]:
        """The update that clears an unusable token set and keeps the registration."""
        now = _now_dt(self._clock())
        return {
            "$set": {
                "encrypted_tokens": None,
                "status": STATUS_REAUTH_REQUIRED,
                "access_expires_at": None,
                **_NO_LEASE,
                "models": [],
                "welcome_pending": False,
                "last_error_code": code,
                "last_error_message": message,
                "last_error_at": now,
                "updated_at": now,
            },
            "$inc": {"token_version": 1},
        }

    def _end_session(self, user_id: str, version: int, owner: str, code: str, message: str) -> None:
        """Clear an unusable token set while still owning the lease."""
        self._connections().update_one(
            self._lease_filter(user_id, version, owner), self._session_ended(code, message)
        )

    def _retire_unfinished_exchange(self, user_id: str, doc: dict[str, Any], now: float) -> None:
        """Retire a session whose refresh was sent by a holder that never finished.

        Fenced on the observed version, owner, started flag and expired lease,
        so a newer sign-in, a sign-out or a live holder is never touched.
        """
        retired = self._connections().find_one_and_update(
            {
                "user_id": user_id,
                "token_version": int(doc.get("token_version") or 0),
                "refresh_owner": doc.get("refresh_owner"),
                "refresh_exchange_started": True,
                "refresh_lock_until": {"$lt": now},
            },
            self._session_ended(OUTCOME_UNKNOWN, OUTCOME_UNKNOWN_MESSAGE),
            return_document=ReturnDocument.BEFORE,
        )
        if retired is not None:
            logger.warning("Retired a ChatGPT session whose token refresh never finished")
            self._revoke_stored(retired)

    def _revoke_stored(self, doc: dict[str, Any]) -> None:
        """Best-effort revocation of a retired token set's refresh token.

        Revocation is not a token exchange: it ends whichever session the token
        still belongs to and never yields new tokens.
        """
        try:
            tokens = json.loads(credential_cipher.decrypt(str(doc["encrypted_tokens"])))
        except (
            KeyError,
            ValueError,
            credential_cipher.CredentialDecryptError,
            credential_cipher.CredentialCipherUnavailableError,
        ):
            return
        if not self.client.revoke(
            client_id=str(doc["client_id"]), refresh_token=tokens["refresh_token"], attempts=1
        ):
            logger.warning("A retired ChatGPT session could not be revoked")

    def _outcome_unknown(
        self, user_id: str, version: int, owner: str, doc: dict[str, Any]
    ) -> ChatGPTConnectionError:
        """Retire the session after a refresh whose result QDash cannot know."""
        self._end_session(user_id, version, owner, OUTCOME_UNKNOWN, OUTCOME_UNKNOWN_MESSAGE)
        self._revoke_stored(doc)
        return ChatGPTConnectionError(STATUS_REAUTH_REQUIRED, OUTCOME_UNKNOWN_MESSAGE, 409)

    def _refresh_leased(
        self, user_id: str, doc: dict[str, Any], version: int, owner: str
    ) -> tuple[str, int]:
        """Send the refresh token once and settle the lease from the outcome.

        The call is synchronous and bounded only by the HTTP client's
        per-operation timeouts. Safety does not depend on its duration: after
        ``_start_exchange`` no other worker sends this token, and a result that
        arrives after the session was retired fails the fenced commit.
        """
        tokens = self._decrypt_tokens(user_id, doc)
        client_id = str(doc["client_id"])
        try:
            # Load the signing keys while the current refresh token is still unused.
            self.client.warm_signing_keys()
        except oauth.TemporaryOAuthError as exc:
            self._release(user_id, version, owner)
            raise ChatGPTConnectionError(
                "temporarily_unavailable", "OpenAI could not be reached; try again", 503
            ) from exc
        if not self._start_exchange(user_id, version, owner):
            # The lease expired before sending and another worker, a sign-out
            # or a new sign-in took over; this worker sends nothing.
            return self._after_lost_lease(user_id, version)
        try:
            fresh = self.client.refresh(client_id=client_id, refresh_token=tokens["refresh_token"])
        except oauth.RequestNotSentError as exc:
            self._release(user_id, version, owner)
            raise ChatGPTConnectionError(
                "temporarily_unavailable", "OpenAI could not be reached; try again", 503
            ) from exc
        except oauth.TemporaryOAuthError as exc:
            # Sent, then any 5xx or a broken connection. A proxy or gateway can
            # answer with any 5xx after OpenAI rotated the token, and nothing
            # documents that OpenAI's own 5xx leaves it unspent: never resend it.
            raise self._outcome_unknown(user_id, version, owner, doc) from exc
        except oauth.OAuthError as exc:
            if exc.code in oauth.TERMINAL_REFRESH_ERRORS or exc.code == "invalid_client":
                # Unusable refresh token: clear the tokens, keep the registration.
                self._end_session(
                    user_id, version, owner, exc.code, "The ChatGPT session ended; connect again"
                )
                raise ChatGPTConnectionError(
                    STATUS_REAUTH_REQUIRED, "The ChatGPT session ended; connect again", 409
                ) from exc
            if exc.rfc6749 and exc.code in oauth.RFC6749_REFRESH_REJECTIONS:
                # An RFC 6749 error response: the server rejected the request and,
                # per RFC 6749 section 6, issued nothing, so the token is unspent.
                self._release(user_id, version, owner)
                raise ChatGPTConnectionError(exc.code, f"Token refresh failed: {exc}", 502) from exc
            # An unreadable HTTP 200 body, or any other answer QDash cannot prove
            # came before rotation (for example 429 or a proxy's 403): retire.
            raise self._outcome_unknown(user_id, version, owner, doc) from exc
        except Exception as exc:
            raise self._outcome_unknown(user_id, version, owner, doc) from exc
        id_token = tokens.get("id_token")
        if fresh.id_token is not None:
            # The account bound to this connection never changes on refresh.
            try:
                self.client.verify_refreshed_id_token(
                    fresh.id_token,
                    client_id=client_id,
                    subject=str(doc.get("subject") or ""),
                    original_id_token=id_token,
                )
            except oauth.OAuthError as exc:
                # The old refresh token is spent and the new identity cannot be
                # trusted: drop both and ask the user to connect again.
                self._end_session(
                    user_id,
                    version,
                    owner,
                    exc.code,
                    "ChatGPT returned an unexpected identity; connect again",
                )
                self._discard(client_id, fresh)
                raise ChatGPTConnectionError(
                    STATUS_REAUTH_REQUIRED,
                    "ChatGPT returned an unexpected identity; connect again",
                    409,
                ) from exc
            id_token = fresh.id_token
        now = self._clock()
        plan = fresh.plan_usage_granted
        result = self._connections().update_one(
            {**self._lease_filter(user_id, version, owner), "refresh_exchange_started": True},
            {
                "$set": {
                    "encrypted_tokens": self._encrypt_tokens(fresh, id_token),
                    "scopes": list(fresh.scopes),
                    "status": STATUS_CONNECTED if plan else STATUS_PLAN_DISABLED,
                    "access_expires_at": now + fresh.expires_in,
                    "saved_at": _now_dt(now),
                    **_NO_LEASE,
                    "updated_at": _now_dt(now),
                },
                "$inc": {"token_version": 1},
            },
        )
        if result.modified_count != 1:
            # The session was retired, replaced or signed out while the request
            # ran: never store this result, and end the session OpenAI issued.
            self._discard(client_id, fresh)
            return self._after_lost_lease(user_id, version)
        if not plan:
            raise ChatGPTConnectionError(
                STATUS_PLAN_DISABLED, "ChatGPT plan usage is no longer granted", 409
            )
        return fresh.access_token, version + 1

    def _after_lost_lease(self, user_id: str, version: int) -> tuple[str, int]:
        """What a worker that no longer owns the lease answers with."""
        current = self._find(user_id) or {}
        if not current.get("encrypted_tokens"):
            if current.get("status") == STATUS_REAUTH_REQUIRED:
                raise ChatGPTConnectionError(
                    STATUS_REAUTH_REQUIRED,
                    str(current.get("last_error_message") or "Connect ChatGPT again in Settings"),
                    409,
                )
            raise ChatGPTConnectionError(STATUS_NOT_CONNECTED, "ChatGPT was disconnected", 409)
        if int(current.get("token_version") or 0) != version:
            # A newer token set of this user is stored; use it.
            return self._access_token(user_id)
        raise ChatGPTConnectionError(
            "temporarily_unavailable", "ChatGPT token refresh was superseded; try again", 503
        )

    # -- models and errors -------------------------------------------------

    def list_models(self, user_id: str) -> list[dict[str, str]]:
        """Fetch the account's current model catalog and cache it for that token set.

        The cache write is fenced on the ``token_version`` the access token
        belongs to, so a response for a signed-out or replaced session never
        overwrites the catalog of the connection stored now.
        """
        token, version = self._access_token(user_id)
        try:
            models = self.client.list_models(token)
        except oauth.TemporaryOAuthError as exc:
            raise ChatGPTConnectionError(
                "temporarily_unavailable", "OpenAI could not be reached; try again", 503
            ) from exc
        except oauth.OAuthError as exc:
            self._set_error(user_id, exc.code, str(exc), version=version)
            raise ChatGPTConnectionError(exc.code, f"Model list failed: {exc}", 502) from exc
        self._connections().update_one(
            {"user_id": user_id, "token_version": version}, {"$set": {"models": models}}
        )
        return models

    def _refresh_models_best_effort(self, user_id: str) -> None:
        try:
            self.list_models(user_id)
        except ChatGPTConnectionError as exc:
            logger.info("ChatGPT model list unavailable after sign-in: %s", exc.code)

    def cached_models(self, user_id: str) -> list[dict[str, str]]:
        doc = self._find(user_id)
        return list(doc.get("models") or []) if doc else []

    def record_inference_error(
        self, user_id: str, token_version: int, code: str, message: str
    ) -> None:
        """Remember a plan-usage failure so Settings can explain it.

        ``token_version`` is the one returned with the turn's access token. The
        write applies only while that token set is stored, so a turn that ends
        after a sign-out, a new sign-in or a refresh never touches the newer one.
        """
        self._set_error(user_id, code, message, version=token_version)

    def clear_inference_error(self, user_id: str, token_version: int) -> None:
        """Clear an earlier failure after a turn succeeded on that same token set."""
        self._connections().update_one(
            {"user_id": user_id, "token_version": token_version, "status": STATUS_CONNECTED},
            {"$set": {"last_error_code": None, "last_error_message": None, "last_error_at": None}},
        )

    # -- sign-out ----------------------------------------------------------

    def disconnect(self, user_id: str) -> DisconnectResult:
        """Stop using the tokens, revoke the renewable session and clear them.

        The registration (client ID, account identity, host ID) is kept so a
        later sign-in reuses it.
        """
        before = self._connections().find_one_and_update(
            {"user_id": user_id},
            {
                "$set": {
                    "encrypted_tokens": None,
                    "status": STATUS_SIGNED_OUT,
                    "access_expires_at": None,
                    **_NO_LEASE,
                    "models": [],
                    "welcome_pending": False,
                    "last_error_code": None,
                    "last_error_message": None,
                    "last_error_at": None,
                    "updated_at": _now_dt(self._clock()),
                },
                # Invalidate pending attempts, including callbacks already in flight.
                "$inc": {"token_version": 1, "auth_generation": 1},
            },
            return_document=ReturnDocument.BEFORE,
        )
        self._attempts().delete_many({"user_id": user_id})
        if before is None or not before.get("encrypted_tokens"):
            return DisconnectResult(revocation_confirmed=True)
        try:
            tokens = json.loads(credential_cipher.decrypt(str(before["encrypted_tokens"])))
        except (
            credential_cipher.CredentialDecryptError,
            credential_cipher.CredentialCipherUnavailableError,
        ):
            return DisconnectResult(revocation_confirmed=False)
        confirmed = self.client.revoke(
            client_id=str(before["client_id"]), refresh_token=tokens["refresh_token"]
        )
        if not confirmed:
            logger.warning("ChatGPT session revocation was not confirmed for a QDash user")
        return DisconnectResult(revocation_confirmed=confirmed)
