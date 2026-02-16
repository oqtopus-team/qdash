# ZX90InterleavedRandomizedBenchmarking

Measures ZX90 two-qubit gate error rate via interleaved randomized benchmarking.

## What it measures

Error per ZX90 gate isolated via two-qubit interleaved RB.

## Physical principle

Two-qubit RB with ZX90 interleaved between random two-qubit Cliffords.

## Expected result

Two-qubit survival probability decays; interleaved faster than reference.

- result_type: decay_curve
- x_axis: Two-qubit Clifford sequence length
- y_axis: Survival probability
- fit_model: A * p^m + B for both reference and interleaved
- good_visual: two clear exponential decays with interleaved faster, sufficient data points for fitting

![ZX90 interleaved randomized benchmarking](figures/ZX90InterleavedRandomizedBenchmarking/0.png)

## Evaluation criteria

ZX90 gate error should meet the target; the decay should be well-fitted and the reference should be clean enough to isolate the ZX90 contribution.

- check_questions:
  - "Is the ZX90 gate error below the target?"
  - "Is the reference two-qubit RB clean enough to isolate ZX90 error?"
  - "Are there signs of leakage in either qubit during CR drive?"

## Output parameters

- zx90_gate_error: ZX90-specific error rate; lower is better
- reference_epc: Reference two-qubit error per Clifford
- interleaved_epc: Interleaved two-qubit error per Clifford

## Common failure patterns

- [warning] Two-qubit Clifford compilation errors
  - cause: errors from decomposing two-qubit Cliffords into native gates
  - visual: reference decay faster than expected from individual gate errors
  - next: verify Clifford decomposition, check compiler
- [warning] Leakage during CR drive
  - cause: CR pulse excites higher levels in either qubit
  - visual: non-exponential decay, especially at longer sequences
  - next: check DRAG on both qubits, optimize CR parameters
- [info] Long sequences exceed coherence time
  - cause: total circuit duration approaches T1/T2 of either qubit
  - visual: survival drops to 0.25 before meaningful fit is possible
  - next: shorten maximum sequence length, improve coherence

## Tips for improvement

- Two-qubit RB requires many more sequences for convergence.
- Compare with process tomography for consistency.
- Gate error includes contributions from both qubits' decoherence.

## Analysis guide

1. Compare the reference and interleaved two-qubit decay curves.
2. Extract the ZX90-specific error rate from the decay ratio.
3. Check for non-exponential behavior indicating leakage.
4. Compare with single-qubit gate errors to assess two-qubit gate contribution.
5. If error is dominated by coherence, recommend coherence improvements first.

## Prerequisites

- RandomizedBenchmarking
- CheckZX90

## Related context

- history(last_n=5)
- coupling(zx_rate, coupling_strength)
