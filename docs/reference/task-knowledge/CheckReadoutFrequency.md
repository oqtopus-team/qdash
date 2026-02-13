# CheckReadoutFrequency

Calibrates the readout resonator frequency for optimal state discrimination.

## What it measures

Readout resonator frequency – the optimal probe frequency for qubit state measurement.

## Physical principle

Sweep readout tone detuning around the expected resonator frequency while measuring transmission; the optimal point maximizes state-dependent signal.

## Expected curve

Transmission dip centered at the resonator frequency; optimal readout is near the dispersive-shifted midpoint.

## Evaluation criteria

Frequency within ±5 MHz of design; clear transmission feature.

## Common failure patterns

- Resonator shifted from coupling – qubit-induced dispersive shift not accounted for.
- Multiple modes visible – parasitic resonances or box modes.
- Drift between cooldowns – thermal contraction or connector issues.

## Tips for improvement

- Run after qubit frequency calibration since dispersive shift depends on qubit-resonator detuning.
- If readout fidelity is poor despite good frequency, check dispersive shift magnitude.
- Compare with broadband resonator scan for consistency.
