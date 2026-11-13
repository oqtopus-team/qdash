"""2-Qubit calibration steps.

This module defines steps for 2-qubit calibration:
- CustomTwoQubit: Flexible custom 2Q task execution
- GenerateCRSchedule: CR schedule generation
- TwoQubitCalibration: Full 2Q calibration

``CustomTwoQubit`` and ``TwoQubitCalibration`` take an ``execution_mode``:
``automatic`` (default) runs an earlier CR schedule or generates one, and
``manual`` runs the step's ``rounds`` of directed pairs exactly as written
(see :mod:`qdash.datamodel.two_qubit_execution_mode`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from prefect import get_run_logger

from qdash.common.manual_rounds import PairRounds, pair_rounds_for_mode
from qdash.datamodel.task_call import StepCalls, TaskCall, normalize_calls
from qdash.datamodel.two_qubit_execution_mode import (
    DEFAULT_MAX_PARALLEL_OPS,
    TwoQubitExecutionMode,
    validate_two_qubit_execution_mode,
)
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
from qdash.workflow.service._internal.call_runner import latest_call_output
from qdash.workflow.service.results import (
    TwoQubitResult,
    build_two_qubit_result,
    normalize_metric_value,
)
from qdash.workflow.service.steps.base import CalibrationStep, TransformStep
from qdash.workflow.service.tasks import FULL_2Q_TASKS

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target


def _run_coupling_groups(
    session: CalibSession,
    coupling_groups: list[list[str]],
    plan: StepCalls,
) -> dict[str, Any]:
    """Run the plan on scheduled coupling groups.

    Groups run one after another because the CR schedule separates conflicting
    pairs; pairs within a group run in parallel processes, each running the
    plan's calls in order without waiting for the other pairs.
    """
    from qdash.workflow.service._internal.scheduling_tasks import (
        run_coupling_calibrations_parallel,
    )

    worker = session.worker_spec()
    all_raw_results: dict[str, Any] = {}
    for group in coupling_groups:
        all_raw_results.update(
            run_coupling_calibrations_parallel(
                coupling_qids=group,
                plan=plan,
                worker=worker,
            )
        )
    return all_raw_results


def _init_mode(step: Any) -> PairRounds | None:
    """Validate ``execution_mode``, ``rounds`` and ``max_parallel_ops``; store pairs as tuples."""
    step.execution_mode = validate_two_qubit_execution_mode(step.execution_mode)
    rounds = pair_rounds_for_mode(
        step.execution_mode, step.rounds, step.max_parallel_ops, step=step.name
    )
    step.rounds = [list(round_) for round_ in rounds] if rounds is not None else None
    return rounds


def _max_parallel_ops(step: Any) -> int:
    value: int | None = step.max_parallel_ops
    return DEFAULT_MAX_PARALLEL_OPS if value is None else value


def _execute_manual_two_qubit(
    step: Any, session: CalibSession, ctx: StepContext, plan: StepCalls
) -> dict[str, Any]:
    """Run manual rounds after checking them against the current candidate qubits."""
    from qdash.workflow.service.manual_rounds import run_pair_rounds

    if "cr_schedule" in ctx.metadata:
        get_run_logger().info(
            f"[{step.name}] Manual rounds run as written; the earlier CR schedule is not used"
        )
    assert step._rounds is not None
    return run_pair_rounds(
        session, step._rounds, plan=plan, candidates=ctx.candidate_qids, step=step.name
    )


def _preflight_manual(step: Any, session: CalibSession) -> None:
    if step._rounds is not None:
        from qdash.workflow.service.manual_rounds import check_pair_rounds

        check_pair_rounds(session, step._rounds, step=step.name)


@dataclass
class CustomTwoQubit(CalibrationStep):
    """Custom 2-qubit calibration step with user-defined tasks.

    Similar to CustomOneQubit, this allows specifying exactly which
    2-qubit tasks to run.

    Example:
        # Run only CR check
        CustomTwoQubit(
            step_name="cr_check",
            tasks=[TaskCall(name="CheckCrossResonance")],
        )

        # Run ZX90 calibration twice with different settings
        CustomTwoQubit(
            step_name="zx90_tune",
            tasks=[
                TaskCall(name="CreateZX90"),
                TaskCall(name="CheckZX90", call_id="zx90_check_coarse"),
                TaskCall(name="CheckZX90", call_id="zx90_check_fine", run={"shots": 4096}),
            ],
        )

        # Run exactly these rounds of directed (control, target) pairs
        CustomTwoQubit(
            step_name="cr_rounds",
            execution_mode="manual",
            rounds=[[("0", "1"), ("4", "5")], [("8", "9")]],
            tasks=[TaskCall(name="CheckCrossResonance")],
        )

    ``continue_on_failure`` keeps a pair's independent later calls running. A
    call's ``on_failure="stop"`` keeps a prerequisite fail-fast for that pair.

    ``max_parallel_ops`` caps the pairs of an automatically generated group
    (default 10). It is rejected with ``manual``, whose rounds are never split.
    """

    step_name: str = "custom_two_qubit"
    tasks: list[TaskCall] = field(default_factory=list)
    max_parallel_ops: int | None = None
    continue_on_failure: bool = False
    execution_mode: TwoQubitExecutionMode = "automatic"
    rounds: list[list[tuple[str, str]]] | None = None

    def __post_init__(self) -> None:
        self._rounds = _init_mode(self)
        if self.step_id is not None and self.step_id != self.step_name:
            raise ValueError(
                f"CustomTwoQubit uses step_name as its step_id; got step_name="
                f"{self.step_name!r} and step_id={self.step_id!r}"
            )
        self.tasks = list(normalize_calls(self.tasks, where=f"{self.step_name}.tasks"))

    @property
    def name(self) -> str:
        return self.step_name

    def calls(self) -> tuple[TaskCall, ...]:
        return tuple(self.tasks)

    @property
    def requires(self) -> set[str]:
        return {"candidate_qids"}

    @property
    def provides(self) -> set[str]:
        return {self.step_name, "candidate_couplings"}

    def preflight(self, session: CalibSession) -> None:
        """Check manual rounds against the chip before the pipeline starts."""
        _preflight_manual(self, session)

    def execute(
        self,
        session: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute custom 2-qubit calibration."""
        logger = get_run_logger()

        if not self.tasks:
            logger.warning(f"[{self.name}] No tasks specified, skipping")
            return ctx

        plan = self.step_calls(session)
        logger.info(
            f"[{self.name}] Starting with {len(self.tasks)} calls: "
            f"{[call.resolved_call_id for call in self.tasks]}"
        )

        if self._rounds is not None:
            manual_results = _execute_manual_two_qubit(self, session, ctx, plan)
            session.record_stage_result(self.name, manual_results)
            result = self._build_result(manual_results)
            ctx.metadata[self.step_name] = result
            ctx.record_step_result(self.resolved_step_id, result)
            logger.info(
                f"[{self.name}] Completed. "
                f"{len(result.successful_couplings())}/{len(manual_results)} successful"
            )
            return ctx

        # Use pre-generated schedule if available, otherwise generate
        if "cr_schedule" in ctx.metadata:
            parallel_groups = ctx.metadata["cr_schedule"]
            logger.info(f"[{self.name}] Using pre-generated CR schedule")
        else:
            candidate_qubits = ctx.candidate_qids
            if len(candidate_qubits) < 2:
                logger.warning(
                    f"[{self.name}] Not enough candidates ({len(candidate_qubits)}) for 2Q"
                )
                ctx.metadata[self.step_name] = TwoQubitResult(step_id=self.resolved_step_id)
                ctx.record_step_result(self.resolved_step_id, ctx.metadata[self.step_name])
                return ctx

            from qdash.workflow.engine import CRScheduler

            wiring_config_path = str(get_qubex_paths().wiring_yaml(session.chip_id))
            scheduler = CRScheduler(
                session.username,
                session.chip_id,
                wiring_config_path=wiring_config_path,
                project_id=session.project_id,
            )
            schedule = scheduler.generate(
                candidate_qubits=candidate_qubits,
                max_parallel_ops=_max_parallel_ops(self),
            )
            parallel_groups = schedule.parallel_groups

        if not parallel_groups:
            logger.warning(f"[{self.name}] No valid CR pairs found")
            ctx.metadata[self.step_name] = TwoQubitResult(step_id=self.resolved_step_id)
            ctx.record_step_result(self.resolved_step_id, ctx.metadata[self.step_name])
            return ctx

        coupling_groups = [[f"{c}-{t}" for c, t in group] for group in parallel_groups]
        total_pairs = sum(len(g) for g in coupling_groups)
        logger.info(
            f"[{self.name}] Executing {total_pairs} coupling pairs in {len(coupling_groups)} groups"
        )

        all_raw_results = _run_coupling_groups(session, coupling_groups, plan)

        session.record_stage_result(self.name, all_raw_results)

        # Build typed result
        result = self._build_result(all_raw_results)
        ctx.metadata[self.step_name] = result
        ctx.record_step_result(self.resolved_step_id, result)

        logger.info(
            f"[{self.name}] Completed. "
            f"{len(result.successful_couplings())}/{total_pairs} successful"
        )
        return ctx

    def _build_result(self, raw_results: dict[str, Any]) -> TwoQubitResult:
        """Build typed result from raw backend data."""
        return build_two_qubit_result(raw_results, self.resolved_step_id, self._extract_metrics)

    def _extract_metrics(self, raw: dict[str, Any]) -> dict[str, float]:
        """Custom steps derive no metrics; read calls with ``CouplingCalibData.call``."""
        return {}


