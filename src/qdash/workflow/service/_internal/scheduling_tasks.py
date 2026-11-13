"""Internal Prefect tasks for calibration workflows.

This module consolidates common Prefect tasks used across calibration strategies.
These are internal implementation details and should not be imported directly.

Tasks:
    calibrate_mux_qubits: Execute tasks for qubits in a single MUX sequentially
    calibrate_single_qubit: Execute tasks for a single qubit
    calibrate_round_qubits_parallel: Execute the qubits of a parallel_by_round round in parallel
    execute_coupling_pair: Execute tasks for a single coupling pair
    calibrate_parallel_group: Execute coupling tasks for a parallel group

Multiprocess Parallel Execution (using Dask):
    For parallel execution with isolated sessions, use the multiprocess versions:
    - run_mux_calibrations_parallel: Run multiple MUX groups in parallel processes
    - run_qubit_calibrations_parallel: Run multiple qubits in parallel processes

    These use DaskTaskRunner with processes=True to spawn separate Python processes,
    each with its own memory space. This avoids qubex's global state issues
    (boxpool, device_controller) without requiring locks.

Every runner takes the step's normalized calls as one ``StepCalls`` plan and
returns, per target, the ordered call results built by ``call_runner``.
"""

from __future__ import annotations

import logging
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

from prefect import flow, get_run_logger, task

# Runtime imports: Prefect resolves the annotations of the flows defined here.
from qdash.datamodel.task_call import StepCalls, TaskCall  # noqa: TC001
from qdash.workflow.service._internal.call_runner import (
    format_exception_details,
    run_batch_calls,
    run_target_calls,
)
from qdash.workflow.service._internal.session import borrowed_session
from qdash.workflow.service._internal.settings import WorkerSpec  # noqa: TC001

# DaskTaskRunner is optional - only needed for multiprocess parallel execution
DaskTaskRunner: Any
try:
    prefect_dask: Any = import_module("prefect_dask")
    DaskTaskRunner = prefect_dask.DaskTaskRunner

    _DASK_AVAILABLE = True
except ImportError:
    _DASK_AVAILABLE = False
    DaskTaskRunner = None
except Exception as exc:
    # psutil can observe a stale container PID while Dask determines CPU
    # affinity during import. Treat that environment race like an unavailable
    # optional runner, while allowing unrelated import failures to surface.
    if type(exc).__name__ != "NoSuchProcess":
        raise
    _DASK_AVAILABLE = False
    DaskTaskRunner = None

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession

# Module-level logger for subprocess execution (Prefect logger not available in subprocesses)
_logger = logging.getLogger(__name__)


def _get_session() -> CalibSession:
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
    """Format exception details, including sub-exceptions for ExceptionGroup."""
    return format_exception_details(e)


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


def _mux_skip(backend_name: str) -> Any:
    """A ``skip_call`` that skips MUX tasks on non-representative qubits."""

    def skip(call: TaskCall, qid: str) -> bool:
        return _should_skip_task_for_qid(call.name, qid, backend_name)

    return skip


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


def _execute_mux_qubits_with_session(
    session: CalibSession,
    qids: list[str],
    plan: StepCalls,
    logger: Any,
) -> dict[str, Any]:
    """Run the step's calls for each qubit of a MUX group, one qubit after another."""
    skip = _mux_skip(session.backend_name)
    return {qid: run_target_calls(session, qid, plan, logger, skip_call=skip) for qid in qids}


@task(task_run_name=_mux_task_run_name, log_prints=True)
def calibrate_mux_qubits(
    qids: list[str],
    plan: StepCalls,
    worker: WorkerSpec | None = None,
) -> dict[str, Any]:
    """Execute a step's calls for qubits in a single MUX sequentially (Prefect task).

    For MUX-level tasks, only the representative qubit (qid % 4 == 0) executes
    the task. Other qubits in the MUX are skipped for MUX tasks.

    Note: This Prefect task uses threading. For true parallel execution with
    qubex backend, use run_mux_calibrations_parallel() instead, which
    spawns separate processes to avoid qubex's global state issues.

    Args:
        qids: List of qubit IDs in the MUX
        plan: The step's calls and failure policy
        worker: The owner's ``WorkerSpec``. If provided, runs in a borrowed
            worker session; if None, uses the owner session in this process.

    Returns:
        Dictionary mapping qid to its ordered call results
    """
    # Ensure Prefect logging is configured in Dask worker processes
    _ensure_prefect_logging()

    logger = get_run_logger()

    if worker is not None:
        with borrowed_session(worker, qids) as session:
            results = _execute_mux_qubits_with_session(session, qids, plan, logger)
    else:
        results = _execute_mux_qubits_with_session(_get_session(), qids, plan, logger)

    # Flush logs before returning (critical for Dask worker processes)
    _flush_prefect_logs()
    return results


