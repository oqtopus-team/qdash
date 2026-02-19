# CheckReadoutFrequency

Calibrates the readout resonator frequency for optimal state discrimination.

## What it measures

Readout resonator frequency – the optimal probe frequency for qubit state measurement.

## Physical principle

Sweep readout tone detuning around the expected resonator frequency while measuring transmission; the optimal point maximizes state-dependent signal.

## Expected result

Transmission dip centered at the resonator frequency; optimal readout is near the dispersive-shifted midpoint.

- result_type: peak_curve
- x_axis: Readout frequency (GHz)
- y_axis: Transmission amplitude
- good_visual: clear transmission dip with well-defined minimum, symmetric line shape

## Evaluation criteria

Frequency should be within expected range of design; clear transmission feature with good signal-to-noise ratio.

- check_questions:
  - "Is the resonator frequency within ±5 MHz of design target?"
  - "Is the transmission feature clear with good SNR?"
  - "Are there any parasitic modes or spurious features?"

## Input parameters

None.

## Output parameters

- readout_frequency: Readout frequency (GHz)

## Run parameters

- detuning_range: Detuning range (GHz)
- time_range: Time range (ns)
- shots: Number of shots (a.u.)
- interval: Time interval (ns)

## Common failure patterns

- [warning] Resonator shifted from design
  - cause: qubit-induced dispersive shift not accounted for
  - visual: transmission dip shifted from expected position
  - next: run after qubit frequency calibration, re-center readout
- [warning] Multiple modes visible
  - cause: parasitic resonances or box modes
  - visual: multiple dips in transmission spectrum
  - next: identify which mode is the target resonator
- [info] Drift between cooldowns
  - cause: thermal contraction or connector issues
  - visual: systematic frequency shift from previous cooldown
  - next: recalibrate after each cooldown

## Tips for improvement

- Run after qubit frequency calibration since dispersive shift depends on qubit-resonator detuning.
- If readout fidelity is poor despite good frequency, check dispersive shift magnitude.
- Compare with broadband resonator scan for consistency.

## Analysis guide

1. Verify the readout frequency is near the design target.
2. Check for parasitic modes or spurious features in the spectrum.
3. Compare with previous cooldown values for drift assessment.
4. If shifted significantly, assess impact on readout fidelity.

## Related context

- history(last_n=5)
