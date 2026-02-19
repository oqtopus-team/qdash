# CheckPIPulse

Validates π pulse quality by repeated application and population measurement.

## What it measures

π pulse fidelity – accumulated error over multiple applications.

## Physical principle

Apply the calibrated π pulse repeatedly N times; odd repetitions should give |1⟩, even should give |0⟩. Deviation indicates rotation error.

## Expected result

Population oscillation between 0 and 1 across repetitions; contrast decay reveals error accumulation.

- result_type: oscillation
- x_axis: Number of π pulse repetitions
- y_axis: P(|1⟩)
- good_visual: sharp alternation between 0 and 1 with minimal contrast decay over 20+ repetitions

![PI pulse error amplification](./0.png)

## Evaluation criteria

Contrast should remain high over many repetitions; per-gate error rate extracted from decay should be low.

- check_questions:
  - "Is the contrast >99% over 20 repetitions?"
  - "Is the decay envelope slow (small per-gate error)?"
  - "Is there evidence of leakage (non-oscillatory decay)?"

## Output parameters

- gate_fidelity: Estimated X180 gate fidelity from repetition decay
- per_gate_error: Error per application extracted from contrast decay

## Common failure patterns

- [critical] Amplitude error accumulation
  - cause: π pulse amplitude slightly off, error compounds with repetitions
  - visual: population drifts from ideal 0/1 alternation pattern
  - next: re-run CreatePIPulse with finer amplitude scan
- [warning] Leakage to |2⟩
  - cause: pulse too fast relative to anharmonicity, insufficient DRAG
  - visual: population decay envelope on oscillation (not just amplitude error)
  - next: try DRAG correction, slow down pulse
- [info] Decoherence during measurement
  - cause: T1/T2 limit the number of useful repetitions
  - visual: exponential decay of contrast independent of gate error
  - next: reduce number of repetitions, compare with T1 timescale

## Tips for improvement

- If contrast decays rapidly, re-run CreatePIPulse with finer amplitude scan.
- Compare with CheckDRAGPIPulse to see if DRAG correction improves fidelity.
- The decay rate gives an estimate of per-gate error.

## Analysis guide

1. Check the oscillation contrast over 20 repetitions.
2. Separate decoherence-induced decay from gate-error-induced decay.
3. Estimate per-gate error from the contrast decay rate.
4. If error is too large, recommend recalibration with CreatePIPulse.
5. Compare with DRAG version for improvement assessment.

## Prerequisites

- CreatePIPulse
- CheckRabi

## Related context

- history(last_n=5)
