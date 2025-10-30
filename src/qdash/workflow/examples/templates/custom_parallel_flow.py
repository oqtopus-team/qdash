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

    # Execute each qubit in order
    for qid in qids:
        logger.info(f"  Calibrating qubit {qid}...")

        try:
            # Execute all tasks for this qubit
            result = {}
            for task_name in tasks:
                logger.info(f"    Executing {task_name}...")
                task_result = session.execute_task(task_name, qid)
                result[task_name] = task_result

            logger.info(f"  ✓ Qubit {qid} completed successfully")
            result["status"] = "success"

        except Exception as e:
            # Log the error and continue with next qubit
            logger.error(f"  ✗ Failed to calibrate qubit {qid}: {e}")
            logger.warning(f"  Skipping remaining tasks for qubit {qid}")
            result["status"] = "failed"
            result["error"] = str(e)

        results[qid] = result

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
    groups = [
        ["33", "32"],  # Group 1: 32 → 33 (sequential)
        ["36", "38"],  # Group 2: 36 → 38 (sequential)
        # Add more groups as needed
    ]

    # Flatten all qids for initialization
    all_qids = [qid for group in groups for qid in group]

    logger.info(f"Starting calibration for user={username}, chip_id={chip_id}")
    for i, group in enumerate(groups, start=1):
        logger.info(f"Group {i}: {group} (sequential)")
    logger.info("Groups will run in parallel")

    try:
        # Initialize session
        init_calibration(username, chip_id, all_qids, flow_name=flow_name)

        # Optional: GitHub integration (uncomment to enable)
        # from qdash.workflow.helpers import GitHubPushConfig, ConfigFileType
        # init_calibration(
        #     username, chip_id, all_qids, flow_name=flow_name,
        #     enable_github_pull=True,
        #     github_push_config=GitHubPushConfig(
        #         enabled=True,
        #         file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.PROPS]
        #     )
        # )

        # TODO: Edit the tasks you want to run
        tasks = ["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"]

        # Submit all groups for parallel execution
        logger.info("Submitting groups for parallel execution...")
        futures = [calibrate_group.submit(qids=group, tasks=tasks) for group in groups]

        # Wait for completion
        logger.info("Waiting for groups to complete...")
        results_list = [future.result() for future in futures]

        # Combine results
        all_results = {}
        for results in results_list:
            all_results.update(results)

        finish_calibration()

        return all_results

    except Exception as e:
        logger.error(f"Custom parallel calibration failed: {e}")
        try:
            session = get_session()
            session.fail_calibration(str(e))
        except RuntimeError:
            # Session not initialized yet, skip fail_calibration
            pass
        raise
