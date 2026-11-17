"""Server-side encryption for third-party credentials stored in MongoDB.

The key comes from ``QDASH_CREDENTIAL_KEY`` or the file named by
``QDASH_CREDENTIAL_KEY_FILE``: one or more comma-separated Fernet keys, newest
first, so a key can be rotated by prepending a new one. Without a key, features
that store credentials are unavailable; they never fall back to plaintext.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

KEY_ENV = "QDASH_CREDENTIAL_KEY"
KEY_FILE_ENV = "QDASH_CREDENTIAL_KEY_FILE"


class CredentialCipherUnavailableError(RuntimeError):
    """No usable encryption key is configured."""


class CredentialDecryptError(RuntimeError):
    """Stored ciphertext cannot be read with the configured keys."""


def _raw_keys() -> str:
    value = os.environ.get(KEY_ENV, "").strip()
    if value:
        return value
    path = os.environ.get(KEY_FILE_ENV, "").strip()
    if path:
        try:
            return Path(path).read_text().strip()
        except OSError:
            return ""
    return ""


def load_cipher() -> MultiFernet:
    """Return the configured cipher, or raise when no valid key is set."""
    raw = _raw_keys()
    keys = [key.strip() for key in raw.split(",") if key.strip()]
    if not keys:
        raise CredentialCipherUnavailableError(
            f"Set {KEY_ENV} or {KEY_FILE_ENV} to store ChatGPT credentials"
        )
    try:
        return MultiFernet([Fernet(key.encode()) for key in keys])
    except (ValueError, TypeError) as exc:
        raise CredentialCipherUnavailableError(f"{KEY_ENV} is not a valid Fernet key") from exc


def cipher_available() -> bool:
    """Whether credentials can be stored on this server."""
    try:
        load_cipher()
    except CredentialCipherUnavailableError:
        return False
    return True


def encrypt(plaintext: str) -> str:
    """Encrypt and authenticate a UTF-8 string."""
    return load_cipher().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a value written by :func:`encrypt`."""
    try:
        return load_cipher().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CredentialDecryptError("Stored credentials cannot be decrypted") from exc
