# CheckDispersiveShift

Measures dispersive shift (χ) between qubit and readout resonator.

## What it measures

Dispersive shift (χ) – the frequency shift of the resonator conditioned on the qubit state.

## Physical principle

Measure resonator spectrum with qubit in |0⟩ and |1⟩; in the dispersive regime the resonator shifts by 2χ, enabling QND readout.

## Expected curve

Two transmission peaks/dips separated by 2χ; one for each qubit state.

## Evaluation criteria

2χ > resonator linewidth (κ); typically 2χ > 1 MHz for reliable readout.

## Common failure patterns

- Insufficient coupling – 2χ too small, states cannot be distinguished.
- Purcell limit – large χ degrades T1 via Purcell decay.
- Overlapping peaks – χ < κ/2 makes states unresolvable.

## Tips for improvement

- Use the midpoint between the two peaks as optimal readout frequency.
- If 2χ is too small, readout fidelity will be fundamentally limited.
- Monitor χ over time; shifts indicate qubit frequency drift.
