"""MUX layout constants for resonator spectroscopy analysis.

Lives here (not under workflow) so it can be shared by the API container,
which does not ship the workflow engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Number of resonators expected per MUX.
NUM_RESONATORS: int = 4

# Qubit offsets in frequency-sorted resonator order. Reflects the usual
# physical arrangement of the four resonators in a MUX.
DEFAULT_RESONATOR_ASSIGNMENT_ORDER: tuple[int, ...] = (3, 0, 2, 1)
RESONATOR_ASSIGNMENT_PATTERNS: dict[str, tuple[int, ...]] = {
    "default": DEFAULT_RESONATOR_ASSIGNMENT_ORDER,
    "16q": (0, 3, 1, 2),
}

# Mapping from a qubit's position in its MUX (qid % 4) to the index of its
# resonance in the spectroscopy result.
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


def resonator_assignment_order_from_pattern(pattern: str | None) -> tuple[int, ...]:
    """Return the resonator assignment order for a named pattern."""
    normalized = (pattern or "default").strip().lower()
    if normalized not in RESONATOR_ASSIGNMENT_PATTERNS:
        valid_patterns = ", ".join(sorted(RESONATOR_ASSIGNMENT_PATTERNS))
        raise ValueError(
            f"unknown resonator_assignment_pattern {pattern!r}; expected one of: {valid_patterns}"
        )
    return RESONATOR_ASSIGNMENT_PATTERNS[normalized]


def resolve_resonator_assignment_order(pattern: str | None = None) -> tuple[int, ...]:
    """Resolve a named resonator assignment pattern."""
    return resonator_assignment_order_from_pattern(pattern)


def peak_positions_from_assignment_order(
    assignment_order: Sequence[int] | None,
) -> dict[int, int]:
    """Build qid-offset to sorted-slot mapping from frequency-sorted offsets.

    ``assignment_order`` is the list of qubit offsets in increasing resonator
    frequency order. For example, ``[3, 0, 2, 1]`` means the first detected
    frequency belongs to ``mux[3]``, then ``mux[0]``, ``mux[2]``, ``mux[1]``.
    """
    if assignment_order is None:
        return PEAK_POSITIONS.copy()

    normalized = [int(offset) for offset in assignment_order]
    expected_offsets = set(range(NUM_RESONATORS))
    if len(normalized) != NUM_RESONATORS or set(normalized) != expected_offsets:
        raise ValueError(
            "resonator_assignment_order must contain each qubit offset "
            f"0..{NUM_RESONATORS - 1} exactly once"
        )

    return {qid_offset: sorted_slot for sorted_slot, qid_offset in enumerate(normalized)}


def qid_for_sorted_slot(
    mux_index: int,
    sorted_slot: int,
    peak_positions: dict[int, int] | None = None,
) -> int:
    """Return the qubit id for a MUX index and sorted resonator slot."""
    if peak_positions is None:
        peak_positions = PEAK_POSITIONS
    inverse_peak_positions = {slot: pos for pos, slot in peak_positions.items()}
    return mux_index * NUM_RESONATORS + inverse_peak_positions[sorted_slot]
