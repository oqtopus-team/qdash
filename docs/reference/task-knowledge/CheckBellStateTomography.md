# CheckBellStateTomography

Full density matrix tomography of the Bell state for detailed characterization.

## What it measures

Complete density matrix of prepared Bell state; concurrence and entanglement metrics.

## Physical principle

Prepare Bell state, measure in 9 Pauli basis combinations (XX, XY, ..., ZZ), reconstruct density matrix via maximum likelihood.

## Expected curve

Density matrix close to ideal Bell state |Φ+⟩; off-diagonal elements indicating coherence.

## Evaluation criteria

State fidelity >90%; concurrence >0.9.

## Common failure patterns

- Systematic tomography errors – measurement basis miscalibration.
- Decoherence – reduced off-diagonal elements.
- State preparation errors dominate reconstruction.

## Tips for improvement

- Requires well-calibrated measurement rotations (X90, Y90).
- Use maximum likelihood reconstruction to ensure physical state.
- Compare diagonal elements with simple Bell state measurement for consistency.
