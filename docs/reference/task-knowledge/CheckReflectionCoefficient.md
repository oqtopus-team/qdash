# CheckReflectionCoefficient

Measures the resonator reflection coefficient to extract resonator frequency and coupling rates.

## What it measures

Resonator reflection parameters – measures the S11 (reflection coefficient) of the readout resonator to precisely determine the resonator frequency (f_r), external coupling rate (kappa_external), and internal loss rate (kappa_internal).

## Physical principle

Reflection coefficient spectroscopy: the resonator is probed in reflection, and the complex S11 parameter is measured as a function of frequency. The resonance appears as a circle in the complex plane. Fitting to a resonator model extracts the resonance frequency and coupling rates. The external coupling rate (kappa_external) quantifies the resonator-feedline coupling, while the internal loss rate (kappa_internal) quantifies intrinsic losses.

## Expected result

Reflection coefficient spectrum showing a clear resonance dip with a circular trajectory in the IQ plane.

- result_type: spectroscopy
- x_axis: Frequency (GHz)
- y_axis: |S11| (dB) / Phase (rad)
- good_visual: sharp resonance dip with clean circular trajectory in IQ plane

## Evaluation criteria

The resonance should be well-fit by the model. The coupling rates should be physically reasonable. External coupling should dominate over internal losses for a good resonator (kappa_external >> kappa_internal).

- check_questions:
  - "Is the resonance clearly visible and well-fit?"
  - "Is the resonator frequency consistent with previous measurements?"
  - "Is kappa_external >> kappa_internal (over-coupled regime)?"
  - "Are the coupling rates in a physically reasonable range?"

## Output parameters

- resonator_frequency: Precise resonator frequency f_r (GHz)
- kappa_external: External coupling rate (MHz); quantifies resonator-feedline coupling
- kappa_internal: Internal coupling rate (MHz); quantifies intrinsic resonator losses

## Common failure patterns

- [critical] No resonance detected
  - cause: resonator frequency far from scan range or readout line issue
  - visual: flat reflection response
  - next: run CheckResonatorFrequencies to locate resonance first
- [warning] Poor fit quality
  - cause: distorted resonance from impedance mismatch or background slope
  - visual: resonance visible but fit does not match well
  - next: check for background calibration issues, verify readout chain
- [warning] High internal loss (kappa_internal > kappa_external)
  - cause: resonator material defects, TLS loss, or fabrication issues
  - visual: shallow resonance dip, small circle in IQ plane
  - next: investigate chip quality; may indicate materials issue

## Tips for improvement

- This task provides the most precise resonator frequency measurement.
- Use kappa_external/kappa_internal ratio as a resonator quality diagnostic.
- Compare coupling rates across resonators for fabrication uniformity assessment.

## Analysis guide

1. Verify the resonance is clearly visible in the reflection spectrum.
2. Check the fit quality to the resonator model.
3. Verify resonator frequency is consistent with coarse measurements.
4. Assess kappa_external vs kappa_internal; over-coupled is preferred.
5. Compare with design values and previous measurements.

## Prerequisites

- Configure
- CheckResonatorFrequencies

## Related context

- history(last_n=5)
