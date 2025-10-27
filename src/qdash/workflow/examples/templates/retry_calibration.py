"""Retry calibration with different parameters for failed qubits.

Based on full_qubit_calibration with automatic retry capability:
1. Execute complete 1-qubit calibration suite with default parameters
2. Detect failed qubits
3. Retry failed qubits with alternative parameters
4. Supports group-based parallel execution
5. Report final success/failure status

Useful when some qubits fail due to parameter sensitivity.
"""

from prefect import flow, get_run_logger, task
from qdash.workflow.helpers import finish_calibration, get_session, init_calibration


@task
def calibrate_group_with_retry(
    qids: list[str], tasks: list[str], retry_strategies: list[dict | None], max_retries: int
) -> dict:
    """Execute complete calibration suite for a group of qubits with smart per-qubit retry.

    Each qubit is calibrated independently with immediate retry on failure.
    - Successfully completed qubits are NOT retried
    - Failed qubits retry ALL tasks from the beginning (due to task dependencies)

    For example, if Q33 fails on CheckPIPulse:
    - Q32: All tasks succeed → No retry needed
    - Q33: Fails on CheckPIPulse → Retry ALL tasks from CheckRabi with new parameters
    - Q36: All tasks succeed → No retry needed

    This is because calibration tasks have dependencies (e.g., CheckPIPulse depends on
    CreatePIPulse which depends on CheckRabi), so changing parameters requires full re-execution.

    Args:
    ----
        qids: List of qubit IDs to calibrate (executed in order)
        tasks: List of task names to execute
        retry_strategies: List of task_details for each retry attempt
        max_retries: Maximum number of retry attempts per qubit

    Returns:
    -------
        Results for each qubit with status, attempt count, and failed task info

    """
    logger = get_run_logger()
    logger.info(f"Starting group calibration with retry for qubits: {qids}")

    session = get_session()
    results = {}

    # Execute each qubit in order with immediate retry capability
    for qid in qids:
        logger.info(f"  Calibrating qubit {qid}...")

        # Try calibration with retry logic
        for attempt in range(1, max_retries + 1):
            task_details = retry_strategies[attempt - 1] if attempt <= len(retry_strategies) else None

            if attempt > 1:
                logger.info(f"  Retry attempt {attempt} for qubit {qid} - re-executing ALL tasks from beginning...")
                if task_details:
                    logger.info(f"    Using custom parameters: {list(task_details.keys())}")

            try:
                # Execute all tasks from beginning (due to task dependencies)
                result = {}
                for task_name in tasks:
                    logger.info(f"    Executing {task_name}...")
                    task_result = session.execute_task(task_name, qid, task_details=task_details)
                    result[task_name] = task_result

                # All tasks completed successfully
                logger.info(f"  ✓ Qubit {qid} completed all tasks successfully on attempt {attempt}")
                result["status"] = "success"
                result["attempt"] = attempt
                results[qid] = result
                break  # Success - move to next qubit

            except Exception as e:
                # Failed - record failure info
                failed_task = str(e).split(":")[0] if ":" in str(e) else "unknown"

                logger.error(f"  ✗ Failed to calibrate qubit {qid} on attempt {attempt}: {e}")

                if attempt < max_retries:
                    logger.warning(
                        f"  Will retry qubit {qid} from the beginning with different parameters "
                        f"(attempt {attempt + 1}/{max_retries})..."
                    )
                else:
                    logger.warning(f"  Max retries reached for qubit {qid} - giving up")
                    result = {
                        "status": "failed",
                        "error": str(e),
                        "failed_task": failed_task,
                        "attempt": attempt,
                    }
                    results[qid] = result

    return results


