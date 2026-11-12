"""Calibration strategy classes for one-qubit calibration steps.

Each one-qubit execution mode maps to one strategy here. The mode names, their
deprecated aliases and the difference between rounds and MUX parallelism are
defined in :mod:`qdash.datamodel.one_qubit_execution_mode`. Every strategy keeps
the scheduler's hardware stage constraints; the strategies differ only in how
targets wait for each other, and every target runs the step's full call list.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from prefect import get_run_logger

from qdash.datamodel.one_qubit_execution_mode import resolve_one_qubit_execution_mode
from qdash.workflow.engine import OneQubitScheduler
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
from qdash.workflow.service._internal.scheduling_tasks import (
    calibrate_mux_qubits as _calibrate_mux_qubits,
)
from qdash.workflow.service._internal.scheduling_tasks import (
    run_mux_calibrations_parallel,
    run_qubit_calibrations_parallel,
)

if TYPE_CHECKING:
    from qdash.datamodel.task_call import StepCalls
    from qdash.workflow.service._internal.session import CalibSession


# =============================================================================
# Strategy Data Classes
# =============================================================================


@dataclass
class OneQubitConfig:
    """Configuration for 1-qubit calibration.

    ``plan`` holds the step's normalized calls, its step_id and failure policy.
    The strategy decides only where and when targets run; every target runs the
    plan's calls in order.
    """

    mux_ids: list[int]
    exclude_qids: list[str]
    plan: StepCalls
    qids: list[str] | None = None  # Explicit qubit IDs (overrides mux_ids if set)
    simultaneous_spectroscopy_schedule_mode: str = "local_index"

    @property
    def tasks(self) -> list[str]:
        """Task names in call order, with repeats."""
        return self.plan.task_names()


# =============================================================================
# Strategy Base Class
# =============================================================================


class OneQubitStrategy(ABC):
    """Abstract base class for 1-qubit calibration strategies."""

    @abstractmethod
    def execute(
        self,
        session: CalibSession,
        config: OneQubitConfig,
    ) -> dict[str, Any]:
        """Execute the 1-qubit calibration strategy.

        Args:
            session: CalibSession instance with username, chip_id, etc.
            config: Configuration for the calibration

        Returns:
            Dictionary of results organized by stage
        """
        ...

    def _get_wiring_config_path(self, chip_id: str) -> str:
        """Get the wiring config path for a chip."""
        return str(get_qubex_paths().wiring_yaml(chip_id))

    def _filter_qids(self, qids: list[str], allowed_qids: list[str] | None) -> list[str]:
        """Filter qids to only include those in allowed_qids.

        Args:
            qids: List of qubit IDs to filter
            allowed_qids: List of allowed qubit IDs (None means no filtering)

        Returns:
            Filtered list of qubit IDs
        """
        if allowed_qids is None:
            return qids
        allowed_set = set(allowed_qids)
        return [qid for qid in qids if qid in allowed_set]


# =============================================================================
# Concrete Strategies
# =============================================================================


class OneQubitScheduledStrategy(OneQubitStrategy):
    """``parallel_by_mux`` (formerly ``scheduled``): MUXes in parallel, qubits per MUX in turn.

    Groups qubits by Box type (A/B/MIXED) and executes MUX groups in parallel
    with qubits within each group running sequentially. MUXes do not wait for
    each other between qubits: with MUX0 = {Q0, Q1} and MUX1 = {Q4, Q5}, Q1 may
    start as soon as Q0 finishes while Q4 is still running (illustrative; the
    scheduler decides grouping and order).

    Execution pattern:
        Box_A:
            [MUX0 qubits] parallel with [MUX4 qubits] parallel with ...
        Box_MIXED:
            [MUX1 qubits] parallel with [MUX2 qubits] parallel with ...
    """

    def execute(
        self,
        session: CalibSession,
        config: OneQubitConfig,
    ) -> dict[str, Any]:
        """Execute Box-based scheduled calibration."""
        wiring_config_path = self._get_wiring_config_path(session.chip_id)
        scheduler = OneQubitScheduler(
            chip_id=session.chip_id, wiring_config_path=wiring_config_path
        )
        schedule = scheduler.generate_from_mux(
            mux_ids=config.mux_ids, exclude_qids=config.exclude_qids
        )

        all_results = {}

        # Group stages by box_type to execute same-type stages in one session
        # This handles MIXED stages that are split by Box B module sharing
        stages_by_box: dict[str, list[Any]] = {}
        for stage_info in schedule.stages:
            box_type = stage_info.box_type
            if box_type not in stages_by_box:
                stages_by_box[box_type] = []
            stages_by_box[box_type].append(stage_info)

        # Collect ALL qids across all box types for a single execution
        all_qids: list[str] = []
        box_sequential_groups: dict[str, list[list[list[str]]]] = {}

        for box_type, stages in stages_by_box.items():
            sequential_groups: list[list[list[str]]] = []

            for stage_info in stages:
                filtered_groups = [
                    self._filter_qids(group, config.qids) for group in stage_info.parallel_groups
                ]
                parallel_groups = [g for g in filtered_groups if g]

                if parallel_groups:
                    sequential_groups.append(parallel_groups)
                    for group in parallel_groups:
                        all_qids.extend(group)

            if sequential_groups:
                box_sequential_groups[box_type] = sequential_groups

        # Skip if no qubits remain after filtering
        if not all_qids:
            return {}

        # Deduplicate while preserving order
        all_qids = list(dict.fromkeys(all_qids))

        # Workers borrow the Execution owned by the pipeline step.
        worker = session.worker_spec()

        # Execute stages grouped by box type (sequentially between box types)
        for box_type, sequential_groups in box_sequential_groups.items():
            stage_name = f"Box_{box_type}"
            stage_results = {}

            for parallel_groups in sequential_groups:
                mux_results = run_mux_calibrations_parallel(
                    mux_groups=parallel_groups,
                    plan=config.plan,
                    worker=worker,
                )
                stage_results.update(mux_results)

            all_results[stage_name] = stage_results

        # Record all box results within the current step Execution
        session.record_stage_result("1q_scheduled", all_results)

        return all_results


class OneQubitSynchronizedStrategy(OneQubitStrategy):
    """``parallel_by_round`` (formerly ``synchronized``): rounds of qubits from different MUXes.

    The scheduler selects rounds (``SynchronizedOneQubitScheduleResult.steps``).
    A round is a set of qubits from different MUXes; each qubit of the round
    runs the step's full call list, and the next round starts only after every
    qubit of the round has finished. A round is not a per-task barrier and does
    not synchronize pulse timing. The order within a MUX follows the
    checkerboard ordering strategy.

    With MUX0 = {Q0, Q1} and MUX1 = {Q4, Q5}, Q0 and Q4 both finish before Q1
    and Q5 start (illustrative; the scheduler decides the rounds).

    Execution pattern:
        Round 1: [Q0, Q8, Q16, ...] all in parallel (different MUXes, same position)
        Round 2: [Q1, Q9, Q17, ...] all in parallel
        ...
    """

    def execute(
        self,
        session: CalibSession,
        config: OneQubitConfig,
    ) -> dict[str, Any]:
        """Execute the rounds one after another, the qubits of a round in parallel."""
        logger = get_run_logger()

        wiring_config_path = self._get_wiring_config_path(session.chip_id)
        scheduler = OneQubitScheduler(
            chip_id=session.chip_id, wiring_config_path=wiring_config_path
        )
        schedule = scheduler.generate_synchronized_from_mux(
            mux_ids=config.mux_ids,
            exclude_qids=config.exclude_qids,
            use_checkerboard=True,
        )

        logger.info(f"parallel_by_round schedule: {schedule.total_steps} rounds")

        # Collect ALL qids across all steps for a single execution
        all_qids: list[str] = []
        for step in schedule.steps:
            filtered_qids = self._filter_qids(step.parallel_qids, config.qids)
            all_qids.extend(filtered_qids)

        # Deduplicate while preserving order
        all_qids = list(dict.fromkeys(all_qids))

        if not all_qids:
            return {}

        # Workers borrow the Execution owned by the pipeline step.
        worker = session.worker_spec()

        all_results: dict[str, Any] = {}

        for step in schedule.steps:
            filtered_qids = self._filter_qids(step.parallel_qids, config.qids)
            if not filtered_qids:
                continue

            step_results = run_qubit_calibrations_parallel(
                qids=filtered_qids,
                plan=config.plan,
                worker=worker,
            )
            # Group results by box type for organized output
            box_key = f"Box_{step.box_type}"
            if box_key not in all_results:
                all_results[box_key] = {}
            all_results[box_key].update(step_results)

        # Record all scheduling rounds within the current step Execution
        session.record_stage_result("1q_synchronized", all_results)

        return all_results


class OneQubitSimultaneousSpectroscopyStrategy(OneQubitStrategy):
    """Experimental 4-step local-index strategy for simultaneous spectroscopy."""

    def execute(
        self,
        session: CalibSession,
        config: OneQubitConfig,
    ) -> dict[str, Any]:
        """Execute local-index spectroscopy steps as hardware-aware batches."""
        from qdash.workflow.service.one_qubit_stage_runner import OneQubitStageRunner

        wiring_config_path = self._get_wiring_config_path(session.chip_id)
        scheduler = OneQubitScheduler(
            chip_id=session.chip_id, wiring_config_path=wiring_config_path
        )
        schedule = scheduler.generate_simultaneous_spectroscopy_batches_from_mux(
            mux_ids=config.mux_ids,
            exclude_qids=config.exclude_qids,
            mode=config.simultaneous_spectroscopy_schedule_mode,
        )

        runner = OneQubitStageRunner(session)
        all_qids = runner.collect_simultaneous_qids(schedule, config.qids)
        if not all_qids:
            return {}

        # Reject what the batch path cannot run before any batch measures.
        runner.preflight_batch(config.plan)
        all_results = runner.execute_simultaneous_spectroscopy_schedule(
            schedule,
            plan=config.plan,
            allowed_qids=config.qids,
        )

        session.record_stage_result("experimental_simultaneous_spectroscopy", all_results)
        return all_results


class OneQubitSerialStrategy(OneQubitStrategy):
    """``sequential`` (formerly ``serial``): fully sequential 1-qubit calibration.

    Executes all MUXes one by one, completely sequentially.
    Useful for debugging or when hardware constraints require no parallelism.

    Execution pattern:
        [MUX0 qubits] -> [MUX1 qubits] -> [MUX2 qubits] -> ...
    """

    def execute(
        self,
        session: CalibSession,
        config: OneQubitConfig,
    ) -> dict[str, Any]:
        """Execute fully serial calibration."""
        wiring_config_path = self._get_wiring_config_path(session.chip_id)
        scheduler = OneQubitScheduler(
            chip_id=session.chip_id, wiring_config_path=wiring_config_path
        )
        schedule = scheduler.generate_from_mux(
            mux_ids=config.mux_ids, exclude_qids=config.exclude_qids
        )

        # Collect all qids from all stages
        all_qids = []
        all_mux_groups = []  # Each element is a list of qids for one MUX

        for stage_info in schedule.stages:
            for group in stage_info.parallel_groups:
                filtered_group = self._filter_qids(group, config.qids)
                if filtered_group:
                    all_mux_groups.append(filtered_group)
                    all_qids.extend(filtered_group)

        if not all_qids:
            return {}

        # Execute MUX groups one by one (completely serial) in the parent session
        all_results = {}
        for mux_group in all_mux_groups:
            all_results.update(_calibrate_mux_qubits(qids=mux_group, plan=config.plan))

        session.record_stage_result("1q_serial", all_results)

        return {"serial": all_results}


# =============================================================================
# Strategy Registry
# =============================================================================


ONE_QUBIT_STRATEGIES: dict[str, type[OneQubitStrategy]] = {
    "parallel_by_round": OneQubitSynchronizedStrategy,
    "parallel_by_mux": OneQubitScheduledStrategy,
    "simultaneous_spectroscopy": OneQubitSimultaneousSpectroscopyStrategy,
    "sequential": OneQubitSerialStrategy,
}


def get_one_qubit_strategy(mode: str) -> OneQubitStrategy:
    """Get a 1-qubit calibration strategy by execution mode.

    Args:
        mode: A canonical execution mode (``parallel_by_round``,
            ``parallel_by_mux``, ``sequential`` or ``simultaneous_spectroscopy``).
            The deprecated names ``synchronized``, ``scheduled`` and ``serial``
            are still accepted with a ``DeprecationWarning``.

    Returns:
        Strategy instance

    Raises:
        ValueError: If mode is not recognized
    """
    canonical, _ = resolve_one_qubit_execution_mode(mode, default="parallel_by_round")
    return ONE_QUBIT_STRATEGIES[canonical]()
