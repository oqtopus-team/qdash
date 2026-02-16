# CheckResonatorFrequencies

Coarse frequency scan to locate readout resonator resonance frequencies.

## What it measures

Coarse resonator frequency – performs a broadband frequency sweep to identify the approximate resonance frequency of the readout resonator.

## Physical principle

Resonator frequency sweep: a probe tone is swept across a wide frequency range, and the transmitted or reflected signal phase is measured. At the resonator's resonance frequency, a sharp phase shift occurs, identifying the resonance.

## Expected result

Phase response showing a clear resonance feature (sharp phase shift) at the resonator frequency. Multiple peaks may be visible if the scan covers a MUX with multiple resonators.

- result_type: spectroscopy
- x_axis: Frequency (GHz)
- y_axis: Phase (rad) / Phase derivative
- good_visual: clear, sharp phase shift at resonator frequency with well-separated peaks for each resonator in the MUX

## Evaluation criteria

A clear phase shift should be visible at the expected resonator frequency. The number of detected peaks should match the expected number of resonators in the MUX (typically 4).

- check_questions:
  - "Is a clear phase shift visible at the expected resonator frequency?"
  - "Are the expected number of resonator peaks detected (typically 4 per MUX)?"
  - "Are the peaks well-separated and individually resolvable?"

## Output parameters

- coarse_resonator_frequency: Approximate resonator resonance frequency (GHz)

## Common failure patterns

- [critical] No resonance detected
  - cause: resonator frequency outside scan range or readout line not connected
  - visual: flat phase response with no features
  - next: widen scan range, check readout line connectivity
- [warning] Fewer peaks than expected
  - cause: overlapping resonators, insufficient scan resolution, or damaged resonator
  - visual: fewer than expected number of phase shifts
  - next: increase scan resolution, check chip layout for expected frequencies
- [warning] Broad or asymmetric resonance
  - cause: low Q-factor or impedance mismatch
  - visual: wide or distorted phase response
  - next: check readout chain for impedance issues

## Tips for improvement

- Default frequency range is 9.75-10.75 GHz; adjust based on chip design.
- For QUEL1SE_R8 readout boxes, the range shifts to 5.75-6.75 GHz.
- Peak positions within a MUX are mapped by qubit index (qid % 4).
- Use phase derivative (fig_phase_diff) for sharper peak identification.

## Analysis guide

1. Check the phase response for clear resonance features.
2. Verify the number of detected peaks matches expectations.
3. Identify the correct peak for this qubit based on MUX position (qid % 4).
4. Record the coarse frequency for use in subsequent spectroscopy.

## Prerequisites

- Configure

## Related context

- history(last_n=5)
