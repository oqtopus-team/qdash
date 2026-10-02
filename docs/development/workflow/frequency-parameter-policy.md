# Frequency Parameter Policy

QDash frequency parameters distinguish measured device properties from operational drive settings.
Input resolution and snapshot semantics follow [Parameter Resolution](./parameter-resolution.md).

## Parameter roles

| Parameter | Meaning | Independent persistent QDash parameter |
| --- | --- | --- |
| `coarse_qubit_frequency` | Exploration estimate used to start or repeat qubit calibration | Yes |
| `qubit_frequency` | Measured qubit frequency obtained from Chevron or Ramsey | Yes |
| `control_frequency` | Control drive frequency used by ordinary experiments | Yes |
| `resonator_frequency` | Resonator frequency estimated by an experiment | Yes |
| `readout_frequency` | Readout drive frequency used by ordinary experiments | Yes |

The persistent values are the accepted results used by subsequent tasks. Task history retains measurements regardless of whether they are accepted. A newer history record does not necessarily replace a persistent value.

`coarse_qubit_frequency` is an exploration input, not simply a less precise alias for `qubit_frequency`. Keeping the values separate allows spectroscopy to be repeated without replacing a working calibration. They may differ normally. Chevron and Ramsey do not copy their results back into the exploration parameter.

`qubit_frequency` and `resonator_frequency` are physical measurement results. They are never
treated as sweep knobs. `control_frequency` and `readout_frequency` are operational values and may
be changed independently. A calibration can publish one measured result to both roles when that
result should immediately become the operating value.

## Task update targets

Task update targets are fixed and have the same meaning in standalone runs and workflows. Publication requires both enabled output persistence and successful validation.

| Experiment | Frequency output to publish | Effect |
| --- | --- | --- |
| Qubit Spectroscopy, including 2D and 1D frequency estimation | `coarse_qubit_frequency` | Update the exploration estimate |
| CheckControlAmplitude, when its frequency fit succeeds | `coarse_qubit_frequency` | Refine the exploration estimate |
| Chevron | `qubit_frequency`, `control_frequency` | Record the measurement and use it as the control drive |
| Ramsey | `qubit_frequency`, `control_frequency` | Record the measurement and use it as the control drive |
| Resonator Spectroscopy | `resonator_frequency`, `readout_frequency` | Record the measurement and use it as the initial readout drive |
| CKP, for its resonator-frequency estimate | `resonator_frequency` | Update the measured resonator frequency |
| Optimal Readout Frequency | `readout_frequency` | Update only the operational readout drive |

The spectroscopy rows describe measurement methods, not a requirement to introduce a task class for each method. The CKP mapping assumes that the relevant output estimates the resonator frequency; its concrete task and output contract require verification before implementation.

`CheckCoarseReadoutParams` selects `readout_frequency` by maximizing the Rabi IQ response range
across readout frequencies and amplitudes. This updates the operating value without replacing
`resonator_frequency`.

Update targets are specified per output, not by classifying the entire task as exploration or calibration. Amplitude and other outputs retain their own declared destinations. In particular, Resonator Spectroscopy also produces `readout_amplitude`; maintaining the readout frequency does not imply that every readout setting remains unchanged.

### Replacement within the same parameter

There is no automatic ranking of task names or calibration stages. With publication enabled, a validated Chevron result can replace a Ramsey result in `qubit_frequency`. Likewise, a validated Resonator Spectroscopy result can replace a CKP result in `resonator_frequency` when that mapping is confirmed.

The execution UI explains the current source and the replacement before the run. Operators can choose measurement-only execution. This policy protects calibrated qubit frequencies from exploration updates; it does not guarantee that every accepted recalibration improves precision or device performance.

## Runtime frequency resolution

Ordinary experiments declare the operational names and explicitly list the measured names as
fallbacks:

```python
input_spec = {
    "control_frequency": InputParameterSpec.required_database(
        fallback_parameter_names=("qubit_frequency",),
    ),
    "readout_frequency": InputParameterSpec.required_database(
        fallback_parameter_names=("resonator_frequency",),
    ),
}
```

Resolution prefers `control_frequency` or `readout_frequency`. It uses the corresponding measured
frequency only when the operational parameter is absent. `fallback_parameter_names` expresses
semantic fallback; `parameter_aliases` remains reserved for legacy names that mean the same thing.
The resolved input records the database parameter name that supplied the value, so provenance and
snapshot re-execution retain the distinction.

Do not automatically copy or fall back from `coarse_qubit_frequency` into `qubit_frequency` or the default control drive frequency. Exploration and Chevron tasks explicitly consume the exploration value where required. Experiments investigating the resonator explicitly consume `resonator_frequency` for their measurement needs; this is separate from resolving a default readout drive frequency.

