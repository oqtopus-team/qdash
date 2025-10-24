"""Example: Repeat CheckRabi multiple times in parallel.

This example demonstrates how to execute the same task multiple times
for each qubit, with each qubit running in parallel.
"""

from prefect import flow
from qdash.workflow.helpers import (
    finish_calibration,
    get_session,
    init_calibration,
    parallel_map,
)


def repeat_check_rabi(qid: str, num_iterations: int) -> list[dict]:
    """Execute CheckRabi multiple times for a single qubit.

    Each iteration creates a separate task in the workflow with a numbered suffix.

    Args:
        qid: Qubit ID
        num_iterations: Number of times to execute CheckRabi

    Returns:
        List of results from each iteration
    """
    session = get_session()
    results = []

    for i in range(num_iterations):
        # Add task with numbered suffix to ensure each iteration is recorded separately
        task_name = f"CheckRabi_{i+1}"
        session._ensure_task_in_workflow(task_name, "qubit", qid)

        # Execute the actual CheckRabi task
        result = session.execute_task("CheckRabi", qid)
        results.append(result)
        print(f"Q{qid}: {task_name} completed")

    return results


@flow(name="repeat-rabi-parallel")
def repeat_rabi_parallel(
    username: str = "orangekame3",
    chip_id: str = "64Qv3",
    qids: list[str] | None = None,
    num_iterations: int = 3,
) -> dict:
    """Execute CheckRabi multiple times for each qubit in parallel.

    Each qubit runs its iterations independently in parallel.
    All qubits appear as separate tasks in Prefect UI.

    Args:
        username: Username for calibration
        chip_id: Chip ID to calibrate
        qids: List of qubit IDs (default: ["32", "38"])
        num_iterations: Number of times to execute CheckRabi per qubit

    Returns:
        Dictionary mapping qubit IDs to their iteration results
    """
    if qids is None:
        qids = ["32", "38"]

    # Initialize calibration session
    init_calibration(
        username=username,
        chip_id=chip_id,
        qids=qids,
        name="Repeat Rabi Parallel",
        tags=["example", "parallel", "repeat"],
    )

    # Execute CheckRabi 3 times for each qubit in parallel
    # Each qubit appears as "repeat-rabi-Q{qid}" in Prefect UI
    results = parallel_map(
        items=qids,
        func=repeat_check_rabi,
        task_name_func=lambda qid: f"repeat-rabi-Q{qid}",
        num_iterations=num_iterations,
    )

    # Finish calibration
    finish_calibration()

    return {qid: result for qid, result in zip(qids, results)}


if __name__ == "__main__":
    # Run the flow directly
    results = repeat_rabi_parallel()
    print("\n=== Final Results ===")
    for qid, result in results.items():
        print(f"Q{qid}: Completed {len(result)} iterations")
