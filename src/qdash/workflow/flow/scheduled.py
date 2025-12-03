"""Scheduled calibration helpers for automatic Box/CR scheduling.

High-level functions that combine scheduler + execution for simple user code.

Example:
    from prefect import flow
    from qdash.workflow.flow import init_calibration, finish_calibration
    from qdash.workflow.flow.scheduled import (
        calibrate_one_qubit_scheduled,
        calibrate_two_qubit_scheduled,
    )

    @flow
    def my_calibration(username: str, chip_id: str):
        # 1-qubit calibration with automatic Box scheduling
        results_1q = calibrate_one_qubit_scheduled(
            username=username,
            chip_id=chip_id,
            mux_ids=[0, 1, 2, 3],
            exclude_qids=["5"],
            tasks=["CheckRabi", "CheckT1"],
        )

        # 2-qubit calibration with automatic CR scheduling
        results_2q = calibrate_two_qubit_scheduled(
            username=username,
            chip_id=chip_id,
            one_qubit_results=results_1q,
            tasks=["CheckCrossResonance", "CreateZX90"],
        )

        return {"1qubit": results_1q, "2qubit": results_2q}
"""

from __future__ import annotations

from typing import Any

from prefect import get_run_logger, task
from qdash.workflow.engine.calibration import CRScheduler, OneQubitScheduler
from qdash.workflow.flow.github import ConfigFileType, GitHubPushConfig
from qdash.workflow.flow.session import finish_calibration, get_session, init_calibration

# =============================================================================
# Default Task Lists
# =============================================================================

FULL_1Q_TASKS = [
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CreatePIPulse",
    "CheckPIPulse",
    "CheckT1",
    "CheckT2Echo",
    "CreateDRAGHPIPulse",
    "CheckDRAGHPIPulse",
    "CreateDRAGPIPulse",
    "CheckDRAGPIPulse",
    "ReadoutClassification",
    "RandomizedBenchmarking",
    "X90InterleavedRandomizedBenchmarking",
]

FULL_2Q_TASKS = [
    "CheckCrossResonance",
    "CreateZX90",
    "CheckZX90",
    "CheckBellState",
]


# =============================================================================
# Internal Prefect Tasks
# =============================================================================


@task
def _calibrate_mux_qubits(qids: list[str], tasks: list[str]) -> dict:
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
def _calibrate_single_qubit(qid: str, tasks: list[str]) -> tuple[str, dict]:
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
def _calibrate_step_qubits_parallel(parallel_qids: list[str], tasks: list[str]) -> dict:
    """Execute tasks for all qubits in a synchronized step in parallel.

    All qubits in parallel_qids are from different MUXes and can be
    calibrated simultaneously in a synchronized step.
    """
    # Submit all qubits in parallel
    futures = [_calibrate_single_qubit.submit(qid, tasks) for qid in parallel_qids]
    pair_results = [f.result() for f in futures]
    return {qid: result for qid, result in pair_results}


@task
def _execute_coupling_pair(coupling_qid: str, tasks: list[str]) -> tuple[str, dict]:
    """Execute tasks for a single coupling pair."""
    logger = get_run_logger()
    session = get_session()

    try:
        result = {}
        for task_name in tasks:
            task_result = session.execute_task(task_name, coupling_qid)
            result[task_name] = task_result
        result["status"] = "success"
    except Exception as e:
        logger.error(f"Failed to calibrate coupling {coupling_qid}: {e}")
        result = {"status": "failed", "error": str(e)}

    return coupling_qid, result


@task
def _calibrate_parallel_group(coupling_qids: list[str], tasks: list[str]) -> dict:
    """Execute coupling tasks for a parallel group."""
    futures = [_execute_coupling_pair.submit(cqid, tasks) for cqid in coupling_qids]
    pair_results = [f.result() for f in futures]
    return {qid: result for qid, result in pair_results}


# =============================================================================
# Utility Functions
# =============================================================================


def extract_candidate_qubits(
    one_qubit_results: dict[str, Any],
    x90_fidelity_threshold: float = 0.90,
) -> list[str]:
    """Extract qubits with high X90 gate fidelity from 1-qubit results.

    Args:
        one_qubit_results: Results from calibrate_one_qubit_scheduled
        x90_fidelity_threshold: Minimum X90 gate fidelity (default: 0.90)

    Returns:
        List of qubit IDs that meet the fidelity threshold
    """
    candidates = []
    for stage_name, stage_data in one_qubit_results.items():
        if not isinstance(stage_data, dict):
            continue
        for qid, result in stage_data.items():
            if not isinstance(result, dict):
                continue
            if result.get("status") != "success":
                continue

            irb_result = result.get("X90InterleavedRandomizedBenchmarking", {})
            x90_fidelity_param = irb_result.get("x90_gate_fidelity")

            if x90_fidelity_param is not None:
                x90_fidelity = x90_fidelity_param.value if hasattr(x90_fidelity_param, "value") else x90_fidelity_param
                if x90_fidelity >= x90_fidelity_threshold:
                    candidates.append(qid)

    return sorted(set(candidates))


