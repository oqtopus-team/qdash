# CheckElectricalDelay

Measures the electrical delay in the readout line.

## What it measures

Electrical delay – the time delay experienced by signals traveling through the readout chain (cables, components, filters) from pulse generation to measurement acquisition.

## Physical principle

Time-of-flight measurement: measures the phase slope of the readout signal as a function of frequency. The electrical delay is proportional to the linear phase gradient across the measurement bandwidth. Accurate delay compensation is essential for proper IQ demodulation and readout fidelity.

## Expected result

A measured electrical delay value in nanoseconds, representing the total signal propagation time through the readout chain.

- result_type: scalar
- good_visual: consistent delay value within expected range for the physical setup

## Evaluation criteria

The measured delay should be consistent with the physical cable lengths and component specifications. Sudden changes in delay indicate hardware changes or issues.

- check_questions:
  - "Is the measured delay within a reasonable range for this setup?"
  - "Is the delay consistent with previous measurements?"
  - "Has any hardware been changed that would affect the delay?"

## Input parameters

None.

## Output parameters

- electrical_delay: Electrical delay (ns)

## Run parameters

None.

## Common failure patterns

- [warning] Unexpected delay change
  - cause: cable replaced, connector issue, or component change
  - visual: delay value significantly different from baseline
  - next: verify hardware configuration, check for loose connectors
- [critical] Unreasonable delay value
  - cause: measurement error, poor signal quality, or disconnected cable
  - visual: delay value far outside physical expectations
  - next: check readout chain connectivity, verify signal quality

## Tips for improvement

- Measure electrical delay after any hardware change to the readout chain.
- Use consistent measurement conditions (frequency range, power) for reproducibility.
- Record baseline delay values for each readout channel as reference.

## Analysis guide

1. Review the measured delay value.
2. Compare with baseline/previous measurements.
3. If delay has changed, identify hardware modifications that could explain the change.
4. Ensure delay compensation is updated in the system configuration.

## Related context

- history(last_n=5)
