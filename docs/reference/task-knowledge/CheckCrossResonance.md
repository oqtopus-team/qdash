# CheckCrossResonance

Measures cross-resonance (CR) interaction strength between coupled qubits.

## What it measures

ZX interaction rate and CR Hamiltonian terms for two-qubit gate calibration.

## Physical principle

Drive control qubit at target frequency; monitor target rotation rate. ZX coupling enables CNOT-type gates.

## Expected curve

Target qubit oscillation proportional to CR drive amplitude; Hamiltonian tomography shows dominant ZX term.

## Evaluation criteria

Clear ZX oscillation; IX/IY/IZ parasitic terms small relative to ZX.

## Common failure patterns

- Weak ZX rate – large detuning or insufficient coupling.
- Large IX term – direct drive leakage to target.
- Classical crosstalk – signal leakage through control lines.
- Frequency collision – spectator qubit interference.

## Tips for improvement

- Ensure single-qubit gates are well-calibrated before CR characterization.
- Check for active cancellation (echo CR) if IX term is large.
- Monitor spectator qubits for correlated errors.

## Related context

- history(last_n=5)
- coupling(zx_rate, coupling_strength)
