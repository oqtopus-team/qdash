# X180InterleavedRandomizedBenchmarking

Measures X180 (π) gate-specific error rate via interleaved randomized benchmarking.

## What it measures

Error per X180 gate isolated from average Clifford error.

## Physical principle

Same interleaved RB protocol as X90 IRB but with X180 gate interleaved.

## Expected curve

Two exponential decays; interleaved decays faster proportional to X180 error.

## Evaluation criteria

X180 gate error <0.1% excellent; <0.5% acceptable.

## Common failure patterns

- X180 amplitude errors accumulate faster than X90.
- Leakage to |2⟩ more likely with full π rotation.
- Same statistical concerns as X90 IRB.

## Tips for improvement

- Compare X180 and X90 errors – X180 should be ≤2x X90 error.
- If X180 error is much worse, suspect DRAG tuning issues.
- Run after DRAG calibration for best results.
