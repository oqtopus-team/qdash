# CheckBellStateTomography

Full density matrix tomography of the Bell state for detailed characterization.

## What it measures

Complete density matrix of prepared Bell state; concurrence and entanglement metrics.

## Physical principle

Prepare Bell state, measure in 9 Pauli basis combinations (XX, XY, ..., ZZ), reconstruct density matrix via maximum likelihood.

## Expected result

Density matrix close to ideal Bell state |Φ+⟩; off-diagonal elements indicating coherence.

- result_type: 2d_map
- x_axis: Density matrix row index
- y_axis: Density matrix column index
- z_axis: Matrix element amplitude
- good_visual: density matrix with large real diagonal and off-diagonal elements matching ideal Bell state pattern

![Bell state tomography](./0.png)

## Evaluation criteria

State fidelity and concurrence should be high; density matrix should be close to ideal Bell state with strong off-diagonal coherence.

- check_questions:
  - "Is the state fidelity >90%?"
  - "Is the concurrence >0.9?"
  - "Are the off-diagonal elements consistent with coherent entanglement?"

## Input parameters

- control_qubit_frequency: (control qubit) (GHz)
- control_drag_hpi_amplitude: (control qubit) (a.u.)
- control_drag_hpi_length: (control qubit) (ns)
- control_drag_hpi_beta: (control qubit) (a.u.)
- control_readout_frequency: (control qubit) (GHz)
- control_readout_amplitude: (control qubit) (a.u.)
- control_readout_length: (control qubit) (ns)
- target_qubit_frequency: (target qubit) (GHz)
- target_readout_frequency: (target qubit) (GHz)
- target_readout_amplitude: (target qubit) (a.u.)
- target_readout_length: (target qubit) (ns)
- cr_amplitude: (control qubit) (a.u.)
- cr_phase: (control qubit) (a.u.)
- cancel_amplitude: (target qubit) (a.u.)
- cancel_phase: (target qubit) (a.u.)
- cancel_beta: (target qubit) (a.u.)
- rotary_amplitude: (control qubit) (a.u.)
- zx_rotation_rate: (coupling qubit) (a.u.)

## Output parameters

- bell_state_fidelity: Bell state fidelity (a.u.)

## Run parameters

- shots: Number of shots (a.u.)
- interval: Time interval (ns)

## Common failure patterns

- [warning] Systematic tomography errors
  - cause: measurement basis miscalibration (X90, Y90 pulses)
  - visual: density matrix has unphysical features or asymmetries
  - next: verify measurement rotation calibration
- [warning] Decoherence
  - cause: T1/T2 reduce off-diagonal coherence elements
  - visual: reduced off-diagonal elements, mixed state
  - next: check coherence times, optimize circuit depth
- [warning] State preparation errors
  - cause: gate errors dominate reconstruction
  - visual: density matrix deviates from ideal Bell state pattern
  - next: check individual gate fidelities

## Tips for improvement

- Requires well-calibrated measurement rotations (X90, Y90).
- Use maximum likelihood reconstruction to ensure physical state.
- Compare diagonal elements with simple Bell state measurement for consistency.

## Analysis guide

1. Check the state fidelity and concurrence values.
2. Examine the density matrix for expected Bell state structure.
3. Compare with the simple CheckBellState Z-basis measurement.
4. If fidelity is lower than expected, identify which matrix elements deviate most.
5. Use deviations to diagnose specific error channels.

## Prerequisites

- CheckBellState
- CheckHPIPulse
- CheckZX90

## Related context

- history(last_n=5)
- coupling(zx_rate, coupling_strength)
