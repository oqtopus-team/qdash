"""Sign in with ChatGPT protocol pieces for ChatGPT plan usage.

Follows OpenAI's documentation for open-source apps
(https://developers.openai.com/siwc/token-sharing-open-source): dynamic
registration through ``dynamic_agent_client``, a stable ``ext_agent_host_id``,
PKCE and nonce per attempt, an ``http://127.0.0.1:<port>/auth/callback``
redirect, ID-token validation against OpenAI's JWKS, and the plan-usage scope
``chatgpt.tokens.use.direct``. The endpoints match OpenAI's discovery document
at https://auth.openai.com/.well-known/openid-configuration.

Nothing here stores or logs tokens; callers own persistence.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt

ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = f"{ISSUER}/api/accounts/authorize"
TOKEN_URL = f"{ISSUER}/api/accounts/oauth/token"
REVOCATION_URL = f"{ISSUER}/api/accounts/oauth/revoke"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
MODELS_URL = f"{RESOURCE}/models"
USAGE_URL = "https://chatgpt.com/settings/usage"

DYNAMIC_CLIENT_ID = "dynamic_agent_client"
AGENT_NAME_HINT = "QDash"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = ("openid", "profile", "email", "offline_access", "resource.invoke", PLAN_SCOPE)
CALLBACK_HOST = "127.0.0.1"
CALLBACK_PATH = "/auth/callback"
DEFAULT_CALLBACK_PORT = 1455
CALLBACK_PORT_ENV = "QDASH_CHATGPT_CALLBACK_PORT"

# Refresh codes that mean the refresh token can no longer be used.
TERMINAL_REFRESH_ERRORS = frozenset(
    {
        "invalid_grant",
        "invalid_refresh_token",
        "token_expired",
        "refresh_token_expired",
        "refresh_token_invalidated",
        "refresh_token_reused",
    }
)

HTTP_TIMEOUT = httpx.Timeout(15.0, connect=10.0)
ID_TOKEN_LEEWAY_SECONDS = 5


class OAuthError(Exception):
    """An OAuth or account-API failure with OpenAI's machine-readable code when given."""

    def __init__(
        self, code: str, message: str, status: int | None = None, *, rfc6749: bool = False
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        # True only for an RFC 6749 section 5.2 error body: a string ``error`` member.
        self.rfc6749 = rfc6749


class TemporaryOAuthError(OAuthError):
    """A network failure or server error; credentials stay as they are."""


class RequestNotSentError(TemporaryOAuthError):
    """No connection to OpenAI was made, so OpenAI never received the request."""


# RFC 6749 section 5.2 error codes, other than the terminal ones above, with which the
# authorization server rejects a refresh request. Section 6 issues tokens only for a valid
# request, so this rejection is the one post-send answer that leaves the token unspent.
RFC6749_REFRESH_REJECTIONS = frozenset(
    {"invalid_request", "unauthorized_client", "unsupported_grant_type", "invalid_scope"}
)
RFC6749_ERROR_STATUSES = frozenset({400, 401})


@dataclass(frozen=True)
class TokenSet:
    """A token-endpoint response. Secrets are excluded from repr."""

    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    id_token: str | None = field(repr=False)
    expires_in: int
    scopes: tuple[str, ...]

    @property
    def plan_usage_granted(self) -> bool:
        return PLAN_SCOPE in self.scopes


@dataclass(frozen=True)
class CallbackResult:
    """The query of the loopback redirect the user's browser landed on."""

    state: str
    code: str | None
    client_id: str | None
    error: str | None


def random_value() -> str:
    """A fresh 256-bit URL-safe random value for state, nonce or PKCE verifier."""
    return secrets.token_urlsafe(32)


def pkce_challenge(verifier: str) -> str:
    """S256 code challenge: base64url SHA-256 of the verifier without padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def state_hash(state: str) -> str:
    """The stored form of an OAuth state."""
    return hashlib.sha256(state.encode()).hexdigest()


def new_host_id() -> str:
    """A UUIDv4 host ID in the documented ``urn:uuid:`` form."""
    return f"urn:uuid:{uuid.uuid4()}"


def callback_port() -> int:
    """Loopback port in the redirect URI; only the port may vary between sign-ins."""
    raw = os.environ.get(CALLBACK_PORT_ENV, "").strip()
    if not raw:
        return DEFAULT_CALLBACK_PORT
    port = int(raw)
    if not 1024 <= port <= 65535:
        msg = f"{CALLBACK_PORT_ENV} must be between 1024 and 65535"
        raise ValueError(msg)
    return port


def redirect_uri(port: int | None = None) -> str:
    """The exact loopback redirect URI for one attempt."""
    return f"http://{CALLBACK_HOST}:{port or callback_port()}{CALLBACK_PATH}"


def authorization_url(
    *,
    client_id: str,
    host_id: str,
    redirect: str,
    state: str,
    nonce: str,
    verifier: str,
    login_hint: str | None = None,
    force_consent: bool = False,
) -> str:
    """Build the authorize URL for a new registration or a reauthorization.

    ``agent_name_hint`` is sent only with ``dynamic_agent_client``. QDash does
    not send ``id_token_hint``: the URL travels through the user's browser and
    QDash keeps ID tokens server-side only.
    """
    params: dict[str, str] = {
        "client_id": client_id,
        "ext_agent_host_id": host_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": " ".join(SCOPES),
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": pkce_challenge(verifier),
    }
    if client_id == DYNAMIC_CLIENT_ID:
        params["agent_name_hint"] = AGENT_NAME_HINT
    elif login_hint:
        params["login_hint"] = login_hint
    if force_consent:
        # Documented way to ask again for plan usage after a decline.
        params["prompt"] = "consent"
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def parse_callback(url: str, expected_redirect: str) -> CallbackResult:
    """Parse the pasted redirect URL; it must be the attempt's exact redirect URI."""
    try:
        parts = urlsplit(url.strip())
        expected = urlsplit(expected_redirect)
        port = parts.port
    except ValueError as exc:
        raise OAuthError("invalid_callback", "Paste the full address from the browser") from exc
    if (parts.scheme, parts.hostname, port, parts.path) != (
        expected.scheme,
        expected.hostname,
        expected.port,
        expected.path,
    ):
        raise OAuthError(
            "invalid_callback",
            f"The address must start with {expected_redirect}",
        )
    query = parse_qs(parts.query, keep_blank_values=False)

    def single(name: str) -> str | None:
        values = query.get(name)
        if not values:
            return None
        if len(values) != 1:
            raise OAuthError("invalid_callback", f"The address repeats {name}")
        return values[0].strip() or None

    state = single("state")
    if not state:
        raise OAuthError("invalid_callback", "The address has no state")
    return CallbackResult(
        state=state,
        code=single("code"),
        client_id=single("client_id"),
        error=single("error"),
    )


class JwksResolver(Protocol):
    """Resolves the signing key of a JWT; ``jwt.PyJWKClient`` satisfies it."""

    def get_signing_key_from_jwt(self, token: str) -> Any: ...


def _error_code(response: httpx.Response) -> tuple[str, str]:
    """OpenAI's machine-readable error code and a short diagnostic, never a token."""
    code = "http_error"
    message = response.reason_phrase or f"HTTP {response.status_code}"
    try:
        body = response.json()
    except ValueError:
        return code, message
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, str):
            code = error
            description = body.get("error_description")
            if isinstance(description, str):
                message = description
        elif isinstance(error, dict):
            code = str(error.get("code") or error.get("type") or code)
            if isinstance(error.get("message"), str):
                message = error["message"]
        elif isinstance(body.get("detail"), str):
            message = body["detail"]
    return code, message[:300]


