# RandomizedBenchmarking

Measures average gate error rate via randomized benchmarking (RB).

## What it measures

Average error per Clifford gate (EPC) – gate-set-level fidelity metric.

## Physical principle

Apply random Clifford gate sequences of increasing length with inversion gate; measure survival probability. Exponential decay rate gives average gate error.

## Expected result

Survival probability decays exponentially with sequence length; intercept ~0.5.

- result_type: decay_curve
- x_axis: Clifford sequence length
- y_axis: Survival probability
- fit_model: A * p^m + B, where p is the depolarizing parameter
- good_visual: smooth exponential decay with clear trend, low shot noise

![Randomized benchmarking decay](./0.png)

## Evaluation criteria

Error per Clifford should be low; decay should be well-fitted by single exponential (Markovian errors).

- check_questions:
  - "Is the EPC (error per Clifford) below target?"
  - "Is the decay well-fitted by a single exponential (Markovian)?"
  - "Are there signs of leakage (non-exponential decay)?"

## Output parameters

- error_per_clifford: Average error per Clifford gate; lower is better
- depolarizing_parameter: Decay parameter p; fidelity = 1 - (1-p)(d-1)/d
- fit_r_squared: Fit quality; expected > 0.95

## Common failure patterns

- [warning] Non-exponential decay
  - cause: leakage or non-Markovian errors
  - visual: curve deviates from single exponential, kink or plateau
  - next: check for leakage, investigate non-Markovian noise
- [critical] Very fast decay
  - cause: gate errors too large for useful RB
  - visual: survival drops to 0.5 within a few Cliffords
  - next: recalibrate single-qubit gates first
- [info] SPAM errors dominating short sequences
  - cause: readout or preparation errors
  - visual: intercept significantly different from 0.5 or 1.0
  - next: improve readout calibration, use SPAM-robust fitting

## Tips for improvement

- Use >=30 random sequences per length for reliable statistics.
- Compare with interleaved RB to isolate specific gate errors.
- If decay is non-exponential, check for leakage.

## Analysis guide

1. Verify the exponential decay fit quality.
2. Extract the error per Clifford from the decay parameter.
3. Check for non-exponential behavior indicating leakage or non-Markovian errors.
4. Compare with individual gate error estimates for consistency.
5. If EPC is too high, recommend specific gate recalibration.

## Prerequisites

- CheckPIPulse
- CheckHPIPulse

## Related context

- history(last_n=5)