def _execute_single_qubit_with_session(
    session: CalibSession,
    qid: str,
    plan: StepCalls,
    logger: Any,
) -> dict[str, Any]:
    """Run the step's calls for a single qubit using the provided session."""
    return run_target_calls(session, qid, plan, logger, skip_call=_mux_skip(session.backend_name))


@task(task_run_name=_single_qubit_task_run_name, log_prints=True)
def calibrate_single_qubit(
    qid: str,
    plan: StepCalls,
    worker: WorkerSpec | None = None,
) -> tuple[str, dict[str, Any]]:
    """Execute a step's calls for a single qubit (Prefect task).

    For MUX-level tasks, only the representative qubit (qid % 4 == 0) executes
    the task. Other qubits in the MUX are skipped for MUX tasks.

    Args:
        qid: Qubit ID
        plan: The step's calls and failure policy
        worker: The owner's ``WorkerSpec``. If provided, runs in a borrowed
            worker session; if None, uses the owner session in this process.

    Returns:
        Tuple of (qid, ordered call results)
    """
    # Ensure Prefect logging is configured in Dask worker processes
    _ensure_prefect_logging()

    logger = get_run_logger()

    if worker is not None:
        with borrowed_session(worker, [qid]) as session:
            result = _execute_single_qubit_with_session(session, qid, plan, logger)
    else:
        result = _execute_single_qubit_with_session(_get_session(), qid, plan, logger)

    # Flush logs before returning (critical for Dask worker processes)
    _flush_prefect_logs()
    return qid, result


@task(log_prints=True)
def calibrate_round_qubits_parallel(
    parallel_qids: list[str],
    plan: StepCalls,
    worker: WorkerSpec | None = None,
) -> dict[str, Any]:
    """Execute the step's calls for every qubit of one round in parallel.

    The qubits of a ``parallel_by_round`` round come from different MUXes;
    this returns after every qubit has run its full call list.

    When ``worker`` is provided, each qubit gets its own borrowed worker
    session with an independent Experiment instance, avoiding shared state
    conflicts during parallel execution.

    Args:
        parallel_qids: List of qubit IDs to calibrate in parallel
        plan: The step's calls and failure policy
        worker: The owner's ``WorkerSpec``. If provided, each qubit runs in its
            own borrowed worker session; if None, uses the owner session.

    Returns:
        Dictionary mapping qid to results
    """
    # Submit all qubits in parallel
    futures = [calibrate_single_qubit.submit(qid, plan, worker) for qid in parallel_qids]
    pair_results = [f.result() for f in futures]
    return dict(pair_results)


# =============================================================================
# Coupling Tasks (for 2-qubit calibration)
# =============================================================================


def _execute_coupling_pair_with_session(
    session: CalibSession,
    coupling_qid: str,
    plan: StepCalls,
    logger: Any,
) -> dict[str, Any]:
    """Run the step's calls for a coupling pair using the provided session."""
    return run_target_calls(session, coupling_qid, plan, logger)


@task(task_run_name=_coupling_task_run_name, log_prints=True)
def execute_coupling_pair(
    coupling_qid: str,
    plan: StepCalls,
    worker: WorkerSpec | None = None,
) -> tuple[str, dict[str, Any]]:
    """Execute a step's calls for a single coupling pair.

    Args:
        coupling_qid: Coupling ID (e.g., "0-1")
        plan: The step's calls and failure policy
        worker: The owner's ``WorkerSpec``. If provided, runs in a borrowed
            worker session; if None, uses the owner session in this process.

    Returns:
        Tuple of (coupling_qid, ordered call results)
    """
    # Ensure Prefect logging is configured in Dask worker processes
    _ensure_prefect_logging()

    logger = get_run_logger()

    # Parse coupling_qid to get involved qubit IDs
    qids = coupling_qid.split("-")

    if worker is not None:
        with borrowed_session(worker, qids) as session:
            result = _execute_coupling_pair_with_session(session, coupling_qid, plan, logger)
    else:
        result = _execute_coupling_pair_with_session(_get_session(), coupling_qid, plan, logger)

    # Flush logs before returning (critical for Dask worker processes)
    _flush_prefect_logs()
    return coupling_qid, result


