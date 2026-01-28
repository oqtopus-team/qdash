"""Calibration strategy classes for CalibService.

Strategy pattern implementation for different calibration execution modes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from prefect import get_run_logger
from qdash.workflow.engine import OneQubitScheduler
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
from qdash.workflow.service._internal.scheduling_tasks import (
    calibrate_mux_qubits as _calibrate_mux_qubits,
)
from qdash.workflow.service._internal.scheduling_tasks import (
    run_mux_calibrations_parallel,
    run_qubit_calibrations_parallel,
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

        # Group stages by box_type to execute same-type stages in one session
        # This handles MIXED stages that are split by Box B module sharing
        stages_by_box: dict[str, list[Any]] = {}
        for stage_info in schedule.stages:
            box_type = stage_info.box_type
            if box_type not in stages_by_box:
                stages_by_box[box_type] = []
            stages_by_box[box_type].append(stage_info)

        # Execute stages grouped by box type
        for box_type, stages in stages_by_box.items():
            stage_name = f"Box_{box_type}"

            # Collect all qids and parallel groups for this box type
            all_stage_qids = []
            all_sequential_groups = []  # Groups that must run sequentially

            for stage_info in stages:
                # Filter parallel groups by allowed qids (if config.qids is set)
                filtered_groups = [
                    self._filter_qids(group, config.qids) for group in stage_info.parallel_groups
                ]
                # Remove empty groups
                parallel_groups = [g for g in filtered_groups if g]

                if parallel_groups:
                    all_sequential_groups.append(parallel_groups)
                    for group in parallel_groups:
                        all_stage_qids.extend(group)

            # Skip if no qubits remain after filtering
            if not all_stage_qids:
                continue

            # Determine flow name for this stage
            stage_flow_name = f"{config.flow_name}_{stage_name}" if config.flow_name else stage_name

            init_calibration(
                cal_service.username,
                cal_service.chip_id,
                all_stage_qids,
                flow_name=stage_flow_name,
                backend_name=cal_service.backend_name,  # Inherit backend from parent
                tags=[config.flow_name] if config.flow_name else None,
                project_id=config.project_id,
                use_lock=False,  # Parent session already holds the lock
                enable_github_pull=True,
                github_push_config=GitHubPushConfig(
                    enabled=True,
                    file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
                ),
                note={
                    "type": "1-qubit-scheduled",
                    "box": box_type,
                    "sequential_groups": len(all_sequential_groups),
                    "total_qubits": len(all_stage_qids),
                },
            )

            # Get parent session's execution_id for child sessions
            parent_session = get_session()
            parent_execution_id = parent_session.execution_id

            # Build session config for isolated parallel execution
            session_config = {
                "username": cal_service.username,
                "chip_id": cal_service.chip_id,
                "backend_name": cal_service.backend_name,
                "project_id": config.project_id,
                "muxes": None,  # MUX info not needed for qubit-level tasks
                "execution_id": parent_execution_id,  # Share parent's execution_id
            }

            # Execute sequential groups (for Box B module sharing constraint)
            # Within each sequential group, MUX groups run in parallel (multiprocess)
            stage_results = {}
            for seq_idx, parallel_groups in enumerate(all_sequential_groups):
                # Execute MUX groups in parallel using separate processes
                # Each process has isolated memory, avoiding qubex global state issues
                mux_results = run_mux_calibrations_parallel(
                    mux_groups=parallel_groups,
                    tasks=config.tasks,
                    session_config=session_config,
                )
                stage_results.update(mux_results)

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
                    backend_name=cal_service.backend_name,  # Inherit backend from parent
                    tags=[config.flow_name] if config.flow_name else None,
                    project_id=config.project_id,
                    use_lock=False,  # Parent session already holds the lock
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

            # Get parent session's execution_id for child sessions
            parent_session = get_session()
            parent_execution_id = parent_session.execution_id

            # Build session config for isolated parallel execution
            session_config = {
                "username": cal_service.username,
                "chip_id": cal_service.chip_id,
                "backend_name": cal_service.backend_name,
                "project_id": config.project_id,
                "muxes": None,  # MUX info not needed for qubit-level tasks
                "execution_id": parent_execution_id,  # Share parent's execution_id
            }

            # Execute synchronized step (all qubits in parallel using separate processes)
            # Each process has isolated memory, avoiding qubex global state issues
            step_results = run_qubit_calibrations_parallel(
                qids=filtered_qids,
                tasks=config.tasks,
                session_config=session_config,
            )
            box_session_results.update(step_results)

        # Finish final session
        if current_box_type is not None:
            session = get_session()
            session.record_stage_result(f"1q_Box_{current_box_type}", box_session_results)
            finish_calibration()
            all_results[f"Box_{current_box_type}"] = box_session_results

        return all_results


class OneQubitSerialStrategy(OneQubitStrategy):
    """Fully serial 1-qubit calibration.

    Executes all MUXes one by one, completely sequentially.
    Useful for debugging or when hardware constraints require no parallelism.

    Execution pattern:
        [MUX0 qubits] -> [MUX1 qubits] -> [MUX2 qubits] -> ...
    """

    def execute(
        self,
        cal_service: CalibService,
        config: OneQubitConfig,
    ) -> dict[str, Any]:
        """Execute fully serial calibration."""
        wiring_config_path = self._get_wiring_config_path(cal_service.chip_id)
        scheduler = OneQubitScheduler(
            chip_id=cal_service.chip_id, wiring_config_path=wiring_config_path
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

        # Single session for all MUXes
        stage_flow_name = f"{config.flow_name}_serial" if config.flow_name else "serial"

        init_calibration(
            cal_service.username,
            cal_service.chip_id,
            all_qids,
            flow_name=stage_flow_name,
            backend_name=cal_service.backend_name,
            tags=[config.flow_name] if config.flow_name else None,
            project_id=config.project_id,
            use_lock=False,
            enable_github_pull=True,
            github_push_config=GitHubPushConfig(
                enabled=True,
                file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
            ),
            note={
                "type": "1-qubit-serial",
                "total_mux_groups": len(all_mux_groups),
                "total_qubits": len(all_qids),
            },
        )

        # Execute MUX groups one by one (completely serial)
        all_results = {}
        for mux_group in all_mux_groups:
            # Execute single MUX group (no parallelism)
            result = _calibrate_mux_qubits(qids=mux_group, tasks=config.tasks)
            all_results.update(result)

        session = get_session()
        session.record_stage_result("1q_serial", all_results)
        finish_calibration()

        return {"serial": all_results}


# =============================================================================
# Strategy Registry
# =============================================================================


ONE_QUBIT_STRATEGIES: dict[str, type[OneQubitStrategy]] = {
    "synchronized": OneQubitSynchronizedStrategy,
    "scheduled": OneQubitScheduledStrategy,
    "serial": OneQubitSerialStrategy,
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
