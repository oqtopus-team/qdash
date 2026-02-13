# CheckQubit

Quick qubit validation via brief Rabi oscillation check.

## What it measures

Basic qubit responsiveness – whether the qubit shows coherent Rabi oscillations.

## Physical principle

Short Rabi experiment with varying pulse duration to confirm qubit is functional and control/readout lines are operational.

## Expected curve

Sinusoidal Rabi oscillation with clear |0⟩/|1⟩ contrast.

## Evaluation criteria

Clear oscillation visible; R² > 0.9; Rabi frequency consistent with drive amplitude.

## Common failure patterns

- No oscillation – qubit not responding; check drive line and frequency.
- Very low contrast – thermal population or T1 too short.
- Irregular oscillation – frequency collision or TLS coupling.

## Tips for improvement

- This is a quick sanity check; if it fails, investigate drive and readout chains first.
- Compare Rabi frequency across qubits to identify drive uniformity issues.
- If amplitude is very small, adjust control amplitude.
