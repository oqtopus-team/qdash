"""Calibration strategy classes for CalibService.

Strategy pattern implementation for different calibration execution modes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from prefect import get_run_logger

from qdash.workflow.engine import OneQubitScheduler
from qdash.workflow.service._internal.scheduling_tasks import (
    calibrate_mux_qubits as _calibrate_mux_qubits,
    calibrate_step_qubits_parallel as _calibrate_step_qubits_parallel,
)
from qdash.workflow.service.calib_service import finish_calibration, get_session, init_calibration
from qdash.workflow.service.github import ConfigFileType, GitHubPushConfig

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService


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
    qids: list[str] | None = None  # Explicit qubit IDs (overrides mux_ids if set)


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
        ...

    def _get_wiring_config_path(self, chip_id: str) -> str:
        """Get the wiring config path for a chip."""
        return f"/app/config/qubex/{chip_id}/config/wiring.yaml"

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

            # Filter parallel groups by allowed qids (if config.qids is set)
            filtered_groups = [
                self._filter_qids(group, config.qids) for group in stage_info.parallel_groups
            ]
            # Remove empty groups
            parallel_groups = [g for g in filtered_groups if g]

            # Skip stage if no qubits remain after filtering
            if not parallel_groups:
                continue

            # Get filtered qids for this stage
            stage_qids = [qid for group in parallel_groups for qid in group]

            # Determine flow name for this stage
            stage_flow_name = f"{config.flow_name}_{stage_name}" if config.flow_name else stage_name

            init_calibration(
                cal_service.username,
                cal_service.chip_id,
                stage_qids,
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
                    "total_qubits": len(stage_qids),
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
            # Filter parallel_qids by allowed qids (if config.qids is set)
            filtered_qids = self._filter_qids(step.parallel_qids, config.qids)

            # Skip step if no qubits remain after filtering
            if not filtered_qids:
                continue

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

                # Filter box_qids by allowed qids
                box_qids = self._filter_qids(
                    [qid for s in box_steps for qid in s.parallel_qids],
                    config.qids,
                )

                # Build schedule info: list of filtered parallel qid groups per step
                schedule_steps = [
                    self._filter_qids(s.parallel_qids, config.qids) for s in box_steps
                ]
                # Remove empty steps from schedule info
                schedule_steps = [s for s in schedule_steps if s]

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
                        "total_steps": len(schedule_steps),
                        "schedule": schedule_steps,
                    },
                )

            # Execute synchronized step (all qubits in parallel)
            step_results = _calibrate_step_qubits_parallel(
                parallel_qids=filtered_qids,
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
