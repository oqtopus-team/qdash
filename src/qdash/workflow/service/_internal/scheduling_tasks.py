"""Internal Prefect tasks for calibration workflows.

This module consolidates common Prefect tasks used across calibration strategies.
These are internal implementation details and should not be imported directly.

Tasks:
    calibrate_mux_qubits: Execute tasks for qubits in a single MUX sequentially
    calibrate_single_qubit: Execute tasks for a single qubit
    calibrate_step_qubits_parallel: Execute tasks for synchronized step in parallel
    execute_coupling_pair: Execute tasks for a single coupling pair
    calibrate_parallel_group: Execute coupling tasks for a parallel group

Multiprocess Parallel Execution (using Dask):
    For parallel execution with isolated sessions, use the multiprocess versions:
    - run_mux_calibrations_parallel: Run multiple MUX groups in parallel processes
    - run_qubit_calibrations_parallel: Run multiple qubits in parallel processes

    These use DaskTaskRunner with processes=True to spawn separate Python processes,
    each with its own memory space. This avoids qubex's global state issues
    (boxpool, device_controller) without requiring locks.
"""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING, Any

from prefect import flow, get_run_logger, task

# DaskTaskRunner is optional - only needed for multiprocess parallel execution
try:
    from prefect_dask import DaskTaskRunner

    _DASK_AVAILABLE = True
except ImportError:
    _DASK_AVAILABLE = False
    DaskTaskRunner = None

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService

# Module-level logger for subprocess execution (Prefect logger not available in subprocesses)
_logger = logging.getLogger(__name__)


def _get_session() -> CalibService:
    """Get the current session from global context (internal use)."""
    from qdash.workflow.service.session_context import get_current_session

    session = get_current_session()
    if session is None:
        msg = "No active calibration session."
        raise RuntimeError(msg)
    return session


def _ensure_prefect_logging() -> None:
    """Ensure Prefect logging is configured in Dask worker processes.

    When using DaskTaskRunner with processes=True or remote clusters,
    the APILogHandler is not automatically attached to loggers in worker
    processes. This function manually sets up logging so that task logs
    appear in the Prefect UI.

    See: https://github.com/PrefectHQ/prefect/issues/18067
    """
    try:
        from prefect.logging.configuration import setup_logging
        from prefect.logging.handlers import APILogHandler

        # First try the standard setup
        setup_logging()

        # Check if APILogHandler is attached to the task_runs logger
        # If not, manually add it (workaround for Dask worker processes)
        task_logger = logging.getLogger("prefect.task_runs")
        has_api_handler = any(isinstance(h, APILogHandler) for h in task_logger.handlers)

        if not has_api_handler:
            handler = APILogHandler()
            task_logger.addHandler(handler)
            # Also add to root prefect logger
            prefect_logger = logging.getLogger("prefect")
            if not any(isinstance(h, APILogHandler) for h in prefect_logger.handlers):
                prefect_logger.addHandler(APILogHandler())

    except Exception:  # noqa: S110
        # Silently ignore if setup fails - logging is best-effort
        pass


def _flush_prefect_logs() -> None:
    """Flush all Prefect log handlers to ensure logs are sent to the API.

    This is critical for Dask worker processes where logs might not be
    flushed before the process exits. Must be called before task completion.

    See: https://github.com/PrefectHQ/prefect/issues/18067
    """
    try:
        from prefect.logging.handlers import APILogHandler

        # Flush all APILogHandler instances
        for handler in logging.root.handlers:
            if isinstance(handler, APILogHandler):
                handler.flush()

        # Also check prefect loggers
        for name in ["prefect", "prefect.task_runs", "prefect.flow_runs"]:
            logger = logging.getLogger(name)
            for handler in logger.handlers:
                if isinstance(handler, APILogHandler):
                    handler.flush()
    except Exception:  # noqa: S110
        # Silently ignore flush errors
        pass


