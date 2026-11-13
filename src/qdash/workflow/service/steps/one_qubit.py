"""1-Qubit calibration steps.

This module defines steps for 1-qubit calibration:
- CustomOneQubit: Flexible custom task execution
- OneQubitCheck: Basic characterization (Rabi, HPI and PI pulses)
- OneQubitFineTune: Advanced calibration (DRAG, RB, etc.)

Every step takes an ``execution_mode`` (default ``parallel_by_round``) that decides
where and when its targets run; see :mod:`qdash.datamodel.one_qubit_execution_mode`
for ``parallel_by_round`` versus ``parallel_by_mux``. With ``execution_mode="manual"``
the step's ``rounds`` list the rounds explicitly, and they run exactly as written
(:mod:`qdash.workflow.service.manual_rounds`). Any other value, ``rounds`` without
``manual``, or ``manual`` without ``rounds`` raises ``ValueError`` when the step
is constructed.

Every step lists its work as ``TaskCall`` entries. A step may run the same task
more than once when each occurrence has its own ``call_id``; each call on each
target produces its own task result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from prefect import get_run_logger

from qdash.common.manual_rounds import QubitRounds, qubit_rounds_for_mode
from qdash.datamodel.calibration_pipeline import (
    ONE_QUBIT_CHECK_METRICS,
    ONE_QUBIT_FINE_TUNE_METRICS,
    calls_with_configure,
)
from qdash.datamodel.one_qubit_execution_mode import (
    OneQubitExecutionMode,
    OneQubitStepExecutionMode,
    validate_one_qubit_execution_mode,
    validate_one_qubit_step_execution_mode,
)
from qdash.datamodel.task_call import StepCalls, TaskCall, normalize_calls
from qdash.workflow.service._internal.call_runner import latest_call_output
from qdash.workflow.service.results import (
    OneQubitResult,
    build_one_qubit_result,
    normalize_metric_value,
)
from qdash.workflow.service.steps.base import CalibrationStep
from qdash.workflow.service.tasks import CHECK_1Q_TASKS, FULL_1Q_TASKS_AFTER_CHECK

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target


def _execute_direct_one_qubit(
    session: CalibSession,
    *,
    qids: list[str],
    plan: StepCalls,
    stage_name: str,
) -> dict[str, Any]:
    """Run explicit qubit targets under a visible parent Execution."""
    from qdash.workflow.service._internal.scheduling_tasks import (
        run_qubit_calibrations_parallel,
    )

    if not qids:
        return {"direct": {}}

    results = run_qubit_calibrations_parallel(
        qids=qids,
        plan=plan,
        worker=session.worker_spec(),
    )
    wrapped_results = {"direct": results}
    session.record_stage_result(stage_name, wrapped_results)
    return wrapped_results


def _execute_scheduled_one_qubit(
    session: CalibSession,
    *,
    qids: list[str],
    plan: StepCalls,
    stage_name: str,
    execution_mode: OneQubitExecutionMode,
) -> dict[str, Any]:
    """Run explicit qubit targets through the same scheduler used by MUX targets."""
    from qdash.workflow.service.strategy import OneQubitConfig, get_one_qubit_strategy

    if not qids:
        return {}

    mux_ids = sorted({int(qid) // 4 for qid in qids})
    config = OneQubitConfig(
        mux_ids=mux_ids,
        exclude_qids=[],
        qids=qids,
        plan=plan,
    )
    strategy = get_one_qubit_strategy(execution_mode)
    result: dict[str, Any] = strategy.execute(session, config)
    return result


def _execute_mux_one_qubit(
    session: CalibSession,
    *,
    targets: Any,
    plan: StepCalls,
    stage_name: str,
    execution_mode: OneQubitExecutionMode,
) -> dict[str, Any]:
    """Run MUX targets through the selected one-qubit strategy."""
    from qdash.workflow.service.strategy import OneQubitConfig, get_one_qubit_strategy

    config = OneQubitConfig(
        mux_ids=targets.mux_ids,
        exclude_qids=targets.exclude_qids,
        plan=plan,
    )
    result: dict[str, Any] = get_one_qubit_strategy(execution_mode).execute(session, config)
    return result


def _metric(raw: dict[str, Any], task_name: str, parameter: str) -> float | None:
    return normalize_metric_value(latest_call_output(raw, task_name).get(parameter))


def _init_mode(step: Any) -> QubitRounds | None:
    """Validate ``execution_mode`` and ``rounds``; store the rounds as lists."""
    step.execution_mode = validate_one_qubit_step_execution_mode(step.execution_mode)
    rounds = qubit_rounds_for_mode(step.execution_mode, step.rounds, step=step.name)
    step.rounds = [list(round_) for round_ in rounds] if rounds is not None else None
    return rounds


def _scheduled_mode(step: Any) -> OneQubitExecutionMode:
    """The execution mode of a step that the scheduler plans."""
    return validate_one_qubit_execution_mode(step.execution_mode)


def _preflight_manual(step: Any, session: CalibSession) -> None:
    """Check manual rounds against the chip before any step of the pipeline runs."""
    if step._rounds is not None:
        from qdash.workflow.service.manual_rounds import check_qubit_rounds

        check_qubit_rounds(session, step._rounds, step=step.name)


def _execute_manual_one_qubit(
    step: Any, session: CalibSession, candidates: list[str], plan: StepCalls
) -> dict[str, Any]:
    """Run the step's manual rounds after checking them against its current qubits."""
    from qdash.workflow.service.manual_rounds import run_qubit_rounds

    assert step._rounds is not None
    return run_qubit_rounds(session, step._rounds, plan=plan, candidates=candidates, step=step.name)