Permitted per-execution overrides remain explicit inputs. An arbitrary drive override does not
become a measured qubit or resonator frequency. Record the actual resolved drive frequencies,
their sources, and overrides in execution history.

Snapshot re-execution uses the recorded effective inputs and permitted overrides, not current database values or current YAML defaults. Preserve enough source information in the snapshot to reproduce the frequency selection.

## Bringup and repeated measurements

Bringup uses the normal task destinations rather than a separate calibration-stage reset or an all-workflow publication checkpoint:

1. Qubit Spectroscopy updates `coarse_qubit_frequency` after validation.
2. CheckControlAmplitude consumes and refines the exploration parameters.
3. Chevron consumes the exploration parameters and publishes `qubit_frequency` after validation.
4. Subsequent calibration tasks consume the updated calibrated values.

Validated outputs are published as the workflow progresses when persistence is enabled. A failure in a later task does not roll back earlier accepted outputs. Report the outputs already updated and the tasks that did not complete. Failed outputs must not become the normal inputs of downstream tasks.

An initial bringup can reach Chevron without an existing `qubit_frequency`, using its explicit exploration inputs. Repeating only Qubit Spectroscopy on a calibrated device updates the exploration value while retaining the calibrated value. Repeating bringup can replace the calibrated value when Chevron succeeds; the start screen identifies bringup as a recalibration operation.

### Readout transitions

| Operation with publication enabled and validation passed | `resonator_frequency` | `readout_frequency` |
| --- | --- | --- |
| Resonator Spectroscopy | Update | Update to the measured resonance |
| Readout frequency optimization | Retain | Update to the optimized drive |

Repeating Resonator Spectroscopy intentionally restores the measured resonance as the operational
readout starting point. Run readout optimization afterward when the optimal drive should differ.

Frequency selection alone does not establish that an old optimization remains suitable after other readout settings change. Show other updated outputs, such as readout amplitude, alongside the frequency behavior. Do not claim that all readout settings are preserved when only the frequency is retained.

### Coarse readout scan settings

`CheckCoarseReadoutParams` declares the calibration inputs used by both the readout scan and its underlying Rabi measurements:

| Input parameter | Purpose | Resolution |
| --- | --- | --- |
| `control_frequency` | Qubit drive frequency for the Rabi measurements | Required operational value; falls back to `qubit_frequency` |
| `control_amplitude` | Control pulse amplitude for the Rabi measurements | Required database value |
| `readout_frequency` | Center frequency of the readout scan | Required operational value; falls back to `resonator_frequency` |
| `readout_amplitude` | Reference amplitude of the readout scan | Required database value |

All four calibration inputs are recorded for snapshot re-execution. Explicit input overrides define the values for that run; the scan does not independently reload them from Qubex YAML. Drive frequency and amplitude overrides are scoped to the scan and restored on success or failure. The session-scoped `readout_duration` is recorded as a Run parameter. The Qubex contrib helper has no readout-duration argument, so a task-local adapter forwards that value to each underlying Rabi call without replacing methods on the shared Experiment instance.

| Run parameter | Default | Meaning |
| --- | --- | --- |
| `readout_duration` | Qubex session value | Readout pulse duration in ns for all underlying Rabi measurements |
| `detuning_range` | `(-0.015, 0.015, 13)` | Frequency offsets in GHz, as `(start, stop, number of points)` |
| `readout_amplitude_ratio_range` | `(0.8, 1.2, 5)` | Multipliers of the reference amplitude, as `(start, stop, number of points)` |
| `time_range` | `(0, 101, 4)` | Rabi drive durations in ns, as `(start, exclusive stop, step)` |
| `shots` | `1024` | Shots per Rabi drive duration at each readout point |
| `interval` | Existing Qubex default | Shot interval in ns |

The default scan includes the current frequency and amplitude: 13 frequency points over ±15 MHz and 5 amplitude points over ±20%. Amplitudes are capped at 1 and duplicate points are removed, so a reference near the upper bound can produce fewer than 5 amplitude points. The reference amplitude must be finite and within `(0, 1]`; invalid references fail rather than being replaced or clipped.

Normally this performs 65 Rabi traces, compared with the previous 147-point grid using ±25 MHz and amplitudes from zero to the configured value. The shot count is halved from 2048 to 1024, while the default Rabi time window and shot interval are retained. These are adjustable starting settings, not a claim of equivalent measurement quality. Operators can widen the scan, change the Rabi time window, or restore 2048 shots using run parameters.

