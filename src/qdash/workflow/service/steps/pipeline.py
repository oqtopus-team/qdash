"""Step context and pipeline classes.

This module defines StepContext for sharing state between steps,
and Pipeline for validating step sequences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qdash.datamodel.calibration_pipeline import STEP_ID_PATTERN

_STEP_ID = re.compile(STEP_ID_PATTERN)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from qdash.workflow.service.results import (
        FilterResult,
        OneQubitResult,
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
        candidate_qids: Current list of candidate qubit IDs (can be filtered)
        candidate_couplings: Current list of candidate coupling IDs
        metadata: Additional metadata for the pipeline run
    """

    # Typed step results
    one_qubit_check: OneQubitResult | None = None
    one_qubit_fine_tune: OneQubitResult | None = None
    two_qubit: TwoQubitResult | None = None
    filters: list[FilterResult] = field(default_factory=list)

    # Candidate tracking
    candidate_qids: list[str] = field(default_factory=list)
    candidate_couplings: list[str] = field(default_factory=list)

    # Generic storage
    metadata: dict[str, Any] = field(default_factory=dict)

    # Every calibration step's result by step_id, in execution order
    step_results: dict[str, OneQubitResult | TwoQubitResult] = field(default_factory=dict)

    def get_latest_one_qubit_result(self) -> OneQubitResult | None:
        """The default filter source: OneQubitFineTune if it ran, else OneQubitCheck.

        This is the reference-free selection of earlier versions. It ignores
        custom and bring-up steps; reference a step_id to read those.
        """
        return self.one_qubit_fine_tune or self.one_qubit_check

    def record_step_result(self, step_id: str, result: OneQubitResult | TwoQubitResult) -> None:
        """Keep a calibration step's result for explicit references by step_id."""
        self.step_results[step_id] = result

    def get_step_result(self, step_id: str) -> OneQubitResult | TwoQubitResult | None:
        """The result of the step with this step_id, or None if it has not run."""
        return self.step_results.get(step_id)


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
        """Validate step dependencies, step ids, and filter references.

        Raises:
            ValueError: If a step requires context keys that no previous step
                provides, two calibration steps share a step_id, or a filter
                references a step or call that does not run before it.
        """
        from qdash.workflow.service.steps.base import CalibrationStep
        from qdash.workflow.service.steps.filters import StepReferenceFilter

        # Initial context always has these available
        available: set[str] = {"candidate_qids", "candidate_couplings"}
        earlier: dict[str, CalibrationStep] = {}

        for step in self.steps:
            if isinstance(step, StepReferenceFilter) and step.references_step:
                step.validate_reference(earlier)
            else:
                # An "or" requirement (FilterByMetric/FilterByStatus need
                # one_qubit_check or one_qubit_fine_tune) needs any one of them.
                missing = step.requires - available
                if missing and not (step.requires & available):
                    raise ValueError(
                        f"Step '{step.name}' requires {step.requires}, "
                        f"but only {available} are available. "
                        f"Missing: {missing}"
                    )

            if isinstance(step, CalibrationStep):
                step_id = step.resolved_step_id
                if not _STEP_ID.match(step_id):
                    raise ValueError(
                        f"step_id {step_id!r} must start with a lowercase letter and use "
                        "lowercase letters, digits and underscores (at most 64)"
                    )
                if step_id in earlier:
                    raise ValueError(
                        f"Two steps use step_id {step_id!r}; set a unique step_id "
                        "(or step_name) on repeated steps so results stay addressable"
                    )
                earlier[step_id] = step
                available.add(step_id)

            # Add what this step provides
            available.update(step.provides)

    def __iter__(self) -> Iterator[Step]:
        """Iterate over steps."""
        return iter(self.steps)

    def __len__(self) -> int:
        """Return number of steps."""
        return len(self.steps)
