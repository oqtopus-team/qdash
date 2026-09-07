"""Backend-independent task progress models."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ProgressPlan:
    """Known bounds for the number of sequential measurement phases."""

    minimum_phases: int
    maximum_phases: int


@dataclass(frozen=True)
class TaskProgress:
    """Serializable progress snapshot produced by an execution backend."""

    current: int
    total: int | None
    description: str
    elapsed_seconds: float
    eta_seconds: float | None
    updated_at: str
    phase: int = 1
    has_multiple_phases: bool = False
    phase_total_min: int | None = None
    phase_total_max: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for task metadata."""
        return asdict(self)


ProgressReporter = Callable[[TaskProgress], None]
