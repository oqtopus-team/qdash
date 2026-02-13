# CheckHPIPulse

Validates π/2 pulse quality by repeated application and population measurement.

## What it measures

π/2 pulse fidelity – accumulated rotation error over multiple applications.

## Physical principle

Apply the calibrated π/2 pulse repeatedly; population should cycle through superposition states. Deviation indicates rotation or phase error.

## Expected curve

Population oscillation with period 4 (four π/2 pulses = full rotation); contrast decay reveals error.

## Evaluation criteria

Correct cycling over 20 repetitions; minimal contrast decay.

## Common failure patterns

- Rotation angle error – population drifts from expected pattern.
- Phase error – visible in tomographic basis but not always in Z measurement.
- Decoherence during sequence – limits useful number of repetitions.

## Tips for improvement

- If validation fails, re-run CreateHPIPulse or try DRAG correction.
- Compare error rate with CheckPIPulse for consistency.
- Phase errors may require separate X/Y pulse calibration.
