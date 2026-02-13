# CreateZX90

Calibrates ZX90 (CNOT-equivalent) two-qubit gate from cross-resonance interaction.

## What it measures

Optimal CR pulse amplitude and duration for π/2 ZX rotation.

## Physical principle

Tune CR drive parameters to achieve exactly 90° ZX rotation; combine with single-qubit corrections for CNOT.

## Expected curve

ZX rotation angle vs CR pulse duration; target the 90° crossing point.

## Evaluation criteria

ZX rotation within 1° of 90°; parasitic rotations compensated.

## Common failure patterns

- CR pulse too long – decoherence limits fidelity.
- Parasitic ZZ coupling – requires echo sequence.
- Amplitude nonlinearity – ZX rate not proportional to drive.

## Tips for improvement

- Use echo CR sequence to cancel IX and IZ terms.
- After calibration, validate with CheckZX90.
- Consider active cancellation tone on target qubit.
