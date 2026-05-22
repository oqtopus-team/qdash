"""Helpers for machine-generated commit messages."""

from __future__ import annotations

import os
import re

_UNSAFE_TOKEN_CHARS = re.compile(r"[\s\[\]]+")


def _sanitize_commit_token(value: str) -> str:
    """Convert an environment value into a safe single-line commit token."""
    token = _UNSAFE_TOKEN_CHARS.sub("-", value.strip()).strip("-")
    return token or "unknown"


def format_machine_commit_message(
    message: str,
    committed_at: str,
    *,
    env: str | None = None,
) -> str:
    """Format a machine-generated commit message with the runtime environment first."""
    env_name = os.getenv("ENV", "unknown") if env is None else env
    return f"[ENV={_sanitize_commit_token(env_name)}] {message} at {committed_at}"
