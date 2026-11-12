"""Base classes for calibration steps.

This module defines the abstract base classes for all step types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qdash.datamodel.one_qubit_execution_mode import (
    OneQubitExecutionMode,
    resolve_one_qubit_execution_mode,
)
from qdash.datamodel.task_call import StepCalls, TaskCall

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession
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

    @abstractmethod
    def execute(
        self,
        session: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute the step.

        Args:
            session: CalibSession instance (provides execute_task, etc.)
            targets: Target specification
            ctx: Current pipeline context

        Returns:
            Updated StepContext with results
        """
        ...


@dataclass
class CalibrationStep(Step):
    """Base class for steps that execute actual calibration on hardware.

    The pipeline creates one Execution for each CalibrationStep and owns its
    completion, failure, and cancellation. Steps and their strategies use the
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

    def step_calls(self, session: CalibSession) -> StepCalls:
        """The calls with step identity and failure policy, as workers receive them."""
        digest = getattr(session, "plan_digest", None)
        return StepCalls(
            step_id=self.resolved_step_id,
            calls=self.calls(),
            continue_on_failure=self.continue_on_failure,
            plan_digest=digest if isinstance(digest, str) else None,
        )


class OneQubitExecutionModeMixin:
    """``execution_mode`` handling shared by the one-qubit step dataclasses.

    A step declares ``execution_mode: str | None = None`` where ``mode`` used to
    be, so positional arguments still land on it, and the deprecated
    ``mode: str | None = None`` as its last field. ``None`` means "not given",
    so the step's default never conflicts with an explicit ``mode``. After
    ``__post_init__`` the step holds the canonical mode in ``execution_mode`` and
    ``mode`` is None. The modes are described in
    :mod:`qdash.datamodel.one_qubit_execution_mode`.
    """

    execution_mode: str | None
    mode: str | None
    _execution_mode_deprecations: list[str]

    def _resolve_execution_mode(self, default: OneQubitExecutionMode) -> None:
        """Fold ``mode`` and old value names into ``execution_mode``; warn on legacy forms.

        Raises ``ValueError`` when ``execution_mode`` and ``mode`` name different modes.
        """
        resolved, notes = resolve_one_qubit_execution_mode(
            self.execution_mode,
            self.mode,
            default=default,
            where=f"{type(self).__name__}.",
            # warn -> resolve helper -> this method -> __post_init__ -> __init__ -> caller
            stacklevel=4,
        )
        self.execution_mode = resolved
        self.mode = None
        self._execution_mode_deprecations = notes

    @property
    def resolved_execution_mode(self) -> OneQubitExecutionMode:
        """The canonical execution mode set by ``__post_init__``."""
        mode = self.execution_mode
        if mode is None:  # pragma: no cover - __post_init__ always sets it
            raise RuntimeError("execution_mode is resolved in __post_init__")
        return mode  # type: ignore[return-value]

    def _log_execution_mode_deprecations(self, logger: Any) -> None:
        """Repeat the construction-time deprecation messages in the run log."""
        for note in getattr(self, "_execution_mode_deprecations", ()):
            logger.warning(note)


def resolve_execution_mode(
    execution_mode: str | None,
    mode: str | None = None,
    *,
    default: OneQubitExecutionMode,
) -> OneQubitExecutionMode:
    """Resolve a flow's ``execution_mode`` and deprecated ``mode`` parameters.

    Flow templates declare ``execution_mode: str | None = None`` and a trailing
    ``mode: str | None = None`` and pass their own ``default``. Legacy forms
    emit a ``DeprecationWarning`` and are repeated in the run log; values that
    name different modes raise ``ValueError``.
    """
    resolved, notes = resolve_one_qubit_execution_mode(
        execution_mode, mode, default=default, stacklevel=3
    )
    if notes:
        from prefect import get_run_logger
        from prefect.exceptions import MissingContextError

        try:
            logger = get_run_logger()
        except MissingContextError:
            return resolved
        for note in notes:
            logger.warning(note)
    return resolved


@dataclass
class TransformStep(Step):
    """Base class for steps that transform data without hardware execution.

    TransformSteps do NOT create execution history entries because they
    only filter, schedule, or transform existing data.

    Examples: FilterByMetric, FilterByStatus, GenerateCRSchedule
    """
