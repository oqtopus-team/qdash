"""Full chip calibration workflow with automatic Box/CR scheduling.

Features:
- Automatic Box detection from wiring configuration
- MUX-based qubit grouping with exclude support
- Automatic CR scheduling with fidelity filtering
- Each stage tracked with separate execution_id

Example:
    scheduled_full_calibration(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
        exclude_qids=["5", "12"],
    )
"""

from prefect import flow, get_run_logger
from qdash.workflow.flow import (
    calibrate_one_qubit_scheduled,
    calibrate_two_qubit_scheduled,
    extract_candidate_qubits,
)


@flow
def scheduled_full_calibration(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    flow_name: str | None = None,
):
    """Full chip calibration with automatic Box/CR scheduling.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate. Default: all 16 (0-15)
        exclude_qids: Qubit IDs to exclude (e.g., known-bad qubits)
        qids: Not used (for UI compatibility)
        flow_name: Flow name (auto-injected)
    """
    logger = get_run_logger()

    # =========================================================================
    # Configuration - Edit these as needed
    # =========================================================================

    # MUX selection (default: all 16 MUXes for 64Q chip)
    if mux_ids is None:
        mux_ids = list(range(16))
    if exclude_qids is None:
        exclude_qids = []

    # 1-qubit calibration tasks
    tasks_1q = [
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CreatePIPulse",
        "CheckPIPulse",
        "CheckT1",
        "CheckT2Echo",
        "CreateDRAGHPIPulse",
        "CheckDRAGHPIPulse",
        "CreateDRAGPIPulse",
        "CheckDRAGPIPulse",
        "ReadoutClassification",
        "RandomizedBenchmarking",
        "X90InterleavedRandomizedBenchmarking",
    ]

    # 2-qubit calibration tasks
    tasks_2q = [
        "CheckCrossResonance",
        "CreateZX90",
        "CheckZX90",
        "CheckBellState",
    ]

    # CR scheduling parameters
    x90_fidelity_threshold = 0.90  # Minimum fidelity for 2Q candidates
    max_parallel_ops = 10  # Max parallel CR operations per group

    # =========================================================================
    # Execution
    # =========================================================================

    # Stage 1: 1-qubit calibration with automatic Box scheduling
    results_1q = calibrate_one_qubit_scheduled(
        username=username,
        chip_id=chip_id,
        mux_ids=mux_ids,
        exclude_qids=exclude_qids,
        tasks=tasks_1q,
        flow_name=flow_name,
    )

    # Stage 2: Extract candidates and run 2-qubit calibration
    candidates = extract_candidate_qubits(results_1q, x90_fidelity_threshold)
    logger.info(f"1-qubit success: {len(candidates)} qubits")

    if len(candidates) == 0:
        logger.warning("No candidates, skipping 2-qubit")
        return {"1qubit": results_1q, "2qubit": {}}

    results_2q = calibrate_two_qubit_scheduled(
        username=username,
        chip_id=chip_id,
        candidate_qubits=candidates,
        tasks=tasks_2q,
        flow_name=flow_name,
        max_parallel_ops=max_parallel_ops,
    )

    return {"1qubit": results_1q, "2qubit": results_2q}
