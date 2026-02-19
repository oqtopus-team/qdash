# CheckReadoutAmplitude

Optimizes readout pulse amplitude by sweeping amplitude and measuring signal-to-noise ratio.

## What it measures

Optimal readout amplitude – sweeps the readout pulse amplitude and measures the resulting signal-to-noise ratio (SNR) to find the minimum amplitude that achieves sufficient measurement fidelity.

## Physical principle

Readout amplitude optimization: the readout pulse amplitude is varied while measuring both signal strength and noise. At low amplitudes, SNR is poor and state discrimination is unreliable. As amplitude increases, SNR improves until reaching a threshold for reliable measurement. Excessive amplitude can cause unwanted qubit transitions (measurement-induced mixing) or nonlinear resonator effects.

## Expected result

SNR vs amplitude curve showing a monotonic increase that crosses the SNR threshold at the optimal readout amplitude.

- result_type: sweep
- x_axis: Readout amplitude (a.u.)
- y_axis: Signal / Noise / SNR
- good_visual: clear SNR increase with amplitude, crossing the threshold at a well-defined amplitude

## Evaluation criteria

The SNR should cross the threshold at a reasonable amplitude. The optimal amplitude should be in a region where SNR is increasing but not at the maximum to avoid measurement-induced effects.

- check_questions:
  - "Does the SNR cross the threshold within the sweep range?"
  - "Is the optimal amplitude at a reasonable value (not at the extremes)?"
  - "Is the SNR curve monotonically increasing?"

## Output parameters

- readout_amplitude: Optimal readout amplitude where SNR first exceeds the threshold (a.u.)

## Common failure patterns

- [critical] SNR never crosses threshold
  - cause: readout chain issue, poor qubit-resonator coupling, or amplitude range too narrow
  - visual: SNR stays below threshold for all amplitudes
  - next: check readout chain, increase amplitude range, verify resonator frequency
- [warning] SNR oscillates
  - cause: nonlinear resonator response or interference
  - visual: non-monotonic SNR curve with oscillations
  - next: check for resonator bifurcation, reduce maximum amplitude
- [warning] Threshold crossed at very high amplitude
  - cause: weak coupling, poor readout frequency calibration, or high noise floor
  - visual: SNR crosses threshold only near the maximum amplitude
  - next: verify readout frequency, check noise levels, recalibrate resonator

## Tips for improvement

- Default amplitude range is 0.0-0.2 with 51 points; adjust if optimal amplitude is near the edge.
- Default SNR threshold is 1.0; increase for higher fidelity requirements.
- Run after readout frequency calibration for best results.
- Compare optimal amplitudes across qubits for readout chain uniformity assessment.

## Analysis guide

1. Check the 3-panel figure (signal, noise, SNR vs amplitude).
2. Verify SNR crosses the threshold at a reasonable amplitude.
3. Check that signal increases and noise remains manageable.
4. Record the optimal amplitude for use in subsequent measurements.

## Prerequisites

- CheckResonatorSpectroscopy or CheckResonatorFrequencies

## Related context

- history(last_n=5)
