# CheckRabi

Measures Rabi oscillation to extract drive amplitude, frequency, and contrast.

## What it measures

Rabi oscillation parameters: amplitude (contrast), frequency (drive strength), and decay.

## Physical principle

Apply a resonant drive pulse of variable duration; the qubit oscillates between |0⟩ and |1⟩ at the Rabi frequency Ω_R.

## Expected result

Damped sinusoidal oscillation of P(|1⟩) vs pulse duration. Frequency gives Ω_R, envelope gives T_Rabi.

- result_type: oscillation
- x_axis: Pulse duration (ns)
- y_axis: P(|1⟩)
- fit_model: A * cos(2π·Ω_R·t) * exp(-t/T_Rabi) + B
- good_visual: clear sinusoidal oscillation with high contrast and slow decay envelope

![Rabi oscillation](figures/CheckRabi/0.png)

## Evaluation criteria

Rabi contrast should be high; frequency should be consistent with calibrated drive amplitude; fit quality should be good.

- check_questions:
  - "Is the Rabi contrast >90%?"
  - "Is the Rabi frequency consistent with the expected drive amplitude?"
  - "Is the fit R² > 0.95?"
  - "Is the decay (T_Rabi) slow compared to the oscillation period?"

## Output parameters

- rabi_frequency: Rabi oscillation frequency Ω_R; indicates drive strength
- rabi_contrast: Peak-to-trough amplitude; expected > 0.9
- t_rabi: Rabi decay time; longer is better
- fit_r_squared: Fit quality; expected > 0.95

## Common failure patterns

- [critical] Low contrast (<70%)
  - cause: readout miscalibration, thermal population, or leakage
  - visual: small oscillation amplitude, large DC offset
  - next: check readout fidelity and effective qubit temperature
- [warning] Rapid decay
  - cause: T1/T2 limiting or drive-induced heating
  - visual: oscillation amplitude drops quickly with pulse duration
  - next: check T1, reduce drive amplitude if heating is suspected
- [warning] Frequency mismatch
  - cause: drive amplitude changed or DAC nonlinearity
  - visual: oscillation frequency inconsistent with drive setting
  - next: recalibrate drive amplitude, check DAC linearity
- [warning] Beating pattern
  - cause: TLS strongly coupled near qubit frequency
  - visual: amplitude modulation with a second frequency component
  - next: check for TLS, try different qubit frequency operating point

## Tips for improvement

- Use Rabi frequency to calibrate π and π/2 pulse amplitudes.
- If contrast is low, check effective qubit temperature and readout fidelity first.
- Compare Rabi frequency across qubits for drive-line uniformity assessment.

## Analysis guide

1. Assess the oscillation contrast and fit quality (R²).
2. Verify Rabi frequency is consistent with the drive amplitude setting.
3. Check the decay envelope – rapid decay indicates decoherence or heating.
4. Look for beating patterns that would indicate TLS coupling.
5. Compare with recent history for drift in drive calibration.

## Prerequisites

- CheckQubitFrequency
- CheckReadoutFrequency

## Related context

- history(last_n=5)
