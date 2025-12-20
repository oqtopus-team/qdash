"""Step context and pipeline classes.

This module defines StepContext for sharing state between steps,
and Pipeline for validating step sequences.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from qdash.workflow.service.results import (
        FilterResult,
        OneQubitResult,
        SkewCheckResult,
        TwoQubitResult,
    )
    from qdash.workflow.service.steps.base import Step


@dataclass
class StepContext:
    """Context shared between steps in a calibration pipeline.

    This context is passed through all steps and accumulates typed results.
    Filter steps modify `candidate_qids` to affect subsequent steps.

    Attributes:
        one_qubit_check: Result from OneQubitCheck step
        one_qubit_fine_tune: Result from OneQubitFineTune step
        two_qubit: Result from TwoQubitCalibration step
        filters: List of filter results applied
        skew_check: Result from CheckSkew step
        candidate_qids: Current list of candidate qubit IDs (can be filtered)
        candidate_couplings: Current list of candidate coupling IDs
        metadata: Additional metadata for the pipeline run
    """

    # Typed step results
    one_qubit_check: OneQubitResult | None = None
    one_qubit_fine_tune: OneQubitResult | None = None
    two_qubit: TwoQubitResult | None = None
    filters: list[FilterResult] = field(default_factory=list)
    skew_check: SkewCheckResult | None = None

    # Candidate tracking
    candidate_qids: list[str] = field(default_factory=list)
    candidate_couplings: list[str] = field(default_factory=list)

    # Generic storage
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_latest_one_qubit_result(self) -> OneQubitResult | None:
        """Get the most recent 1-qubit result (fine_tune if available, else check)."""
        return self.one_qubit_fine_tune or self.one_qubit_check


@dataclass
class Pipeline:
    """A validated sequence of calibration steps.

    Pipeline validates step dependencies at construction time,
    ensuring all required context keys are available before each step runs.

    Example:
        pipeline = Pipeline([
            OneQubitCheck(),
            FilterByMetric(metric="t1", threshold=30.0),
            TwoQubitCalibration(),
        ])
        # Raises ValueError if dependencies are not satisfied
    """

    steps: Sequence[Step]

    def __post_init__(self) -> None:
        """Validate step dependencies."""
        self._validate()

    def _validate(self) -> None:
        """Validate that all step dependencies are satisfied.

        Raises:
            ValueError: If a step requires context keys that no previous step provides
        """
        # Initial context always has these available
        available: set[str] = {"candidate_qids", "candidate_couplings"}

        for step in self.steps:
            # Check if all requirements are met
            # For "or" requirements (like one_qubit_check OR one_qubit_fine_tune),
            # we check if ANY of them is available
            missing = step.requires - available
            if missing:
                # Check if this is an "or" requirement situation
                # FilterByMetric/FilterByStatus require one_qubit_check | one_qubit_fine_tune
                # meaning they need at least one of them
                if not (step.requires & available):
                    raise ValueError(
                        f"Step '{step.name}' requires {step.requires}, "
                        f"but only {available} are available. "
                        f"Missing: {missing}"
                    )

            # Add what this step provides
            available.update(step.provides)

    def __iter__(self) -> Iterator[Step]:
        """Iterate over steps."""
        return iter(self.steps)

    def __len__(self) -> int:
        """Return number of steps."""
        return len(self.steps)
