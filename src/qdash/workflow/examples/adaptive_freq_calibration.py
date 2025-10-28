"""Adaptive Frequency Calibration Example.

This example demonstrates how to use frequency feedback to perform
adaptive calibration using the Python Flow Editor.

The workflow:
1. Measures qubit frequency using CheckFreq
2. Uses the measured frequency to run CheckRabi with frequency override
3. Repeats until convergence or max iterations

This pattern can be extended to any calibration tasks that benefit from
accurate frequency tracking.
"""

from prefect import flow, get_run_logger

from qdash.workflow.helpers import finish_calibration, get_session, init_calibration


@flow
def adaptive_freq_calibration(
    username: str,
    chip_id: str,
    qids: list[str],
    target_frequency: float = 5.0,
    frequency_tolerance: float = 0.001,
    max_iterations: int = 10,
    flow_name: str | None = None,
) -> dict:
    """Adaptive frequency calibration with feedback loop.

    Args:
        username: Username for the calibration session
        chip_id: Target chip ID
        qids: List of qubit IDs to calibrate
        target_frequency: Target qubit frequency in GHz (default: 5.0)
        frequency_tolerance: Convergence threshold in GHz (default: 0.001)
        max_iterations: Maximum number of iterations (default: 10)
        flow_name: Flow name for display (auto-injected by API)

    Returns:
        Dictionary containing final results for each qubit

    Example:
        ```python
        results = adaptive_freq_calibration(
            username="alice",
            chip_id="chip_1",
            qids=["0", "1"],
            target_frequency=5.0,
            frequency_tolerance=0.001
        )
        ```

    """
    logger = get_run_logger()

    # Initialize calibration session
    session = init_calibration(
        username=username,
        chip_id=chip_id,
        qids=qids,
        flow_name=flow_name or "Adaptive Frequency Calibration",
    )

    results = {}

    # Calibrate each qubit independently
    for qid in qids:
        logger.info(f"Starting adaptive calibration for qubit {qid}")

        iteration_results = []

        for iteration in range(max_iterations):
            logger.info(f"Qubit {qid} - Iteration {iteration + 1}/{max_iterations}")

            # Step 1: Measure qubit frequency
            freq_result = session.execute_task("CheckFreq", qid)
            measured_freq = freq_result["bare_frequency"]

            logger.info(f"Qubit {qid} - Measured frequency: {measured_freq:.6f} GHz")

            # Step 2: Run Rabi with the measured frequency
            rabi_result = session.execute_task(
                "CheckRabi",
                qid,
                task_details={"CheckRabi": {"input_parameters": {"qubit_frequency": {"value": measured_freq}}}},
            )

            logger.info(f"Qubit {qid} - Rabi frequency: {rabi_result['rabi_frequency']:.2f} MHz")

            # Store iteration results
            iteration_results.append(
                {
                    "iteration": iteration + 1,
                    "measured_frequency": measured_freq,
                    "rabi_frequency": rabi_result["rabi_frequency"],
                    "rabi_amplitude": rabi_result["rabi_amplitude"],
                }
            )

            # Step 3: Check convergence
            freq_error = abs(measured_freq - target_frequency)
            logger.info(f"Qubit {qid} - Frequency error: {freq_error:.6f} GHz")

            if freq_error < frequency_tolerance:
                logger.info(f"Qubit {qid} - Converged in {iteration + 1} iterations!")
                break
        else:
            logger.warning(f"Qubit {qid} - Did not converge within {max_iterations} iterations")

        # Store final results
        results[qid] = {
            "final_frequency": measured_freq,
            "final_rabi": rabi_result,
            "iterations": iteration_results,
            "converged": freq_error < frequency_tolerance,
        }

    # Finish calibration
    finish_calibration()

    return results


@flow
def adaptive_multi_task_calibration(
    username: str,
    chip_id: str,
    qids: list[str],
    target_frequency: float = 5.0,
    frequency_tolerance: float = 0.001,
    max_iterations: int = 10,
    flow_name: str | None = None,
) -> dict:
    """Adaptive calibration with multiple tasks using the same frequency.

    This example shows how to run multiple calibration tasks (Rabi, T1, T2)
    using the same measured frequency.

    Args:
        username: Username for the calibration session
        chip_id: Target chip ID
        qids: List of qubit IDs to calibrate
        target_frequency: Target qubit frequency in GHz (default: 5.0)
        frequency_tolerance: Convergence threshold in GHz (default: 0.001)
        max_iterations: Maximum number of iterations (default: 10)
        flow_name: Flow name for display (auto-injected by API)

    Returns:
        Dictionary containing final results for each qubit

    """
    logger = get_run_logger()

    # Initialize calibration session
    session = init_calibration(
        username=username,
        chip_id=chip_id,
        qids=qids,
        flow_name=flow_name or "Adaptive Multi-Task Calibration",
    )

    results = {}

    for qid in qids:
        logger.info(f"Starting adaptive multi-task calibration for qubit {qid}")

        for iteration in range(max_iterations):
            logger.info(f"Qubit {qid} - Iteration {iteration + 1}/{max_iterations}")

            # Step 1: Measure qubit frequency
            freq_result = session.execute_task("CheckFreq", qid)
            measured_freq = freq_result["bare_frequency"]

            logger.info(f"Qubit {qid} - Measured frequency: {measured_freq:.6f} GHz")

            # Step 2: Run multiple tasks with the same frequency
            task_details_with_freq = {"input_parameters": {"qubit_frequency": {"value": measured_freq}}}

            rabi_result = session.execute_task("CheckRabi", qid, task_details={"CheckRabi": task_details_with_freq})
            t1_result = session.execute_task("CheckT1", qid, task_details={"CheckT1": task_details_with_freq})
            t2_result = session.execute_task("CheckT2Echo", qid, task_details={"CheckT2Echo": task_details_with_freq})

            logger.info(
                f"Qubit {qid} - Rabi: {rabi_result['rabi_frequency']:.2f} MHz, "
                f"T1: {t1_result['t1']:.2f} μs, T2: {t2_result['t2_echo']:.2f} μs"
            )

            # Check convergence
            freq_error = abs(measured_freq - target_frequency)

            if freq_error < frequency_tolerance:
                logger.info(f"Qubit {qid} - Converged in {iteration + 1} iterations!")
                break
        else:
            logger.warning(f"Qubit {qid} - Did not converge within {max_iterations} iterations")

        results[qid] = {
            "final_frequency": measured_freq,
            "rabi": rabi_result,
            "t1": t1_result,
            "t2": t2_result,
            "converged": freq_error < frequency_tolerance,
        }

    finish_calibration()

    return results
