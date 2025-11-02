"""Simple sequential calibration flow template.

This is the simplest example - tasks are executed sequentially for each qubit.
Each qubit is processed independently - if one fails, the next qubit continues.
For parallel execution, see custom_parallel_flow.py instead.
"""

from prefect import flow, get_run_logger
from qdash.workflow.flow import finish_calibration, get_session, init_calibration


def calibrate_single_qubit(qid: str, tasks: list[str]) -> dict:
    """Execute tasks for a single qubit with error handling.

    If a task fails, remaining tasks for this qubit are skipped.

    Args:
    ----
        qid: Qubit ID to calibrate
        tasks: List of task names to execute

    Returns:
    -------
        Results for this qubit (includes error information if failed)

    """
    logger = get_run_logger()
    session = get_session()
    result = {}

    try:
        logger.info(f"Calibrating qubit {qid}...")

        for task_name in tasks:
            logger.info(f"  Executing {task_name}...")
            task_result = session.execute_task(task_name, qid)
            result[task_name] = task_result

        logger.info(f"  ✓ Qubit {qid} completed successfully")
        result["status"] = "success"

    except Exception as e:
        logger.error(f"  ✗ Failed to calibrate qubit {qid}: {e}")
        logger.warning(f"  Skipping remaining tasks for qubit {qid}")
        result["status"] = "failed"
        result["error"] = str(e)

    return result


@flow
def my_custom_flow(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    flow_name: str | None = None,  # Automatically injected by API
):
    """Simple sequential calibration flow for demonstration.

    This flow executes tasks sequentially:
    - For each qubit, execute all tasks in order
    - Qubits are also processed sequentially

    For parallel execution across qubits, see custom_parallel_flow.py.

    Note: username and chip_id are automatically provided from UI properties.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        qids: List of qubit IDs to calibrate (e.g., ["32", "38"])
        flow_name: Flow name (automatically injected by API)

    """
    logger = get_run_logger()

    if qids is None:
        qids = ["32", "33"]  # TODO: Change to your qubit IDs

    logger.info(f"Starting calibration for user={username}, chip_id={chip_id}, qids={qids}")

    try:
        # Initialize calibration session with GitHub integration
        from qdash.workflow.flow import GitHubPushConfig, ConfigFileType
        init_calibration(
            username, chip_id, qids, flow_name=flow_name,
            enable_github_pull=True,  # Pull latest config before calibration
            github_push_config=GitHubPushConfig(
                enabled=True,
                file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
                commit_message=f"Update calibration results for {chip_id}"
            )
        )

        # TODO: Edit the tasks you want to run
        # Available tasks: CheckRabi, CreateHPIPulse, CheckHPIPulse, etc.
        tasks = ["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"]

        # Execute tasks sequentially for each qubit
        # If one qubit fails, continue with the next qubit
        results = {}

        for qid in qids:
            result = calibrate_single_qubit(qid, tasks)
            results[qid] = result

        # Finish calibration
        finish_calibration()

        return results

    except Exception as e:
        logger.error(f"Calibration failed: {e}")
        try:
            session = get_session()
            session.fail_calibration(str(e))
        except RuntimeError:
            # Session not initialized yet, skip fail_calibration
            pass
        raise