def _format_exception_details(e: Exception) -> str:
    """Format exception details, including sub-exceptions for ExceptionGroup.

    For ExceptionGroup (from asyncio.TaskGroup), this extracts and formats
    all sub-exceptions with their tracebacks for better debugging.
    """
    # Check for ExceptionGroup (Python 3.11+) or exceptiongroup backport
    if hasattr(e, "exceptions"):
        parts = [f"{e}"]
        for i, sub_exc in enumerate(e.exceptions, 1):
            tb_str = "".join(
                traceback.format_exception(type(sub_exc), sub_exc, sub_exc.__traceback__)
            )
            parts.append(f"\n--- Sub-exception {i} ---\n{tb_str}")
        return "".join(parts)
    return "".join(traceback.format_exception(type(e), e, e.__traceback__))


def _create_isolated_session(
    session_config: dict[str, Any],
    qids: list[str],
) -> CalibService:
    """Create an isolated CalibService session for parallel execution.

    This creates a new CalibService instance with its own Experiment,
    avoiding shared state conflicts during parallel execution.

    The isolated session shares the parent's execution_id, so task results
    are recorded under the parent Execution document (not creating new ones).

    Note: When using multiprocessing, each process has isolated memory,
    so no locks are needed. Each process gets its own qubex global state.

    Args:
        session_config: Configuration dict containing:
            - username: Username for the session
            - chip_id: Chip ID
            - backend_name: Backend name (e.g., 'qubex', 'fake')
            - project_id: Project ID (optional)
            - muxes: List of MUX IDs (optional)
            - execution_id: Parent's execution_id (to share Execution document)
        qids: List of qubit IDs for this session

    Returns:
        CalibService instance with isolated backend/Experiment
    """
    from qdash.workflow.service.calib_service import CalibService

    return CalibService(
        username=session_config["username"],
        chip_id=session_config["chip_id"],
        qids=qids,
        execution_id=session_config.get("execution_id"),  # Use parent's execution_id
        backend_name=session_config["backend_name"],
        project_id=session_config.get("project_id"),
        muxes=session_config.get("muxes"),
        use_lock=False,  # Parent session holds the lock
        skip_execution=True,  # Don't create new Execution, use parent's
        enable_github_pull=False,  # Parent session handles GitHub pull
        enable_github=False,  # No GitHub operations for isolated sessions
    )


def _is_mux_representative(qid: str) -> bool:
    """Check if the qubit is the MUX representative (first qubit in MUX).

    For MUX tasks, only the representative qubit (qid % 4 == 0) executes the task.

    Args:
        qid: Qubit ID

    Returns:
        True if this qubit is the MUX representative
    """
    try:
        return int(qid) % 4 == 0
    except ValueError:
        # If qid is not a simple integer, assume it's a representative
        return True


def _should_skip_task_for_qid(task_name: str, qid: str, backend_name: str) -> bool:
    """Check if a task should be skipped for the given qubit.

    MUX tasks are only executed for the representative qubit of each MUX.

    Args:
        task_name: Name of the task
        qid: Qubit ID
        backend_name: Backend name (e.g., 'qubex', 'fake')

    Returns:
        True if the task should be skipped for this qubit
    """
    from qdash.workflow.calibtasks.active_protocols import is_mux_task

    if is_mux_task(task_name, backend_name):
        if not _is_mux_representative(qid):
            return True
    return False


# =============================================================================
# Task Run Name Generators (for Prefect UI visibility)
# =============================================================================


def _mux_task_run_name() -> str:
    """Generate dynamic task name for MUX calibration tasks."""
    from prefect.runtime import task_run

    params = task_run.parameters
    qids = params.get("qids", [])
    if qids:
        # Show MUX number based on first qubit ID
        try:
            mux_num = int(qids[0]) // 4
            return f"mux-{mux_num:02d}-Q{qids[0]}-{qids[-1]}"
        except (ValueError, IndexError):
            return f"mux-Q{qids[0]}-{qids[-1]}"
    return "mux-calibration"


def _single_qubit_task_run_name() -> str:
    """Generate dynamic task name for single qubit calibration tasks."""
    from prefect.runtime import task_run

    params = task_run.parameters
    qid = params.get("qid", "?")
    return f"qubit-{qid}"


