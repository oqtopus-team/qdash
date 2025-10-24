"""Smart calibration flow with conditional branching.

This example demonstrates conditional task execution based on measurement results.
"""

from prefect import flow
from qdash.workflow.helpers import finish_calibration, init_calibration


@flow(name="Smart Calibration with Branching")
def smart_calibration(
    username: str,
    chip_id: str,
    qids: list[str],
    execution_id: str | None = None,
    frequency_threshold: float = 5.0,
) -> dict:
    """Execute calibration with conditional branching based on initial measurements.

    This flow demonstrates how to make calibration decisions based on
    measurement results, executing different task sequences for different qubits.

    Args:
        username: Username for the calibration session
        chip_id: Target chip ID
        qids: List of qubit IDs to calibrate
        execution_id: Unique execution identifier (auto-generated if None)
        frequency_threshold: Frequency threshold for branching logic (GHz)

    Returns:
        Dictionary mapping qubit IDs to their calibration results

    Example:
        ```python
        results = smart_calibration(
            username="alice",
            chip_id="chip_1",
            qids=["0", "1", "2"],
            frequency_threshold=5.0
        )
        ```

    """
    # Initialize calibration session
    session = init_calibration(
        username=username,
        chip_id=chip_id,
        qids=qids,
        execution_id=execution_id,
        name="Smart Calibration",
        tags=["smart", "conditional"],
    )

    results = {}

    for qid in qids:
        # Initial frequency check
        freq_result = session.execute_task("CheckFreq", qid)
        results[qid] = freq_result.copy()

        qubit_frequency = freq_result.get("qubit_frequency", 0)

        if qubit_frequency < frequency_threshold:
            # Low frequency qubits: execute special calibration
            print(
                f"Q{qid}: Low frequency detected ({qubit_frequency:.3f} GHz), " f"executing low-frequency calibration"
            )

            # For demonstration - in real use, you would have a LowFreqCalibration task
            # low_freq_result = session.execute_task("LowFreqCalibration", qid)
            # results[qid].update(low_freq_result)

            # Fallback: execute standard tasks with adjusted parameters
            rabi_result = session.execute_task(
                "CheckRabi",
                qid,
                task_details={"CheckRabi": {"adjust_for_low_freq": True}},
            )
            results[qid].update(rabi_result)

        else:
            # Normal frequency qubits: execute standard calibration sequence
            print(f"Q{qid}: Normal frequency ({qubit_frequency:.3f} GHz), " f"executing standard calibration")

            rabi_result = session.execute_task("CheckRabi", qid)
            t1_result = session.execute_task("CheckT1", qid)

            results[qid].update(rabi_result)
            results[qid].update(t1_result)

    # Complete calibration
    finish_calibration()

    return results


if __name__ == "__main__":
    # Example usage (execution_id auto-generated)
    result = smart_calibration(
        username="test_user",
        chip_id="chip_1",
        qids=["0", "1"],
        frequency_threshold=5.0,
    )
    print(f"Smart calibration completed: {result}")
