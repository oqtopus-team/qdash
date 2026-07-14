"""Deterministic, side-effect-free gates for local-agent candidates."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class GateDecision:
    accepted: bool
    reason: str


def evaluate_numeric_candidate(
    value: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> GateDecision:
    """Accept only finite values within inclusive bounds."""
    if not math.isfinite(value):
        return GateDecision(False, "candidate must be finite")
    if minimum is not None and value < minimum:
        return GateDecision(False, "candidate is below the minimum bound")
    if maximum is not None and value > maximum:
        return GateDecision(False, "candidate is above the maximum bound")
    return GateDecision(True, "candidate passed deterministic bounds gate")
