"""Base classes and context objects for CR Scheduler plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdash.datamodel.chip import ChipModel


@dataclass
class FilterContext:
    """Context object passed to CR pair filters.

    Attributes:
        chip: Current chip data (metadata only, for backwards compatibility)
        grid_size: Grid dimension (8 for 64-qubit, 12 for 144-qubit)
        qubit_frequency: Mapping from qubit ID to frequency (if available)
        qid_to_mux: Mapping from qubit ID to MUX ID
        qubit_models: Qubit data from individual QubitDocument collection (scalable)
        topology_directions: Pre-computed set of valid coupling directions from topology.
            If set, used by FrequencyDirectionalityFilter instead of design/measured methods.
    """

    chip: ChipModel
    grid_size: int
    qubit_frequency: dict[str, float] = field(default_factory=dict)
    qid_to_mux: dict[str, int] = field(default_factory=dict)
    qubit_models: dict[str, Any] = field(default_factory=dict)
    topology_directions: set[str] | None = None


@dataclass
class ScheduleContext:
    """Context object passed to CR scheduling strategies.

    Attributes:
        qid_to_mux: Mapping from qubit ID to MUX ID
        mux_conflict_map: MUX conflict relationships
    """

    qid_to_mux: dict[str, int]
    mux_conflict_map: dict[int, set[int]]


class CRPairFilter(ABC):
    """Base class for CR pair filtering strategies.

    Filters can be chained together to create complex filtering pipelines.
    Each filter receives a list of CR pairs and returns a filtered subset.
    """

    @abstractmethod
    def filter(self, pairs: list[str], context: FilterContext) -> list[str]:
        """Filter CR pairs based on specific criteria.

        Args:
            pairs: List of CR pair strings (e.g., ["0-1", "2-3"])
            context: Context object containing chip data and configuration

        Returns:
            Filtered list of CR pair strings
        """

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Return filtering statistics.

        Returns:
            Dictionary containing filter-specific statistics
        """

    def __repr__(self) -> str:
        """String representation of the filter."""
        return f"{self.__class__.__name__}()"


class CRSchedulingStrategy(ABC):
    """Base class for CR pair scheduling strategies.

    Scheduling strategies determine how to group CR pairs into parallel
    execution groups while respecting hardware constraints.
    """

    @abstractmethod
    def schedule(self, pairs: list[str], context: ScheduleContext) -> list[list[str]]:
        """Group CR pairs into parallel execution groups.

        Args:
            pairs: List of CR pair strings to schedule
            context: Context object containing MUX configuration and conflicts

        Returns:
            List of groups where each group contains CR pairs that can run in parallel
        """

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Return scheduler metadata.

        Returns:
            Dictionary containing scheduler-specific metadata
        """

    def __repr__(self) -> str:
        """String representation of the scheduler."""
        return f"{self.__class__.__name__}()"
