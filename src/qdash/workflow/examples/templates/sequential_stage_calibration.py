"""Sequential stage calibration: Multiple stages with isolated sessions.

This template demonstrates how to execute the same calibration tasks across
multiple stages where hardware constraints prevent simultaneous execution.

Example use case:
- Chassis A qubits: Q0, Q1, Q2 (cannot run simultaneously with Chassis B)
- Chassis B qubits: Q3, Q4, Q5 (cannot run simultaneously with Chassis A)

Pattern: [init → Stage1 parallel → finish] → [init → Stage2 parallel → finish] → ...

Each stage has its own execution_id, providing clear separation in execution history.

This pattern is useful when:
- Hardware constraints prevent simultaneous execution across different groups
- You want separate execution tracking per stage/chassis
- Clear stage boundaries in execution history and logs
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
def sequential_stage_calibration(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,
):
    """Sequential stage calibration with isolated sessions per stage.

    This flow executes the same calibration tasks across multiple stages
    with complete isolation between stages. Each stage gets its own execution_id.

    Example: Chassis-based execution
    - Stage 1 (Chassis A): Q0, Q1, Q2 → execution_id: "20250102-001"
    - Stage 2 (Chassis B): Q3, Q4, Q5 → execution_id: "20250102-002"

    All standard 1-qubit calibration tasks:
    - Basic characterization (Rabi, T1, T2)
    - Pulse optimization (HPI, PI, DRAG)
    - Readout calibration
    - Benchmarking (RB, IRB)

    Benefits:
    - Each stage has separate execution_id for clear tracking
    - Complete isolation prevents resource conflicts between chassis
    - Easy to identify stage in execution history
    - Clear stage boundaries in logs

    Args:
    ----
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        qids: Qubit IDs (not used, defined explicitly in stages)
        flow_name: Flow name (auto-injected)

    """
    logger = get_run_logger()

    # TODO: Define stages with qubit groups
    # Each stage runs independently with its own execution_id
    # Groups within a stage run in parallel
    stages = [
        {
            "name": "Chassis_A",
            "groups": [
                ["0", "1"],  # Group 1 in Chassis A (parallel)
                ["2"],  # Group 2 in Chassis A (parallel)
            ],
        },
        {
            "name": "Chassis_B",
            "groups": [
                ["3", "4"],  # Group 1 in Chassis B (parallel)
                ["5"],  # Group 2 in Chassis B (parallel)
            ],
        },
        # Add more stages as needed
    ]

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

    logger.info(f"Starting sequential stage calibration for chip_id={chip_id}")
    logger.info(f"Total stages: {len(stages)}")
    for i, stage in enumerate(stages, start=1):
        logger.info(f"  Stage {i} ({stage['name']}): {sum(len(g) for g in stage['groups'])} qubits")

    all_results = {}

    try:
        # Execute each stage sequentially
        for stage_idx, stage in enumerate(stages, start=1):
            stage_name = stage["name"]
            stage_groups = stage["groups"]

            logger.info("=" * 60)
            logger.info(f"STAGE {stage_idx}: {stage_name}")
            logger.info("=" * 60)

            # Flatten qids for this stage
            stage_qids = list(set(qid for group in stage_groups for qid in group))

            # Initialize NEW session for this stage with GitHub integration
            # A NEW execution_id will be auto-generated (e.g., "20250102-001", "20250102-002", ...)
            from qdash.workflow.flow import ConfigFileType, GitHubPushConfig

            init_calibration(
                username,
                chip_id,
                stage_qids,
                flow_name=f"{flow_name}_{stage_name}" if flow_name else stage_name,
                enable_github_pull=True,
                github_push_config=GitHubPushConfig(
                    enabled=True, file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS]
                ),
            )

            # Execute all groups in this stage in parallel
            logger.info(f"Submitting {len(stage_groups)} groups for parallel execution...")
            stage_futures = [calibrate_group.submit(qids=group, tasks=tasks) for group in stage_groups]

            logger.info(f"Waiting for all groups in {stage_name} to complete...")
            stage_results_list = [future.result() for future in stage_futures]

            # Combine results for this stage
            stage_results = {}
            for results in stage_results_list:
                stage_results.update(results)

            # Store results with stage name
            all_results[stage_name] = stage_results

            # Finish this stage's session
            finish_calibration()
            logger.info(f"✓ Stage {stage_idx} ({stage_name}) session completed and closed!")

        logger.info("=" * 60)
        logger.info("Sequential stage calibration completed successfully!")
        logger.info("=" * 60)

        return all_results

    except Exception as e:
        logger.error(f"Sequential stage calibration failed: {e}")
        try:
            session = get_session()
            session.fail_calibration(str(e))
        except RuntimeError:
            pass
        raise