The progress plan uses the effective frequency count multiplied by the effective amplitude count, after clipping and duplicate removal. The UI shows all-sweep progress from the first Rabi trace: normally 65 sweeps, or 39 with a reference amplitude of 1 and the default ranges. The displayed count is completed sweeps out of the total; the percentage also includes progress within the active sweep. After the first sweep completes, the remaining-time estimate extrapolates the total elapsed measurement time across the planned sweeps. It includes time between sweeps and remains an estimate, since measurement speed can vary. The UI hides the inner Rabi time-point count and per-sweep ETA for this search.

Older snapshots without the newly declared reference inputs cannot silently use current settings; handle missing snapshot inputs according to [Parameter Resolution](./parameter-resolution.md#effective-input-validation).

### Coarse readout R² validation

`CheckCoarseReadoutParams` validates the Rabi fit at the selected readout frequency and amplitude before accepting either output. In the installed Qubex revision pinned by `uv.lock`, `rabi_results` contains the scan results in amplitude-major order; each result exposes `rabi_params[qubit_label].r2`. Use this stored R² without refitting or averaging the scan.

The default threshold is shared with QDash's `CheckRabi`: `0.6`. As with the existing task executor, a value must be strictly greater than the threshold to pass. Missing, non-finite, or greater-than-one R² values also fail validation. Selection metadata that cannot identify the matching scan point is a validation failure, not permission to skip the check.

Do not require every scan point to pass: exploration can include low readout amplitudes and other settings with poor responses. Conversely, a good fit at an unrelated point must not authorize publishing a noisy selected point. Do not silently choose a different candidate when the selected point fails.

Preserve the heatmap and available raw scan data for inspection, mark the task failed, and publish neither frequency nor amplitude on rejection. The selected R² is recorded as task quality metadata when finite. This gate is implemented in the task; it does not establish that the response maximum is the fidelity optimum or guarantee rejection of every possible noise realization.

## YAML export

YAML files represent accepted parameter values and the default drive configuration derived from them. They do not export every new measurement automatically.

| YAML file | Exported value |
| --- | --- |
| `qubit_frequency.yaml` | Accepted measured qubit frequency |
| `control_frequency.yaml` | Accepted operational control frequency |
| `resonator_frequency.yaml` | Accepted measured resonator frequency |
| `readout_frequency.yaml` | Accepted operational readout frequency |

On accepted Chevron or Ramsey updates, update both `qubit_frequency.yaml` and
`control_frequency.yaml`. On accepted Resonator Spectroscopy updates, update both
`resonator_frequency.yaml` and `readout_frequency.yaml`. Readout optimization updates only
`readout_frequency.yaml`.

Seed import is deliberately narrower: only operational frequency and amplitude files may update
the calibration database. It cannot import `qubit_frequency.yaml` or
`resonator_frequency.yaml`; experiments own those measured values.

## Execution UX

### Execution intent

Expose the execution purpose and update destinations in user-facing language rather than relying on an ambiguous “Update params” switch.

| Action | Input baseline | Default publication behavior |
| --- | --- | --- |
| Measure only | Current calibration state, plus permitted overrides | History only |
| Calibrate and apply | Current calibration state, plus permitted overrides | Publish validated outputs to declared destinations |
| Repeat with the same conditions | Recorded snapshot, plus permitted overrides | History only |
| Bringup | Current calibration state and outputs from preceding steps | Publish validated outputs as tasks complete |

Keep measurement-only execution as the initial selection for Tasks quick runs. A new run using current settings and a snapshot re-execution must be distinguishable in navigation and labels. Publication is separate from input selection and from bypassing validation.

### Before execution

Show the update destinations and their current source task near the execution action. For spectroscopy that publishes exploration results, use explanatory text such as:

> Updates the exploration frequency (`coarse_qubit_frequency`). The calibrated qubit frequency is retained; its current source is Chevron.

For Chevron replacing a Ramsey calibration:

> Updates `qubit_frequency`. The current value comes from Ramsey. A validated result will replace it with this Chevron measurement.

For Resonator Spectroscopy after readout optimization:

> Updates `resonator_frequency` and resets `readout_frequency` to this measured resonance. Run readout optimization afterward to select a different operating frequency.

List other updated outputs separately. Generate the source descriptions from the selected target's actual calibration metadata. Measurement-only runs must instead state that results are recorded without applying parameter updates. Keep the measurement-only choice near the action; routine execution does not require another confirmation dialog.

### After execution

Display execution outcome and publication outcome separately. For each output, show the measured value, whether it was applied, the previous accepted value where applicable, and the reason when it was not applied. Show the retained operating frequency and its source when an exploration result was updated.

Use explicit outcomes such as “Applied,” “History only,” and “Not applied: validation failed.” A successful measurement alone does not mean the calibration database or YAML was updated. YAML synchronization failures must remain distinguishable from measurement failures.

Existing historical `readout_frequency` records may originate from spectroscopy or optimization.
Preserve their original provenance rather than retroactively treating them as
`resonator_frequency` measurements.
