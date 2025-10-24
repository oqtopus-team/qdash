"""Parallel execution helpers using Prefect @task + submit().

This module provides parallel execution capabilities for Python Flow Editor,
using Prefect's task parallelism to execute calibration tasks concurrently
across multiple qubits.
"""

from typing import Any, Callable

from prefect import get_run_logger, task
from qdash.workflow.core.calibration.execution_manager import ExecutionManager
from qdash.workflow.core.calibration.task import execute_dynamic_task_by_qid
from qdash.workflow.helpers.flow_helpers import get_session
from qdash.workflow.tasks.active_protocols import generate_task_instances


@task
def _execute_calibration_for_qubit(
    qid: str,
    tasks: list[str],
    task_details: dict[str, Any],
) -> dict[str, Any]:
    """Execute calibration tasks for a single qubit.

    This is an internal task function used by calibrate_parallel().
    It executes all tasks sequentially for one qubit.
    """
    logger = get_run_logger()
    session = get_session()

    logger.info(f"Starting calibration for qubit {qid}: tasks={tasks}")

    results = {}
    for task_name in tasks:
        try:
            task_result = session.execute_task(task_name, qid, task_details)
            results.update(task_result)
        except Exception as e:
            logger.error(f"Task {task_name} failed for qubit {qid}: {e}")
            results[f"{task_name}_error"] = str(e)

    logger.info(f"Completed calibration for qubit {qid}")
    return results


def calibrate_parallel(
    qids: list[str],
    tasks: list[str],
    task_details: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Execute calibration tasks in true parallel using Prefect task parallelism.

    Each qubit is calibrated concurrently using Prefect's @task + submit().
    All qubits run in parallel, executing their tasks sequentially within
    each qubit's task chain.

    Execution pattern (parallel across qubits):
    - Q0: Task1 → Task2 → Task3  ┐
    - Q1: Task1 → Task2 → Task3  ├─ All in parallel
    - Q2: Task1 → Task2 → Task3  ┘

    Args:
        qids: List of qubit IDs to calibrate
        tasks: List of task names to execute for each qubit
        task_details: Optional task-specific configuration

    Returns:
        Dictionary mapping qubit IDs to their output parameters

    Example:
        ```python
        from prefect import flow
        from qdash.workflow.helpers import init_calibration, calibrate_parallel, finish_calibration

        @flow
        def my_calibration(username, chip_id, qids):
            session = init_calibration(username, chip_id, qids)

            # True parallel execution using @task + submit()
            results = calibrate_parallel(
                qids=["0", "1", "2", "3"],
                tasks=["CheckFreq", "CheckRabi", "CheckT1"]
            )

            finish_calibration()
            return results
        ```

    Note:
        - Uses Prefect's task parallelism (@task + submit())
        - No deployment required
        - All qubits share the same FlowSession
        - Suitable for shared hardware like qubex
    """
    logger = get_run_logger()

    if task_details is None:
        task_details = {}

    logger.info(f"Starting parallel calibration for {len(qids)} qubits: {qids}")

    # Submit tasks for parallel execution (one task per qubit)
    futures = [_execute_calibration_for_qubit.submit(qid, tasks, task_details) for qid in qids]

    # Wait for all tasks to complete and collect results
    results = {}
    for qid, future in zip(qids, futures):
        try:
            results[qid] = future.result()
        except Exception as e:
            logger.error(f"Calibration failed for qubit {qid}: {e}")
            results[qid] = {"error": str(e)}

    logger.info(f"Parallel calibration completed for {len(qids)} qubits")
    return results


@task
def _run_custom_function(
    item: Any,
    func: Callable,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute a custom function for a single item.

    This is an internal task function used by parallel_map().
    """
    return func(item, *args, **kwargs)


def parallel_map(
    items: list[Any],
    func: Callable,
    task_name_func: Callable[[Any], str] | None = None,
    *args: Any,
    **kwargs: Any,
) -> list[Any]:
    """Apply a function to items in parallel using Prefect tasks.

    This is a generic parallel map function that can be used for any
    custom calibration logic. Each item is processed as a separate Prefect
    task, making it easy to monitor progress in the Prefect UI.

    Args:
        items: List of items to process (e.g., qubit IDs)
        func: Function to apply to each item
            Signature: func(item, *args, **kwargs) -> result
        task_name_func: Optional function to generate task names from items.
            If provided, will be called as task_name_func(item) to get the
            task name for Prefect UI. If None, uses str(item).
            Example: lambda qid: f"calibrate-Q{qid}"
        *args: Additional positional arguments passed to func
        **kwargs: Additional keyword arguments passed to func

    Returns:
        List of results in the same order as items

    Example:
        ```python
        from prefect import flow
        from qdash.workflow.helpers import init_calibration, parallel_map, get_session, finish_calibration

        def my_adaptive_calibration(qid, threshold, max_iter):
            '''Custom adaptive calibration with own convergence logic.'''
            session = get_session()

            for iteration in range(max_iter):
                result = session.execute_task("CheckFreq", qid)

                # Your own convergence check
                if abs(result["qubit_frequency"] - 5.0) < threshold:
                    print(f"Q{qid} converged in {iteration} iterations")
                    break

                # Your own parameter update
                session.set_parameter(qid, "qubit_frequency", result["qubit_frequency"])

            return result

        @flow
        def my_flow(username, chip_id, qids):
            session = init_calibration(username, chip_id, qids)

            # Apply custom function in parallel with named tasks
            results = parallel_map(
                items=qids,
                func=my_adaptive_calibration,
                task_name_func=lambda qid: f"adaptive-Q{qid}",  # Shows in Prefect UI
                threshold=0.01,
                max_iter=10
            )

            finish_calibration()
            return results
        ```

    Note:
        Tasks inside func (e.g., session.execute_task()) will also appear
        as nested tasks in the Prefect UI, giving full visibility into
        the calibration process.
    """
    logger = get_run_logger()
    logger.info(f"Starting parallel_map for {len(items)} items")

    # Submit tasks for parallel execution with custom names
    futures = []
    for item in items:
        # Generate task name for Prefect UI
        if task_name_func is not None:
            task_name = task_name_func(item)
        else:
            task_name = f"process-{item}"

        # Submit with custom task name
        future = _run_custom_function.with_options(task_run_name=task_name).submit(item, func, *args, **kwargs)
        futures.append((item, future))

    # Wait for all tasks to complete and collect results
    results = []
    for item, future in futures:
        try:
            results.append(future.result())
        except Exception as e:
            logger.error(f"parallel_map failed for item {item}: {e}")
            results.append(None)

    logger.info(f"parallel_map completed for {len(items)} items")
    return results
