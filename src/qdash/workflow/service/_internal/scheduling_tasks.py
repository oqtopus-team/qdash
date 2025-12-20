"""Internal Prefect tasks for calibration workflows.

This module consolidates common Prefect tasks used across calibration strategies.
These are internal implementation details and should not be imported directly.

Tasks:
    calibrate_mux_qubits: Execute tasks for qubits in a single MUX sequentially
    calibrate_single_qubit: Execute tasks for a single qubit
    calibrate_step_qubits_parallel: Execute tasks for synchronized step in parallel
    execute_coupling_pair: Execute tasks for a single coupling pair
    calibrate_parallel_group: Execute coupling tasks for a parallel group
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prefect import get_run_logger, task

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService


def _get_session() -> "CalibService":
    """Get the current session from global context (internal use)."""
    from qdash.workflow.service.session_context import get_current_session

    session = get_current_session()
    if session is None:
        msg = "No active calibration session."
        raise RuntimeError(msg)
    return session


# =============================================================================
# MUX-level Tasks (for scheduled/strategy execution)
# =============================================================================


@task
def calibrate_mux_qubits(qids: list[str], tasks: list[str]) -> dict[str, Any]:
    """Execute tasks for qubits in a single MUX sequentially.

    Args:
        qids: List of qubit IDs in the MUX
        tasks: List of task names to execute

    Returns:
        Dictionary mapping qid to results
    """
    logger = get_run_logger()
    session = _get_session()
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
def calibrate_single_qubit(qid: str, tasks: list[str]) -> tuple[str, dict[str, Any]]:
    """Execute tasks for a single qubit.

    Args:
        qid: Qubit ID
        tasks: List of task names to execute

    Returns:
        Tuple of (qid, results)
    """
    logger = get_run_logger()
    session = _get_session()

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
def calibrate_step_qubits_parallel(parallel_qids: list[str], tasks: list[str]) -> dict[str, Any]:
    """Execute tasks for all qubits in a synchronized step in parallel.

    All qubits in parallel_qids are from different MUXes and can be
    calibrated simultaneously in a synchronized step.

    Args:
        parallel_qids: List of qubit IDs to calibrate in parallel
        tasks: List of task names to execute

    Returns:
        Dictionary mapping qid to results
    """
    # Submit all qubits in parallel
    futures = [calibrate_single_qubit.submit(qid, tasks) for qid in parallel_qids]
    pair_results = [f.result() for f in futures]
    return {qid: result for qid, result in pair_results}


# =============================================================================
# Coupling Tasks (for 2-qubit calibration)
# =============================================================================


@task
def execute_coupling_pair(coupling_qid: str, tasks: list[str]) -> tuple[str, dict[str, Any]]:
    """Execute tasks for a single coupling pair.

    Args:
        coupling_qid: Coupling ID (e.g., "0-1")
        tasks: List of task names to execute

    Returns:
        Tuple of (coupling_qid, results)
    """
    logger = get_run_logger()
    session = _get_session()

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
def calibrate_parallel_group(coupling_qids: list[str], tasks: list[str]) -> dict[str, Any]:
    """Execute coupling tasks for a parallel group.

    Args:
        coupling_qids: List of coupling IDs (e.g., ["0-1", "2-3"])
        tasks: List of task names to execute

    Returns:
        Dictionary mapping coupling_qid to results
    """
    futures = [execute_coupling_pair.submit(cqid, tasks) for cqid in coupling_qids]
    pair_results = [f.result() for f in futures]
    return {qid: result for qid, result in pair_results}
