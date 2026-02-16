# CheckHPIPulse

Validates π/2 pulse quality by repeated application and population measurement.

## What it measures

π/2 pulse fidelity – accumulated rotation error over multiple applications.

## Physical principle

Apply the calibrated π/2 pulse repeatedly; population should cycle through superposition states. Deviation indicates rotation or phase error.

## Expected result

Population oscillation with period 4 (four π/2 pulses = full rotation); contrast decay reveals error.

- result_type: oscillation
- x_axis: Number of π/2 pulse repetitions
- y_axis: P(|1⟩)
- good_visual: clear oscillation with period 4, high contrast maintained over 20+ repetitions

![HPI pulse error amplification](figures/CheckHPIPulse/0.png)

## Evaluation criteria

Correct cycling pattern over many repetitions with minimal contrast decay.

- check_questions:
  - "Does the population cycle with period 4 as expected?"
  - "Is the contrast maintained over 20 repetitions?"
  - "Is the per-gate error rate acceptable?"

## Output parameters

- gate_fidelity: Estimated X90 gate fidelity from repetition decay
- per_gate_error: Error per application extracted from contrast decay

## Common failure patterns

- [critical] Rotation angle error
  - cause: π/2 pulse amplitude off, population drifts from expected pattern
  - visual: oscillation period deviates from 4, systematic drift
  - next: re-run CreateHPIPulse with finer amplitude scan
- [warning] Phase error
  - cause: phase calibration off, visible in tomographic basis
  - visual: pattern distortion not visible in Z-only measurement
  - next: check phase calibration, use tomographic validation
- [info] Decoherence during sequence
  - cause: T1/T2 limit useful number of repetitions
  - visual: exponential contrast decay
  - next: reduce repetitions, compare with coherence times

## Tips for improvement

- If validation fails, re-run CreateHPIPulse or try DRAG correction.
- Compare error rate with CheckPIPulse for consistency.
- Phase errors may require separate X/Y pulse calibration.

## Analysis guide

1. Verify the oscillation period is 4 (four X90 = full rotation).
2. Check contrast decay rate to estimate per-gate error.
3. Compare with CheckPIPulse error rate for consistency.
4. If error is large, recommend recalibration.

## Prerequisites

- CreateHPIPulse
- CheckRabi

## Related context

- history(last_n=5)
