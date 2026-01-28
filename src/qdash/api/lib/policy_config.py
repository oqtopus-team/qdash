"""Provenance policy configuration loader.

This module loads quality policy rules for provenance/parameter evaluation from YAML.
The policy is intended to drive UI-visible "violations" (warn/error) for current
parameter versions.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from qdash.api.lib.config_loader import ConfigLoader


class PolicyCheck(BaseModel):
    """Single check applied to a parameter value."""

    type: Literal["min", "max", "staleness_hours", "uncertainty_ratio"]
    warn: float
    message: str = ""


class PolicyRule(BaseModel):
    """Policy rules for one parameter."""

    id: str = ""
    parameter: str
    checks: list[PolicyCheck] = Field(default_factory=list)


class PolicyConfig(BaseModel):
    """Top-level policy configuration."""

    version: int = 1
    rules: list[PolicyRule] = Field(default_factory=list)


def load_policy_config() -> PolicyConfig:
    """Load policy configuration from YAML.

    Uses ConfigLoader for unified loading with local override support.
    Configuration is loaded from policy.yaml with optional policy.local.yaml overlay.
    """
    data: dict[str, Any] = ConfigLoader.load_policy()
    try:
        return PolicyConfig(**(data or {}))
    except Exception as e:
        raise ValueError(f"Invalid policy configuration: {e}") from e


def clear_policy_config_cache() -> None:
    """Clear the cached policy configuration.

    Useful when policy.yaml changes and needs to be reloaded without restarting.
    """
    return
