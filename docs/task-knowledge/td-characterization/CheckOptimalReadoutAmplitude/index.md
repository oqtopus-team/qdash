# CheckOptimalReadoutAmplitude

Optimizes readout pulse amplitude for best state discrimination.

## What it measures

Optimal readout drive amplitude – the power level that maximizes |0⟩/|1⟩ discrimination.

## Physical principle

Sweep readout amplitude while measuring state separation; too low gives poor SNR, too high causes measurement-induced transitions (QND violation).

## Expected result

Separation/fidelity vs amplitude: rises from noise floor, peaks at optimum, may decrease at high power.

- result_type: peak_curve
- x_axis: Readout amplitude (a.u.)
- y_axis: State separation or readout fidelity
- good_visual: clear peak in fidelity vs amplitude curve with well-defined optimum

## Evaluation criteria

State separation should be high at optimal amplitude; amplitude should be in the linear regime below QND violation threshold.

- check_questions:
  - "Is there a clear optimum in the fidelity vs amplitude curve?"
  - "Is the optimal amplitude in the linear regime (not too high)?"
  - "Is the state separation >95% at the optimal point?"

## Input parameters

None.

## Output parameters

- optimal_readout_amplitude: Optimal Readout Amplitude (a.u.)

## Run parameters

- amplitude_range: Readout amplitude range (a.u.)
- shots: Number of shots for Rabi oscillation (a.u.)
- interval: Time interval for Rabi oscillation (ns)

## Common failure patterns

- [warning] Amplitude too low
  - cause: insufficient SNR for state discrimination
  - visual: IQ blobs overlap significantly, poor fidelity
  - next: increase readout amplitude or integration time
- [critical] Amplitude too high
  - cause: measurement-induced transitions, qubit heating
  - visual: fidelity decreases at high amplitudes, QND violation
  - next: reduce amplitude, check for non-QND effects
- [warning] Flat curve
  - cause: resonator off-resonance or dispersive shift too small
  - visual: fidelity does not vary significantly with amplitude
  - next: verify readout frequency and dispersive shift

## Tips for improvement

- Run after dispersive shift characterization for best results.
- If optimal amplitude is very high, check if dispersive shift is sufficient.
- Monitor both |0⟩ and |1⟩ populations at optimal point for QND verification.

## Analysis guide

1. Identify the optimal amplitude from the fidelity vs amplitude curve.
2. Verify the optimum is well-defined (clear peak, not plateau).
3. Check that the optimal amplitude is not in the nonlinear/QND-violation regime.
4. Compare the achieved fidelity with expectations from the dispersive shift.

## Related context

- history(last_n=5)
