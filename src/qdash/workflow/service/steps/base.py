"""Base classes for calibration steps.

This module defines the abstract base classes for all step types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from qdash.datamodel.task_call import StepCalls, TaskCall

if TYPE_CHECKING:
    from qdash.datamodel.step_record import TransformStepRecord
    from qdash.workflow.service._internal.session import ExecutionRuntime
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target


@dataclass
class Step(ABC):
    """Abstract base class for calibration steps.

    Steps are composable units of work in a calibration pipeline.
    Each step declares its dependencies (requires) and outputs (provides).

    Subclasses must implement:
        - name: Step identifier
        - execute: Main execution logic
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Step name for identification."""
        ...

    @property
    def requires(self) -> set[str]:
        """Context keys this step requires from previous steps.

        Override to declare dependencies. Default: no requirements.
        """
        return set()

    @property
    def provides(self) -> set[str]:
        """Context keys this step provides.

        Override to declare outputs. Default: {self.name}.
        """
        return {self.name}

    @property
    def connect_parent_backend(self) -> bool:
        """Whether the pipeline owner needs a hardware connection for this step."""
        return True

    def preflight(self, session: ExecutionRuntime) -> None:
        """Reject what the step can never run, before any step of the pipeline starts.

        Runs without hardware access. Steps with manual rounds check them
        against the chip's wiring and couplings here. Default: no check.
        """

    @abstractmethod
    def execute(
        self,
        session: ExecutionRuntime,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute the step.

        Args:
            session: ExecutionRuntime instance (provides execute_task, etc.)
            targets: Target specification
            ctx: Current pipeline context

        Returns:
            Updated StepContext with results
        """
        ...


@dataclass
class CalibrationStep(Step):
    """Base class for steps that execute actual calibration on hardware.

    The pipeline creates one Execution for each CalibrationStep (as for every
    step it reaches) and owns its completion, failure, and cancellation. Steps and their strategies use the
    supplied session without creating additional execution history entries.

    Examples: OneQubitCheck, OneQubitFineTune, TwoQubitCalibration

    A calibration step that runs tasks lists them as ``TaskCall`` entries and
    exposes them through :meth:`calls`. ``step_id`` names the step in the plan;
    it defaults to the step's name and must be unique within a pipeline, so set
    it when a pipeline runs the same step type twice.
    """

    step_id: str | None = field(default=None, kw_only=True)

    @property
    def resolved_step_id(self) -> str:
        """Plan-scoped identifier of this step; filters reference it."""
        return self.step_id or self.name

    def calls(self) -> tuple[TaskCall, ...]:
        """The normalized calls the step runs on each target, in order."""
        return ()

    @property
    def continue_on_failure(self) -> bool:
        """Default for calls without on_failure: run a target's later calls after a failure."""
        return False

    def step_calls(self, session: ExecutionRuntime) -> StepCalls:
        """The calls with step identity and failure policy, as workers receive them."""
        digest = getattr(session, "plan_digest", None)
        return StepCalls(
            step_id=self.resolved_step_id,
            calls=self.calls(),
            continue_on_failure=self.continue_on_failure,
            plan_digest=digest if isinstance(digest, str) else None,
        )


@dataclass(frozen=True)
class CandidateSnapshot:
    """Copies of the candidates a transform step started from."""

    qids: tuple[str, ...]
    couplings: tuple[str, ...]
    filter_count: int

    @classmethod
    def of(cls, ctx: StepContext) -> CandidateSnapshot:
        return cls(tuple(ctx.candidate_qids), tuple(ctx.candidate_couplings), len(ctx.filters))


@dataclass
class TransformStep(Step):
    """Base class for steps that select or plan without hardware execution.

    The pipeline records each transform step it reaches in its own Execution,
    like a calibration step, but opens no backend, runs no task and publishes
    no calibration data: the Execution holds the step's
    :meth:`result_record` (``note.transform_result``). The pipeline's
    hardware reservation is kept across it.

    Examples: FilterByMetric, FilterByStatus, GenerateCRSchedule
    """

    def result_record(self, before: CandidateSnapshot, ctx: StepContext) -> TransformStepRecord:
        """What the step decided, as recorded in its Execution.

        ``before`` holds the candidates the step started from; ``ctx`` is the
        context it returned. The default records the candidates before and
        after; built-in filters and schedules add their decisions.
        """
        from qdash.datamodel.step_record import TransformStepRecord

        return TransformStepRecord(
            kind="transform",
            input_qids=list(before.qids),
            output_qids=list(ctx.candidate_qids),
            input_couplings=list(before.couplings),
            output_couplings=list(ctx.candidate_couplings),
        )
