"""Example: Parallel calibration using @task + submit().

This example demonstrates true parallel execution of calibration tasks
across multiple qubits using Prefect's task parallelism.
"""

from prefect import flow

from qdash.workflow.helpers import calibrate_parallel, finish_calibration, init_calibration


@flow(name="parallel-calibration-example")
def parallel_calibration_example(
    username: str = "orangekame3",
    chip_id: str = "64Qv3",
    qids: list[str] | None = None,
) -> dict[str, dict[str, any]]:
    """Example of parallel calibration across multiple qubits.

    Each qubit is calibrated concurrently, significantly reducing total
    calibration time compared to sequential execution.

    Args:
        username: Username for calibration
        chip_id: Chip ID to calibrate
        qids: List of qubit IDs (default: ["32", "38"])

    Returns:
        Dictionary mapping qubit IDs to their calibration results
    """
    if qids is None:
        qids = ["32", "38"]

    # Initialize calibration session
    session = init_calibration(
        username=username,
        chip_id=chip_id,
        qids=qids,
        name="Parallel Calibration Example",
        tags=["example", "parallel"],
    )

    # Execute calibration tasks in parallel
    # Each qubit runs concurrently, executing its tasks sequentially
    results = calibrate_parallel(
        qids=qids,
        tasks=["CheckFreq", "CheckRabi"],  # Add more tasks as needed
    )

    # Finish calibration and save results
    finish_calibration()

    return results


if __name__ == "__main__":
    # Run the flow directly
    results = parallel_calibration_example()
    print(f"Calibration results: {results}")
