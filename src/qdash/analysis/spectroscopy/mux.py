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
