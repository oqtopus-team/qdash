"""Example: Parallel adaptive calibration with custom convergence logic.

This example demonstrates parallel closed-loop calibration where each qubit
independently iterates until YOUR OWN convergence criterion is met.

Key points:
- You write your own convergence logic
- You control the update strategy
- Each qubit runs in parallel and appears separately in Prefect UI
"""

from prefect import flow

from qdash.workflow.helpers import (
    calibrate_parallel,
    finish_calibration,
    get_session,
    init_calibration,
    parallel_map,
)


def adaptive_frequency_calibration(qid: str, threshold: float, max_iterations: int) -> dict:
    """Custom adaptive calibration with your own convergence logic.

    This function demonstrates how to write your own closed-loop calibration.
    You have complete control over:
    - What tasks to run
    - How to check convergence
    - How to update parameters
    - When to stop

    Args:
        qid: Qubit ID
        threshold: Your convergence threshold
        max_iterations: Maximum iterations

    Returns:
        Calibration result with convergence info
    """
    session = get_session()

    history = []
    converged = False

    for iteration in range(max_iterations):
        # Execute calibration task
        result = session.execute_task("CheckFreq", qid)
        freq = result.get("qubit_frequency", 0.0)
        history.append(freq)

        # YOUR convergence logic
        if iteration > 0:
            diff = abs(freq - history[-2])
            if diff < threshold:
                converged = True
                print(f"Q{qid}: Converged in {iteration + 1} iterations (diff={diff:.6f})")
                break

        # YOUR parameter update strategy
        session.set_parameter(qid, "qubit_frequency", freq)

    if not converged:
        print(f"Q{qid}: Did not converge after {max_iterations} iterations")

    return {
        "qid": qid,
        "converged": converged,
        "iterations": len(history),
        "final_frequency": history[-1] if history else None,
        "history": history,
    }


@flow(name="adaptive-parallel-example")
def adaptive_parallel_example(
    username: str = "orangekame3",
    chip_id: str = "64Qv3",
    qids: list[str] | None = None,
    threshold: float = 0.01,
    max_iterations: int = 10,
) -> dict:
    """Example of parallel adaptive calibration with custom convergence.

    This flow shows how to:
    1. Write your own adaptive calibration function
    2. Parallelize it using parallel_map()
    3. Monitor each qubit separately in Prefect UI
    4. Run follow-up calibration based on results

    Args:
        username: Username for calibration
        chip_id: Chip ID to calibrate
        qids: List of qubit IDs (default: ["32", "38"])
        threshold: Convergence threshold for parameter change
        max_iterations: Maximum iterations per qubit

    Returns:
        Calibration results with convergence info
    """
    if qids is None:
        qids = ["32", "38"]

    # Initialize calibration session
    session = init_calibration(
        username=username,
        chip_id=chip_id,
        qids=qids,
        name="Adaptive Parallel Calibration Example",
        tags=["example", "adaptive", "parallel"],
    )

    # Run adaptive calibration in parallel
    # Each qubit appears as "adaptive-Q{qid}" in Prefect UI
    adaptive_results = parallel_map(
        items=qids,
        func=adaptive_frequency_calibration,
        task_name_func=lambda qid: f"adaptive-Q{qid}",  # Shows in Prefect UI
        threshold=threshold,
        max_iterations=max_iterations,
    )

    # Convert list to dict for easier access
    results_dict = {r["qid"]: r for r in adaptive_results if r}

    # Log convergence summary
    converged_qubits = [qid for qid, r in results_dict.items() if r["converged"]]
    print(f"\nConvergence summary: {len(converged_qubits)}/{len(qids)} qubits converged")

    for qid in qids:
        if qid in results_dict:
            r = results_dict[qid]
            status = "✓" if r["converged"] else "✗"
            print(f"  Q{qid}: {status} {r['iterations']} iterations, freq={r['final_frequency']:.6f}")

    # Run follow-up calibration only for converged qubits
    followup_results = {}
    if converged_qubits:
        print(f"\nRunning follow-up calibration for {len(converged_qubits)} converged qubits...")
        followup_results = calibrate_parallel(
            qids=converged_qubits,
            tasks=["CheckRabi"],
        )

    # Finish calibration
    finish_calibration()

    return {
        "adaptive_results": results_dict,
        "followup_results": followup_results,
    }


if __name__ == "__main__":
    # Run the flow directly
    results = adaptive_parallel_example()
    print(f"\n=== Final Results ===")
    print(f"Adaptive results: {results['adaptive_results']}")
    print(f"Follow-up results: {results['followup_results']}")
