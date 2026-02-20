# CreateZX90

Calibrates ZX90 (CNOT-equivalent) two-qubit gate from cross-resonance interaction.

## What it measures

Optimal CR pulse amplitude and duration for π/2 ZX rotation.

## Physical principle

Tune CR drive parameters to achieve exactly 90° ZX rotation; combine with single-qubit corrections for CNOT.

```mermaid
gantt
    title CreateZX90 Pulse Sequence
    dateFormat x
    axisFormat " "

    section Control Drive
    CR pulse (sweep duration) :d1, 0, 120ms

    section Target Drive
    Cancel tone               :active, t1, 0, 120ms

    section Readout (Target)
    Measurement               :crit, r1, after d1, 50ms
```

## Expected result

ZX rotation angle vs CR pulse duration; target the 90° crossing point.

- result_type: oscillation
- x_axis: CR pulse duration (ns)
- y_axis: ZX rotation angle (degrees)
- good_visual: clear oscillation with well-defined 90° crossing point

![ZX90 calibration n=1](./create_zx90_expected_1.png)
![ZX90 calibration n=3](./create_zx90_expected_2.png)
![ZX90 final calibration](./create_zx90_expected_3.png)

## Evaluation criteria

ZX rotation should be precisely 90°; parasitic rotations should be compensated by echo or correction pulses.

- check_questions:
  - "Is the ZX rotation within 1° of 90°?"
  - "Are parasitic rotations (IX, IZ) compensated?"
  - "Is the gate duration practical (<500 ns)?"

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

- cr_amplitude: Amplitude of the CR pulse. (a.u.)
- cr_phase: Phase of the CR pulse. (a.u.)
- cancel_amplitude: Amplitude of the cancel pulse. (a.u.)
- cancel_phase: Phase of the cancel pulse. (a.u.)
- cancel_beta: Beta of the cancel pulse. (a.u.)
- rotary_amplitude: Amplitude of the rotary pulse. (a.u.)
- zx_rotation_rate: ZX rotation rate. (a.u.)
- zx90_gate_time: Duration of the ZX90 pulse. (ns)

## Run parameters

- shots: Number of shots (a.u.)
- interval: Time interval (ns)

## Common failure patterns

- [critical] CR pulse too long
  - cause: weak ZX rate requires long gate, decoherence limits fidelity
  - visual: 90° crossing occurs at long duration, fidelity drops
  - next: increase CR amplitude, check coupling strength
- [warning] Parasitic ZZ coupling
  - cause: static ZZ coupling not cancelled by echo sequence
  - visual: phase error accumulating during gate
  - next: implement echo CR sequence
- [warning] Amplitude nonlinearity
  - cause: ZX rate not proportional to CR drive at high amplitudes
  - visual: non-sinusoidal rotation angle vs duration
  - next: operate in linear regime, reduce CR amplitude

## Tips for improvement

- Use echo CR sequence to cancel IX and IZ terms.
- After calibration, validate with CheckZX90.
- Consider active cancellation tone on target qubit.

## Analysis guide

1. Identify the 90° ZX crossing point in the rotation vs duration data.
2. Verify the crossing is clean (smooth oscillation, good fit).
3. Check that the gate duration is practical.
4. If parasitic terms are visible, recommend echo CR.
5. Validate with CheckZX90 after calibration.

## Related context

- history(last_n=5)
- coupling(zx_rate, coupling_strength)
