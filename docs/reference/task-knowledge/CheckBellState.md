# CheckBellState

Prepares Bell state (|00⟩+|11⟩)/√2 and measures state fidelity.

## What it measures

Bell state fidelity – quality of entanglement between qubit pair.

## Physical principle

Apply H⊗I then CNOT; measure in Z basis and verify equal |00⟩/|11⟩ populations with coherent superposition.

## Expected curve

Population histogram showing ~50/50 |00⟩/|11⟩ with minimal |01⟩/|10⟩.

## Evaluation criteria

Bell state fidelity >90% acceptable; >95% excellent.

## Common failure patterns

- Low fidelity from single-qubit gate errors.
- Residual |01⟩/|10⟩ population from ZX90 miscalibration.
- Decoherence during circuit.
- Readout crosstalk – correlated measurement errors.

## Tips for improvement

- This is an end-to-end test combining single and two-qubit gates.
- Low fidelity here means debug gates individually first.
- Compare with Bell state tomography for full density matrix.