@dataclass
class SetCRSchedule(TransformStep):
    """Set pre-defined CR schedule for 2-qubit calibration.

    Use this step when you have a pre-computed schedule (e.g., from external
    scheduling logic or manual specification) instead of auto-generating it.

    The schedule is a list of parallel groups, where each group contains
    (control, target) qubit ID tuples that can be executed in parallel.

    Requires: nothing
    Provides: candidate_couplings, candidate_qids

    Example:
        # Manual schedule with 2 parallel groups
        SetCRSchedule(
            schedule=[
                [("0", "1"), ("4", "5")],   # Group 1: run in parallel
                [("2", "3"), ("8", "9")],   # Group 2: run after group 1
            ]
        )
    """

    schedule: list[list[tuple[str, str]]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return "set_cr_schedule"

    @property
    def requires(self) -> set[str]:
        return set()

    @property
    def provides(self) -> set[str]:
        return {"candidate_couplings", "candidate_qids"}

    def execute(
        self,
        session: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Set the CR schedule from external input."""
        logger = get_run_logger()

        if not self.schedule:
            logger.warning(f"[{self.name}] Empty schedule provided")
            ctx.candidate_couplings = []
            ctx.candidate_qids = []
            return ctx

        # Flatten to coupling IDs
        all_couplings = [f"{c}-{t}" for group in self.schedule for c, t in group]
        ctx.candidate_couplings = all_couplings

        # Extract unique qubit IDs
        qids = set()
        for group in self.schedule:
            for control, target in group:
                qids.add(control)
                qids.add(target)
        ctx.candidate_qids = sorted(qids)

        # Store schedule in metadata for TwoQubitCalibration
        ctx.metadata["cr_schedule"] = self.schedule

        logger.info(
            f"[{self.name}] Set {len(all_couplings)} couplings in "
            f"{len(self.schedule)} parallel groups"
        )
        return ctx


@dataclass
class GenerateCRSchedule(TransformStep):
    """Generate CR (Cross-Resonance) schedule for 2-qubit calibration.

    Uses CRScheduler to generate parallel execution groups based on:
    - MUX conflicts
    - Frequency constraints
    - Candidate qubit availability

    The `inverse` parameter controls the CR direction based on the checkerboard pattern:
    - False (default): Forward direction (control has lower frequency by design)
    - True: Reverse direction (control has higher frequency by design)

    Requires: candidate_qids (at least 2 qubits)
    Provides: candidate_couplings (scheduled coupling pairs)
    """

    max_parallel_ops: int = 10
    inverse: bool = False

    @property
    def name(self) -> str:
        return "generate_cr_schedule"

    @property
    def requires(self) -> set[str]:
        return {"candidate_qids"}

    @property
    def provides(self) -> set[str]:
        return {"candidate_couplings"}

    def execute(
        self,
        session: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Generate CR schedule from candidate qubits."""
        logger = get_run_logger()

        candidate_qubits = ctx.candidate_qids
        if len(candidate_qubits) < 2:
            logger.warning(f"[{self.name}] Not enough candidates ({len(candidate_qubits)}) for 2Q")
            ctx.candidate_couplings = []
            return ctx

        from qdash.workflow.engine import CRScheduler

        wiring_config_path = str(get_qubex_paths().wiring_yaml(session.chip_id))
        scheduler = CRScheduler(
            session.username,
            session.chip_id,
            wiring_config_path=wiring_config_path,
            project_id=session.project_id,
        )
        schedule = scheduler.generate(
            candidate_qubits=candidate_qubits,
            max_parallel_ops=self.max_parallel_ops,
            inverse=self.inverse,
        )

        if not schedule.parallel_groups:
            logger.warning(f"[{self.name}] No valid CR pairs found")
            ctx.candidate_couplings = []
            return ctx

        # Flatten to coupling IDs
        all_couplings = [f"{c}-{t}" for group in schedule.parallel_groups for c, t in group]
        ctx.candidate_couplings = all_couplings

        # Store schedule in metadata for TwoQubitCalibration
        ctx.metadata["cr_schedule"] = schedule.parallel_groups

        direction = "reverse" if self.inverse else "forward"
        logger.info(
            f"[{self.name}] Generated {len(all_couplings)} couplings in "
            f"{len(schedule.parallel_groups)} groups (direction: {direction})"
        )
        return ctx


@dataclass
class TwoQubitCalibration(CalibrationStep):
    """2-qubit coupling calibration step.

    Executes FULL_2Q_TASKS on scheduled coupling pairs.
    Uses schedule from GenerateCRSchedule if available in ctx.metadata["cr_schedule"],
    otherwise generates schedule internally.

    With ``execution_mode="manual"`` it runs ``rounds`` of directed pairs exactly
    as written instead, and ``max_parallel_ops`` is rejected.

    Requires: candidate_qids (and optionally cr_schedule in metadata)
    Provides: two_qubit, candidate_couplings
    """

    tasks: list[TaskCall] | None = None
    max_parallel_ops: int | None = None
    execution_mode: TwoQubitExecutionMode = "automatic"
    rounds: list[list[tuple[str, str]]] | None = None

    def __post_init__(self) -> None:
        self._rounds = _init_mode(self)
        calls = self.tasks if self.tasks is not None else FULL_2Q_TASKS
        self._calls = normalize_calls(calls, where=f"{self.name}.tasks")

    @property
    def name(self) -> str:
        return self.step_id or "two_qubit_calibration"

    def calls(self) -> tuple[TaskCall, ...]:
        return self._calls

    @property
    def requires(self) -> set[str]:
        return {"candidate_qids"}

    @property
    def provides(self) -> set[str]:
        return {"two_qubit", "candidate_couplings"}

    def preflight(self, session: CalibSession) -> None:
        """Check manual rounds against the chip before the pipeline starts."""
        _preflight_manual(self, session)

    def execute(
        self,
        session: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute 2-qubit calibration."""
        logger = get_run_logger()
        plan = self.step_calls(session)

        if self._rounds is not None:
            manual_results = _execute_manual_two_qubit(self, session, ctx, plan)
            session.record_stage_result(self.name, manual_results)
            ctx.two_qubit = self._build_result(manual_results)
            ctx.record_step_result(self.resolved_step_id, ctx.two_qubit)
            logger.info(
                f"[{self.name}] Completed. "
                f"{len(ctx.two_qubit.successful_couplings())}/{len(manual_results)} successful"
            )
            return ctx

        candidate_qubits = ctx.candidate_qids
        if len(candidate_qubits) < 2:
            logger.warning(f"[{self.name}] Not enough candidates ({len(candidate_qubits)}) for 2Q")
            ctx.two_qubit = TwoQubitResult(step_id=self.resolved_step_id)
            ctx.record_step_result(self.resolved_step_id, ctx.two_qubit)
            return ctx

        # Use pre-generated schedule if available, otherwise generate
        if "cr_schedule" in ctx.metadata:
            parallel_groups = ctx.metadata["cr_schedule"]
            logger.info(f"[{self.name}] Using pre-generated CR schedule")
        else:
            from qdash.workflow.engine import CRScheduler

            wiring_config_path = str(get_qubex_paths().wiring_yaml(session.chip_id))
            scheduler = CRScheduler(
                session.username,
                session.chip_id,
                wiring_config_path=wiring_config_path,
                project_id=session.project_id,
            )
            schedule = scheduler.generate(
                candidate_qubits=candidate_qubits,
                max_parallel_ops=_max_parallel_ops(self),
            )
            parallel_groups = schedule.parallel_groups

        if not parallel_groups:
            logger.warning(f"[{self.name}] No valid CR pairs found")
            ctx.two_qubit = TwoQubitResult(step_id=self.resolved_step_id)
            ctx.record_step_result(self.resolved_step_id, ctx.two_qubit)
            return ctx

        coupling_groups = [[f"{c}-{t}" for c, t in group] for group in parallel_groups]
        total_pairs = sum(len(g) for g in coupling_groups)
        logger.info(
            f"[{self.name}] Executing {total_pairs} coupling pairs in {len(coupling_groups)} groups"
        )

        all_raw_results = _run_coupling_groups(session, coupling_groups, plan)

        session.record_stage_result(self.name, all_raw_results)

        # Build typed result
        result = self._build_result(all_raw_results)
        ctx.two_qubit = result
        ctx.record_step_result(self.resolved_step_id, result)

        logger.info(
            f"[{self.name}] Completed. "
            f"{len(result.successful_couplings())}/{total_pairs} successful"
        )
        return ctx

    def _build_result(self, raw_results: dict[str, Any]) -> TwoQubitResult:
        """Build typed result from raw backend data."""
        return build_two_qubit_result(raw_results, self.resolved_step_id, self._extract_metrics)

    def _extract_metrics(self, raw: dict[str, Any]) -> dict[str, float]:
        """Extract metrics from the latest call of each task in the step."""
        metrics = {}
        for task_name, parameter, metric in (
            ("ZX90InterleavedRandomizedBenchmarking", "zx90_gate_fidelity", "zx90_fidelity"),
            ("CheckBellState", "bell_fidelity", "bell_fidelity"),
            (
                "Check2QGateCoherenceLimit",
                "two_qubit_gate_coherence_limit",
                "two_qubit_gate_coherence_limit",
            ),
        ):
            value = normalize_metric_value(latest_call_output(raw, task_name).get(parameter))
            if value is not None:
                metrics[metric] = value
        return metrics
