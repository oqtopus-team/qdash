# CheckNoise

Checks the noise levels in the control and readout system.

## What it measures

System noise floor – measures the baseline noise level across control and readout channels to ensure the system is operating within acceptable noise margins.

## Physical principle

Measures the signal amplitude with no intentional drive applied, characterizing the noise floor from electronics, thermal sources, and environmental interference.

## Expected result

Noise levels within acceptable thresholds for all channels.

- result_type: noise_measurement
- good_visual: low, uniform noise floor across all channels with no spurious peaks

## Evaluation criteria

Noise levels should be below system-specific thresholds. Elevated noise or spurious peaks indicate hardware issues or electromagnetic interference.

- check_questions:
  - "Is the noise floor within acceptable limits for all channels?"
  - "Are there any spurious peaks or unexpected spectral features?"
  - "Is the noise level consistent across channels?"

## Output parameters

None.

## Common failure patterns

- [warning] Elevated noise floor
  - cause: grounding issue, thermal noise, or amplifier saturation
  - next: check grounding, verify attenuator settings, check cryostat temperature
- [critical] Spurious tones
  - cause: electromagnetic interference or oscillating amplifier
  - next: identify interference source, check shielding and filtering
- [warning] Channel-dependent noise
  - cause: faulty cable, connector, or component in specific channel
  - next: isolate the noisy channel and inspect hardware

## Tips for improvement

- Run noise check after any hardware change (cable swap, attenuator adjustment).
- Compare with historical noise data to detect degradation trends.
- Ensure proper shielding and filtering in the measurement setup.

## Analysis guide

1. Review noise levels across all channels.
2. Compare with baseline/historical measurements.
3. Identify any channels with anomalously high noise.
4. Check for spurious tones that could interfere with qubit operations.

## Prerequisites

- LinkUp

## Related context

- history(last_n=5)
