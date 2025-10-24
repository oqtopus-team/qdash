"""Iterative parallel group calibration flow.

This template demonstrates how to repeat parallel group calibration multiple times,
which is useful for:
- Stability testing (repeated measurements with parallel groups)
- Data collection (gather statistics from multiple runs)
- Iterative optimization with parallel execution
"""

from prefect import flow, get_run_logger, task
from qdash.workflow.helpers import finish_calibration, get_session, init_calibration


@task
def calibrate_group(
    qids: list[str], tasks: list[str], group_name: str, iteration: int, task_details: dict | None = None
) -> dict:
    """Execute tasks for a group of qubits sequentially with error handling.

    If a qubit fails during calibration, it will be skipped and the next qubit
    will be processed. Failed qubits are logged and marked in the results.

    Args:
    ----
        qids: List of qubit IDs to calibrate (executed in order)
        tasks: List of task names to execute
        group_name: Name of the group (for logging)
        iteration: Current iteration number (for logging)
        task_details: Optional task-specific configuration parameters
            Example: {"CheckRabi": {"input_parameters": {"detune_frequency": {"value": 5.0}}}}

    Returns:
    -------
        Results for the group (includes error information for failed qubits)

    """
    logger = get_run_logger()
    logger.info(f"Iteration {iteration + 1} - {group_name}: Starting calibration for qubits: {qids}")

    if task_details:
        logger.info(f"  Using custom task parameters for: {list(task_details.keys())}")

    session = get_session()
    results = {}
    failed_qubits = []
    last_task_id = None  # Track last task_id for upstream dependency

    # Execute each qubit in order
    for qid in qids:
        logger.info(f"  Calibrating qubit {qid}")

        try:
            # Execute all tasks for this qubit
            for task_name in tasks:
                logger.info(f"    Executing {task_name} on qubit {qid}")

                # Pass upstream_id from previous qid's last task (for group dependency)
                result = session.execute_task(task_name, qid, task_details=task_details, upstream_id=last_task_id)

                if qid not in results:
                    results[qid] = {"status": "success", "iteration": iteration, "group": group_name}

                results[qid].update(result)

                # Update last_task_id for next task/qid
                last_task_id = result.get("task_id")

            logger.info(f"  ✓ Successfully calibrated qubit {qid}")

        except Exception as e:
            # Log the error and continue with next qubit
            logger.error(f"  ✗ Failed to calibrate qubit {qid}: {e}")
            logger.warning(f"  Skipping qubit {qid} and continuing with next qubit")

            failed_qubits.append(qid)
            results[qid] = {"status": "failed", "error": str(e), "iteration": iteration, "group": group_name}

            # Continue to next qubit (last_task_id preserved for next qid)
            continue

    # Summary
    successful_qubits = [qid for qid in qids if qid not in failed_qubits]
    logger.info(f"Iteration {iteration + 1} - {group_name} completed:")
    logger.info(f"  Successful: {successful_qubits}")
    if failed_qubits:
        logger.warning(f"  Failed: {failed_qubits}")

    return results


@flow
def iterative_flow(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    max_iterations: int = 3,  # TODO: Adjust number of iterations
    flow_name: str | None = None,  # Automatically injected by API
):
    """Iterative parallel group calibration flow.

    This flow repeats parallel group calibration multiple times, useful for:
    - Stability testing (measure parameter stability across iterations)
    - Data collection (gather statistics from multiple runs)
    - Iterative optimization with parallel groups

    Example: With max_iterations=3:
    - Iteration 1: Group1 (33→32) || Group2 (36→38) in parallel
    - Iteration 2: Group1 (33→32) || Group2 (36→38) in parallel
    - Iteration 3: Group1 (33→32) || Group2 (36→38) in parallel

    Note: username and chip_id are automatically provided from UI properties.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        qids: List of qubit IDs (not used, groups are defined explicitly)
        max_iterations: Number of times to repeat the parallel calibration

    """
    logger = get_run_logger()

    # TODO: Define your qubit groups
    group1 = ["33", "32"]  # 33 → 32
    group2 = ["36", "38"]  # 36 → 38

    all_qids = group1 + group2

    logger.info(f"Starting iterative parallel calibration for user={username}, chip_id={chip_id}")
    logger.info(f"Group 1: {group1} (sequential)")
    logger.info(f"Group 2: {group2} (sequential)")
    logger.info(f"Max iterations: {max_iterations}")
    logger.info("Groups will run in parallel within each iteration")

    # Initialize session
    init_calibration(username, chip_id, all_qids)

    # TODO: Edit the tasks you want to run
    tasks = ["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"]

    # TODO: Define task_details for each iteration (optional)
    # You can customize input parameters for each iteration
    # Example: Change CheckRabi's detune_frequency for each iteration
    task_details_per_iteration = [
        None,  # Iteration 1: Use default parameters (detune_frequency=0)
        {
            "CheckRabi": {
                "input_parameters": {
                    "detune_frequency": {"value": 5.0}  # Iteration 2: detune_frequency=5.0 MHz
                }
            }
        },
        {
            "CheckRabi": {
                "input_parameters": {
                    "detune_frequency": {"value": 10.0}  # Iteration 3: detune_frequency=10.0 MHz
                }
            }
        },
    ]

    # Store results from all iterations
    all_iterations_results = []

    # Execute multiple iterations
    for iteration in range(max_iterations):
        logger.info("=" * 60)
        logger.info(f"Starting iteration {iteration + 1}/{max_iterations}")
        logger.info("=" * 60)

        # Get task_details for this iteration (if defined)
        task_details = task_details_per_iteration[iteration] if iteration < len(task_details_per_iteration) else None

        # Submit both groups for parallel execution
        logger.info("Submitting groups for parallel execution...")
        future1 = calibrate_group.submit(
            qids=group1, tasks=tasks, group_name="Group1", iteration=iteration, task_details=task_details
        )
        future2 = calibrate_group.submit(
            qids=group2, tasks=tasks, group_name="Group2", iteration=iteration, task_details=task_details
        )

        # Wait for completion
        logger.info("Waiting for groups to complete...")
        results1 = future1.result()
        results2 = future2.result()

        # Combine results for this iteration
        iteration_results = {**results1, **results2}
        all_iterations_results.append(iteration_results)

    finish_calibration()

    return all_iterations_results
