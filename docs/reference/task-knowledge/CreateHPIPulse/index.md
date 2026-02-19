# CreateHPIPulse

Calibrates π/2 (X90) gate pulse amplitude via Rabi-based fitting.

## What it measures

Optimal pulse amplitude for a half-π rotation (|0⟩ → superposition).

## Physical principle

Same Rabi-based calibration as CreatePIPulse but targeting the π/2 rotation point – the first point where population reaches 0.5.

## Expected result

Rabi oscillation vs amplitude; π/2 pulse at the quarter-period point.

- result_type: oscillation
- x_axis: Drive amplitude (a.u.)
- y_axis: P(|1⟩)
- fit_model: A * cos(π · amp / amp_π) + B (π/2 at half of π amplitude)
- good_visual: clear oscillation with well-identified π/2 amplitude at the 0.5 population crossing

![HPI pulse calibration](./0.png)

## Evaluation criteria

The π/2 amplitude should be approximately half of the π amplitude; fit quality should be high.

- check_questions:
  - "Is the π/2 amplitude approximately half the π amplitude?"
  - "Is the fit R² > 0.95?"
  - "Is the amplitude consistent with previous calibrations?"

## Output parameters

- hpi_pulse_amplitude: Calibrated amplitude for π/2 rotation
- fit_r_squared: Fit quality; expected > 0.95

## Common failure patterns

- [critical] Amplitude calibration error
  - cause: incorrect π/2 amplitude affects all quantum algorithms using superposition
  - visual: population does not reach 0.5 at the identified amplitude
  - next: refine amplitude scan, verify against π amplitude
- [warning] Leakage
  - cause: same concerns as π pulse but at lower amplitude
  - visual: population offset from expected 0.5
  - next: consider DRAG correction
- [warning] Phase error
  - cause: X90 may accumulate phase errors visible in tomography
  - visual: not always visible in Z-only measurement
  - next: validate with tomographic measurement

## Tips for improvement

- Run after CreatePIPulse; the π/2 amplitude should be close to half the π amplitude.
- If amplitude differs significantly from π_pulse/2, suspect drive nonlinearity.
- Validate with CheckHPIPulse after calibration.

## Analysis guide

1. Compare the π/2 amplitude with half the π amplitude for consistency.
2. Verify fit quality (R²).
3. If significant deviation from π/2 = π_amp/2, investigate drive nonlinearity.
4. Recommend CheckHPIPulse validation after calibration.

## Prerequisites

- CreatePIPulse
- CheckQubitFrequency

## Related context

- history(last_n=5)
