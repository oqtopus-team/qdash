"""Iterative ChevronPattern calibration flow with parameter variation.

This template demonstrates how to execute ChevronPattern repeatedly with different
parameters (e.g., readout_amplitude, qubit_frequency), which is useful for:
- Investigating the effect of readout power on qubit bare frequency measurements
- Finding optimal readout amplitude for chevron pattern measurements
- Exploring parameter space systematically
- Collecting data across different experimental conditions

The flow uses the task_details mechanism to override input parameters, supporting:
- readout_amplitude: Readout power (a.u.)
- qubit_frequency: Qubit drive frequency (GHz)
- control_amplitude: Control pulse amplitude (a.u.)
- readout_frequency: Readout frequency (GHz)
- Any combination of the above
"""

from prefect import flow, get_run_logger, task
from qdash.workflow.helpers import finish_calibration, get_session, init_calibration


@task
def calibrate_group(
    qids: list[str],
    task_details: dict | None,
    iteration: int,
) -> dict:
    """Execute ChevronPattern for a group of qubits with custom parameters.

    This task uses task_details to pass parameters (e.g., readout_amplitude, qubit_frequency)
    to the ChevronPattern task, allowing flexible parameter exploration.

    If a qubit fails during calibration, it will be skipped and the next qubit
    will be processed. Failed qubits are logged and marked in the results.

    Args:
    ----
        qids: List of qubit IDs to calibrate (executed in order)
        task_details: Task configuration with input_parameters to override
            Example: {"ChevronPattern": {"input_parameters": {"readout_amplitude": {"value": 0.15}}}}
        iteration: Current iteration number (for logging)

    Returns:
    -------
        Results for the group (includes error information for failed qubits)

    """
    logger = get_run_logger()
    logger.info(f"Iteration {iteration + 1}: Starting ChevronPattern for qubits: {qids}")

    # Log parameter overrides
    if task_details and "ChevronPattern" in task_details:
        params = task_details["ChevronPattern"].get("input_parameters", {})
        if params:
            logger.info(f"  Parameter overrides: {list(params.keys())}")
            for param_name, param_value in params.items():
                logger.info(f"    {param_name} = {param_value.get('value')}")

    session = get_session()
    results = {}

    # Execute each qubit in order
    for qid in qids:
        logger.info(f"  Calibrating qubit {qid}...")

        try:
            # Execute ChevronPattern task with parameter overrides
            logger.info("    Executing ChevronPattern...")
            result = session.execute_task("ChevronPattern", qid, task_details=task_details)

            logger.info(f"    ✓ ChevronPattern completed: bare_frequency={result.get('bare_frequency')} GHz")

            results[qid] = {
                "iteration": iteration,
                "bare_frequency": result.get("bare_frequency"),
                "task_id": result.get("task_id"),
                "status": "success",
            }

        except Exception as e:
            # Log the error and continue with next qubit
            logger.error(f"    ✗ Failed to execute ChevronPattern for Q{qid}: {e}")
            logger.warning(f"    Skipping qubit {qid}")
            results[qid] = {
                "iteration": iteration,
                "status": "failed",
                "error": str(e),
            }

    return results


