"""Two-qubit parallel calibration with constraint management.

This template demonstrates how to execute 2-qubit coupling calibration tasks
with parallel execution constraints (no shared qubits within a parallel group).

Example use case:
- Parallel group 1: [Q0-Q1, Q2-Q3] - both run simultaneously (no shared qubits)
- Parallel group 2: [Q1-Q2, Q4-Q5] - both run simultaneously (no shared qubits)
- Parallel group 3: [Q3-Q4] - runs alone

Pattern: init → parallel_group_1 → parallel_group_2 → ... → finish

All groups execute under a single execution_id with clear parallel group boundaries.

This pattern is useful when:
- Need to manage parallel execution constraints (no shared qubits within a group)
- Want to maximize parallelization while respecting hardware constraints
- Need clear execution tracking with group boundaries in logs
"""

from prefect import flow, get_run_logger, task
from qdash.workflow.flow import finish_calibration, get_session, init_calibration


@task
def execute_coupling_pair(coupling_qid: str, tasks: list[str]) -> tuple[str, dict]:
    """Execute tasks for a single coupling pair with error handling.

    Args:
    ----
        coupling_qid: Coupling ID in "control-target" format (e.g., "0-1")
        tasks: List of coupling task names to execute

    Returns:
    -------
        Tuple of (coupling_qid, result dict)

    """
    logger = get_run_logger()
    session = get_session()

    logger.info(f"  Calibrating coupling {coupling_qid}...")

    try:
        result = {}
        for task_name in tasks:
            logger.info(f"    [{coupling_qid}] Executing {task_name}...")
            task_result = session.execute_task(task_name, coupling_qid)
            result[task_name] = task_result

        logger.info(f"  ✓ Coupling {coupling_qid} completed successfully")
        result["status"] = "success"

    except Exception as e:
        logger.error(f"  ✗ Failed to calibrate coupling {coupling_qid}: {e}")
        result = {"status": "failed", "error": str(e)}

    return coupling_qid, result


@task
def calibrate_parallel_group(coupling_qids: list[str], tasks: list[str]) -> dict:
    """Execute coupling tasks for a parallel group of qubit pairs with error handling.

    All coupling pairs in this group run in parallel since they don't share qubits.
    If a coupling pair fails during calibration, it will be marked as failed in the results.

    Args:
    ----
        coupling_qids: List of coupling IDs in "control-target" format (e.g., ["0-1", "2-3"])
                       All pairs in this list can run simultaneously (no shared qubits)
        tasks: List of coupling task names to execute

    Returns:
    -------
        Results for the parallel group (includes error information for failed pairs)

    """
    logger = get_run_logger()
    logger.info(f"Starting parallel group calibration for pairs: {coupling_qids}")

    # Submit all pairs for parallel execution
    futures = [
        execute_coupling_pair.submit(coupling_qid, tasks)
        for coupling_qid in coupling_qids
    ]

    # Wait for all pairs to complete
    logger.info(f"  Waiting for {len(futures)} pairs to complete in parallel...")
    pair_results = [future.result() for future in futures]

    # Combine results
    results = {}
    for qid, result in pair_results:
        results[qid] = result

    return results


@flow
def two_qubit_parallel_calibration(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,
):
    """Two-qubit parallel calibration with constraint management.

    This flow executes 2-qubit coupling calibration tasks with parallel groups
    to manage qubit-sharing constraints. All groups execute under a single execution_id.

    Example execution:
    - Parallel group 1: [Q0-Q1, Q2-Q3] (both run simultaneously)
    - Parallel group 2: [Q1-Q2, Q4-Q5] (both run simultaneously)
    - Parallel group 3: [Q3-Q4] (runs alone)

    Key concept - Parallel Groups:
    Each parallel group contains coupling pairs that can run simultaneously
    because they don't share any qubits. Groups execute sequentially.

    Standard 2-qubit calibration tasks:
    - Cross-resonance calibration (CheckCrossResonance)
    - ZX90 gate calibration (CreateZX90, CheckZX90)
    - Bell state verification (CheckBellState)

    Benefits:
    - Single execution_id for the entire calibration
    - Parallel groups naturally express qubit-sharing constraints
    - Simple and intuitive structure
    - Clear group boundaries in logs

    Args:
    ----
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        qids: Qubit IDs (not used, defined explicitly in stages)
        flow_name: Flow name (auto-injected)

    """
    logger = get_run_logger()

    # TODO: Define parallel groups
    # Each group contains coupling pairs that can run simultaneously (no shared qubits)
    # Groups execute sequentially
    # Coupling pairs: (control, target) format
    #
    # Example:
    # parallel_groups = [
    #     [("0", "1"), ("2", "3")],  # Group 1: Both run in parallel
    #     [("1", "2"), ("4", "5")],  # Group 2: Both run in parallel
    #     [("3", "4")],              # Group 3: Runs alone
    # ]
    parallel_groups = [
        # Group 1: These pairs run simultaneously (no shared qubits)
        [("0", "1"), ("2", "3")],
        # Group 2: These pairs run simultaneously (no shared qubits)
        [("1", "2")],
        # Add more parallel groups as needed
    ]

    # Standard 2-qubit calibration task suite
    tasks = [
        # Phase 1: Cross-resonance calibration
        "CheckCrossResonance",  # Optimize cross-resonance parameters
        # Phase 2: ZX90 gate calibration
        "CreateZX90",           # Create ZX90 gate pulse
        "CheckZX90",            # Verify ZX90 gate performance
        # Phase 3: Entanglement verification
        "CheckBellState",       # Verify Bell state fidelity
    ]

    # Convert coupling groups to ID format and extract all qubits
    coupling_qid_groups = [[f"{c}-{t}" for c, t in group] for group in parallel_groups]
    all_qids = list(set(qid for group in parallel_groups for pair in group for qid in pair))

    total_pairs = sum(len(group) for group in parallel_groups)
    total_groups = len(parallel_groups)
    logger.info(f"Starting two-qubit parallel calibration for chip_id={chip_id}")
    logger.info(f"Total: {total_pairs} coupling pairs in {total_groups} parallel groups")

    try:
        # Initialize calibration session with GitHub integration
        from qdash.workflow.flow import GitHubPushConfig, ConfigFileType
        init_calibration(
            username, chip_id, all_qids, flow_name=flow_name,
            enable_github_pull=True,
            github_push_config=GitHubPushConfig(
                enabled=True,
                file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS]
            )
        )

        # Execute parallel groups sequentially (pairs within each group run in parallel)
        logger.info(f"Executing {len(coupling_qid_groups)} parallel groups sequentially...")
        results_list = []
        for group_idx, group in enumerate(coupling_qid_groups, start=1):
            logger.info(f"  Group {group_idx}/{len(coupling_qid_groups)}: Executing {len(group)} pairs in parallel: {group}")
            # Call directly (no submit) since groups execute sequentially
            result = calibrate_parallel_group(coupling_qids=group, tasks=tasks)
            results_list.append(result)
            logger.info(f"    ✓ Group {group_idx} completed")

        # Combine results
        results = {}
        for r in results_list:
            results.update(r)

        # Finish calibration session
        finish_calibration()
        logger.info("✓ Two-qubit parallel calibration completed successfully!")

        return results

    except Exception as e:
        logger.error(f"Two-qubit parallel calibration failed: {e}")
        try:
            session = get_session()
            session.fail_calibration(str(e))
        except RuntimeError:
            pass
        raise