def _is_rfc6749_error(response: httpx.Response) -> bool:
    """Whether the body is an RFC 6749 section 5.2 error: JSON with a string ``error``."""
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and isinstance(body.get("error"), str)


def _token_set(body: Any, *, require_id_token: bool) -> TokenSet:
    if not isinstance(body, dict):
        raise OAuthError("invalid_token_response", "Token response is not an object")
    access = body.get("access_token")
    refresh = body.get("refresh_token")
    id_token = body.get("id_token")
    expires_in = body.get("expires_in")
    scope = body.get("scope")
    if not isinstance(access, str) or not access:
        raise OAuthError("invalid_token_response", "Token response has no access_token")
    if not isinstance(refresh, str) or not refresh:
        raise OAuthError("invalid_token_response", "Token response has no refresh_token")
    if require_id_token and (not isinstance(id_token, str) or not id_token):
        raise OAuthError("invalid_token_response", "Token response has no id_token")
    if not isinstance(expires_in, int) or isinstance(expires_in, bool) or expires_in <= 0:
        raise OAuthError("invalid_token_response", "Token response has no valid expires_in")
    if not isinstance(scope, str):
        raise OAuthError("invalid_token_response", "Token response has no scope")
    return TokenSet(
        access_token=access,
        refresh_token=refresh,
        id_token=id_token if isinstance(id_token, str) and id_token else None,
        expires_in=expires_in,
        scopes=tuple(sorted(set(scope.split()))),
    )


