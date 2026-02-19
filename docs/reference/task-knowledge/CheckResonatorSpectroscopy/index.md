# CheckResonatorSpectroscopy

High-resolution 2D spectroscopy of all resonators in a readout multiplexer (MUX).

## What it measures

Readout resonator frequency – performs a 2D sweep (frequency x power) to precisely determine each resonator's resonance frequency within a MUX, including power-dependent behavior.

## Physical principle

2D resonator spectroscopy: the readout resonator response is measured across both frequency and power ranges. At low power, the resonator frequency reflects the dispersive shift from the qubit (dressed frequency). At high power, the resonator approaches its bare frequency. Comparing low-power and high-power responses reveals coupling strength and optimal readout conditions.

## Expected result

A 2D color map of resonator response vs frequency and power, with detected resonance peaks annotated.

- result_type: 2d_spectroscopy
- x_axis: Frequency (GHz)
- y_axis: Power (dB)
- z_axis: Readout signal (a.u.)
- good_visual: clear resonance dips/peaks at each resonator frequency, with visible power-dependent frequency shift

## Evaluation criteria

All expected resonators in the MUX should be detected. Resonance frequencies should be well-separated and consistent with the chip design.

- check_questions:
  - "Are all expected resonators detected (typically 4 per MUX)?"
  - "Are the detected frequencies consistent with the chip design?"
  - "Is the power-dependent frequency shift visible and physical?"
  - "Are the peaks well-resolved at both low and high power levels?"

## Input parameters

None.

## Output parameters

- readout_frequency: Estimated resonator frequency from spectroscopy (GHz)

## Run parameters

- frequency_range: Frequency range for resonator spectroscopy (GHz)
- power_range: Power range for resonator spectroscopy (dB)
- shots: Number of shots for resonator spectroscopy (a.u.)
- num_resonators: Number of resonators to detect (a.u.)
- high_power_min: Minimum power for high-power peak detection (dB)
- high_power_max: Maximum power for high-power peak detection (dB)
- low_power: Power level for low-power peak detection (dB)

## Common failure patterns

- [critical] Missing resonator peaks
  - cause: resonator frequency outside scan range, damaged resonator, or readout line issue
  - visual: fewer peaks than expected in the 2D map
  - next: widen scan range, check readout chain hardware
- [warning] Overlapping resonators
  - cause: fabrication variation causing frequency collision
  - visual: two resonators with nearly identical frequencies
  - next: use higher resolution scan to resolve; may indicate chip fabrication issue
- [warning] No power dependence
  - cause: very weak qubit-resonator coupling or qubit not at expected frequency
  - visual: resonator frequency constant across all power levels
  - next: verify qubit frequency and coupling design

## Tips for improvement

- This is a MUX-level task: it runs once per MUX and provides frequencies for all qubits in that MUX.
- Default frequency range is 9.75-10.75 GHz; QUEL1SE_R8 readout boxes use 5.75-6.75 GHz.
- Adjust num_resonators if the MUX has a non-standard number of resonators.
- Use high_power_min/max and low_power parameters to tune peak detection sensitivity.

## Analysis guide

1. Review the 2D spectroscopy map for all expected resonator peaks.
2. Verify peak detection accuracy on the annotated figure.
3. Check that the assigned frequency for this qubit corresponds to the correct MUX position.
4. Compare detected frequencies with design values and previous measurements.
5. Note any power-dependent behavior anomalies.

## Prerequisites

- Configure
- CheckResonatorFrequencies

## Related context

- history(last_n=5)
