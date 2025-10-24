"""Schedule-based calibration flow example.

This example demonstrates how to use schedule definitions (SerialNode, ParallelNode,
BatchNode) to orchestrate calibration tasks, similar to the existing dispatch_cal_flow
but within the Python Flow API.
"""

from prefect import flow
from qdash.datamodel.menu import BatchNode, ParallelNode, SerialNode
from qdash.workflow.helpers import (
    execute_schedule,
    finish_calibration,
    init_calibration,
)


@flow(name="Schedule-based Calibration")
def schedule_calibration(
    username: str,
    chip_id: str,
    qids: list[str],
    execution_id: str | None = None,
) -> dict:
    """Execute calibration using schedule definitions.

    This flow demonstrates how to use schedule nodes to define complex
    calibration orchestration patterns, similar to MenuModel schedules.

    Args:
        username: Username for the calibration session
        chip_id: Target chip ID
        qids: List of qubit IDs to calibrate
        execution_id: Unique execution identifier (auto-generated if None)

    Returns:
        Dictionary mapping qubit IDs to their calibration results

    Example:
        ```python
        # Execute calibration with custom schedule
        results = schedule_calibration(
            username="alice",
            chip_id="chip_1",
            qids=["0", "1", "2"]
        )
        ```

    Schedule Patterns:
        - SerialNode: Execute sub-nodes sequentially
        - ParallelNode: Execute sub-nodes (sequentially in Python Flow)
        - BatchNode: Execute tasks for multiple qubits together
        - String qid: Execute tasks for a single qubit

    """
    # Initialize calibration session
    init_calibration(
        username=username,
        chip_id=chip_id,
        qids=qids,
        execution_id=execution_id,
        name="Schedule Calibration",
        tags=["schedule", "orchestration"],
    )

    # Example 1: Simple serial schedule
    # Execute Q0 → Q1 → Q2 sequentially
    SerialNode(serial=["0", "1", "2"])

    # Example 2: Batch schedule
    # Execute all qubits together for each task
    BatchNode(batch=["0", "1", "2"])

    # Example 3: Complex nested schedule
    # This mimics real-world calibration patterns:
    # 1. First, calibrate Q0 and Q1 in serial
    # 2. Then, calibrate Q2
    # 3. Finally, run all qubits together as a batch
    SerialNode(
        serial=[
            ParallelNode(parallel=["0", "1"]),  # Q0 and Q1 (sequential)
            "2",  # Q2
            BatchNode(batch=["0", "1", "2"]),  # All together
        ]
    )

    # Use the schedule from qids - for this example, use batch schedule
    # In real usage, you would choose based on your requirements
    # schedule = BatchNode(batch=qids)

    schedule = ParallelNode(parallel=[SerialNode(serial=["32"]), SerialNode(serial=["38"])])

    # Define tasks to execute
    tasks = ["CheckRabi"]

    # Execute calibration according to schedule
    # Note: Despite ParallelNode name, execution is sequential in Python Flow
    # For true parallelism, use dispatch_cal_flow with Prefect deployments
    results = execute_schedule(tasks=tasks, schedule=schedule)

    # Complete calibration
    finish_calibration()

    return results


@flow(name="Advanced Schedule Calibration")
def advanced_schedule_calibration(
    username: str,
    chip_id: str,
    qids: list[str],
    execution_id: str | None = None,
) -> dict:
    """Execute calibration with advanced schedule patterns.

    This example shows more complex schedule patterns that might be used
    in real calibration scenarios.

    Args:
        username: Username for the calibration session
        chip_id: Target chip ID
        qids: List of qubit IDs to calibrate
        execution_id: Unique execution identifier (auto-generated if None)

    Returns:
        Dictionary mapping qubit IDs to their calibration results

    """
    # Initialize calibration session
    init_calibration(
        username=username,
        chip_id=chip_id,
        qids=qids,
        execution_id=execution_id,
        name="Advanced Schedule Calibration",
        tags=["schedule", "advanced"],
    )

    # Advanced pattern: Group qubits by physical proximity or characteristics
    # Example: Q0-Q1 are neighbors, Q2-Q3 are neighbors
    # First calibrate each pair, then calibrate all together
    if len(qids) >= 4:
        schedule = SerialNode(
            serial=[
                # Stage 1: Calibrate pairs
                ParallelNode(
                    parallel=[
                        BatchNode(batch=[qids[0], qids[1]]),  # First pair
                        BatchNode(batch=[qids[2], qids[3]]),  # Second pair
                    ]
                ),
                # Stage 2: Calibrate all together
                BatchNode(batch=qids),
            ]
        )
    else:
        # Fallback for fewer qubits: simple serial execution
        schedule = SerialNode(serial=qids)

    # Define tasks with different priorities
    # First priority: Frequency characterization
    freq_tasks = ["CheckFreq"]
    results = execute_schedule(tasks=freq_tasks, schedule=schedule)

    # Second priority: Pulse calibration
    pulse_tasks = ["CheckRabi", "CheckT1"]
    results.update(execute_schedule(tasks=pulse_tasks, schedule=schedule))

    # Complete calibration
    finish_calibration()

    return results


if __name__ == "__main__":
    # Example usage 1: Simple schedule calibration
    result1 = schedule_calibration(
        username="test_user",
        chip_id="chip_1",
        qids=["32", "38"],
    )
    print(f"Schedule calibration completed: {result1}")

    # Example usage 2: Advanced schedule calibration
    # result2 = advanced_schedule_calibration(
    #     username="test_user",
    #     chip_id="chip_1",
    #     qids=["0", "1", "2", "3"],
    # )
    # print(f"Advanced schedule calibration completed: {result2}")
