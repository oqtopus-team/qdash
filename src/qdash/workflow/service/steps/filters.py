"""Filter steps for calibration pipelines.

This module defines transform steps that filter candidate qubits:
- FilterByMetric: Filter by a named metric threshold
- FilterByStatus: Filter by calibration success status

Which result a filter reads:

* ``step`` and ``call_id`` set: that one call of that step. A qubit passes only
  when the call succeeded on it (and, for ``FilterByMetric``, its output
  parameter ``metric`` meets the threshold). A failed, skipped, or missing call
  removes the qubit; another call of the same task is never used instead.
* ``step`` only: that step's per-qubit status, or its step-level metrics for
  ``FilterByMetric`` (built-in steps derive them; custom steps have none, so
  they need ``call_id``).
* Neither: the latest built-in one-qubit result, ``OneQubitFineTune`` if it
  ran, else ``OneQubitCheck``, as before task calls existed. Custom and bring-up
  steps are not read this way.

Status here is completion and acceptance of the step's own calls in this run,
not the latest value stored in the calibration database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from prefect import get_run_logger

from qdash.workflow.service.results import FilterResult, OneQubitResult
from qdash.workflow.service.steps.base import TransformStep

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qdash.workflow.service._internal.session import CalibSession
    from qdash.workflow.service.steps.base import CalibrationStep
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target

_ONE_QUBIT_STEP_TYPES = frozenset(
    {"BringUp", "CustomOneQubit", "OneQubitCheck", "OneQubitFineTune"}
)


@dataclass
class StepReferenceFilter(TransformStep):
    """Shared selection of the result a filter reads (see the module docstring)."""

    step: str | None = field(default=None, kw_only=True)
    call_id: str | None = field(default=None, kw_only=True)

    @property
    def references_step(self) -> bool:
        """Whether the filter names its source instead of using the default."""
        return self.step is not None or self.call_id is not None

    @property
    def requires(self) -> set[str]:
        if self.step is not None:
            return {self.step}
        return {"one_qubit_check"} | {"one_qubit_fine_tune"}

    @property
    def provides(self) -> set[str]:
        return {"candidate_qids"}

    def _source_label(self) -> str:
        if self.step is None:
            return "latest one-qubit check/fine-tune"
        if self.call_id is None:
            return f"step {self.step}"
        return f"{self.step}.{self.call_id}"

    def validate_reference(self, earlier: Mapping[str, CalibrationStep]) -> None:
        """Raise if the referenced step or call does not run before this filter."""
        if self.call_id is not None and self.step is None:
            raise ValueError(f"{self.name}: call_id {self.call_id!r} needs the step it belongs to")
        assert self.step is not None
        target = earlier.get(self.step)
        if target is None:
            known = ", ".join(earlier) or "none"
            raise ValueError(
                f"{self.name}: step {self.step!r} is not an earlier step (earlier: {known})"
            )
        if type(target).__name__ not in _ONE_QUBIT_STEP_TYPES:
            raise ValueError(
                f"{self.name}: step {self.step!r} is a {type(target).__name__}, which has no "
                "per-qubit result"
            )
        if self.call_id is not None:
            call_ids = [call.resolved_call_id for call in target.calls()]
            if self.call_id not in call_ids:
                raise ValueError(
                    f"{self.name}: step {self.step!r} has no call {self.call_id!r} "
                    f"(calls: {', '.join(call_ids)})"
                )
        self._validate_step_level(target)

    def _validate_step_level(self, target: CalibrationStep) -> None:
        """Hook for checks that depend on the filter kind."""

    def _source(self, ctx: StepContext) -> OneQubitResult | None:
        if self.step is None:
            return ctx.get_latest_one_qubit_result()
        result = ctx.get_step_result(self.step)
        if result is None:
            # The step ran but produced nothing (e.g. no candidates): nothing passes.
            return OneQubitResult(step_id=self.step)
        if not isinstance(result, OneQubitResult):
            raise TypeError(f"{self.name}: step {self.step!r} has no per-qubit result")
        return result


@dataclass
class FilterByMetric(StepReferenceFilter):
    """Filter qubits by a named metric threshold.

    This step filters `ctx.candidate_qids` to the qubits whose metric from the
    selected result meets the threshold. With ``call_id`` the metric is an
    output parameter of that call (e.g. ``"t2_star"`` of a ``CheckRamsey`` call).

    Requires: the referenced step, else one_qubit_check or one_qubit_fine_tune
    Provides: filter result appended to ctx.filters
    """

    metric: str = "x90_fidelity"
    threshold: float = 0.9

    @property
    def name(self) -> str:
        return f"filter_by_{self.metric}"

    def _validate_step_level(self, target: CalibrationStep) -> None:
        if self.call_id is not None:
            return
        metrics = getattr(target, "step_metrics", ())
        if self.metric not in metrics:
            derived = ", ".join(metrics) or "none"
            raise ValueError(
                f"{self.name}: step {self.step!r} derives the metrics {derived}; set call_id "
                f"to read output parameter {self.metric!r} of one of its calls"
            )

    def execute(
        self,
        service: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Filter candidate qubits by metric threshold."""
        logger = get_run_logger()

        result = self._source(ctx)
        if result is None:
            logger.warning(f"[{self.name}] No 1-qubit results found, keeping all candidates")
            return ctx

        input_qids = ctx.candidate_qids.copy()
        if self.call_id is not None:
            output_qids = result.filter_by_call_metric(self.call_id, self.metric, self.threshold)
        else:
            output_qids = result.filter_by_metric(self.metric, self.threshold)

        # Intersect with current candidates
        output_qids = sorted(set(output_qids) & set(input_qids))

        criteria = f"{self._source_label()}: {self.metric} >= {self.threshold}"
        logger.info(f"[{self.name}] Filtered {len(input_qids)} -> {len(output_qids)} ({criteria})")

        ctx.candidate_qids = output_qids
        ctx.filters.append(
            FilterResult(
                input_qids=input_qids,
                output_qids=output_qids,
                filter_criteria=(
                    criteria if self.references_step else f"{self.metric} >= {self.threshold}"
                ),
            )
        )
        return ctx


@dataclass
class FilterByStatus(StepReferenceFilter):
    """Filter qubits by calibration status.

    Keeps only qubits whose selected step (or call) succeeded.

    Requires: the referenced step, else one_qubit_check or one_qubit_fine_tune
    Provides: candidate_qids
    """

    @property
    def name(self) -> str:
        return "filter_by_status"

    def execute(
        self,
        service: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Filter candidate qubits by success status."""
        logger = get_run_logger()

        result = self._source(ctx)
        if result is None:
            logger.warning(f"[{self.name}] No 1-qubit results found")
            return ctx

        input_qids = ctx.candidate_qids.copy()
        if self.call_id is not None:
            output_qids = result.call_succeeded_qids(self.call_id)
        else:
            output_qids = result.successful_qids()

        # Intersect with current candidates
        output_qids = sorted(set(output_qids) & set(input_qids))

        logger.info(
            f"[{self.name}] Filtered {len(input_qids)} -> {len(output_qids)} qubits "
            f"({self._source_label()})"
        )

        ctx.candidate_qids = output_qids
        ctx.filters.append(
            FilterResult(
                input_qids=input_qids,
                output_qids=output_qids,
                filter_criteria=(
                    f"{self._source_label()}: status == success"
                    if self.references_step
                    else "status == success"
                ),
            )
        )
        return ctx