def get_wiring_config_path(chip_id: str) -> str:
    """Get the wiring config path for a chip."""
    return f"/app/config/qubex/{chip_id}/config/wiring.yaml"


# =============================================================================
# High-Level Calibration Functions
# =============================================================================


def calibrate_one_qubit_scheduled(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    tasks: list[str] | None = None,
    flow_name: str | None = None,
) -> dict[str, Any]:
    """Execute 1-qubit calibration with automatic Box scheduling.

    Uses OneQubitScheduler to detect Box A/B constraints from wiring config
    and groups qubits for sequential execution within each Box.

    Args:
        username: User name
        chip_id: Chip ID
        mux_ids: List of MUX IDs to calibrate. If None, uses all 16 MUXes (0-15)
        exclude_qids: List of qubit IDs to exclude from calibration
        tasks: List of 1-qubit task names. If None, uses FULL_1Q_TASKS
        flow_name: Flow name prefix for stage names

    Returns:
        Dictionary of results organized by Box stage:
        {"Box_A": {...}, "Box_B": {...}, "Box_MIXED": {...}}

    Example:
        results = calibrate_one_qubit_scheduled(
            username="alice",
            chip_id="64Qv3",
            mux_ids=[0, 1, 2, 3],
            exclude_qids=["5", "12"],
            tasks=["CheckRabi", "CheckT1"],
        )
    """
    # Defaults
    if mux_ids is None:
        mux_ids = list(range(16))
    if exclude_qids is None:
        exclude_qids = []
    if tasks is None:
        tasks = FULL_1Q_TASKS

    # Generate schedule
    wiring_config_path = get_wiring_config_path(chip_id)
    scheduler = OneQubitScheduler(chip_id=chip_id, wiring_config_path=wiring_config_path)
    schedule = scheduler.generate_from_mux(mux_ids=mux_ids, exclude_qids=exclude_qids)

    all_results = {}

    # Execute each Box stage
    for stage_info in schedule.stages:
        stage_name = f"Box_{stage_info.box_type}"

        # Use parallel_groups from scheduler (MUX-based grouping)
        # Each group can run in parallel, qubits within group run sequentially
        parallel_groups = stage_info.parallel_groups

        init_calibration(
            username,
            chip_id,
            stage_info.qids,
            flow_name=f"{flow_name}_{stage_name}" if flow_name else stage_name,
            enable_github_pull=True,
            github_push_config=GitHubPushConfig(
                enabled=True,
                file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
            ),
            note={
                "type": "1-qubit",
                "box": stage_info.box_type,
                "schedule": parallel_groups,  # [[mux0_qids], [mux1_qids], ...] - groups run in parallel
            },
        )

        # Execute MUX groups in parallel, qubits within each group sequentially
        futures = [_calibrate_mux_qubits.submit(qids=group, tasks=tasks) for group in parallel_groups]
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