@flow
def retry_calibration(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    flow_name: str | None = None,  # Automatically injected by API
    max_retries: int = 2,  # Maximum number of retry attempts
):
    """Complete 1-qubit calibration with automatic retry for failed qubits.

    This flow combines full_qubit_calibration with adaptive retry:
    1. Execute complete calibration suite with default parameters
    2. Detect failed qubits
    3. Retry failed qubits with alternative parameters (e.g., wider frequency range)
    4. Supports group-based parallel execution
    5. Report final results

    Example retry strategy:
    - Attempt 1: Default parameters (detune_frequency=0)
    - Attempt 2: Increased frequency range (detune_frequency=5.0)
    - Attempt 3: Even larger range (detune_frequency=10.0)

    Note: username and chip_id are automatically provided from UI properties.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        qids: List of qubit IDs (not used, groups are defined explicitly)
        flow_name: Flow name (automatically injected by API)
        max_retries: Maximum number of retry attempts (default: 2)

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

    logger.info(f"Starting retry calibration for user={username}, chip_id={chip_id}")
    for i, group in enumerate(groups, start=1):
        logger.info(f"Group {i}: {group} (sequential)")
    logger.info(f"Max retries: {max_retries}")

    try:
        # Initialize session
        init_calibration(username, chip_id, all_qids, flow_name=flow_name)

        # Complete 1-qubit calibration task suite (same as full_qubit_calibration)
        tasks = [
            # Phase 1: Basic characterization
            "CheckRabi",
            # Phase 2: Half-pi pulse optimization
            "CreateHPIPulse",
            "CheckHPIPulse",
            # Phase 3: Pi pulse optimization
            "CreatePIPulse",
            "CheckPIPulse",
            # Phase 4: Decoherence characterization
            "CheckT1",
            "CheckT2Echo",
            # Phase 5: DRAG pulse optimization
            "CreateDRAGHPIPulse",
            "CheckDRAGHPIPulse",
            "CreateDRAGPIPulse",
            "CheckDRAGPIPulse",
            # Phase 6: Readout calibration
            "ReadoutClassification",
            # Phase 7: Gate benchmarking
            "RandomizedBenchmarking",
            "X90InterleavedRandomizedBenchmarking",
        ]

        # TODO: Define retry strategies - adjust parameters for each retry attempt
        retry_strategies = [
            None,  # Attempt 1: Default parameters
            {
                "CheckRabi": {
                    "input_parameters": {
                        "detune_frequency": {"value": 5.0}  # MHz - wider frequency range
                    }
                }
            },  # Attempt 2: Retry with increased frequency range
            {
                "CheckRabi": {
                    "input_parameters": {
                        "detune_frequency": {"value": 10.0}  # MHz - even wider range
                    }
                }
            },  # Attempt 3: Retry with larger frequency range
        ]

        # Submit all groups for parallel execution (each group handles its own retries)
        logger.info("Submitting groups for parallel execution...")
        logger.info("Each group will retry failed qubits immediately without waiting for other groups")
        futures = [
            calibrate_group_with_retry.submit(
                qids=group, tasks=tasks, retry_strategies=retry_strategies, max_retries=max_retries
            )
            for group in groups
        ]

        # Wait for completion
        logger.info("Waiting for groups to complete...")
        results_list = [future.result() for future in futures]

        # Combine results from all groups
        all_results = {}
        for result_dict in results_list:
            all_results.update(result_dict)

        # Final summary
        logger.info("=" * 60)
        logger.info("FINAL RESULTS")
        logger.info("=" * 60)

        successful_qubits = [qid for qid, r in all_results.items() if r["status"] == "success"]
        final_failed_qubits = [qid for qid, r in all_results.items() if r["status"] == "failed"]

        logger.info(f"Successful qubits ({len(successful_qubits)}): {successful_qubits}")
        if final_failed_qubits:
            logger.warning(f"Failed qubits ({len(final_failed_qubits)}): {final_failed_qubits}")
            for qid in final_failed_qubits:
                logger.warning(f"  {qid}: {all_results[qid].get('error', 'Unknown error')}")
            logger.warning("Consider manual investigation or different retry strategies")
        else:
            logger.info("All qubits completed successfully!")

        finish_calibration()

        logger.info("Retry calibration completed!")
        return all_results

    except Exception as e:
        logger.error(f"Retry calibration failed: {e}")
        session = get_session()
        session.fail_calibration(str(e))
        raise
