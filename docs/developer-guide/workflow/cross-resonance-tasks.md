# Cross-Resonance Tasks

`CheckCrossResonance` and `CreateZX90` calibrate the cross-resonance (CR) pulse of one coupling
and the ZX90 gate built from it. Both are ordinary `QubexTask` subclasses: QDash validates their
run parameters before any acquisition and decides whether to accept the Qubex result, and Qubex
performs the measurements and fits. Input precedence and snapshots follow
[Parameter Resolution](./parameter-resolution.md).

`CheckCrossResonance` runs Qubex `obtain_cr_params`: CR Hamiltonian tomography that fixes the CR
and cancel phases, the cancel amplitude and the ZX rotation rate. `CreateZX90` runs Qubex
`calibrate_zx90`: it scans the CR amplitude at one CR duration and takes the root of a
degree-3 polynomial fit as the ZX90 amplitude.

## Run parameters

A workflow sets these through each `TaskCall`'s `run` entry, as described in
[Task Calls](./task-calls.md#settings).

| Parameter | Task | Accepted values | When unset |
| --- | --- | --- | --- |
| `ramptime` | Both | Finite, > 0 ns | `CheckCrossResonance`: Qubex default, 16 ns or 32 ns when the control f_ge is at or above the target f_ef. `CreateZX90`: input `cr_ramptime` |
| `adiabatic_safe_factor` | Both | (0, 1] | `CheckCrossResonance`: 0.75. `CreateZX90`: see [Amplitude caps](#amplitude-caps) |
| `max_amplitude` | Both | (0, 1] | `CheckCrossResonance`: 1.0. `CreateZX90`: see [Amplitude caps](#amplitude-caps) |
| `duration` | `CreateZX90` | Finite, > 0 ns, at least `2 * ramptime` | Input `cr_duration`, with the Qubex retry |
| `amplitude_range` | `CreateZX90` | `(start, stop, num)` with `0 <= start < stop <= cap` and `num >= 4` | Scan derived from the input `cr_amplitude` |
| `rotary_multiple` | `CreateZX90` | > 0 | Qubex default, 9 |
| `duration_buffer` | `CreateZX90` | >= 1 | Qubex default, 1.05 |

`CreateZX90` also requires a nonzero input `cr_duration` to be at least `2 * ramptime`; an input
of 0 lets Qubex derive the duration. Both tasks fail when the ramp time Qubex stored differs
from the requested one. A ramp time is a pulse-shape choice; no value is safe for every pair.

```python
from qdash.workflow import TaskCall, sweep

tasks = [
    TaskCall(
        name="CheckCrossResonance",
        run={"ramptime": 24.0, "max_amplitude": 0.6},
    ),
    TaskCall(
        name="CreateZX90",
        run={"duration": 208.0, "amplitude_range": sweep.linspace(0.2, 0.5, 50)},
    ),
]
```

## Amplitude caps

The CR amplitude cap is `min(max_amplitude, amplitude(adiabatic_safe_factor * |f_control -
f_target|))`, the clip Qubex applies to its scans. `CheckCrossResonance` publishes the bounds it
used on the coupling as `cr_max_amplitude` and `cr_adiabatic_safe_factor`. `CreateZX90` reads them
as optional inputs:

| `CreateZX90` run value | Inherited value present | Result |
| --- | --- | --- |
| Unset | Yes | The inherited value |
| Unset | No (pair characterized before the bounds were published) | Default: 0.75 or 1.0 |
| Equal or tighter | Yes | The run value |
| Looser | Yes | Rejected before acquisition |

To approve a looser bound, rerun `CheckCrossResonance` with it, or override the input
`cr_max_amplitude` or `cr_adiabatic_safe_factor` in the task's `input` entry.

## CR duration

`CreateZX90` scans in one of three modes:

| Run parameters | Rough scan | Final scan | Duration |
| --- | --- | --- | --- |
| Neither `duration` nor `amplitude_range` | Qubex: 20 points from 0 to twice the input `cr_amplitude` | Qubex: 50 points from 0.8 to 1.2 times the rough root | Input `cr_duration`, or derived by Qubex when it is 0. When the rough scan finds no root, Qubex lengthens the duration once and retries |
| `duration` | QDash, at that duration: 20 points from 0 to `min(2 * cr_amplitude, cap)`, without storing | 50 points from 0.8 times the rough root to `min(1.2 * root, cap)` | Fixed. No rough root fails the task |
| `amplitude_range` | Skipped | The given range | Run `duration` if set, else as in the first row but without the retry |

With `duration`, QDash runs the rough scan itself because Qubex `calibrate_zx90` lengthens the
duration whenever its own rough scan finds no root, even when a duration is given. The task
result does not record whether Qubex retried in the first mode; compare the published
`cr_duration` with the input.

## Accepting a result

Qubex stores amplitude 1.0 when the final ZX90 fit has no root, so a value of 1.0 cannot be told
apart from a real root by value. `CreateZX90` judges the fit root that Qubex returns with the
result instead, and rejects the result when:

- the final fit has no root;
- the stored `cr_amplitude` is not the fitted root;
- the root lies outside the scanned range or above the cap;
- the stored duration differs from a requested `duration`, or the stored ramp time differs from
  the requested one.

A root of exactly 1.0 that passes these checks is accepted. `CheckCrossResonance` rejects a result
whose outputs are not finite.

A rejected result fails the task with a validation error; its figures stay with the task result.
The task puts the pair's Qubex CR note entry back to the entry it read just before the Qubex
call, timestamp included, and does not save the note file. The same happens when the Qubex call
or the checks raise. Only an accepted result is saved with `save_calibration`. This keeps the
task's own rejected fit out of the Qubex note; it does not undo the CR inputs that `QubexTask`
synchronized into the note before the run, and it covers only failures inside the task's `run`
and `postprocess`.

## Fresh results

Qubex merges an update into a note entry only when the update's timestamp is strictly newer, at
one-second resolution, and otherwise drops it without an error. Reading the entry back would
then return the old values as if they were the run's result. Both tasks therefore fail with
`Qubex did not store fresh CR parameters` when the entry after the Qubex call is not newer than
the entry before it, for example when the previous entry is future-dated.

`CheckCrossResonance` stores every tomography iteration in the same entry. The check proves that
the entry was written during this run, not that it holds the last iteration: two iterations in
the same second keep the earlier one.

## Deferred: evaluation runs

A run that measures a candidate without changing the Qubex calibration note is not supported.
`update_calibration_parameters: false` stops QDash from writing the outputs to the calibration
database, but an accepted result still stays in the Qubex note and is saved to the note file.
Non-destructive evaluation is planned as separate work.

## Testing

`tests/qdash/workflow/calibtasks/qubex/test_cr_zx90_controls.py` mocks the Qubex calls but uses
the real Qubex `CalibrationNote`, so putting a rejected fit back and the freshness check run
against its timestamp merge. Mocked tests do not show how a ramp time or cap affects gate
fidelity on hardware.

## Implementation files

- `src/qdash/workflow/calibtasks/qubex/two_qubit/cr_controls.py`: validation and note helpers
- `src/qdash/workflow/calibtasks/qubex/two_qubit/check_cross_resonance.py`
- `src/qdash/workflow/calibtasks/qubex/two_qubit/create_zx90.py`
