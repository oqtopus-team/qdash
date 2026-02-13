# CheckZX90

Validates ZX90 two-qubit gate fidelity via process or state fidelity measurement.

## What it measures

ZX90 gate fidelity – closeness to ideal CNOT-equivalent operation.

## Physical principle

Apply calibrated ZX90 gate and measure output state fidelity against ideal; may use interleaved RB or QPT.

## Expected curve

Gate fidelity metric; conditional rotation of target by control state.

## Evaluation criteria

ZX90 fidelity >95% acceptable; >99% excellent.

## Common failure patterns

- Coherence-limited – T1/T2 of either qubit too short.
- Residual ZZ – static coupling causes phase errors.
- CR amplitude drift – gate angle deviates from 90°.

## Tips for improvement

- Compare with interleaved RB for gate-specific error rate.
- Check both control states (|0⟩ and |1⟩) independently.
- If fidelity is poor, re-run CreateZX90 with fresh CR calibration.