@flow
def iterative_chevron_pattern_flow(
    username: str,  # Automatically provided from UI properties
    chip_id: str,  # Automatically provided from UI properties
    qids: list[str] | None = None,
    max_iterations: int = 5,  # TODO: Adjust number of iterations
    flow_name: str | None = None,  # Automatically injected by API
):
    """Iterative ChevronPattern calibration with parameter variation.

    This flow executes ChevronPattern multiple times with different parameter configurations,
    allowing you to systematically explore parameter space and investigate effects on
    bare frequency measurements.

    Example: With max_iterations=3 and groups=[["0", "1"], ["2", "3"]]:
    - Iteration 1 (readout_amp=0.05): Group1 (0→1) || Group2 (2→3) in parallel
    - Iteration 2 (readout_amp=0.10): Group1 (0→1) || Group2 (2→3) in parallel
    - Iteration 3 (readout_amp=0.15): Group1 (0→1) || Group2 (2→3) in parallel

    You can also override multiple parameters simultaneously:
    - Iteration 1: readout_amplitude=0.05, qubit_frequency=5.0
    - Iteration 2: readout_amplitude=0.10, qubit_frequency=5.1

    Note: username and chip_id are automatically provided from UI properties.

    Args:
    ----
        username: User name for calibration (from UI)
        chip_id: Target chip ID (from UI)
        qids: List of qubit IDs (not used, groups are defined explicitly)
        max_iterations: Number of iterations with different parameter configurations

    """
    logger = get_run_logger()

    # TODO: Define your qubit groups
    groups = [
        ["0", "1"],  # Group 1: 0 → 1 (sequential)
        ["2", "3"],  # Group 2: 2 → 3 (sequential)
        # Add more groups as needed
    ]

    # Flatten all qids for initialization
    all_qids = [qid for group in groups for qid in group]

    # TODO: Define task_details for each iteration
    # You can override any parameter: readout_amplitude, qubit_frequency, control_amplitude, etc.
    # Multiple parameters can be overridden simultaneously
    task_details_per_iteration = [
        {
            "ChevronPattern": {
                "input_parameters": {
                    "readout_amplitude": {"value": 0.05}  # Iteration 1: 0.05 a.u.
                }
            }
        },
        {
            "ChevronPattern": {
                "input_parameters": {
                    "readout_amplitude": {"value": 0.10}  # Iteration 2: 0.10 a.u.
                }
            }
        },
        {
            "ChevronPattern": {
                "input_parameters": {
                    "readout_amplitude": {"value": 0.15}  # Iteration 3: 0.15 a.u.
                }
            }
        },
        # Example: Override multiple parameters simultaneously
        # {
        #     "ChevronPattern": {
        #         "input_parameters": {
        #             "readout_amplitude": {"value": 0.20},
        #             "qubit_frequency": {"value": 5.2}
        #         }
        #     }
        # },
    ]

    logger.info(f"Starting iterative ChevronPattern calibration for user={username}, chip_id={chip_id}")
    for i, group in enumerate(groups, start=1):
        logger.info(f"Group {i}: {group} (sequential)")
    logger.info(f"Max iterations: {max_iterations}")
    logger.info(f"Iterations: {len(task_details_per_iteration)}")
    logger.info("Groups will run in parallel within each iteration")

    try:
        # Initialize session
        init_calibration(username, chip_id, all_qids, flow_name=flow_name)

        # Store results from all iterations
        all_iterations_results = []

        # Execute multiple iterations with different parameter configurations
        for iteration in range(max_iterations):
            if iteration >= len(task_details_per_iteration):
                logger.warning(f"No more task_details defined for iteration {iteration + 1}")
                break

            task_details = task_details_per_iteration[iteration]

            logger.info("=" * 60)
            logger.info(f"Starting iteration {iteration + 1}/{max_iterations}")
            logger.info("=" * 60)

            # Submit all groups for parallel execution
            logger.info("Submitting groups for parallel execution...")
            futures = [
                calibrate_group.submit(
                    qids=group,
                    task_details=task_details,
                    iteration=iteration,
                )
                for group in groups
            ]

            # Wait for completion
            logger.info("Waiting for groups to complete...")
            results_list = [future.result() for future in futures]

            # Combine results for this iteration
            iteration_results = {}
            for results in results_list:
                iteration_results.update(results)
            all_iterations_results.append(
                {"iteration": iteration, "task_details": task_details, "results": iteration_results}
            )

            # Log summary
            logger.info(f"Iteration {iteration + 1} summary:")
            for qid, result in iteration_results.items():
                if result["status"] == "success":
                    logger.info(f"  Q{qid}: bare_frequency = {result['bare_frequency']} GHz")
                else:
                    logger.error(f"  Q{qid}: FAILED - {result.get('error')}")

        finish_calibration()

        logger.info("=" * 60)
        logger.info("Iterative ChevronPattern calibration completed successfully!")
        logger.info("=" * 60)

        return all_iterations_results

    except Exception as e:
        logger.error(f"Iterative ChevronPattern calibration failed: {e}")
        session = get_session()
        session.fail_calibration(str(e))
        raise
