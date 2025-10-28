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


def _apply_frequency_offset_strategy(
    retry_strategy: dict | None,
    tasks_before_ramsey: list[str],
    session,
    qid: str,
    logger,
    attempt: int,
) -> dict | None:
    """Apply frequency offset strategy for retry attempts.

    Args:
        retry_strategy: Retry strategy configuration (e.g., {"frequency_offset": 0.01})
        tasks_before_ramsey: List of task names to apply frequency override
        session: FlowSession instance
        qid: Qubit ID
        logger: Prefect logger
        attempt: Current attempt number

    Returns:
        task_details with frequency override, or None if no offset strategy

    """
    if retry_strategy is None or "frequency_offset" not in retry_strategy:
        if attempt > 1:
            logger.info(f"  Retry attempt {attempt} for qubit {qid} - re-executing ALL tasks from beginning...")
        return None

    frequency_offset = retry_strategy["frequency_offset"]

    # Get current default frequency for this qubit
    exp = session.session.get_session()
    label = exp.get_qubit_label(int(qid))
    current_freq = exp.experiment_system.quantum_system.get_qubit(label).frequency
    target_freq = current_freq + frequency_offset

    logger.info(f"  Retry attempt {attempt} for qubit {qid}")
    logger.info(f"    Current frequency: {current_freq:.6f} GHz")
    logger.info(f"    Frequency offset: {frequency_offset:+.3f} GHz ({frequency_offset*1000:+.0f} MHz)")
    logger.info(f"    Target frequency: {target_freq:.6f} GHz")

    # Create task_details with frequency override for all tasks_before_ramsey
    # Note: Only 'value' needs to be specified - unit/value_type/description are preserved from task definition
    task_details = {}
    for task_name in tasks_before_ramsey:
        task_details[task_name] = {"input_parameters": {"qubit_frequency": {"value": target_freq}}}

    return task_details


def _execute_tasks_before_ramsey(
    tasks_before_ramsey: list[str],
    session,
    qid: str,
    task_details: dict | None,
    logger,
) -> dict:
    """Execute Phase 1: tasks before CheckRamsey.

    Args:
        tasks_before_ramsey: List of task names to execute
        session: FlowSession instance
        qid: Qubit ID
        task_details: Optional task configuration with frequency override
        logger: Prefect logger

    Returns:
        Dictionary of task results

    """
    result = {}
    for task_name in tasks_before_ramsey:
        task_result = session.execute_task(task_name, qid, task_details=task_details)
        result[task_name] = task_result

    return result


def _execute_ramsey_with_fallback(
    session,
    qid: str,
    task_details: dict | None,
    logger,
) -> tuple[dict, float | None, bool]:
    """Execute Phase 2: CheckRamsey with fallback to default frequency on failure.

    Args:
        session: FlowSession instance
        qid: Qubit ID
        task_details: Optional task configuration
        logger: Prefect logger

    Returns:
        Tuple of (ramsey_result_dict, measured_frequency_or_None, success_flag)

    """
    logger.info(f"    Executing CheckRamsey to measure accurate frequency...")
    measured_freq = None

    try:
        ramsey_result = session.execute_task("CheckRamsey", qid, task_details=task_details)

        # Extract values from OutputParameterModel if needed
        measured_freq_raw = ramsey_result.get("bare_frequency")
        ramsey_freq_raw = ramsey_result.get("ramsey_frequency")
        t2_star_raw = ramsey_result.get("t2_star")

        # Convert OutputParameterModel to float values
        from qdash.datamodel.task import OutputParameterModel

        measured_freq = (
            measured_freq_raw.value if isinstance(measured_freq_raw, OutputParameterModel) else measured_freq_raw
        )
        ramsey_freq = ramsey_freq_raw.value if isinstance(ramsey_freq_raw, OutputParameterModel) else ramsey_freq_raw
        t2_star = t2_star_raw.value if isinstance(t2_star_raw, OutputParameterModel) else t2_star_raw

        # Log Ramsey measurement result
        logger.info(
            f"    ✓ CheckRamsey: {measured_freq:.6f} GHz (R_freq={ramsey_freq:.1f} MHz, T2*={t2_star:.1f} μs)"
            if ramsey_freq and t2_star
            else f"    ✓ CheckRamsey: {measured_freq:.6f} GHz"
        )

        return {"CheckRamsey": ramsey_result}, measured_freq, True

    except Exception as ramsey_error:
        # Log error information
        logger.warning(f"    ✗ CheckRamsey failed: {str(ramsey_error)}")

        return {"CheckRamsey": {"error": str(ramsey_error)}}, None, False


