# CheckPIPulse

Validates π pulse quality by repeated application and population measurement.

## What it measures

π pulse fidelity – accumulated error over multiple applications.

## Physical principle

Apply the calibrated π pulse repeatedly N times; odd repetitions should give |1⟩, even should give |0⟩. Deviation indicates rotation error.

## Expected curve

Population oscillation between 0 and 1 across repetitions; contrast decay reveals error accumulation.

## Evaluation criteria

Contrast >99% over 20 repetitions; minimal decay envelope.

## Common failure patterns

- Amplitude error accumulates – population drifts from ideal 0/1 alternation.
- Leakage to |2⟩ – population decay visible as envelope on oscillation.
- Decoherence during measurement – T1/T2 limit the number of useful repetitions.

## Tips for improvement

- If contrast decays rapidly, re-run CreatePIPulse with finer amplitude scan.
- Compare with CheckDRAGPIPulse to see if DRAG correction improves fidelity.
- The decay rate gives an estimate of per-gate error.