def calibrate_one_qubit_synchronized(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    tasks: list[str] | None = None,
    flow_name: str | None = None,
) -> dict[str, Any]:
    """Execute 1-qubit calibration with synchronized step-based scheduling.

    All MUXes execute the same step simultaneously before moving to the next.
    Uses checkerboard pattern for frequency isolation and handles Box B module
    sharing constraints (MIXED MUXes get 8 steps instead of 4).

    Total steps for full chip: 12 (4 Box A + 8 MIXED)

    Args:
        username: User name
        chip_id: Chip ID
        mux_ids: List of MUX IDs to calibrate. If None, uses all 16 MUXes (0-15)
        exclude_qids: List of qubit IDs to exclude from calibration
        tasks: List of 1-qubit task names. If None, uses FULL_1Q_TASKS
        flow_name: Flow name prefix for stage names

    Returns:
        Dictionary of results organized by Box stage:
        {"Box_A": {...}, "Box_MIXED": {...}}

    Example:
        results = calibrate_one_qubit_synchronized(
            username="alice",
            chip_id="64Qv3",
            mux_ids=[0, 1, 2, 3],
            exclude_qids=["5", "12"],
            tasks=["CheckRabi", "CheckT1"],
        )
    """
    logger = get_run_logger()

    # Defaults
    if mux_ids is None:
        mux_ids = list(range(16))
    if exclude_qids is None:
        exclude_qids = []
    if tasks is None:
        tasks = FULL_1Q_TASKS

    # Generate synchronized schedule with checkerboard pattern
    wiring_config_path = get_wiring_config_path(chip_id)
    scheduler = OneQubitScheduler(chip_id=chip_id, wiring_config_path=wiring_config_path)
    schedule = scheduler.generate_synchronized_from_mux(
        mux_ids=mux_ids,
        exclude_qids=exclude_qids,
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
            box_qids = [qid for s in schedule.get_steps_by_box(current_box_type) for qid in s.parallel_qids]

            stage_name = f"Box_{current_box_type}"
            init_calibration(
                username,
                chip_id,
                box_qids,
                flow_name=f"{flow_name}_{stage_name}" if flow_name else stage_name,
                enable_github_pull=True,
                github_push_config=GitHubPushConfig(
                    enabled=True,
                    file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
                ),
                note={
                    "type": "1-qubit-synchronized",
                    "box": current_box_type,
                    "total_steps": len(schedule.get_steps_by_box(current_box_type)),
                },
            )

        # Execute synchronized step (all qubits in parallel)
        step_results = _calibrate_step_qubits_parallel(
            parallel_qids=step.parallel_qids,
            tasks=tasks,
        )
        box_session_results.update(step_results)

    # Finish final session
    if current_box_type is not None:
        session = get_session()
        session.record_stage_result(f"1q_Box_{current_box_type}", box_session_results)
        finish_calibration()
        all_results[f"Box_{current_box_type}"] = box_session_results

    return all_results


def calibrate_two_qubit_scheduled(
    username: str,
    chip_id: str,
    one_qubit_results: dict[str, Any] | None = None,
    candidate_qubits: list[str] | None = None,
    tasks: list[str] | None = None,
    flow_name: str | None = None,
    max_parallel_ops: int = 10,
    x90_fidelity_threshold: float = 0.90,
) -> dict[str, Any]:
    """Execute 2-qubit calibration with automatic CR scheduling.

    Uses CRScheduler to generate parallel execution groups based on
    MUX conflicts and frequency directionality.

    Args:
        username: User name
        chip_id: Chip ID
        one_qubit_results: Results from calibrate_one_qubit_scheduled (for filtering)
        candidate_qubits: Explicit list of candidate qubits (overrides filtering)
        tasks: List of 2-qubit task names. If None, uses FULL_2Q_TASKS
        flow_name: Flow name for this stage
        max_parallel_ops: Maximum parallel operations per group
        x90_fidelity_threshold: Minimum X90 fidelity for candidate filtering

    Returns:
        Dictionary of results keyed by coupling ID ("control-target")

    Example:
        # Option 1: Use filtering from 1-qubit results
        results_2q = calibrate_two_qubit_scheduled(
            username="alice",
            chip_id="64Qv3",
            one_qubit_results=results_1q,
            tasks=["CheckCrossResonance"],
        )

        # Option 2: Explicit candidate list
        results_2q = calibrate_two_qubit_scheduled(
            username="alice",
            chip_id="64Qv3",
            candidate_qubits=["0", "1", "4", "5"],
            tasks=["CheckCrossResonance"],
        )
    """
    logger = get_run_logger()

    if tasks is None:
        tasks = FULL_2Q_TASKS

    # Determine candidate qubits
    if candidate_qubits is None:
        if one_qubit_results is None:
            msg = "Either one_qubit_results or candidate_qubits must be provided"
            raise ValueError(msg)
        candidate_qubits = extract_candidate_qubits(one_qubit_results, x90_fidelity_threshold)

    if len(candidate_qubits) == 0:
        logger.warning("No candidate qubits, skipping 2-qubit calibration")
        return {}

    # Generate CR schedule
    wiring_config_path = get_wiring_config_path(chip_id)
    scheduler = CRScheduler(username, chip_id, wiring_config_path=wiring_config_path)
    schedule = scheduler.generate(
        candidate_qubits=candidate_qubits,
        max_parallel_ops=max_parallel_ops,
    )

    parallel_groups = schedule.parallel_groups
    coupling_groups = [[f"{c}-{t}" for c, t in group] for group in parallel_groups]

    # Initialize session
    init_calibration(
        username,
        chip_id,
        candidate_qubits,
        flow_name=f"{flow_name}_2Qubit" if flow_name else "2Qubit",
        enable_github_pull=False,
        github_push_config=GitHubPushConfig(
            enabled=True,
            file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
        ),
        note={
            "type": "2-qubit",
            "candidate_qubits": candidate_qubits,
            "schedule": coupling_groups,  # [[group1_pairs], [group2_pairs], ...]
        },
    )

    # Execute groups
    all_results = {}
    for group in coupling_groups:
        group_results = _calibrate_parallel_group(coupling_qids=group, tasks=tasks)
        all_results.update(group_results)

    session = get_session()
    session.record_stage_result("2qubit", all_results)
    finish_calibration()

    return all_results
