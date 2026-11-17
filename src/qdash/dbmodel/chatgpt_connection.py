"""Documents for per-user Sign in with ChatGPT connections used by Copilot chat.

A connection belongs to exactly one QDash user, keyed by the immutable internal
``user_id``. OAuth tokens are stored only as a ciphertext produced by
``qdash.api.lib.credential_cipher``; no plaintext token field exists.
"""

from datetime import datetime
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.common.utils.datetime import now


class ChatGPTConnectionDocument(Document):
    """One QDash user's ChatGPT registration, host identity and encrypted tokens."""

    user_id: str = Field(description="Internal QDash user ID that owns this connection")
    host_id: str = Field(
        description="Stable opaque ext_agent_host_id (urn:uuid) for this user's QDash agent host",
    )
    client_id: str | None = Field(
        default=None,
        description="Issued OAuth client ID from dynamic registration; kept after sign-out",
    )
    issuer: str | None = Field(default=None, description="Validated ID token issuer")
    subject: str | None = Field(default=None, description="Validated ID token subject")
    email: str | None = Field(default=None, description="Email claim, for display and login_hint")
    scopes: list[str] = Field(default_factory=list, description="Granted OAuth scopes")
    status: str = Field(
        default="signed_out",
        description="connected, plan_disabled, reauth_required or signed_out",
    )
    encrypted_tokens: str | None = Field(
        default=None,
        description="Encrypted access, refresh and ID tokens; never stored in plaintext",
    )
    access_expires_at: float | None = Field(
        default=None,
        description="Access-token expiry as Unix seconds",
    )
    saved_at: datetime | None = Field(default=None)
    token_version: int = Field(
        default=0,
        description="Incremented whenever the token set changes; guards refresh and sign-out races",
    )
    refresh_lock_until: float = Field(
        default=0.0,
        description="Unix-seconds lease that serializes refreshes across API workers",
    )
    refresh_owner: str | None = Field(
        default=None,
        description="Random ID of the worker holding the refresh lease; fences its writes",
    )
    refresh_exchange_started: bool = Field(
        default=False,
        description=(
            "Set by the lease holder before it sends the refresh token; no other worker "
            "may send that token, and an expired lease in this state retires the session"
        ),
    )
    auth_generation: int = Field(
        default=0,
        description=(
            "Incremented by each sign-in start and by sign-out; only the newest attempt "
            "may store tokens"
        ),
    )
    models: list[dict[str, str]] = Field(
        default_factory=list,
        description="Last model catalog listed for this account: slug and display_name",
    )
    last_error_code: str | None = Field(default=None)
    last_error_message: str | None = Field(default=None)
    last_error_at: datetime | None = Field(default=None)
    welcome_pending: bool = Field(
        default=False,
        description="Show the one-time 'You're using your ChatGPT plan' confirmation",
    )
    welcome_shown: bool = Field(default=False)
    connected_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo metadata."""

        name = "chatgpt_connection"
        indexes: ClassVar = [
            IndexModel([("user_id", ASCENDING)], unique=True, name="user_id_unique_idx"),
        ]


class ChatGPTAuthorizationAttemptDocument(Document):
    """A pending authorization, consumed once by the callback of the same QDash user."""

    user_id: str = Field(description="Internal QDash user ID that started the attempt")
    state_hash: str = Field(description="SHA-256 of the OAuth state; the state itself is not kept")
    encrypted_secrets: str = Field(description="Encrypted PKCE verifier and OIDC nonce")
    client_id: str = Field(description="dynamic_agent_client or the issued client ID")
    registration: bool = Field(description="True for a new dynamic registration")
    redirect_uri: str = Field(description="Exact loopback redirect URI sent in the request")
    host_id: str = Field(description="ext_agent_host_id sent in the request")
    expected_subject: str | None = Field(
        default=None,
        description="Subject that a reauthorization must return",
    )
    generation: int = Field(
        description="auth_generation of the connection when the attempt started",
    )
    created_at: datetime = Field(default_factory=now)
    expires_at: datetime = Field(description="TTL index anchor; Mongo removes stale attempts")
    expires_epoch: float = Field(description="Unix seconds after which the attempt is rejected")

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo metadata."""

        name = "chatgpt_authorization_attempt"
        indexes: ClassVar = [
            IndexModel(
                [("user_id", ASCENDING), ("state_hash", ASCENDING)],
                unique=True,
                name="user_state_unique_idx",
            ),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="expires_ttl_idx"),
        ]
