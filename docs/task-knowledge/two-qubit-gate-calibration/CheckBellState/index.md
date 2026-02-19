# CheckBellState

Prepares Bell state (|00⟩+|11⟩)/√2 and measures state fidelity.

## What it measures

Bell state fidelity – quality of entanglement between qubit pair.

## Physical principle

Apply H⊗I then CNOT; measure in Z basis and verify equal |00⟩/|11⟩ populations with coherent superposition.

```mermaid
gantt
    title CheckBellState Pulse Sequence (echo CR = ZX90)
    dateFormat x
    axisFormat " "

    section Control
    X/2        :d1, 0, 15ms
    CR pulse   :d2, after d1, 35ms
    π          :d3, after d2, 15ms
    CR pulse   :d4, after d3, 35ms
    Readout    :crit, r1, after d4, 40ms

    section Target
    idle       :done, t0, 0, 15ms
    Cancel     :active, t1, after t0, 35ms
    idle       :done, t2, after t1, 15ms
    Cancel     :active, t3, after t2, 35ms
    Readout    :crit, r2, after t3, 40ms
```

## Expected result

Population histogram showing ~50/50 |00⟩/|11⟩ with minimal |01⟩/|10⟩.

- result_type: histogram
- x_axis: Computational basis states (|00⟩, |01⟩, |10⟩, |11⟩)
- y_axis: Population probability
- good_visual: two tall bars at |00⟩ and |11⟩ (~0.5 each), negligible |01⟩ and |10⟩ bars

![Bell state measurement](./check_bell_state_expected.png)

## Evaluation criteria

Bell state fidelity should be high; |01⟩ and |10⟩ populations should be minimal. This is an end-to-end test of single and two-qubit gates.

- check_questions:
  - "Are the |00⟩ and |11⟩ populations approximately equal (~0.5)?"
  - "Are the |01⟩ and |10⟩ populations negligible (<5%)?"
  - "Is the Bell state fidelity meeting the target?"

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

None.

## Run parameters

- shots: Number of shots (a.u.)
- interval: Time interval (ns)

## Common failure patterns

- [critical] Low fidelity from single-qubit gate errors
  - cause: H gate or measurement basis errors
  - visual: unequal |00⟩/|11⟩ populations or significant |01⟩/|10⟩
  - next: debug single-qubit gates first (CheckHPIPulse, CheckPIPulse)
- [warning] Residual |01⟩/|10⟩ population
  - cause: ZX90 miscalibration, gate angle error
  - visual: non-negligible bars at |01⟩ and |10⟩
  - next: recalibrate ZX90 gate (CreateZX90)
- [warning] Decoherence during circuit
  - cause: T1/T2 too short for the circuit depth
  - visual: overall contrast reduction, all populations mixed
  - next: check coherence times, optimize circuit
- [warning] Readout crosstalk
  - cause: correlated measurement errors between qubits
  - visual: unexpected correlations in error pattern
  - next: check readout isolation between qubits

## Tips for improvement

- This is an end-to-end test combining single and two-qubit gates.
- Low fidelity here means debug gates individually first.
- Compare with Bell state tomography for full density matrix.

## Analysis guide

1. Check the population histogram for |00⟩/|11⟩ balance.
2. Quantify the |01⟩/|10⟩ leakage as fraction of total.
3. Compare Bell fidelity with individual gate fidelities.
4. If fidelity is low, determine if limited by single-qubit, two-qubit, or readout errors.
5. Recommend component-level debugging if needed.

## Prerequisites

- CheckZX90
- CheckHPIPulse
- CheckPIPulse

## Related context

- history(last_n=5)
- coupling(zx_rate, coupling_strength)