@task(log_prints=True)
def calibrate_parallel_group(
    coupling_qids: list[str],
    plan: StepCalls,
    worker: WorkerSpec | None = None,
) -> dict[str, Any]:
    """Execute coupling tasks for a parallel group.

    Note: This Prefect task uses threading. For true parallel execution with
    qubex backend, use run_coupling_calibrations_parallel() instead, which
    spawns separate processes to avoid qubex's global state issues.

    Args:
        coupling_qids: List of coupling IDs (e.g., ["0-1", "2-3"])
        plan: The step's calls and failure policy
        worker: The owner's ``WorkerSpec``. If provided, each pair runs in its
            own borrowed worker session; if None, uses the owner session.

    Returns:
        Dictionary mapping coupling_qid to results
    """
    futures = [execute_coupling_pair.submit(cqid, plan, worker) for cqid in coupling_qids]
    pair_results = [f.result() for f in futures]
    return dict(pair_results)


# =============================================================================
# Multiprocess Parallel Execution (using Dask)
# =============================================================================
# These functions use DaskTaskRunner with processes=True for true parallel
# execution in separate Python processes. This avoids qubex's global state
# issues (boxpool, device_controller) that occur with threaded execution.


_DEFAULT_DASK_WORKERS = 16


def _get_dask_task_runner(n_workers: int = _DEFAULT_DASK_WORKERS) -> Any:
    """Get DaskTaskRunner configured for multiprocess execution.

    Args:
        n_workers: Number of Dask workers (parallel processes). Default: 16.

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
        cluster_kwargs={"n_workers": n_workers, "threads_per_worker": 1, "processes": True}
    )


def _qubit_batch_task_run_name(parameters: dict[str, Any]) -> str:
    qids = parameters.get("qids", [])
    return f"simultaneous-Q{'-'.join(map(str, qids))}"


@task(task_run_name=cast("Any", _qubit_batch_task_run_name), log_prints=True)
def calibrate_qubit_batch(
    qids: list[str],
    plan: StepCalls,
    worker: WorkerSpec,
) -> dict[str, Any]:
    """Execute batch-capable calls for qids in one isolated session."""
    _ensure_prefect_logging()
    logger = get_run_logger()
    try:
        with borrowed_session(worker, qids) as session:
            return run_batch_calls(session, qids, plan, logger)
    finally:
        _flush_prefect_logs()


def run_qubit_batch_calibration_isolated(
    qids: list[str],
    plan: StepCalls,
    worker: WorkerSpec,
) -> dict[str, Any]:
    """Run batch-capable qubit calls in one isolated process.

    This is used for hardware-aware tasks that must receive all qids in one
    ``execute_task_batch`` call, while still avoiding qubex global state in the
    parent flow process.
    """

    @flow(task_runner=_get_dask_task_runner())
    def _run_qubit_batch_flow(
        qids: list[str],
        plan: StepCalls,
        worker: WorkerSpec,
    ) -> dict[str, Any]:
        future = calibrate_qubit_batch.submit(
            qids=qids,
            plan=plan,
            worker=worker,
        )
        result: dict[str, Any] = future.result()
        return result

    result: dict[str, Any] = _run_qubit_batch_flow(qids, plan, worker)
    return result


def _log_subprocess_failures(logger: Any, kind: str, results: dict[str, Any]) -> None:
    """Log error details from subprocesses, whose own logs do not propagate."""
    for target, target_result in results.items():
        if target_result.get("status") == "failed" and "error_details" in target_result:
            logger.error(
                f"[From subprocess] Failed to calibrate {kind} {target}:\n"
                f"{target_result['error_details']}"
            )


def run_mux_calibrations_parallel(
    mux_groups: list[list[str]],
    plan: StepCalls,
    worker: WorkerSpec,
) -> dict[str, Any]:
    """Run multiple MUX group calibrations in parallel using separate processes.

    Each MUX group runs in its own process with isolated memory space,
    avoiding qubex's global state issues. Within a group the qubits run one
    after another; groups do not wait for each other between calls.

    Args:
        mux_groups: List of MUX groups, where each group is a list of qubit IDs
        plan: The step's calls and failure policy
        worker: The owner's ``WorkerSpec`` that every worker session inherits

    Returns:
        Dictionary mapping qid to results (combined from all MUX groups)
    """

    # Define flow dynamically to avoid import errors when prefect-dask not installed
    @flow(task_runner=_get_dask_task_runner())
    def _run_mux_parallel_flow(
        mux_groups: list[list[str]],
        plan: StepCalls,
        worker: WorkerSpec,
    ) -> dict[str, Any]:
        logger = get_run_logger()
        logger.info(f"Running {len(mux_groups)} MUX groups in parallel processes")

        futures = [
            calibrate_mux_qubits.submit(qids=group, plan=plan, worker=worker)
            for group in mux_groups
        ]

        all_results: dict[str, Any] = {}
        for future in futures:
            mux_result = future.result()
            _log_subprocess_failures(logger, "qubit", mux_result)
            all_results.update(mux_result)
        return all_results

    result: dict[str, Any] = _run_mux_parallel_flow(mux_groups, plan, worker)
    return result


def run_qubit_calibrations_parallel(
    qids: list[str],
    plan: StepCalls,
    worker: WorkerSpec,
) -> dict[str, Any]:
    """Run multiple qubit calibrations in parallel using separate processes.

    Each qubit runs in its own process with isolated memory space,
    avoiding qubex's global state issues.

    Args:
        qids: List of qubit IDs to calibrate in parallel
        plan: The step's calls and failure policy
        worker: The owner's ``WorkerSpec`` that every worker session inherits

    Returns:
        Dictionary mapping qid to results
    """

    # Define flow dynamically to avoid import errors when prefect-dask not installed
    @flow(task_runner=_get_dask_task_runner())
    def _run_qubit_parallel_flow(
        qids: list[str],
        plan: StepCalls,
        worker: WorkerSpec,
    ) -> dict[str, Any]:
        logger = get_run_logger()
        logger.info(f"Running {len(qids)} qubits in parallel processes")

        futures = [calibrate_single_qubit.submit(qid=qid, plan=plan, worker=worker) for qid in qids]
        results = dict(f.result() for f in futures)
        _log_subprocess_failures(logger, "qubit", results)
        return results

    result: dict[str, Any] = _run_qubit_parallel_flow(qids, plan, worker)
    return result


def run_coupling_calibrations_parallel(
    coupling_qids: list[str],
    plan: StepCalls,
    worker: WorkerSpec,
) -> dict[str, Any]:
    """Run multiple coupling pair calibrations in parallel using separate processes.

    Each coupling pair runs in its own process with isolated memory space,
    avoiding qubex's global state issues.

    Args:
        coupling_qids: List of coupling IDs (e.g., ["0-1", "2-3"])
        plan: The step's calls and failure policy
        worker: The owner's ``WorkerSpec`` that every worker session inherits

    Returns:
        Dictionary mapping coupling_qid to results
    """

    # Define flow dynamically to avoid import errors when prefect-dask not installed
    @flow(task_runner=_get_dask_task_runner())
    def _run_coupling_parallel_flow(
        coupling_qids: list[str],
        plan: StepCalls,
        worker: WorkerSpec,
    ) -> dict[str, Any]:
        logger = get_run_logger()
        logger.info(f"Running {len(coupling_qids)} coupling pairs in parallel processes")

        futures = [
            execute_coupling_pair.submit(coupling_qid=cqid, plan=plan, worker=worker)
            for cqid in coupling_qids
        ]
        results = dict(f.result() for f in futures)
        _log_subprocess_failures(logger, "coupling", results)
        return results

    result: dict[str, Any] = _run_coupling_parallel_flow(coupling_qids, plan, worker)
    return result
