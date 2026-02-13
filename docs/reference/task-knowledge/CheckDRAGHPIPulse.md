# CheckDRAGHPIPulse

Validates DRAG-corrected π/2 pulse quality for leakage suppression.

## What it measures

Gate fidelity of DRAG-corrected X90 pulse.

## Physical principle

Same DRAG principle as π pulse but for half rotation. Critical for quantum algorithms using superposition states.

## Expected curve

Correct superposition state after single pulse; oscillation under repeated application.

## Evaluation criteria

Gate fidelity >99.5%; leakage to |2⟩ <0.1%.

## Common failure patterns

- DRAG beta mis-tuned – phase or leakage errors.
- Amplitude off – does not produce exact π/2 rotation.
- Decoherence during measurement corrupts validation signal.

## Tips for improvement

- Compare with non-DRAG X90 to verify improvement.
- Run after DRAG π pulse is validated since they share parameters.
- Check phase accuracy with tomography if fidelity is borderline.
