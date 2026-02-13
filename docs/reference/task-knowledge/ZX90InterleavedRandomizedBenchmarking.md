# ZX90InterleavedRandomizedBenchmarking

Measures ZX90 two-qubit gate error rate via interleaved randomized benchmarking.

## What it measures

Error per ZX90 gate isolated via two-qubit interleaved RB.

## Physical principle

Two-qubit RB with ZX90 interleaved between random two-qubit Cliffords.

## Expected curve

Two-qubit survival probability decays; interleaved faster than reference.

## Evaluation criteria

ZX90 gate error <1% acceptable; <0.5% excellent.

## Common failure patterns

- Two-qubit Clifford compilation errors.
- Leakage in either qubit during CR drive.
- Long sequences exceed coherence time.

## Tips for improvement

- Two-qubit RB requires many more sequences for convergence.
- Compare with process tomography for consistency.
- Gate error includes contributions from both qubits' decoherence.