ACCOUNT_CLAIM = "https://api.openai.com/auth"


def _unverified_claims(token: str | None) -> dict[str, Any]:
    """Claims of an ID token that was validated when it was stored."""
    if not token:
        return {}
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return {}
    return claims if isinstance(claims, dict) else {}


def _chatgpt_account(claims: dict[str, Any]) -> str | None:
    """The ChatGPT account ID in OpenAI's auth claim, when the token carries it."""
    auth = claims.get(ACCOUNT_CLAIM)
    if not isinstance(auth, dict):
        return None
    account = auth.get("chatgpt_account_id")
    return account if isinstance(account, str) and account else None


class OpenAIAccountsClient:
    """HTTP calls to OpenAI's OAuth endpoints and model list."""

    def __init__(
        self,
        http: httpx.Client | None = None,
        jwks: JwksResolver | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        # trust_env stays on: an operator's HTTPS proxy is how this server reaches OpenAI.
        self._http = http or httpx.Client(timeout=HTTP_TIMEOUT)
        self._jwks = jwks or jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)
        self._sleep = sleep

    def _post_form(self, url: str, data: dict[str, str]) -> httpx.Response:
        try:
            response = self._http.post(url, data=data, headers={"Accept": "application/json"})
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            # Raised before any request byte reached OpenAI.
            raise RequestNotSentError("network_error", "Could not reach OpenAI") from exc
        except httpx.HTTPError as exc:
            raise TemporaryOAuthError("network_error", "Could not reach OpenAI") from exc
        if response.status_code >= 500:
            code, message = _error_code(response)
            raise TemporaryOAuthError(code, message, response.status_code)
        return response

    def exchange_code(self, *, client_id: str, code: str, verifier: str, redirect: str) -> TokenSet:
        """Exchange an authorization code with PKCE; no client secret exists."""
        response = self._post_form(
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect,
                "resource": RESOURCE,
            },
        )
        if response.status_code != httpx.codes.OK:
            code_, message = _error_code(response)
            raise OAuthError(code_, message, response.status_code)
        return _token_set(response.json(), require_id_token=True)

    def refresh(self, *, client_id: str, refresh_token: str) -> TokenSet:
        """Rotate the token set; ``scope`` is omitted to retain the grant.

        Raises ``RequestNotSentError`` when OpenAI never received the request.
        Every other failure happens after the token may have reached OpenAI:
        ``TemporaryOAuthError`` for a 5xx response or a broken connection,
        ``OAuthError`` with ``status=None`` for an unreadable HTTP 200 body, and
        ``OAuthError`` with the status for any other answer, with ``rfc6749``
        set only for an RFC 6749 error response. A 5xx can come from a proxy or
        gateway after OpenAI rotated the token, so its status proves nothing.
        """
        response = self._post_form(
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
                "resource": RESOURCE,
            },
        )
        if response.status_code != httpx.codes.OK:
            code, message = _error_code(response)
            raise OAuthError(
                code,
                message,
                response.status_code,
                rfc6749=response.status_code in RFC6749_ERROR_STATUSES
                and _is_rfc6749_error(response),
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise OAuthError("invalid_token_response", "Token response is not JSON") from exc
        return _token_set(body, require_id_token=False)

    def revoke(self, *, client_id: str, refresh_token: str, attempts: int = 3) -> bool:
        """End the renewable session; True when OpenAI confirmed with HTTP 200."""
        for attempt in range(attempts):
            try:
                response = self._http.post(
                    REVOCATION_URL,
                    data={
                        "token": refresh_token,
                        "token_type_hint": "refresh_token",
                        "client_id": client_id,
                    },
                )
            except httpx.HTTPError:
                response = None
            if response is not None and response.status_code == httpx.codes.OK:
                return True
            if response is not None and response.status_code < 500:
                return False
            if attempt + 1 < attempts:
                self._sleep(0.5 * 2**attempt)
        return False

    def verify_id_token(self, id_token: str, *, client_id: str, nonce: str) -> dict[str, Any]:
        """Validate signature, issuer, audience, expiry and nonce; return the claims."""
        try:
            key = self._jwks.get_signing_key_from_jwt(id_token)
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key=key.key if hasattr(key, "key") else key,
                algorithms=["RS256"],
                audience=client_id,
                issuer=ISSUER,
                leeway=ID_TOKEN_LEEWAY_SECONDS,
                options={"require": ["sub", "exp", "iat", "iss", "aud"]},
            )
        except (jwt.PyJWTError, ValueError) as exc:
            raise OAuthError(
                "invalid_id_token", f"ID token rejected: {type(exc).__name__}"
            ) from exc
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OAuthError("invalid_id_token", "ID token nonce does not match")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise OAuthError("invalid_id_token", "ID token has no subject")
        return claims

    def warm_signing_keys(self) -> None:
        """Load OpenAI's JWKS before a refresh rotates the token.

        A refreshed ID token must be validated before the rotated tokens are
        stored. Fetching the key set first turns an unreachable JWKS into a
        temporary failure while the current refresh token is still unused.
        """
        loader = getattr(self._jwks, "get_signing_keys", None)
        if loader is None:
            return
        try:
            loader()
        except (jwt.PyJWTError, ValueError) as exc:
            raise TemporaryOAuthError("jwks_unavailable", "Could not load OpenAI's keys") from exc

    def verify_refreshed_id_token(
        self,
        id_token: str,
        *,
        client_id: str,
        subject: str,
        original_id_token: str | None,
    ) -> dict[str, Any]:
        """Validate an ID token returned by a refresh against the original sign-in.

        Applies OpenID Connect Core 1.0 section 12.2: a valid signature from
        OpenAI's JWKS, the same issuer, audience (the issued client ID) and
        subject as the original sign-in, and no nonce unless it equals the
        original one. When the original token carried OpenAI's ChatGPT account
        claim, the refreshed token must carry the same account.
        """
        try:
            key = self._jwks.get_signing_key_from_jwt(id_token)
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key=key.key if hasattr(key, "key") else key,
                algorithms=["RS256"],
                audience=client_id,
                issuer=ISSUER,
                leeway=ID_TOKEN_LEEWAY_SECONDS,
                options={"require": ["sub", "exp", "iat", "iss", "aud"]},
            )
        except (jwt.PyJWTError, ValueError) as exc:
            raise OAuthError(
                "invalid_id_token", f"Refreshed ID token rejected: {type(exc).__name__}"
            ) from exc
        if not secrets.compare_digest(str(claims.get("sub", "")), subject):
            raise OAuthError("account_mismatch", "Refreshed ID token names another account")
        original = _unverified_claims(original_id_token)
        if "nonce" in claims:
            expected_nonce = original.get("nonce")
            if not isinstance(expected_nonce, str) or not secrets.compare_digest(
                str(claims["nonce"]), expected_nonce
            ):
                raise OAuthError("invalid_id_token", "Refreshed ID token nonce does not match")
        if "azp" in original and claims.get("azp") != original["azp"]:
            raise OAuthError("invalid_id_token", "Refreshed ID token names another client")
        original_account = _chatgpt_account(original)
        if original_account is not None and _chatgpt_account(claims) != original_account:
            raise OAuthError("account_mismatch", "Refreshed ID token names another workspace")
        return claims

    def list_models(self, access_token: str) -> list[dict[str, str]]:
        """The account's model catalog, entries meant for display, in server order."""
        try:
            response = self._http.get(
                MODELS_URL,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise TemporaryOAuthError("network_error", "Could not reach OpenAI") from exc
        if response.status_code != httpx.codes.OK:
            code, message = _error_code(response)
            error_type = TemporaryOAuthError if response.status_code >= 500 else OAuthError
            raise error_type(code, message, response.status_code)
        body = response.json()
        entries = body.get("models") if isinstance(body, dict) else None
        models: list[dict[str, str]] = []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict) or entry.get("visibility") != "list":
                continue
            slug = entry.get("slug")
            if not isinstance(slug, str) or not slug:
                continue
            name = entry.get("display_name")
            models.append({"slug": slug, "display_name": name if isinstance(name, str) else slug})
        return models
