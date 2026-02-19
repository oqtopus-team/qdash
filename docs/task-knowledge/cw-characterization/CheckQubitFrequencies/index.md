# CheckQubitFrequencies

Coarse qubit frequency scan to locate the qubit transition frequency.

## What it measures

Coarse qubit frequency (f_01) – performs a broadband frequency scan to identify the approximate qubit transition frequency.

## Physical principle

Continuous-wave (CW) qubit spectroscopy: a probe tone is swept across a wide frequency range while monitoring the readout resonator response. When the probe frequency matches the qubit's ground-to-excited state transition (f_01), the qubit absorbs energy, causing a detectable shift in the resonator response.

## Expected result

A spectroscopy trace showing a dip or peak at the qubit transition frequency.

- result_type: spectroscopy
- x_axis: Frequency (GHz)
- y_axis: Readout signal (a.u.)
- good_visual: clear absorption feature (dip or peak) at the qubit frequency against a flat background

## Evaluation criteria

A clear spectral feature should be visible at the expected qubit frequency. The feature should be well-resolved above the noise floor.

- check_questions:
  - "Is a clear absorption feature visible in the spectroscopy trace?"
  - "Is the feature at a reasonable frequency for this qubit?"
  - "Is the signal-to-noise ratio sufficient to identify the peak?"

## Input parameters

None.

## Output parameters

- coarse_qubit_frequency: Coarse qubit frequency (GHz)

## Run parameters

None.

## Common failure patterns

- [critical] No feature detected
  - cause: qubit frequency outside scan range, drive power too low, or qubit not operational
  - visual: flat trace with no discernible features
  - next: widen scan range, increase drive power, or verify qubit is functional
- [warning] Multiple features
  - cause: TLS defects, harmonics, or frequency collisions with other qubits
  - visual: multiple dips/peaks in the spectroscopy trace
  - next: cross-reference with design frequencies to identify the correct feature
- [warning] Broad feature
  - cause: short coherence time or excessive drive power
  - visual: wide absorption feature making frequency determination imprecise
  - next: reduce drive power, check T1/T2

## Tips for improvement

- Use design frequencies to set an appropriate scan range centered on the expected qubit frequency.
- Start with moderate drive power; too much power broadens the feature.
- This is a coarse scan; use CheckQubitSpectroscopy for precise frequency determination.

## Analysis guide

1. Look for a clear absorption feature in the spectroscopy trace.
2. Verify the detected frequency is reasonable for this qubit design.
3. If multiple features exist, use design frequency as a guide.
4. Record the coarse frequency for use in subsequent fine spectroscopy.

## Related context

- history(last_n=5)
