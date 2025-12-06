"""2-Qubit coupling calibration flow template.

This template demonstrates group-based parallel execution for coupling calibration.
Multiple groups run in parallel, while pairs within each group execute sequentially.

Key concepts:
- Coupling IDs use "control-target" format (e.g., "0-1")
- Groups run in parallel (using Prefect @task + submit)
- Pairs within each group execute sequentially
- All qubits in coupling pairs must be included in initialization

For single-qubit calibration, see simple_flow.py or custom_parallel_flow.py.
"""

from prefect import flow, get_run_logger, task
from qdash.workflow.flow import finish_calibration, get_session, init_calibration


@task
def calibrate_coupling_group(coupling_qids: list[str], tasks: list[str]) -> dict:
    """Execute coupling tasks for a group of qubit pairs.

    Args:
    ----
        coupling_qids: List of coupling IDs in "control-target" format (e.g., ["0-1", "2-3"])
        tasks: List of coupling task names to execute

    Returns:
    -------
        Results for all couplings in the group

    """
    logger = get_run_logger()
    session = get_session()
    results = {}

    for coupling_qid in coupling_qids:
        try:
            result = {}
            for task_name in tasks:
                task_result = session.execute_task(task_name, coupling_qid)
                result[task_name] = task_result

            result["status"] = "success"

        except Exception as e:
            logger.error(f"Failed to calibrate coupling {coupling_qid}: {e}")
            result = {"status": "failed", "error": str(e)}

        results[coupling_qid] = result

    return results


@flow
def my_coupling_flow(
    username: str,
    chip_id: str,
    coupling_groups: list[list[tuple[str, str]]] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,  # Automatically injected by API for multi-tenancy
):
    """2-Qubit coupling calibration flow with group-based parallel execution.

    Example (sequential within groups, groups run in parallel):
        coupling_groups = [
            [("0", "1"), ("2", "3")],  # Group 1: 0-1 → 2-3 (sequential)
            [("4", "5"), ("6", "7")],  # Group 2: 4-5 → 6-7 (sequential)
        ]
        # Group 1 and Group 2 run in parallel

    Example (single group, all sequential):
        coupling_groups = [
            [("0", "1"), ("2", "3"), ("4", "5")]  # All sequential
        ]

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        coupling_groups: List of groups, where each group contains coupling pairs as (control, target).
            Groups run in parallel, pairs within a group run sequentially.
        flow_name: Flow name (automatically injected by API)
        project_id: Project ID for multi-tenancy (automatically injected by API)

    """
    logger = get_run_logger()

    if coupling_groups is None:
        # TODO: Define your coupling groups
        coupling_groups = [
            [("0", "1")],  # Group 1
            [("2", "3")],  # Group 2
        ]

    # Convert groups to coupling ID format
    coupling_qid_groups = [[f"{c}-{t}" for c, t in group] for group in coupling_groups]

    # Extract all unique qubit IDs for initialization
    all_qids = list(set([qid for group in coupling_groups for pair in group for qid in pair]))

    logger.info(f"Starting coupling calibration with {len(coupling_groups)} groups")
    for i, group in enumerate(coupling_qid_groups, start=1):
        logger.info(f"Group {i}: {group} (sequential)")

    try:
        # Initialize session with GitHub integration
        from qdash.workflow.flow import ConfigFileType, GitHubPushConfig

        init_calibration(
            username,
            chip_id,
            all_qids,
            flow_name=flow_name,
            project_id=project_id,
            enable_github_pull=True,
            github_push_config=GitHubPushConfig(
                enabled=True, file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS]
            ),
        )

        # TODO: Edit the coupling tasks you want to run
        # Available: CheckCrossResonance, CheckBellState, CheckZX90, CreateZX90
        tasks = ["CheckCrossResonance"]

        # Submit all groups for parallel execution
        futures = [calibrate_coupling_group.submit(group, tasks) for group in coupling_qid_groups]
        results_list = [f.result() for f in futures]

        # Combine results
        results = {}
        for r in results_list:
            results.update(r)

        finish_calibration()
        return results

    except Exception as e:
        logger.error(f"Coupling calibration failed: {e}")
        try:
            session = get_session()
            session.fail_calibration(str(e))
        except RuntimeError:
            # Session not initialized yet, skip fail_calibration
            pass
        raise
