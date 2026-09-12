# Frequency Parameter Policy

QDash frequency parameters distinguish exploration results, calibrated frequencies, and the drive frequencies used for an execution.

This is the agreed design policy for parameter updates, Qubex YAML export, and execution UX. It is not a description of fully implemented behavior; the implementation gaps are recorded below. Input resolution and snapshot semantics follow [Parameter Resolution](./parameter-resolution.md).

## Parameter roles

| Parameter | Meaning | Independent persistent QDash parameter |
| --- | --- | --- |
| `coarse_qubit_frequency` | Exploration estimate used to start or repeat qubit calibration | Yes |
| `qubit_frequency` | Calibrated qubit frequency obtained from Chevron or Ramsey | Yes |
| `control_frequency` | Default control drive frequency resolved from `qubit_frequency` | No |
| `resonator_frequency` | Resonator frequency estimated by an experiment | Yes |
| `optimal_readout_frequency` | Frequency selected by readout optimization | Yes |
| `readout_frequency` | Default readout drive frequency resolved from the readout parameters | No |

The persistent values are the accepted results used by subsequent tasks. Task history retains measurements regardless of whether they are accepted. A newer history record does not necessarily replace a persistent value.

`coarse_qubit_frequency` is an exploration input, not simply a less precise alias for `qubit_frequency`. Keeping the values separate allows spectroscopy to be repeated without replacing a working calibration. They may differ normally. Chevron and Ramsey do not copy their results back into the exploration parameter.

`resonator_frequency` and `optimal_readout_frequency` describe different measurement objectives. Readout optimization does not replace the measured resonator frequency.

## Task update targets

Task update targets are fixed and have the same meaning in standalone runs and workflows. Publication requires both enabled output persistence and successful validation.

| Experiment | Frequency output to publish | Effect |
| --- | --- | --- |
| Qubit Spectroscopy, including 2D and 1D frequency estimation | `coarse_qubit_frequency` | Update the exploration estimate |
| CheckControlAmplitude, when its frequency fit succeeds | `coarse_qubit_frequency` | Refine the exploration estimate |
| Chevron | `qubit_frequency` | Update the calibrated qubit frequency |
| Ramsey | `qubit_frequency` | Update the calibrated qubit frequency |
| Resonator Spectroscopy | `resonator_frequency` | Update the measured resonator frequency |
| CKP, for its resonator-frequency estimate | `resonator_frequency` | Update the measured resonator frequency |
| Optimal Readout Frequency | `optimal_readout_frequency` | Update the readout optimization result |

The spectroscopy rows describe measurement methods, not a requirement to introduce a task class for each method. The CKP mapping assumes that the relevant output estimates the resonator frequency; its concrete task and output contract require verification before implementation.

`CheckCoarseReadoutParams` extracts a result named `optimal_readout_frequency`, selected by maximizing the Rabi IQ response range across readout frequencies and amplitudes. This objective is different from directly optimizing readout fidelity. If this output is treated as readout optimization, its destination is `optimal_readout_frequency`, and the UI must disclose replacement of a value from another optimization task. Confirm that this shared destination is appropriate before changing its output name.

Update targets are specified per output, not by classifying the entire task as exploration or calibration. Amplitude and other outputs retain their own declared destinations. In particular, Resonator Spectroscopy also produces `readout_amplitude`; maintaining the readout frequency does not imply that every readout setting remains unchanged.

### Replacement within the same parameter

There is no automatic ranking of task names or calibration stages. With publication enabled, a validated Chevron result can replace a Ramsey result in `qubit_frequency`. Likewise, a validated Resonator Spectroscopy result can replace a CKP result in `resonator_frequency` when that mapping is confirmed.

The execution UI explains the current source and the replacement before the run. Operators can choose measurement-only execution. This policy protects calibrated qubit frequencies from exploration updates; it does not guarantee that every accepted recalibration improves precision or device performance.

## Runtime frequency resolution

For an ordinary execution without explicit overrides, resolve the default drive frequencies as follows:

```text
control_frequency = qubit_frequency

readout_frequency = optimal_readout_frequency, if set
                    otherwise resonator_frequency
```

“Set” means a usable, accepted value, not truthiness of a number. Invalid values fail validation rather than silently selecting a fallback. If a required frequency cannot be resolved, fail with the missing parameter identified.

Do not automatically copy or fall back from `coarse_qubit_frequency` into `qubit_frequency` or the default control drive frequency. Exploration and Chevron tasks explicitly consume the exploration value where required. Experiments investigating the resonator explicitly consume `resonator_frequency` for their measurement needs; this is separate from resolving a default readout drive frequency.

Permitted per-execution overrides remain explicit inputs. An arbitrary drive override does not become a measured qubit or resonator frequency. Record the actual resolved drive frequencies, their sources, and overrides in execution history even though the drive frequencies are not independent persistent calibration parameters.

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

| Operation with publication enabled and validation passed | `resonator_frequency` | `optimal_readout_frequency` | Resolved `readout_frequency` |
| --- | --- | --- | --- |
| First Resonator Spectroscopy | Update | Unset | New resonator frequency |
| Readout frequency optimization | Retain | Update | New optimized frequency |
| Repeat Resonator Spectroscopy after optimization | Update | Retain | Retained optimized frequency |
| Explicitly clear the accepted optimization value | Retain | Unset | Current resonator frequency |

