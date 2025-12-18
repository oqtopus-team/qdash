"""Utility functions for scheduled calibration workflows.

This module provides utility functions used by calibration workflows.
For actual calibration execution, use CalibService methods instead:
- CalibService.one_qubit(mode="scheduled")
- CalibService.one_qubit(mode="synchronized")
- CalibService.two_qubit()

Example:
    from prefect import flow
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.scheduled import extract_candidate_qubits

    @flow
    def my_calibration(username: str, chip_id: str):
        cal = CalibService(username, chip_id)

        # 1-qubit calibration
        results_1q = cal.one_qubit(mux_ids=[0, 1, 2, 3], mode="synchronized")

        # Extract candidates for 2-qubit calibration
        candidates = extract_candidate_qubits(results_1q)

        # 2-qubit calibration
        results_2q = cal.two_qubit(candidate_qubits=candidates)

        return {"1qubit": results_1q, "2qubit": results_2q}
"""

from __future__ import annotations

from typing import Any


def extract_candidate_qubits(
    one_qubit_results: dict[str, Any],
    x90_fidelity_threshold: float = 0.90,
) -> list[str]:
    """Extract qubits with high X90 gate fidelity from 1-qubit results.

    This utility function analyzes results from 1-qubit calibration and
    extracts qubit IDs that meet the specified X90 gate fidelity threshold.
    Useful for filtering candidates before 2-qubit calibration.

    Args:
        one_qubit_results: Results from CalibService.one_qubit() or similar.
            Expected structure: {"Box_A": {"0": {"status": "success", ...}, ...}, ...}
        x90_fidelity_threshold: Minimum X90 gate fidelity (default: 0.90)

    Returns:
        List of qubit IDs that meet the fidelity threshold, sorted.

    Example:
        results_1q = cal.one_qubit(mux_ids=[0, 1, 2, 3])
        candidates = extract_candidate_qubits(results_1q, x90_fidelity_threshold=0.95)
        print(f"High-fidelity qubits: {candidates}")
    """
    candidates = []
    for stage_name, stage_data in one_qubit_results.items():
        if not isinstance(stage_data, dict):
            continue
        for qid, result in stage_data.items():
            if not isinstance(result, dict):
                continue
            if result.get("status") != "success":
                continue

            irb_result = result.get("X90InterleavedRandomizedBenchmarking", {})
            x90_fidelity_param = irb_result.get("x90_gate_fidelity")

            if x90_fidelity_param is not None:
                x90_fidelity = (
                    x90_fidelity_param.value
                    if hasattr(x90_fidelity_param, "value")
                    else x90_fidelity_param
                )
                if x90_fidelity >= x90_fidelity_threshold:
                    candidates.append(qid)

    return sorted(set(candidates))


def get_wiring_config_path(chip_id: str) -> str:
    """Get the wiring config path for a chip.

    Args:
        chip_id: Chip ID (e.g., "64Qv3")

    Returns:
        Absolute path to the wiring configuration YAML file
    """
    return f"/app/config/qubex/{chip_id}/config/wiring.yaml"
