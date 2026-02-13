# X90InterleavedRandomizedBenchmarking

Measures X90 (π/2) gate-specific error rate via interleaved randomized benchmarking.

## What it measures

Error per X90 gate by interleaving it between random Cliffords.

## Physical principle

Run standard RB and interleaved RB (with X90 between each Clifford); ratio of decay rates gives gate-specific error.

## Expected curve

Two exponential decays; interleaved decays faster than reference.

## Evaluation criteria

X90 gate error <0.1% excellent; <0.5% acceptable.

## Common failure patterns

- Reference RB fidelity too low – can't isolate X90 error.
- Statistical uncertainty too large – need more sequences.
- Coherent errors not captured – IRB gives average over Pauli errors.

## Tips for improvement

- Always run reference RB in same session for fair comparison.
- If X90 error >> reference EPC, focus on pulse amplitude tuning.
- Gate error = (1 - p_interleaved/p_reference) * (d-1)/d where d=2.
