# X90InterleavedRandomizedBenchmarking

Measures X90 (π/2) gate-specific error rate via interleaved randomized benchmarking.

## What it measures

Error per X90 gate by interleaving it between random Cliffords.

## Physical principle

Run standard RB and interleaved RB (with X90 between each Clifford); ratio of decay rates gives gate-specific error.

## Expected result

Two exponential decays; interleaved decays faster than reference.

- result_type: decay_curve
- x_axis: Clifford sequence length
- y_axis: Survival probability
- fit_model: A * p^m + B for both reference and interleaved
- good_visual: two clear exponential decays with the interleaved curve decaying faster, both well-fitted

![X90 interleaved randomized benchmarking](./0.png)

## Evaluation criteria

X90 gate error should be low; reference and interleaved curves should both be well-fitted exponentials.

- check_questions:
  - "Is the X90 gate error below the target?"
  - "Are both reference and interleaved curves well-fitted?"
  - "Is the reference RB fidelity sufficient to isolate X90 error?"

## Output parameters

- x90_gate_error: X90-specific error rate; lower is better
- reference_epc: Reference error per Clifford for comparison
- interleaved_epc: Interleaved error per Clifford

## Common failure patterns

- [warning] Reference RB fidelity too low
  - cause: overall gate quality insufficient to isolate X90 error
  - visual: both curves decay very quickly
  - next: improve overall gate calibration first
- [info] Statistical uncertainty too large
  - cause: insufficient number of random sequences
  - visual: large error bars on fitted parameters
  - next: increase number of random sequences (>=30 per length)
- [warning] Coherent errors not captured
  - cause: IRB gives average over Pauli errors, may miss coherent errors
  - visual: IRB error lower than expected from other diagnostics
  - next: supplement with tomographic diagnostics

## Tips for improvement

- Always run reference RB in same session for fair comparison.
- If X90 error >> reference EPC, focus on pulse amplitude tuning.
- Gate error = (1 - p_interleaved/p_reference) * (d-1)/d where d=2.

## Analysis guide

1. Compare the reference and interleaved decay curves.
2. Extract the X90-specific error rate from the decay ratio.
3. Check if the reference EPC is low enough for meaningful interleaving.
4. Compare the X90 error with the overall EPC for consistency.
5. If X90 error is dominant, recommend pulse recalibration.

## Prerequisites

- RandomizedBenchmarking
- CheckHPIPulse

## Related context

- history(last_n=5)