def _coupling_task_run_name() -> str:
    """Generate dynamic task name for coupling pair calibration tasks."""
    from prefect.runtime import task_run

    params = task_run.parameters
    coupling_qid = params.get("coupling_qid", "?-?")
    return f"coupling-{coupling_qid}"


def _group_retry_task_run_name() -> str:
    """Generate dynamic task name for group with retry calibration tasks."""
    from prefect.runtime import task_run

    params = task_run.parameters
    qids = params.get("qids", [])
    if qids:
        return f"retry-group-Q{qids[0]}-{qids[-1]}"
    return "retry-group"


# =============================================================================
# MUX-level Tasks (for scheduled/strategy execution)
# =============================================================================


def _execute_mux_qubits_with_session(
    session: CalibService,
    qids: list[str],
    tasks: list[str],
    logger: Any,
) -> dict[str, Any]:
    """Execute tasks for qubits using the provided session.

    Internal helper that performs the actual task execution.
    """
    backend_name = session.backend_name
    results = {}

    for qid in qids:
        try:
            result: dict[str, Any] = {}
            for task_name in tasks:
                # Skip MUX tasks for non-representative qubits
                if _should_skip_task_for_qid(task_name, qid, backend_name):
                    logger.info(
                        f"Skipping MUX task {task_name} for qid={qid} " "(not MUX representative)"
                    )
                    result[task_name] = {"skipped": True, "reason": "not_mux_representative"}
                    continue
                task_result = session.execute_task(task_name, qid)
                result[task_name] = task_result
            result["status"] = "success"
        except Exception as e:
            error_details = _format_exception_details(e)
            logger.error(f"Failed to calibrate qubit {qid}:\n{error_details}")
            result = {"status": "failed", "error": str(e), "error_details": error_details}
        results[qid] = result

    return results


