# CheckRabi

Measures Rabi oscillation to extract drive amplitude, frequency, and contrast.

## What it measures

Rabi oscillation parameters: amplitude (contrast), frequency (drive strength), and decay.

## Physical principle

Apply a resonant drive pulse of variable duration; the qubit oscillates between |0⟩ and |1⟩ at the Rabi frequency Ω_R.

## Expected curve

Damped sinusoidal oscillation of P(|1⟩) vs pulse duration. Frequency gives Ω_R, envelope gives T_Rabi.

## Evaluation criteria

Rabi contrast > 90%; frequency consistent with calibrated drive amplitude; R² > 0.95.

## Common failure patterns

- Low contrast – readout miscalibration, thermal population, or |0⟩/|1⟩ leakage.
- Rapid decay – T1/T2 limiting or drive-induced heating.
- Frequency mismatch – drive amplitude changed or DAC nonlinearity.
- Beating pattern – two-level system (TLS) strongly coupled near qubit frequency.

## Tips for improvement

- Use Rabi frequency to calibrate π and π/2 pulse amplitudes.
- If contrast is low, check effective qubit temperature and readout fidelity first.
- Compare Rabi frequency across qubits for drive-line uniformity assessment.
