# CheckOptimalReadoutAmplitude

Optimizes readout pulse amplitude for best state discrimination.

## What it measures

Optimal readout drive amplitude – the power level that maximizes |0⟩/|1⟩ discrimination.

## Physical principle

Sweep readout amplitude while measuring state separation; too low gives poor SNR, too high causes measurement-induced transitions (QND violation).

## Expected curve

Separation/fidelity vs amplitude: rises from noise floor, peaks at optimum, may decrease at high power.

## Evaluation criteria

State separation >95% at optimal amplitude; amplitude in linear regime.

## Common failure patterns

- Amplitude too low – poor SNR, IQ blobs overlap.
- Amplitude too high – measurement-induced transitions, qubit heating.
- Flat curve – resonator off-resonance or dispersive shift too small.

## Tips for improvement

- Run after dispersive shift characterization for best results.
- If optimal amplitude is very high, check if dispersive shift is sufficient.
- Monitor both |0⟩ and |1⟩ populations at optimal point for QND verification.
