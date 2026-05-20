"""MUX layout constants for resonator spectroscopy analysis.

Lives here (not under workflow) so it can be shared by the API container,
which does not ship the workflow engine.
"""

from __future__ import annotations

# Number of resonators expected per MUX.
NUM_RESONATORS: int = 4

# Mapping from a qubit's position in its MUX (qid % 4) to the index of
# its resonance in the spectroscopy result. Reflects the physical
# arrangement of the four resonators in a MUX.
PEAK_POSITIONS: dict[int, int] = {
    0: 1,
    1: 3,
    2: 2,
    3: 0,
}


def guess_sorted_slots_for_partial_mux(
    xs: list[float],
    frequencies: list[float],
) -> tuple[list[int | None], str]:
    """Guess sorted-slot assignment when fewer than four resonator peaks are found."""
    count = len(frequencies)
    if count >= NUM_RESONATORS:
        return list(range(count)), "full"
    if count != 3:
        return [None] * count, "unassigned"

    left_gap = float(frequencies[1] - frequencies[0])
    right_gap = float(frequencies[2] - frequencies[1])
    min_gap = max(min(left_gap, right_gap), 1e-12)
    gap_ratio = max(left_gap, right_gap) / min_gap

    if gap_ratio >= 1.6:
        if left_gap > right_gap:
            return [0, 2, 3], "slot1-missing-large-left-gap"
        return [0, 1, 3], "slot2-missing-large-right-gap"

    scan_min = float(min(xs))
    scan_max = float(max(xs))
    scan_center = (scan_min + scan_max) / 2.0
    cluster_center = sum(frequencies) / len(frequencies)
    if cluster_center < scan_center:
        return [0, 1, 2], "right-edge-missing-cluster-left"
    return [1, 2, 3], "left-edge-missing-cluster-right"


def qid_for_sorted_slot(mux_index: int, sorted_slot: int) -> int:
    """Return the qubit id for a MUX index and sorted resonator slot."""
    inverse_peak_positions = {slot: pos for pos, slot in PEAK_POSITIONS.items()}
    return mux_index * NUM_RESONATORS + inverse_peak_positions[sorted_slot]