def _execute_tasks_after_ramsey(
    tasks_after_ramsey: list[str],
    session: "FlowSession",
    qid: str,
    task_details: dict | None,
    measured_freq: float | None,
    logger,
) -> dict:
    """Execute tasks after CheckRamsey with frequency feedback.

    Args:
        tasks_after_ramsey: List of task names to execute after Ramsey
        session: FlowSession instance
        qid: Qubit ID
        task_details: Task details (may contain frequency offset from retry strategy)
        measured_freq: Measured frequency from CheckRamsey, or None if failed
        logger: Prefect logger

    Returns:
        Dictionary of task results

    """
    result = {}

    for task_name in tasks_after_ramsey:
        # Determine which task_details to use
        if measured_freq is not None:
            # Use measured frequency - only specify value (unit/value_type/description preserved from task)
            freq_override_details = {}
            freq_override_details[task_name] = {"input_parameters": {"qubit_frequency": {"value": measured_freq}}}
        else:
            # Use default frequency - don't pass any task_details to reset to default
            freq_override_details = {}

        task_result = session.execute_task(
            task_name, qid, task_details=freq_override_details if freq_override_details else None
        )
        result[task_name] = task_result

    return result


@task
def calibrate_group_with_retry(
    qids: list[str],
    tasks_before_ramsey: list[str],
    tasks_after_ramsey: list[str],
    retry_strategies: list[dict | None],
    max_retries: int,
) -> dict:
    """Execute complete calibration suite for a group of qubits with smart per-qubit retry.

    Each qubit is calibrated independently with immediate retry on failure.
    - Successfully completed qubits are NOT retried
    - Failed qubits retry ALL tasks from the beginning (due to task dependencies)
    - CheckRamsey is used to measure accurate frequency, which is applied to all subsequent tasks

    Workflow:
    1. Execute tasks before CheckRamsey (CheckRabi, CreateHPIPulse, CheckHPIPulse)
    2. Execute CheckRamsey to measure accurate qubit frequency
       - If CheckRamsey fails (e.g., fit failure), continue with default frequency
    3. Execute remaining tasks with the measured frequency (or default if Ramsey failed)

    For example, if Q33 fails on CheckPIPulse:
    - Q32: All tasks succeed → No retry needed
    - Q33: Fails on CheckPIPulse → Retry ALL tasks from CheckRabi with new parameters
    - Q36: All tasks succeed → No retry needed

    This is because calibration tasks have dependencies (e.g., CheckPIPulse depends on
    CreatePIPulse which depends on CheckRabi), so changing parameters requires full re-execution.

    Args:
    ----
        qids: List of qubit IDs to calibrate (executed in order)
        tasks_before_ramsey: List of task names to execute before CheckRamsey
        tasks_after_ramsey: List of task names to execute after CheckRamsey (with frequency feedback)
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
            retry_strategy = retry_strategies[attempt - 1] if attempt <= len(retry_strategies) else None

            # Apply frequency offset strategy if specified
            task_details = _apply_frequency_offset_strategy(
                retry_strategy, tasks_before_ramsey, session, qid, logger, attempt
            )

            try:
                # Phase 1: Execute tasks before Ramsey
                result = _execute_tasks_before_ramsey(tasks_before_ramsey, session, qid, task_details, logger)

                # Phase 2: Execute CheckRamsey with fallback
                ramsey_result, measured_freq, ramsey_success = _execute_ramsey_with_fallback(
                    session, qid, task_details, logger
                )
                result.update(ramsey_result)

                # Check if CheckRamsey failed and we should retry
                if not ramsey_success and attempt < max_retries:
                    logger.warning(f"    CheckRamsey failed on attempt {attempt}")
                    logger.warning(
                        f"  Will retry qubit {qid} from CheckRabi with different parameters "
                        f"(attempt {attempt + 1}/{max_retries})..."
                    )
                    continue  # Retry from the beginning

                # Phase 3: Execute tasks after Ramsey with measured or default frequency
                if not ramsey_success:
                    logger.warning(f"    Proceeding with default frequency")

                after_ramsey_results = _execute_tasks_after_ramsey(
                    tasks_after_ramsey, session, qid, task_details, measured_freq, logger
                )
                result.update(after_ramsey_results)

                # All tasks completed successfully
                logger.info(f"  ✓ Qubit {qid} completed all tasks successfully on attempt {attempt}")
                result["status"] = "success"
                result["attempt"] = attempt
                result["measured_frequency"] = measured_freq
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
    max_retries: int = 3,  # Maximum number of retry attempts
):
    """Complete 1-qubit calibration with automatic retry and frequency feedback.

    This flow combines full_qubit_calibration with adaptive retry and frequency feedback:
    1. Execute tasks_before_ramsey (CheckRabi, CreateHPIPulse, CheckHPIPulse) to find qubit
    2. Execute CheckRamsey to measure accurate frequency
       - If CheckRamsey fails AND retries remain, retry from CheckRabi with different frequency
       - If CheckRamsey fails on last attempt, continue with default frequency
    3. Execute tasks_after_ramsey with measured frequency for optimal calibration
       - Re-executes CheckRabi, CreateHPIPulse, CheckHPIPulse with measured frequency
       - Then executes remaining calibration tasks (PI pulse, T1/T2, DRAG, etc.)
    4. Retry failed qubits with adjusted parameters in tasks_before_ramsey phase
    5. Supports group-based parallel execution
    6. Report final results

    Retry strategy focuses on finding the qubit with frequency offsets:
    - Attempt 1: Default parameters - try with current frequency estimate
    - Attempt 2: +1 MHz offset - search slightly higher frequency
    - Attempt 3: -1 MHz offset - search slightly lower frequency

    Once the qubit is found and frequency is measured by CheckRamsey, all subsequent
    tasks automatically use the measured frequency for optimal results.

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

        # Complete 1-qubit calibration task suite with frequency feedback
        # Split into two phases: before and after CheckRamsey

        # Phase 1: Tasks before Ramsey (basic characterization and HPI pulse)
        tasks_before_ramsey = [
            "CheckRabi",
            "CreateHPIPulse",
            "CheckHPIPulse",
        ]

        # Phase 2: Tasks after Ramsey (executed with measured frequency from Ramsey)
        tasks_after_ramsey = [
            "CheckRabi",
            "CreateHPIPulse",
            "CheckHPIPulse",
            # Pi pulse optimization (CheckRabi/HPIPulse were already done before Ramsey)
            "CreatePIPulse",
            "CheckPIPulse",
            # Decoherence characterization
            "CheckT1",
            "CheckT2Echo",
            # DRAG pulse optimization
            "CreateDRAGHPIPulse",
            "CheckDRAGHPIPulse",
            "CreateDRAGPIPulse",
            "CheckDRAGPIPulse",
            # Readout calibration
            "ReadoutClassification",
            # Gate benchmarking
            "RandomizedBenchmarking",
            "X90InterleavedRandomizedBenchmarking",
        ]

        # TODO: Define retry strategies for finding optimal frequency
        # The goal is to find the optimal frequency in tasks_before_ramsey phase.
        # Once CheckRamsey measures the accurate frequency, tasks_after_ramsey will
        # automatically use it, so retry strategies only need to focus on the initial
        # frequency search (CheckRabi, CreateHPIPulse, CheckHPIPulse).
        #
        # Strategy: Try frequency offsets of ±1 MHz to find the qubit
        # The frequency offset will be applied to all tasks_before_ramsey
        retry_strategies = [
            None,  # Attempt 1: Default - use current frequency estimate
            {"frequency_offset": 0.001},  # Attempt 2: +1 MHz (+0.001 GHz)
            {"frequency_offset": -0.001},  # Attempt 3: -1 MHz (-0.001 GHz)
        ]

        # Submit all groups for parallel execution (each group handles its own retries)
        logger.info("Submitting groups for parallel execution...")
        logger.info("Each group will retry failed qubits immediately without waiting for other groups")
        logger.info("")
        logger.info("Calibration strategy:")
        logger.info("  1. Find qubit (CheckRabi → CreateHPIPulse → CheckHPIPulse)")
        logger.info("     - Retry with ±1 MHz frequency offsets if failed")
        logger.info("  2. Measure accurate frequency (CheckRamsey)")
        logger.info("  3. Execute remaining tasks with measured frequency")
        logger.info("")
        futures = [
            calibrate_group_with_retry.submit(
                qids=group,
                tasks_before_ramsey=tasks_before_ramsey,
                tasks_after_ramsey=tasks_after_ramsey,
                retry_strategies=retry_strategies,
                max_retries=max_retries,
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
        # Try to fail the calibration if session was initialized
        try:
            session = get_session()
            session.fail_calibration(str(e))
        except RuntimeError:
            # Session was never initialized (e.g., init_calibration failed)
            # Nothing to clean up
            pass
        raise
