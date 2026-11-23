# Cross-Resonance Tasks

`CheckCrossResonance` measures CR parameters; `CreateZX90` fits the amplitude for a ZX90 gate.
Qubex measures and fits; QDash validates settings and accepted outputs.

## Run parameters

Set these in a `TaskCall.run` entry:

| Parameter | Constraint |
| --- | --- |
| `ramptime` | Finite and positive |
| `adiabatic_safe_factor`, `max_amplitude` | In `(0, 1]` |
| `duration` (ZX90) | Positive and at least twice the ramp time |
| `amplitude_range` (ZX90) | Increasing, within the cap, at least four points |
| `rotary_multiple` (ZX90) | Positive |
| `duration_buffer` (ZX90) | At least 1 |

An input CR duration of zero lets Qubex derive it; a nonzero duration must cover both ramps.
Stored ramp time must match the requested value. No ramp time is universally safe for all pairs.

## Amplitude caps

The cap combines `max_amplitude` with Qubex's adiabatic bound. CheckCrossResonance publishes the
bounds it used; CreateZX90 inherits them or uses legacy defaults of 0.75 and 1.0.
A run may tighten inherited bounds but cannot loosen them. To change the accepted bound,
rerun characterization or explicitly override its input.

## CR duration

With no explicit duration/range, Qubex can lengthen duration once when its rough scan finds no
root. An explicit duration stays fixed and a missing root fails. An explicit amplitude range
skips the rough scan and its retry. Compare published duration with input when using defaults.

## Accepting a result

CreateZX90 requires a real fitted root matching the stored amplitude, inside the scanned range
and cap. Requested duration and ramp time must match. Amplitude 1.0 alone is not proof of a root;
Qubex also uses that value when fitting fails. CheckCrossResonance requires finite outputs.

Rejected fits retain figures and restore the CR note entry captured immediately before the
Qubex call. They do not undo inputs synchronized earlier by preprocessing. Only accepted results
save the note file.

## Fresh results

Both tasks require a newer note timestamp after the Qubex call, preventing an old entry from
masquerading as a result. Qubex timestamps have one-second resolution, so this proves a write
in the run, not that the last tomography iteration replaced an earlier same-second iteration.

## Measurement-only runs

`update_calibration_parameters=False` blocks QDash database publication, but accepted CR results
still update and save the Qubex note. It does not make these tasks non-destructive.

## Testing

`tests/qdash/workflow/calibtasks/qubex/test_cr_zx90_controls.py` covers bounds, rejected-fit
restoration, and freshness with real calibration-note behavior and mocked measurements.
It does not establish hardware fidelity or safe pulse choices.

## Implementation files

Under `src/qdash/workflow/calibtasks/qubex/two_qubit/`:
`cr_controls.py`, `check_cross_resonance.py`, and `create_zx90.py`.
