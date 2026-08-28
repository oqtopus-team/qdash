"""Backend-independent task progress models."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TaskProgress:
    """Serializable progress snapshot produced by an execution backend."""

    current: int
    total: int | None
    description: str
    elapsed_seconds: float
    eta_seconds: float | None
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for task metadata."""
        return asdict(self)


ProgressReporter = Callable[[TaskProgress], None]