@task(task_run_name=_mux_task_run_name, log_prints=True)
def calibrate_mux_qubits(
    qids: list[str],
    tasks: list[str],
    session_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute tasks for qubits in a single MUX sequentially (Prefect task).

    For MUX-level tasks, only the representative qubit (qid % 4 == 0) executes
    the task. Other qubits in the MUX are skipped for MUX tasks.

    Note: This Prefect task uses threading. For true parallel execution with
    qubex backend, use run_mux_calibrations_multiprocess() instead, which
    spawns separate processes to avoid qubex's global state issues.

    Args:
        qids: List of qubit IDs in the MUX
        tasks: List of task names to execute
        session_config: Optional configuration for creating isolated session.
            If provided, creates independent CalibService. If None, uses
            global session context.

    Returns:
        Dictionary mapping qid to results
    """
    # Ensure Prefect logging is configured in Dask worker processes
    _ensure_prefect_logging()

    logger = get_run_logger()

    # Create isolated session or use global session
    use_isolated = session_config is not None

    if use_isolated:
        assert session_config is not None
        session = _create_isolated_session(session_config, qids)
        try:
            results = _execute_mux_qubits_with_session(session, qids, tasks, logger)
        finally:
            session.finish_calibration(update_chip_history=False, push_to_github=False)
    else:
        session = _get_session()
        results = _execute_mux_qubits_with_session(session, qids, tasks, logger)

    # Flush logs before returning (critical for Dask worker processes)
    _flush_prefect_logs()
    return results


def _execute_single_qubit_with_session(
    session: CalibService,
    qid: str,
    tasks: list[str],
    logger: Any,
) -> dict[str, Any]:
    """Execute tasks for a single qubit using the provided session.

    Internal helper that performs the actual task execution.
    """
    backend_name = session.backend_name
    result: dict[str, Any] = {}

    try:
        for task_name in tasks:
            # Skip MUX tasks for non-representative qubits
            if _should_skip_task_for_qid(task_name, qid, backend_name):
                logger.info(
                    f"Skipping MUX task {task_name} for qid={qid} " "(not MUX representative)"
                )
                result[task_name] = {"skipped": True, "reason": "not_mux_representative"}
                continue
            task_result = session.execute_task(task_name, qid)
            result[task_name] = task_result
        result["status"] = "success"
    except Exception as e:
        error_details = _format_exception_details(e)
        logger.error(f"Failed to calibrate qubit {qid}:\n{error_details}")
        result = {"status": "failed", "error": str(e), "error_details": error_details}

    return result


@task(task_run_name=_single_qubit_task_run_name, log_prints=True)
def calibrate_single_qubit(
    qid: str,
    tasks: list[str],
    session_config: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Execute tasks for a single qubit (Prefect task).

    For MUX-level tasks, only the representative qubit (qid % 4 == 0) executes
    the task. Other qubits in the MUX are skipped for MUX tasks.

    Note: This Prefect task uses threading. For true parallel execution with
    qubex backend, use run_qubit_calibrations_multiprocess() instead, which
    spawns separate processes to avoid qubex's global state issues.

    Args:
        qid: Qubit ID
        tasks: List of task names to execute
        session_config: Optional configuration for creating isolated session.
            If provided, creates independent CalibService. If None, uses
            global session context.

    Returns:
        Tuple of (qid, results)
    """
    # Ensure Prefect logging is configured in Dask worker processes
    _ensure_prefect_logging()

    logger = get_run_logger()

    # Create isolated session or use global session
    use_isolated = session_config is not None

    if use_isolated:
        assert session_config is not None
        session = _create_isolated_session(session_config, [qid])
        try:
            result = _execute_single_qubit_with_session(session, qid, tasks, logger)
        finally:
            session.finish_calibration(update_chip_history=False, push_to_github=False)
    else:
        session = _get_session()
        result = _execute_single_qubit_with_session(session, qid, tasks, logger)

    # Flush logs before returning (critical for Dask worker processes)
    _flush_prefect_logs()
    return qid, result


@task(log_prints=True)
def calibrate_step_qubits_parallel(
    parallel_qids: list[str],
    tasks: list[str],
    session_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute tasks for all qubits in a synchronized step in parallel.

    All qubits in parallel_qids are from different MUXes and can be
    calibrated simultaneously in a synchronized step.

    When session_config is provided, each qubit gets its own isolated
    CalibService with independent Experiment instance, avoiding shared
    state conflicts during parallel execution.

    Args:
        parallel_qids: List of qubit IDs to calibrate in parallel
        tasks: List of task names to execute
        session_config: Optional configuration for creating isolated sessions.
            If provided, each qubit task creates independent CalibService.
            If None, uses global session context.

    Returns:
        Dictionary mapping qid to results
    """
    # Submit all qubits in parallel
    futures = [calibrate_single_qubit.submit(qid, tasks, session_config) for qid in parallel_qids]
    pair_results = [f.result() for f in futures]
    return dict(pair_results)


# =============================================================================
# Coupling Tasks (for 2-qubit calibration)
# =============================================================================


def _execute_coupling_pair_with_session(
    session: CalibService,
    coupling_qid: str,
    tasks: list[str],
    logger: Any,
) -> dict[str, Any]:
    """Execute tasks for a coupling pair using the provided session.

    Internal helper that performs the actual task execution.
    """
    result: dict[str, Any] = {}
    try:
        for task_name in tasks:
            task_result = session.execute_task(task_name, coupling_qid)
            result[task_name] = task_result
        result["status"] = "success"
    except Exception as e:
        error_details = _format_exception_details(e)
        logger.error(f"Failed to calibrate coupling {coupling_qid}:\n{error_details}")
        result = {"status": "failed", "error": str(e), "error_details": error_details}
    return result


@task(task_run_name=_coupling_task_run_name, log_prints=True)
def execute_coupling_pair(
    coupling_qid: str,
    tasks: list[str],
    session_config: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Execute tasks for a single coupling pair.

    Args:
        coupling_qid: Coupling ID (e.g., "0-1")
        tasks: List of task names to execute
        session_config: Optional configuration for creating isolated session.
            If provided, creates independent CalibService. If None, uses
            global session context.

    Returns:
        Tuple of (coupling_qid, results)
    """
    # Ensure Prefect logging is configured in Dask worker processes
    _ensure_prefect_logging()

    logger = get_run_logger()

    # Parse coupling_qid to get involved qubit IDs
    qids = coupling_qid.split("-")

    # Create isolated session or use global session
    use_isolated = session_config is not None

    if use_isolated:
        assert session_config is not None
        session = _create_isolated_session(session_config, qids)
        try:
            result = _execute_coupling_pair_with_session(session, coupling_qid, tasks, logger)
        finally:
            session.finish_calibration(update_chip_history=False, push_to_github=False)
    else:
        session = _get_session()
        result = _execute_coupling_pair_with_session(session, coupling_qid, tasks, logger)

    # Flush logs before returning (critical for Dask worker processes)
    _flush_prefect_logs()
    return coupling_qid, result


@task(log_prints=True)
def calibrate_parallel_group(
    coupling_qids: list[str],
    tasks: list[str],
    session_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute coupling tasks for a parallel group.

    Note: This Prefect task uses threading. For true parallel execution with
    qubex backend, use run_coupling_calibrations_parallel() instead, which
    spawns separate processes to avoid qubex's global state issues.

    Args:
        coupling_qids: List of coupling IDs (e.g., ["0-1", "2-3"])
        tasks: List of task names to execute
        session_config: Optional configuration for creating isolated sessions.
            If provided, each coupling task creates independent CalibService.
            If None, uses global session context.

    Returns:
        Dictionary mapping coupling_qid to results
    """
    futures = [execute_coupling_pair.submit(cqid, tasks, session_config) for cqid in coupling_qids]
    pair_results = [f.result() for f in futures]
    return dict(pair_results)


# =============================================================================
# Multiprocess Parallel Execution (using Dask)
# =============================================================================
# These functions use DaskTaskRunner with processes=True for true parallel
# execution in separate Python processes. This avoids qubex's global state
# issues (boxpool, device_controller) that occur with threaded execution.


def _get_dask_task_runner() -> Any:
    """Get DaskTaskRunner configured for multiprocess execution.

    Raises:
        ImportError: If prefect-dask is not installed
    """
    if not _DASK_AVAILABLE:
        msg = (
            "prefect-dask is required for multiprocess parallel execution. "
            "Install with: pip install prefect-dask"
        )
        raise ImportError(msg)
    return DaskTaskRunner(
        cluster_kwargs={"n_workers": 4, "threads_per_worker": 1, "processes": True}
    )


def run_mux_calibrations_parallel(
    mux_groups: list[list[str]],
    tasks: list[str],
    session_config: dict[str, Any],
) -> dict[str, Any]:
    """Run multiple MUX group calibrations in parallel using separate processes.

    Each MUX group runs in its own process with isolated memory space,
    avoiding qubex's global state issues.

    Args:
        mux_groups: List of MUX groups, where each group is a list of qubit IDs
        tasks: List of task names to execute
        session_config: Configuration for creating isolated sessions

    Returns:
        Dictionary mapping qid to results (combined from all MUX groups)
    """

    # Define flow dynamically to avoid import errors when prefect-dask not installed
    @flow(task_runner=_get_dask_task_runner())
    def _run_mux_parallel_flow(
        mux_groups: list[list[str]],
        tasks: list[str],
        session_config: dict[str, Any],
    ) -> dict[str, Any]:
        logger = get_run_logger()
        logger.info(f"Running {len(mux_groups)} MUX groups in parallel processes")

        # Submit all MUX groups to run in parallel processes
        futures = [
            calibrate_mux_qubits.submit(
                qids=group,
                tasks=tasks,
                session_config=session_config,
            )
            for group in mux_groups
        ]

        # Collect results and log any errors from subprocesses
        all_results = {}
        for future in futures:
            mux_result = future.result()
            # Log error details from subprocess (since subprocess logs don't propagate)
            for qid, qid_result in mux_result.items():
                if qid_result.get("status") == "failed" and "error_details" in qid_result:
                    logger.error(
                        f"[From subprocess] Failed to calibrate qubit {qid}:\n{qid_result['error_details']}"
                    )
            all_results.update(mux_result)

        return all_results

    result: dict[str, Any] = _run_mux_parallel_flow(mux_groups, tasks, session_config)
    return result


def run_qubit_calibrations_parallel(
    qids: list[str],
    tasks: list[str],
    session_config: dict[str, Any],
) -> dict[str, Any]:
    """Run multiple qubit calibrations in parallel using separate processes.

    Each qubit runs in its own process with isolated memory space,
    avoiding qubex's global state issues.

    Args:
        qids: List of qubit IDs to calibrate in parallel
        tasks: List of task names to execute
        session_config: Configuration for creating isolated sessions

    Returns:
        Dictionary mapping qid to results
    """

    # Define flow dynamically to avoid import errors when prefect-dask not installed
    @flow(task_runner=_get_dask_task_runner())
    def _run_qubit_parallel_flow(
        qids: list[str],
        tasks: list[str],
        session_config: dict[str, Any],
    ) -> dict[str, Any]:
        logger = get_run_logger()
        logger.info(f"Running {len(qids)} qubits in parallel processes")

        # Submit all qubits to run in parallel processes
        futures = [
            calibrate_single_qubit.submit(
                qid=qid,
                tasks=tasks,
                session_config=session_config,
            )
            for qid in qids
        ]

        # Collect results and log any errors from subprocesses
        pair_results = []
        for f in futures:
            qid, qid_result = f.result()
            # Log error details from subprocess (since subprocess logs don't propagate)
            if qid_result.get("status") == "failed" and "error_details" in qid_result:
                logger.error(
                    f"[From subprocess] Failed to calibrate qubit {qid}:\n{qid_result['error_details']}"
                )
            pair_results.append((qid, qid_result))
        return dict(pair_results)

    result: dict[str, Any] = _run_qubit_parallel_flow(qids, tasks, session_config)
    return result


@task(task_run_name=_group_retry_task_run_name, log_prints=True)
def calibrate_group_with_retry(
    qids: list[str],
    tasks: list[str],
    offsets: list[float],
    session_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calibrate a group of qubits sequentially with retry logic.

    Each qubit in the group runs sequentially, with retry on failure
    using frequency offsets.

    Args:
        qids: Qubit IDs in this group (run sequentially)
        tasks: Task names (run sequentially per qubit)
        offsets: Frequency offsets to try on failure (e.g., [0, 0.001, -0.001])
        session_config: Optional configuration for creating isolated session.
            If provided, creates independent CalibService. If None, uses
            global session context.

    Returns:
        Results dict keyed by qubit ID
    """
    # Ensure Prefect logging is configured in Dask worker processes
    _ensure_prefect_logging()

    logger = get_run_logger()

    # Create isolated session or use global session
    use_isolated = session_config is not None

    if use_isolated:
        assert session_config is not None
        session = _create_isolated_session(session_config, qids)
    else:
        session = _get_session()

    results: dict[str, Any] = {}

    try:
        for qid in qids:
            # Retry loop for each qubit
            for attempt, offset in enumerate(offsets):
                try:
                    if offset != 0:
                        logger.info(
                            f"Q{qid}: Attempt {attempt + 1} with {offset * 1000:+.0f} MHz offset"
                        )

                    # Tasks run sequentially within qubit
                    result: dict[str, Any] = {}
                    for task_name in tasks:
                        task_details = None
                        if offset != 0:
                            task_details = {
                                task_name: {
                                    "input_parameters": {
                                        "qubit_frequency_offset": {"value": offset}
                                    }
                                }
                            }
                        result[task_name] = session.execute_task(
                            task_name, qid, task_details=task_details
                        )

                    result["status"] = "success"
                    result["attempt"] = attempt + 1
                    results[qid] = result
                    break  # Success, move to next qubit

                except Exception as e:
                    error_details = _format_exception_details(e)
                    logger.warning(f"Q{qid}: Attempt {attempt + 1} failed:\n{error_details}")
                    if attempt == len(offsets) - 1:
                        results[qid] = {
                            "status": "failed",
                            "error": str(e),
                            "error_details": error_details,
                            "attempt": attempt + 1,
                        }
    finally:
        if use_isolated:
            session.finish_calibration(update_chip_history=False, push_to_github=False)

    # Flush logs before returning (critical for Dask worker processes)
    _flush_prefect_logs()
    return results


def run_groups_with_retry_parallel(
    groups: list[list[str]],
    tasks: list[str],
    offsets: list[float],
    session_config: dict[str, Any],
) -> dict[str, Any]:
    """Run multiple qubit groups with retry logic in parallel using separate processes.

    Each group runs in its own process with isolated memory space.
    Within each group, qubits are processed sequentially with retry logic.

    Args:
        groups: List of qubit groups, where each group is a list of qubit IDs
        tasks: List of task names to execute
        offsets: Frequency offsets to try on failure (e.g., [0, 0.001, -0.001])
        session_config: Configuration for creating isolated sessions

    Returns:
        Dictionary mapping qid to results (combined from all groups)
    """

    # Define flow dynamically to avoid import errors when prefect-dask not installed
    @flow(task_runner=_get_dask_task_runner())
    def _run_groups_retry_parallel_flow(
        groups: list[list[str]],
        tasks: list[str],
        offsets: list[float],
        session_config: dict[str, Any],
    ) -> dict[str, Any]:
        logger = get_run_logger()
        logger.info(f"Running {len(groups)} groups with retry in parallel processes")

        # Submit all groups to run in parallel processes
        futures = [
            calibrate_group_with_retry.submit(
                qids=group,
                tasks=tasks,
                offsets=offsets,
                session_config=session_config,
            )
            for group in groups
        ]

        # Collect results and log any errors from subprocesses
        all_results: dict[str, Any] = {}
        for future in futures:
            group_result = future.result()
            # Log error details from subprocess (since subprocess logs don't propagate)
            for qid, qid_result in group_result.items():
                if qid_result.get("status") == "failed" and "error_details" in qid_result:
                    logger.error(
                        f"[From subprocess] Failed to calibrate qubit {qid}:\n{qid_result['error_details']}"
                    )
            all_results.update(group_result)

        return all_results

    result: dict[str, Any] = _run_groups_retry_parallel_flow(groups, tasks, offsets, session_config)
    return result


def run_coupling_calibrations_parallel(
    coupling_qids: list[str],
    tasks: list[str],
    session_config: dict[str, Any],
) -> dict[str, Any]:
    """Run multiple coupling pair calibrations in parallel using separate processes.

    Each coupling pair runs in its own process with isolated memory space,
    avoiding qubex's global state issues.

    Args:
        coupling_qids: List of coupling IDs (e.g., ["0-1", "2-3"])
        tasks: List of task names to execute
        session_config: Configuration for creating isolated sessions

    Returns:
        Dictionary mapping coupling_qid to results
    """

    # Define flow dynamically to avoid import errors when prefect-dask not installed
    @flow(task_runner=_get_dask_task_runner())
    def _run_coupling_parallel_flow(
        coupling_qids: list[str],
        tasks: list[str],
        session_config: dict[str, Any],
    ) -> dict[str, Any]:
        logger = get_run_logger()
        logger.info(f"Running {len(coupling_qids)} coupling pairs in parallel processes")

        # Submit all coupling pairs to run in parallel processes
        futures = [
            execute_coupling_pair.submit(
                coupling_qid=cqid,
                tasks=tasks,
                session_config=session_config,
            )
            for cqid in coupling_qids
        ]

        # Collect results and log any errors from subprocesses
        pair_results = []
        for f in futures:
            cqid, cqid_result = f.result()
            # Log error details from subprocess (since subprocess logs don't propagate)
            if cqid_result.get("status") == "failed" and "error_details" in cqid_result:
                logger.error(
                    f"[From subprocess] Failed to calibrate coupling {cqid}:\n{cqid_result['error_details']}"
                )
            pair_results.append((cqid, cqid_result))
        return dict(pair_results)

    result: dict[str, Any] = _run_coupling_parallel_flow(coupling_qids, tasks, session_config)
    return result