@dataclass
class CustomOneQubit(CalibrationStep):
    """Custom 1-qubit calibration step with user-defined task calls.

    This is the most flexible 1-qubit step: you specify exactly which calls to
    run, including the same task several times with different settings.

    Example:
        CustomOneQubit(
            step_name="ramsey_two_pass",
            tasks=[
                TaskCall(name="CheckRamsey", call_id="ramsey_coarse",
                         run={"detuning": 0.001}),
                TaskCall(name="CheckRamsey", call_id="ramsey_fine",
                         run={"detuning": 0.0002}),
            ],
            continue_on_failure=True,
        )

    ``continue_on_failure`` keeps a target's later calls running after one of its
    calls fails. A call's ``on_failure="stop"`` keeps a prerequisite such as
    ``Configure`` fail-fast for that target; ``on_failure="continue"`` does the
    opposite under the default fail-fast policy. The step's result keeps every
    call in order; read one with ``result.get_qubit(qid).call("ramsey_fine")``.
    """

    step_name: str = "custom_one_qubit"
    tasks: list[TaskCall] = field(default_factory=list)
    execution_mode: OneQubitStepExecutionMode = "parallel_by_round"
    continue_on_failure: bool = False
    rounds: list[list[str]] | None = None

    step_metrics: ClassVar[tuple[str, ...]] = ()

    def __post_init__(self) -> None:
        self._rounds = _init_mode(self)
        if self.step_id is not None and self.step_id != self.step_name:
            raise ValueError(
                f"CustomOneQubit uses step_name as its step_id; got step_name="
                f"{self.step_name!r} and step_id={self.step_id!r}"
            )
        self.tasks = list(normalize_calls(self.tasks, where=f"{self.step_name}.tasks"))

    @property
    def name(self) -> str:
        return self.step_name

    @property
    def provides(self) -> set[str]:
        return {self.step_name, "candidate_qids"}

    @property
    def connect_parent_backend(self) -> bool:
        """parallel_by_round and manual qubit tasks connect in isolated workers."""
        return self.execution_mode not in ("parallel_by_round", "manual")

    def preflight(self, session: CalibSession) -> None:
        """Check manual rounds against the chip before the pipeline starts."""
        _preflight_manual(self, session)

    def calls(self) -> tuple[TaskCall, ...]:
        return tuple(self.tasks)

    def execute(
        self,
        session: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute custom 1-qubit calibration."""
        logger = get_run_logger()

        if not self.tasks:
            logger.warning(f"[{self.name}] No tasks specified, skipping")
            return ctx

        plan = self.step_calls(session)
        logger.info(
            f"[{self.name}] Starting with {len(self.tasks)} calls: "
            f"{[call.resolved_call_id for call in self.tasks]}"
        )

        has_previous_selection = bool(ctx.filters) or ctx.get_latest_one_qubit_result() is not None
        if self._rounds is not None:
            candidates = (
                ctx.candidate_qids if has_previous_selection else targets.to_qids(session.chip_id)
            )
            raw_results = _execute_manual_one_qubit(self, session, candidates, plan)
        elif has_previous_selection:
            raw_results = self._execute_scheduled(session, ctx.candidate_qids, plan)
        else:
            from qdash.workflow.service.targets import MuxTargets

            if isinstance(targets, MuxTargets):
                raw_results = _execute_mux_one_qubit(
                    session,
                    targets=targets,
                    plan=plan,
                    stage_name=self.name,
                    execution_mode=_scheduled_mode(self),
                )
            else:
                raw_results = self._execute_scheduled(
                    session, targets.to_qids(session.chip_id), plan
                )

        result = self._build_result(raw_results)

        # Store in metadata with step name as key, and by step_id for filters
        ctx.metadata[self.step_name] = result
        ctx.record_step_result(self.resolved_step_id, result)

        logger.info(
            f"[{self.name}] Completed. "
            f"{len(result.successful_qids())}/{len(result.qubits)} successful"
        )
        return ctx

    def _execute_scheduled(
        self,
        session: CalibSession,
        qids: list[str],
        plan: StepCalls | None = None,
    ) -> dict[str, Any]:
        """Execute explicit QubitTargets through hardware-aware scheduling."""
        return _execute_scheduled_one_qubit(
            session,
            qids=qids,
            plan=plan or self.step_calls(session),
            stage_name=self.step_name,
            execution_mode=_scheduled_mode(self),
        )

    def _execute_direct(
        self,
        session: CalibSession,
        qids: list[str],
    ) -> dict[str, Any]:
        """Direct execution for tests and callers that explicitly need unscheduled qid parallelism."""
        return _execute_direct_one_qubit(
            session,
            qids=qids,
            plan=self.step_calls(session),
            stage_name=self.step_name,
        )

    def _build_result(self, raw_results: dict[str, Any]) -> OneQubitResult:
        """Build typed result from raw backend data."""
        return build_one_qubit_result(raw_results, self.resolved_step_id, self._extract_metrics)

    def _extract_metrics(self, raw: dict[str, Any]) -> dict[str, float]:
        """Extract metrics from raw result.

        Custom steps derive no step-level metrics; read a call's outputs with
        ``QubitCalibData.call(call_id)`` or filter with ``call_id``. Subclasses
        may override this for specific metric extraction.
        """
        return {}


@dataclass
class OneQubitCheck(CalibrationStep):
    """Basic 1-qubit characterization step.

    Executes CHECK_1Q_TASKS by default: Rabi, then the HPI and PI pulse
    calibrations.

    Provides: one_qubit_check
    """

    execution_mode: OneQubitStepExecutionMode = "parallel_by_round"
    tasks: list[TaskCall] | None = None
    configure: bool = False
    rounds: list[list[str]] | None = None

    step_metrics: ClassVar[tuple[str, ...]] = ONE_QUBIT_CHECK_METRICS

    def __post_init__(self) -> None:
        self._rounds = _init_mode(self)
        self._calls = self._normalize()

    def _normalize(self) -> tuple[TaskCall, ...]:
        calls = list(self.tasks if self.tasks is not None else CHECK_1Q_TASKS)
        return calls_with_configure(calls, configure=self.configure, where=f"{self.name}.tasks")

    @property
    def name(self) -> str:
        return self.step_id or "one_qubit_check"

    @property
    def provides(self) -> set[str]:
        return {"one_qubit_check", "candidate_qids"}

    def preflight(self, session: CalibSession) -> None:
        """Check manual rounds against the chip before the pipeline starts."""
        _preflight_manual(self, session)

    def calls(self) -> tuple[TaskCall, ...]:
        return self._calls

    def execute(
        self,
        session: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute 1-qubit check calibration."""
        logger = get_run_logger()
        plan = self.step_calls(session)

        logger.info(
            f"[{self.name}] Starting with execution_mode={self.execution_mode}, "
            f"{len(plan.calls)} calls"
        )

        from qdash.workflow.service.targets import MuxTargets

        if self._rounds is not None:
            # OneQubitCheck always runs on the pipeline targets, as in other modes.
            raw_results = _execute_manual_one_qubit(
                self, session, targets.to_qids(session.chip_id), plan
            )
        elif isinstance(targets, MuxTargets):
            raw_results = _execute_mux_one_qubit(
                session,
                targets=targets,
                plan=plan,
                stage_name=self.name,
                execution_mode=_scheduled_mode(self),
            )
        else:
            qids = targets.to_qids(session.chip_id)
            raw_results = self._execute_scheduled(session, qids, plan)

        result = self._build_result(raw_results)
        ctx.one_qubit_check = result
        ctx.record_step_result(self.resolved_step_id, result)

        logger.info(
            f"[{self.name}] Completed. "
            f"{len(result.successful_qids())}/{len(result.qubits)} successful"
        )
        return ctx

    def _execute_scheduled(
        self,
        session: CalibSession,
        qids: list[str],
        plan: StepCalls | None = None,
    ) -> dict[str, Any]:
        """Execute explicit QubitTargets through hardware-aware scheduling."""
        return _execute_scheduled_one_qubit(
            session,
            qids=qids,
            plan=plan or self.step_calls(session),
            stage_name=self.name,
            execution_mode=_scheduled_mode(self),
        )

    def _execute_direct(
        self,
        session: CalibSession,
        qids: list[str],
    ) -> dict[str, Any]:
        """Direct execution for tests and callers that explicitly need unscheduled qid parallelism."""
        return _execute_direct_one_qubit(
            session,
            qids=qids,
            plan=self.step_calls(session),
            stage_name=self.name,
        )

    def _build_result(self, raw_results: dict[str, Any]) -> OneQubitResult:
        """Build typed result from raw backend data."""
        return build_one_qubit_result(raw_results, self.resolved_step_id, self._extract_metrics)

    def _extract_metrics(self, raw: dict[str, Any]) -> dict[str, float]:
        """Extract metrics from the latest call of each task in the step."""
        metrics = {}
        if (value := _metric(raw, "CheckT1Average", "t1_average")) is not None:
            metrics["t1_average"] = value
        if (value := _metric(raw, "CheckT2EchoAverage", "t2_echo_average")) is not None:
            metrics["t2_echo_average"] = value
        return metrics


@dataclass
class OneQubitFineTune(CalibrationStep):
    """Advanced 1-qubit calibration step.

    Executes FULL_1Q_TASKS_AFTER_CHECK: DRAG pulses, ReadoutClassification,
    RandomizedBenchmarking, X90InterleavedRandomizedBenchmarking.

    Requires: candidate_qids (optional, uses targets if not available)
    Provides: one_qubit_fine_tune
    """

    execution_mode: OneQubitStepExecutionMode = "parallel_by_round"
    tasks: list[TaskCall] | None = None
    configure: bool = False
    rounds: list[list[str]] | None = None

    step_metrics: ClassVar[tuple[str, ...]] = ONE_QUBIT_FINE_TUNE_METRICS

    def __post_init__(self) -> None:
        self._rounds = _init_mode(self)
        calls = list(self.tasks if self.tasks is not None else FULL_1Q_TASKS_AFTER_CHECK)
        self._calls = calls_with_configure(
            calls, configure=self.configure, where=f"{self.name}.tasks"
        )

    @property
    def name(self) -> str:
        return self.step_id or "one_qubit_fine_tune"

    @property
    def provides(self) -> set[str]:
        return {"one_qubit_fine_tune", "candidate_qids"}

    def preflight(self, session: CalibSession) -> None:
        """Check manual rounds against the chip before the pipeline starts."""
        _preflight_manual(self, session)

    def calls(self) -> tuple[TaskCall, ...]:
        return self._calls

    def execute(
        self,
        session: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute 1-qubit fine-tuning calibration."""
        logger = get_run_logger()
        plan = self.step_calls(session)

        # Use filtered candidates from context if available
        has_previous_selection = bool(ctx.filters) or ctx.get_latest_one_qubit_result() is not None
        qids = (
            ctx.candidate_qids
            if ctx.candidate_qids or has_previous_selection
            else targets.to_qids(session.chip_id)
        )

        logger.info(
            f"[{self.name}] Starting with execution_mode={self.execution_mode}, "
            f"{len(plan.calls)} calls, {len(qids)} qubits"
        )

        if self._rounds is not None:
            raw_results = _execute_manual_one_qubit(self, session, qids, plan)
            result = self._build_result(raw_results)
            ctx.one_qubit_fine_tune = result
            ctx.record_step_result(self.resolved_step_id, result)
            logger.info(
                f"[{self.name}] Completed. "
                f"{len(result.successful_qids())}/{len(result.qubits)} successful"
            )
            return ctx

        if not qids:
            logger.warning(f"[{self.name}] No candidate qubits, skipping")
            ctx.one_qubit_fine_tune = OneQubitResult(step_id=self.resolved_step_id)
            ctx.record_step_result(self.resolved_step_id, ctx.one_qubit_fine_tune)
            return ctx

        raw_results = self._execute_with_qids(session, qids, plan)

        result = self._build_result(raw_results)
        ctx.one_qubit_fine_tune = result
        ctx.record_step_result(self.resolved_step_id, result)

        logger.info(
            f"[{self.name}] Completed. "
            f"{len(result.successful_qids())}/{len(result.qubits)} successful"
        )
        return ctx

    def _execute_with_qids(
        self,
        session: CalibSession,
        qids: list[str],
        plan: StepCalls | None = None,
    ) -> dict[str, Any]:
        """Execute calibration for specific qubit IDs."""
        return _execute_scheduled_one_qubit(
            session,
            qids=qids,
            plan=plan or self.step_calls(session),
            stage_name=self.name,
            execution_mode=_scheduled_mode(self),
        )

    def _execute_direct(
        self,
        session: CalibSession,
        qids: list[str],
    ) -> dict[str, Any]:
        """Direct execution for QubitTargets using multiprocess parallelism."""
        return _execute_direct_one_qubit(
            session,
            qids=qids,
            plan=self.step_calls(session),
            stage_name=self.name,
        )

    def _build_result(self, raw_results: dict[str, Any]) -> OneQubitResult:
        """Build typed result from raw backend data."""
        return build_one_qubit_result(raw_results, self.resolved_step_id, self._extract_metrics)

    def _extract_metrics(self, raw: dict[str, Any]) -> dict[str, float]:
        """Extract metrics from the latest call of each task in the step."""
        metrics = {}
        if (
            value := _metric(raw, "X90InterleavedRandomizedBenchmarking", "x90_gate_fidelity")
        ) is not None:
            metrics["x90_fidelity"] = value
        if (value := _metric(raw, "RandomizedBenchmarking", "fidelity")) is not None:
            metrics["rb_fidelity"] = value
        if (value := _metric(raw, "CheckT1Average", "t1_average")) is not None:
            metrics["t1_average"] = value
        if (value := _metric(raw, "CheckT2EchoAverage", "t2_echo_average")) is not None:
            metrics["t2_echo_average"] = value
        if (
            value := _metric(raw, "Check1QGateCoherenceLimit", "one_qubit_gate_coherence_limit")
        ) is not None:
            metrics["one_qubit_gate_coherence_limit"] = value
        return metrics
