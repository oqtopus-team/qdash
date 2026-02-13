# RandomizedBenchmarking

Measures average gate error rate via randomized benchmarking (RB).

## What it measures

Average error per Clifford gate (EPC) – gate-set-level fidelity metric.

## Physical principle

Apply random Clifford gate sequences of increasing length with inversion gate; measure survival probability. Exponential decay rate gives average gate error.

## Expected curve

Survival probability decays exponentially with sequence length; intercept ~0.5.

## Evaluation criteria

EPC <0.5% (fidelity >99.5%) is good; <0.1% is excellent.

## Common failure patterns

- Non-exponential decay – leakage or non-Markovian errors.
- Very fast decay – gate errors too large for useful RB.
- SPAM errors dominating short sequences.

## Tips for improvement

- Use ≥30 random sequences per length for reliable statistics.
- Compare with interleaved RB to isolate specific gate errors.
- If decay is non-exponential, check for leakage.
