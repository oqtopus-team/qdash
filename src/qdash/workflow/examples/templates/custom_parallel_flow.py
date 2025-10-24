"""Custom parallel flow with simple parallel execution using .submit()."""

from prefect import flow, get_run_logger, task
from qdash.workflow.helpers import finish_calibration, get_session, init_calibration


@task
def calibrate_group(qids: list[str], tasks: list[str]) -> dict:
    """Execute tasks for a group of qubits sequentially with error handling.

    If a qubit fails during calibration, it will be skipped and the next qubit
    will be processed. Failed qubits are logged and marked in the results.

    Args:
    ----
        qids: List of qubit IDs to calibrate (executed in order)
        tasks: List of task names to execute

    Returns:
    -------
        Results for the group (includes error information for failed qubits)

    """
    logger = get_run_logger()
    logger.info(f"Starting group calibration for qubits: {qids}")

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
                result = session.execute_task(task_name, qid, upstream_id=last_task_id)

                if qid not in results:
                    results[qid] = {"status": "success"}

                results[qid].update(result)

                # Update last_task_id for next task/qid
                last_task_id = result.get("task_id")

            logger.info(f"  ✓ Successfully calibrated qubit {qid}")

        except Exception as e:
            # Log the error and continue with next qubit
            logger.error(f"  ✗ Failed to calibrate qubit {qid}: {e}")
            logger.warning(f"  Skipping qubit {qid} and continuing with next qubit")

            failed_qubits.append(qid)
            results[qid] = {"status": "failed", "error": str(e)}

            # Continue to next qubit (last_task_id preserved for next qid)
            continue

    # Summary
    successful_qubits = [qid for qid in qids if qid not in failed_qubits]
    logger.info(f"Group calibration completed:")
    logger.info(f"  Successful: {successful_qubits}")
    if failed_qubits:
        logger.warning(f"  Failed: {failed_qubits}")

    return results


@flow
def custom_parallel_flow(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    flow_name: str | None = None,  # Automatically injected by API
):
    """Custom parallel calibration with simple group execution.

    Example: Execute (32→33) and (36→38) in parallel
    - Group 1: Calibrate 32, then 33 (sequential)
    - Group 2: Calibrate 36, then 38 (sequential)
    - Both groups run in parallel

    Note: username and chip_id are automatically provided from UI properties.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        qids: List of qubit IDs (not used, groups are defined explicitly)

    """
    logger = get_run_logger()

    # TODO: Define your qubit groups
    group1 = ["33", "32"]  # 32 → 33
    group2 = ["36", "38"]  # 36 → 38

    all_qids = group1 + group2

    logger.info(f"Starting calibration for user={username}, chip_id={chip_id}")
    logger.info(f"Group 1: {group1} (sequential)")
    logger.info(f"Group 2: {group2} (sequential)")
    logger.info("Groups will run in parallel")

    # Initialize session
    session = init_calibration(username, chip_id, all_qids)

    # TODO: Edit the tasks you want to run
    tasks = ["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"]

    # Submit both groups for parallel execution
    logger.info("Submitting groups for parallel execution...")
    future1 = calibrate_group.submit(qids=group1, tasks=tasks)
    future2 = calibrate_group.submit(qids=group2, tasks=tasks)

    # Wait for completion
    logger.info("Waiting for groups to complete...")
    results1 = future1.result()
    results2 = future2.result()

    # Combine results
    all_results = {**results1, **results2}

    finish_calibration()

    return all_results