Remeasuring the resonator does not automatically erase readout optimization. Changes to cooldown or readout conditions can require optimization to be repeated. Provide an explicit action to clear the accepted optimization value and use the resonator frequency again. Retain the old measurement in history and record the clearing action.

Frequency selection alone does not establish that an old optimization remains suitable after other readout settings change. Show other updated outputs, such as readout amplitude, alongside the frequency behavior. Do not claim that all readout settings are preserved when only the frequency is retained.

### Coarse readout scan settings

`CheckCoarseReadoutParams` declares the calibration inputs used by both the readout scan and its underlying Rabi measurements:

| Input parameter | Purpose | Resolution |
| --- | --- | --- |
| `qubit_frequency` | Qubit drive frequency for the Rabi measurements | Required database value |
| `control_amplitude` | Control pulse amplitude for the Rabi measurements | Required database value |
| `readout_frequency` | Center frequency of the readout scan | Required database value |
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
| `coarse_qubit_frequency.yaml` | Accepted exploration qubit frequency |
| `qubit_frequency.yaml` | Accepted calibrated qubit frequency |
| `control_frequency.yaml` | Accepted `qubit_frequency` |
| `resonator_frequency.yaml` | Accepted measured resonator frequency |
| `optimal_readout_frequency.yaml` | Accepted readout optimization result, when set |
| `readout_frequency.yaml` | Result of the runtime readout selection rule |

`coarse_qubit_frequency.yaml` and `optimal_readout_frequency.yaml` preserve and share their respective values even if Qubex does not consume them directly. Verify compatibility with the deployed Qubex parameter loader before placing additional files in its parameter directory.

On accepted exploration updates, update only the exploration frequency file among the qubit frequency files. On accepted Chevron or Ramsey updates, update both `qubit_frequency.yaml` and `control_frequency.yaml`.

On accepted resonator updates, update `resonator_frequency.yaml` and recompute `readout_frequency` from the full accepted state. An existing optimized frequency remains selected. On accepted optimization updates, update `optimal_readout_frequency.yaml` and the derived `readout_frequency.yaml`. Do not overwrite `resonator_frequency.yaml` with an optimized drive frequency.

Clearing an optimization value must remove or unset the affected target's exported optimization value and rewrite its readout drive frequency using the resonator fallback. Do not leave a stale optimized value in either file or remove other targets' values. If the fallback cannot be resolved, report missing configuration rather than silently retaining the old drive frequency.

Use one frequency selection rule for execution and YAML generation. A static mapping that copies each changed source into `readout_frequency.yaml` cannot implement the required precedence. Publication must keep the accepted database state, normal downstream inputs, and exported defaults consistent; export failures must be visible rather than reported as fully applied updates.

QDash-generated defaults are managed outputs. Independent edits to `control_frequency.yaml` or `readout_frequency.yaml` are not QDash calibration inputs. For standalone Qubex experiments requiring different defaults, use separate configuration or explicit execution overrides. QDash cannot guarantee identical behavior while ignoring independent edits to shared drive-frequency files.

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

> Updates `resonator_frequency`. Readout continues to use the accepted Optimal Readout Frequency result.

List other updated outputs separately. Generate the source descriptions from the selected target's actual calibration metadata. Measurement-only runs must instead state that results are recorded without applying parameter updates. Keep the measurement-only choice near the action; routine execution does not require another confirmation dialog.

### After execution

Display execution outcome and publication outcome separately. For each output, show the measured value, whether it was applied, the previous accepted value where applicable, and the reason when it was not applied. Show the retained operating frequency and its source when an exploration result was updated.

Use explicit outcomes such as “Applied,” “History only,” and “Not applied: validation failed.” A successful measurement alone does not mean the calibration database or YAML was updated. YAML synchronization failures must remain distinguishable from measurement failures.

## Implementation gaps

The policy requires changes beyond adding YAML mappings. At the time this policy was added:

- Qubit Spectroscopy and CheckControlAmplitude already output `coarse_qubit_frequency`; Chevron and Ramsey already output `qubit_frequency`.
- Resonator Spectroscopy outputs its resonator estimate as `readout_frequency`. Optimal Readout Frequency and CheckCoarseReadoutParams also output `readout_frequency`, conflating the measured resonator frequency and readout optimization.
- `config/app/workflow.yaml` maps `resonator_frequency` to `readout_frequency.yaml`. It already exports `qubit_frequency` to both qubit and control frequency files, but does not map the coarse qubit or optimal readout frequency files. The publication allowlist also needs to include the new exports.
- Many task inputs request `readout_frequency` directly from the database. These inputs, snapshot handling, and the Qubex adapter need a shared resolution path before the independent database parameter can be retired.
- The executor clears rejected outputs before calling `BackendSaver` for postprocess and R² validation failures. `BackendSaver` itself writes non-empty calibration outputs before its backend-success gate. Preserve the executor's rejection path when implementing this policy; setting only the backend-success flag is insufficient to protect database values.
- `persist_output_parameters` controls output publication. In the single-task flow, `update_params` is passed as `force_update_params`, which can bypass the backend quality gate. The re-execution UI labels it “Update backend params”; this must not serve as the ordinary “Calibrate and apply” control.

Existing `readout_frequency` records may originate from spectroscopy or optimization. Migration must use task provenance where available rather than copying every legacy value into both new parameters. Ambiguous records require an explicit classification or remeasurement. Preserve historical records and their original meanings, including snapshots used for re-execution.
