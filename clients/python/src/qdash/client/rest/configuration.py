from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Configuration:
    """Basic REST client configuration."""

    host: str
    timeout: float = 30.0
    verify_tls: bool = True
    proxy: str | None = None
