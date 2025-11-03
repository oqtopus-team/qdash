"""Complete 1-qubit calibration flow with all standard tasks.

This template includes all standard single-qubit calibration tasks:
- Basic characterization (Rabi, T1, T2)
- Pulse optimization (HPI, PI, DRAG)
- Readout calibration
- Benchmarking (RB, IRB)

Supports parallel execution across multiple qubit groups.
"""

from prefect import flow, get_run_logger, task
from qdash.workflow.flow import finish_calibration, get_session, init_calibration


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
def full_qubit_calibration(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    flow_name: str | None = None,  # Automatically injected by API
):
    """Complete 1-qubit calibration with all standard tasks.

    This flow executes a comprehensive calibration suite for single qubits:
    1. Basic characterization (Rabi oscillations, T1, T2)
    2. Pulse creation and optimization (HPI, PI, DRAG)
    3. Readout calibration
    4. Gate benchmarking (RB, IRB)

    Supports parallel execution across multiple qubit groups.

    Example: Calibrate two groups in parallel
    - Group 1: Q32 → Q33 (sequential)
    - Group 2: Q36 → Q38 (sequential)

    Note: username and chip_id are automatically provided from UI properties.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        qids: List of qubit IDs (not used, groups are defined explicitly)
        flow_name: Flow name (automatically injected by API)

    """
    logger = get_run_logger()

    # TODO: Define your qubit groups
    groups = [
        ["32", "33"],  # Group 1: Q32 → Q33 (sequential)
        ["36", "38"],  # Group 2: Q36 → Q38 (sequential)
        # Add more groups as needed
    ]

    # Flatten all qids for initialization
    all_qids = [qid for group in groups for qid in group]

    logger.info(f"Starting full qubit calibration for user={username}, chip_id={chip_id}")
    for i, group in enumerate(groups, start=1):
        logger.info(f"Group {i}: {group} (sequential)")
    logger.info("Groups will run in parallel")

    try:
        # Initialize session with GitHub integration
        from qdash.workflow.flow import ConfigFileType, GitHubPushConfig

        init_calibration(
            username,
            chip_id,
            all_qids,
            flow_name=flow_name,
            enable_github_pull=True,
            github_push_config=GitHubPushConfig(
                enabled=True, file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS]
            ),
        )

        # Complete 1-qubit calibration task suite
        tasks = [
            # Phase 1: Basic characterization
            "CheckRabi",  # Rabi oscillations for pi-pulse calibration
            # Phase 2: Half-pi pulse optimization
            "CreateHPIPulse",  # Create half-pi pulse
            "CheckHPIPulse",  # Verify half-pi pulse
            # Phase 3: Pi pulse optimization
            "CreatePIPulse",  # Create pi pulse
            "CheckPIPulse",  # Verify pi pulse
            # Phase 4: Decoherence characterization
            "CheckT1",  # Energy relaxation time
            "CheckT2Echo",  # Dephasing time (echo)
            # Phase 5: DRAG pulse optimization
            "CreateDRAGHPIPulse",  # Create DRAG half-pi pulse
            "CheckDRAGHPIPulse",  # Verify DRAG half-pi pulse
            "CreateDRAGPIPulse",  # Create DRAG pi pulse
            "CheckDRAGPIPulse",  # Verify DRAG pi pulse
            # Phase 6: Readout calibration
            "ReadoutClassification",  # Optimize readout fidelity
            # Phase 7: Gate benchmarking
            "RandomizedBenchmarking",  # Overall gate fidelity (RB)
            "X90InterleavedRandomizedBenchmarking",  # X90 gate fidelity (IRB)
        ]

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

        logger.info("Full qubit calibration completed successfully!")
        return all_results

    except Exception as e:
        logger.error(f"Full qubit calibration failed: {e}")
        try:
            session = get_session()
            session.fail_calibration(str(e))
        except RuntimeError:
            # Session not initialized yet, skip fail_calibration
            pass
        raise
