# CreateHPIPulse

Calibrates π/2 (X90) gate pulse amplitude via Rabi-based fitting.

## What it measures

Optimal pulse amplitude for a half-π rotation (|0⟩ → superposition).

## Physical principle

Same Rabi-based calibration as CreatePIPulse but targeting the π/2 rotation point – the first point where population reaches 0.5.

## Expected curve

Rabi oscillation vs amplitude; π/2 pulse at the quarter-period point.

## Evaluation criteria

Amplitude approximately half of π pulse; fit R² > 0.95.

## Common failure patterns

- Amplitude calibration error – superposition state is wrong, affecting all quantum algorithms.
- Leakage – same concerns as π pulse but at lower amplitude.
- Phase error – X90 may accumulate phase errors visible in tomography.

## Tips for improvement

- Run after CreatePIPulse; the π/2 amplitude should be close to half the π amplitude.
- If amplitude differs significantly from π_pulse/2, suspect drive nonlinearity.
- Validate with CheckHPIPulse after calibration.
