# CheckQubit

Quick qubit validation via brief Rabi oscillation check.

## What it measures

Basic qubit responsiveness – whether the qubit shows coherent Rabi oscillations.

## Physical principle

Short Rabi experiment with varying pulse duration to confirm qubit is functional and control/readout lines are operational.

## Expected result

Sinusoidal Rabi oscillation with clear |0⟩/|1⟩ contrast.

- result_type: oscillation
- x_axis: Pulse duration (ns)
- y_axis: P(|1⟩)
- good_visual: clear sinusoidal oscillation with high contrast between |0⟩ and |1⟩ states

## Evaluation criteria

Clear oscillation visible with reasonable contrast; Rabi frequency consistent with drive amplitude. This is a quick sanity check, not a precision measurement.

- check_questions:
  - "Is a clear oscillation visible in the data?"
  - "Is the contrast (peak-to-trough) reasonable (>50%)?"
  - "Is the Rabi frequency consistent with the drive amplitude?"

## Input parameters

None.

## Output parameters

- rabi_amplitude: Rabi oscillation amplitude (a.u.)
- rabi_frequency: Rabi oscillation frequency (MHz)

## Run parameters

- time_range: Time range for Rabi oscillation (ns)
- shots: Number of shots for Rabi oscillation (a.u.)
- interval: Time interval for Rabi oscillation (ns)

## Common failure patterns

- [critical] No oscillation
  - cause: qubit not responding; drive line or frequency misconfigured
  - visual: flat line, no modulation in signal
  - next: check drive line connectivity and qubit frequency calibration
- [warning] Very low contrast
  - cause: thermal population or T1 too short
  - visual: small amplitude oscillation riding on large offset
  - next: check effective qubit temperature and readout fidelity
- [warning] Irregular oscillation
  - cause: frequency collision or TLS coupling
  - visual: beating pattern or non-sinusoidal oscillation
  - next: check for TLS near qubit frequency, verify frequency calibration

## Tips for improvement

- This is a quick sanity check; if it fails, investigate drive and readout chains first.
- Compare Rabi frequency across qubits to identify drive uniformity issues.
- If amplitude is very small, adjust control amplitude.

## Analysis guide

1. Verify that a clear oscillation is present in the data.
2. Check the contrast (should be >50% for a functional qubit).
3. If no oscillation, diagnose drive and readout chain.
4. If low contrast, check temperature and T1.

## Related context

- history(last_n=5)
