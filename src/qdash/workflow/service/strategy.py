"""Calibration strategy classes for CalibService.

Strategy pattern implementation for different calibration execution modes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from prefect import get_run_logger, task

from qdash.workflow.engine.calibration import OneQubitScheduler
from qdash.workflow.service.github import ConfigFileType, GitHubPushConfig
from qdash.workflow.service.session import finish_calibration, get_session, init_calibration

if TYPE_CHECKING:
    from qdash.workflow.service.session import CalibService


# =============================================================================
# Internal Prefect Tasks
# =============================================================================


@task
def _calibrate_mux_qubits(qids: list[str], tasks: list[str]) -> dict[str, Any]:
    """Execute tasks for qubits in a single MUX sequentially."""
    logger = get_run_logger()
    session = get_session()
    results = {}

    for qid in qids:
        try:
            result = {}
            for task_name in tasks:
                task_result = session.execute_task(task_name, qid)
                result[task_name] = task_result
            result["status"] = "success"
        except Exception as e:
            logger.error(f"Failed to calibrate qubit {qid}: {e}")
            result = {"status": "failed", "error": str(e)}
        results[qid] = result

    return results


@task
def _calibrate_single_qubit(qid: str, tasks: list[str]) -> tuple[str, dict[str, Any]]:
    """Execute tasks for a single qubit."""
    logger = get_run_logger()
    session = get_session()

    try:
        result = {}
        for task_name in tasks:
            task_result = session.execute_task(task_name, qid)
            result[task_name] = task_result
        result["status"] = "success"
    except Exception as e:
        logger.error(f"Failed to calibrate qubit {qid}: {e}")
        result = {"status": "failed", "error": str(e)}

    return qid, result


@task
def _calibrate_step_qubits_parallel(parallel_qids: list[str], tasks: list[str]) -> dict[str, Any]:
    """Execute tasks for all qubits in a synchronized step in parallel."""
    futures = [_calibrate_single_qubit.submit(qid, tasks) for qid in parallel_qids]
    pair_results = [f.result() for f in futures]
    return {qid: result for qid, result in pair_results}


# =============================================================================
# Strategy Data Classes
# =============================================================================


@dataclass
class OneQubitConfig:
    """Configuration for 1-qubit calibration."""

    mux_ids: list[int]
    exclude_qids: list[str]
    tasks: list[str]
    flow_name: str | None
    project_id: str | None


# =============================================================================
# Strategy Base Class
# =============================================================================


class OneQubitStrategy(ABC):
    """Abstract base class for 1-qubit calibration strategies."""

    @abstractmethod
    def execute(
        self,
        cal_service: CalibService,
        config: OneQubitConfig,
    ) -> dict[str, Any]:
        """Execute the 1-qubit calibration strategy.

        Args:
            cal_service: CalibService instance with username, chip_id, etc.
            config: Configuration for the calibration

        Returns:
            Dictionary of results organized by stage
        """
        pass

    def _get_wiring_config_path(self, chip_id: str) -> str:
        """Get the wiring config path for a chip."""
        return f"/app/config/qubex/{chip_id}/config/wiring.yaml"


# =============================================================================
# Concrete Strategies
# =============================================================================


class OneQubitScheduledStrategy(OneQubitStrategy):
    """Box-based scheduled 1-qubit calibration.

    Groups qubits by Box type (A/B/MIXED) and executes MUX groups in parallel
    with qubits within each group running sequentially.

    Execution pattern:
        Box_A:
            [MUX0 qubits] parallel with [MUX4 qubits] parallel with ...
        Box_MIXED:
            [MUX1 qubits] parallel with [MUX2 qubits] parallel with ...
    """

    def execute(
        self,
        cal_service: CalibService,
        config: OneQubitConfig,
    ) -> dict[str, Any]:
        """Execute Box-based scheduled calibration."""
        wiring_config_path = self._get_wiring_config_path(cal_service.chip_id)
        scheduler = OneQubitScheduler(
            chip_id=cal_service.chip_id, wiring_config_path=wiring_config_path
        )
        schedule = scheduler.generate_from_mux(
            mux_ids=config.mux_ids, exclude_qids=config.exclude_qids
        )

        all_results = {}

        for stage_info in schedule.stages:
            stage_name = f"Box_{stage_info.box_type}"
            parallel_groups = stage_info.parallel_groups

            # Determine flow name for this stage
            stage_flow_name = f"{config.flow_name}_{stage_name}" if config.flow_name else stage_name

            init_calibration(
                cal_service.username,
                cal_service.chip_id,
                stage_info.qids,
                flow_name=stage_flow_name,
                tags=[config.flow_name] if config.flow_name else None,
                project_id=config.project_id,
                enable_github_pull=True,
                github_push_config=GitHubPushConfig(
                    enabled=True,
                    file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
                ),
                note={
                    "type": "1-qubit-scheduled",
                    "box": stage_info.box_type,
                    "schedule": parallel_groups,
                    "total_groups": len(parallel_groups),
                    "total_qubits": len(stage_info.qids),
                },
            )

            # Execute MUX groups in parallel, qubits within each group sequentially
            futures = [
                _calibrate_mux_qubits.submit(qids=group, tasks=config.tasks)
                for group in parallel_groups
            ]
            mux_results = [f.result() for f in futures]

            # Combine results
            stage_results = {}
            for result in mux_results:
                stage_results.update(result)

            session = get_session()
            session.record_stage_result(f"1q_{stage_name}", stage_results)
            finish_calibration()

            all_results[stage_name] = stage_results

        return all_results


class OneQubitSynchronizedStrategy(OneQubitStrategy):
    """Synchronized step-based 1-qubit calibration.

    All MUXes execute the same step simultaneously before moving to the next.
    Uses checkerboard pattern for frequency isolation.

    Execution pattern:
        Step 1: [Q0, Q8, Q16, ...] all in parallel (different MUXes, same position)
        Step 2: [Q1, Q9, Q17, ...] all in parallel
        ...
    """

    def execute(
        self,
        cal_service: CalibService,
        config: OneQubitConfig,
    ) -> dict[str, Any]:
        """Execute synchronized step-based calibration."""
        logger = get_run_logger()

        wiring_config_path = self._get_wiring_config_path(cal_service.chip_id)
        scheduler = OneQubitScheduler(
            chip_id=cal_service.chip_id, wiring_config_path=wiring_config_path
        )
        schedule = scheduler.generate_synchronized_from_mux(
            mux_ids=config.mux_ids,
            exclude_qids=config.exclude_qids,
            use_checkerboard=True,
        )

        logger.info(f"Synchronized schedule: {schedule.total_steps} steps")

        all_results = {}
        current_box_type = None
        box_session_results = {}

        for step in schedule.steps:
            # Start new session when box type changes
            if step.box_type != current_box_type:
                # Finish previous session
                if current_box_type is not None:
                    session = get_session()
                    session.record_stage_result(f"1q_Box_{current_box_type}", box_session_results)
                    finish_calibration()
                    all_results[f"Box_{current_box_type}"] = box_session_results
                    box_session_results = {}

                # Start new session
                current_box_type = step.box_type
                box_steps = schedule.get_steps_by_box(current_box_type)
                box_qids = [qid for s in box_steps for qid in s.parallel_qids]

                # Build schedule info: list of parallel qid groups per step
                schedule_steps = [s.parallel_qids for s in box_steps]

                stage_name = f"Box_{current_box_type}"
                stage_flow_name = (
                    f"{config.flow_name}_{stage_name}" if config.flow_name else stage_name
                )

                init_calibration(
                    cal_service.username,
                    cal_service.chip_id,
                    box_qids,
                    flow_name=stage_flow_name,
                    tags=[config.flow_name] if config.flow_name else None,
                    project_id=config.project_id,
                    enable_github_pull=True,
                    github_push_config=GitHubPushConfig(
                        enabled=True,
                        file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
                    ),
                    note={
                        "type": "1-qubit-synchronized",
                        "box": current_box_type,
                        "total_steps": len(box_steps),
                        "schedule": schedule_steps,
                    },
                )

            # Execute synchronized step (all qubits in parallel)
            step_results = _calibrate_step_qubits_parallel(
                parallel_qids=step.parallel_qids,
                tasks=config.tasks,
            )
            box_session_results.update(step_results)

        # Finish final session
        if current_box_type is not None:
            session = get_session()
            session.record_stage_result(f"1q_Box_{current_box_type}", box_session_results)
            finish_calibration()
            all_results[f"Box_{current_box_type}"] = box_session_results

        return all_results


# =============================================================================
# Strategy Registry
# =============================================================================


ONE_QUBIT_STRATEGIES: dict[str, type[OneQubitStrategy]] = {
    "synchronized": OneQubitSynchronizedStrategy,
    "scheduled": OneQubitScheduledStrategy,
}


def get_one_qubit_strategy(mode: str) -> OneQubitStrategy:
    """Get a 1-qubit calibration strategy by mode name.

    Args:
        mode: Strategy mode ("synchronized" or "scheduled")

    Returns:
        Strategy instance

    Raises:
        ValueError: If mode is not recognized
    """
    if mode not in ONE_QUBIT_STRATEGIES:
        valid_modes = ", ".join(ONE_QUBIT_STRATEGIES.keys())
        raise ValueError(f"Unknown mode '{mode}'. Valid modes: {valid_modes}")
    return ONE_QUBIT_STRATEGIES[mode]()
