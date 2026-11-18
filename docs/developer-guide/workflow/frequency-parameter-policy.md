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

## Task frequency matrix

Task input precedence and update targets are fixed and have the same meaning in standalone runs
and workflows. In the tables, “fallback” means that the second parameter is read only when the
first is absent. Publication requires enabled output persistence and successful validation.

### Qubit and control frequency

| Task or task family | Drive-frequency input | Frequency result | Published database parameters |
| --- | --- | --- | --- |
| `CheckQubitSpectroscopy` | Qubex spectroscopy sweep range; no calibrated control-frequency input | Coarse f01 estimate | `coarse_qubit_frequency`, `control_frequency` |
| `CheckQubitFrequencyMapping` | Qubex spectroscopy sweep range; no calibrated control-frequency input | Coarse f01 estimate on the selected resonator candidate | `coarse_qubit_frequency`, `control_frequency` |
| `CheckControlAmplitude` | `control_frequency`; fallback: `coarse_qubit_frequency` | Refined coarse f01 estimate | `coarse_qubit_frequency`, `control_frequency` |
| `CheckAdaptiveChevron` | `control_frequency`; fallback: `coarse_qubit_frequency` | Measured qubit frequency | `qubit_frequency`, `control_frequency` |
| `CheckChevron` | `control_frequency`; fallback: `qubit_frequency` | Measured qubit frequency | `qubit_frequency`, `control_frequency` |
| `CheckRamsey` | `control_frequency`; fallback: `qubit_frequency` | Measured qubit frequency | `qubit_frequency`, `control_frequency` |
| Other ordinary one- and two-qubit tasks | `control_frequency`; fallback: `qubit_frequency` | No frequency result | None |

Qubit Spectroscopy and CheckControlAmplitude treat their estimates as exploration measurements,
so they do not update `qubit_frequency`. They publish the estimate to `control_frequency` so the
next bringup task consumes the value measured in the current workflow instead of a stale operating
value. Adaptive Chevron, fixed-grid Chevron, and Ramsey produce a physical qubit-frequency result
and also make it the next operating control frequency.

### EF and FH frequency and configuration

EF and FH calibration separate measured transitions from operational drive frequencies in the
same way as GE calibration.

| Task or task family | Frequency input | Frequency result | Published database parameters |
| --- | --- | --- | --- |
| `CheckAdaptiveEFChevron` | Configured `control_frequency_ef`; otherwise the Qubex missing-anharmonicity default derived from `control_frequency` | Measured EF transition and qubit anharmonicity | `ef_frequency`, `control_frequency_ef`, `qubit_anharmonicity` |
| `CheckEFRabi`, EF pulse creation, and EF readout classification | `control_frequency_ef`; fallback: `ef_frequency` | No transition-frequency result | None |
| `CheckAdaptiveFHChevron` | Configured `control_frequency_fh`; otherwise `2 * control_frequency_ef - control_frequency` | Measured FH transition | `fh_frequency`, `control_frequency_fh` |

`ConfigureEF` must run in the same worker session before an EF- or FH-dependent measurement. It
loads and pushes either the `ge-ef-cr` layout, which is the default, or `ge-ef-fh`. EF tasks reject
a session whose GE and EF targets are not available, and `CheckAdaptiveFHChevron` additionally requires an
FH target. Ordinary `Configure` defaults to `ge-cr-cr`, even after an EF configuration task, so a
flow returning to CR calibration must run `Configure` to restore the CR layout.

`CheckAdaptiveEFChevron` deliberately ignores persisted qubit anharmonicity when selecting its initial search
frequency. If Qubex has an explicit `control_frequency_ef`, the task uses it. Otherwise it uses
`18 / 19 * control_frequency`, matching Qubex's `E_J / E_C = 50` fallback when anharmonicity is
unset. Its initial EF drive amplitude is `control_amplitude / sqrt(2)`, matching Qubex's default
scaling from the calibrated GE control amplitude. Qubit spectroscopy may still display an f12
estimate for diagnosis, but it does not publish that estimate as calibrated qubit anharmonicity.

`CheckAdaptiveFHChevron` requires the `ge-ef-fh` layout, a calibrated GE HPI pulse, and a calibrated EF pi
pulse. It uses the configured `control_frequency_fh` as its initial search frequency when present.
Otherwise it derives the initial frequency from the measured GE and EF transition frequencies
without reading persisted anharmonicity. Its initial FH drive amplitude is
`control_amplitude / sqrt(3)`, matching Qubex's default scaling. The task is available for explicit
task lists but is not part of the `ef_calibration` template.

The `ef_calibration` template keeps all EF tasks in one `CustomOneQubit` step with `execution_mode="parallel_by_round"`. It
starts from existing GE control and readout frequencies and readout amplitude, then runs
`ConfigureEF`, calibrates GE Rabi and HPI, measures the EF transition, and calibrates EF pulses and
three-state readout. `CheckAdaptiveEFChevron` therefore receives the HPI parameters created earlier in the
same task list; a pre-existing HPI calibration is not required by the template.

`CheckEFRabi` records the GE HPI inputs used by the task, but Qubex currently prepares the
`|e>` state through `x180()`. `CheckAdaptiveFHChevron` likewise uses `x180()` for its GE and EF preparation
pulses. For GE, that call can prefer a stored DRAG PI, PI, or DRAG HPI pulse over the restored HPI.
For EF, a stored DRAG PI can take precedence over the restored EF PI. Existing calibration-note
entries can therefore change state preparation even when the recorded task inputs match. Starting
a new QDash execution does not remove those entries.

### Resonator and readout frequency

| Task or task family | Readout-frequency input | Frequency result | Published database parameters |
| --- | --- | --- | --- |
| `CheckResonatorSpectroscopy` | Qubex spectroscopy sweep range; no calibrated readout-frequency input | Measured resonator frequency; none with `detection_only` | `resonator_frequency`, `readout_frequency`; none with `detection_only` |
| `CheckQubitFrequencyMapping` | Resonator candidates from `CheckResonatorSpectroscopy`; not `readout_frequency` | Resonator candidate that shows the qubit's response | `resonator_frequency`, `readout_frequency` |
| `CheckCKP` | `readout_frequency` | Measured resonator frequency and photon-limited optimal drive | `resonator_frequency`, `readout_frequency` |
| `CheckCoarseReadoutParams` | `readout_frequency`; fallback: `resonator_frequency` | Selected operational readout frequency | `readout_frequency` |
| Other ordinary measurement and gate tasks | `readout_frequency`; fallback: `resonator_frequency` | No frequency result | None |

`CheckCoarseReadoutParams` selects `readout_frequency` by maximizing the Rabi IQ response range
across readout frequencies and amplitudes. It does not replace `resonator_frequency`.
Resonator Spectroscopy deliberately publishes its measured resonance to both parameters, so a
subsequent readout optimization starts from the newly measured device state.

`CheckCKP` runs Qubex's filtered CKP experiment. It publishes the fitted ground-state resonator
frequency as `resonator_frequency` and the photon-limited optimum as `readout_frequency`. The task
also publishes its fitted Purcell-filter parameters. It rejects every output when the fit R² is not
finite and strictly greater than `0.7`, or when any required fitted value is invalid.

Update targets are specified per output, not by classifying the entire task as exploration or calibration. Amplitude and other outputs retain their own declared destinations. In particular, Resonator Spectroscopy also produces `readout_amplitude`; maintaining the readout frequency does not imply that every readout setting remains unchanged.

### Qubit frequency mapping

`CheckQubitFrequencyMapping` identifies a qubit's coarse frequency and its resonator in one
task run, without trusting the resonator assignment of `CheckResonatorSpectroscopy`. It is an
opt-in task: only the **Bring-up v2** template runs it, the default **Bring-up** template does not,
and `CheckQubitSpectroscopy` is unchanged.

The candidates come from `CheckResonatorSpectroscopy` with the run parameter `detection_only` set
to `true`. In that mode the task assigns nothing: it publishes no `resonator_frequency`,
`readout_frequency`, `optimal_power`, or `readout_amplitude`, and ignores
`resonator_assignment_order`. It publishes every detected peak of the MUX, sorted by frequency,
for each qubit of the MUX:

| Output | Meaning |
| --- | --- |
| `resonator_candidate_count` | Number of detected peaks, from 1 to 4 |
| `resonator_candidate_<i>_frequency` | Frequency of peak `i`, for `i` below the count |
| `resonator_candidate_<i>_readout_amplitude` | `10**(optimal_power/20)` of the same peak |

The detection result depends only on the MUX measurement, so every qubit of the MUX gets the same
candidate set or the same failure. A run that detects no peak, more than 4 peaks, or a peak without
a finite frequency and optimal power fails for the MUX without outputs; a partial detection with
fewer than 4 valid peaks succeeds, including when the default assignment would fail for some qubit.
With the default `detection_only: false` the task keeps its per-qubit assignment and publishes no
candidates. A qubit of the MUX whose postprocessing rejects the shared result is recorded as failed,
not completed.

`CheckQubitFrequencyMapping` reads the candidates as calibration inputs that cannot be
overridden. Before any hardware call it rejects a count outside 1 to 4, a missing, non-finite, or
non-positive candidate value, frequencies that are not strictly increasing, and any candidate whose
`execution_id` or `task_id` differs from the count's. It then checks the candidate set against the
`CheckResonatorSpectroscopy` task results of every qubit in the target's MUX on the same chip, using
the chip's MUX topology. The set is used only when all of these hold:

- the task result named by the count's `task_id` exists for the target qubit, in the count's
  execution, and completed;
- every `CheckResonatorSpectroscopy` result of that execution in the MUX completed;
- no other execution started a `CheckResonatorSpectroscopy` attempt in the MUX at or after that
  result, whatever the outcome of that attempt.

A failed, partial, or running newer attempt therefore stops the mapping instead of leaving an older
successful set in use, even though a failed attempt does not remove the older values from the
calibration database. A newer attempt with `detection_only: false` also stops it. After such an
attempt, rerun `CheckResonatorSpectroscopy` with `detection_only: true` for the MUX and wait for it to
complete before running `CheckQubitFrequencyMapping`.

The task pairs candidate `i` with the `i`-th valid readout label of the target's Qubex MUX, sorted
by label, and calls `qubex.contrib.multiplexed_readout_qubit_spectroscopy` with one drive target
once per readout group, described below. The labels are acquisition slots only; the result does
not assume that a slot's own qubit owns the candidate. Before measuring a group, the helper
configures the readout of its slots for the group's candidate frequencies and restores the
configuration afterwards; it rejects a group whose candidates on one MUX cannot share one readout
configuration. Run the qubits of one MUX sequentially, as the
[1-qubit scheduler](../architecture/one-qubit-scheduler.md) does; two concurrent runs in one MUX
would read the same resonators.

A readout group is the set of candidates read together in one acquisition. Their tones share one
readout AWG channel, where Qubex sums them with unit-magnitude phase factors and the driver rejects
any I or Q sample above full scale. Tones whose amplitudes sum to at most 1 stay within full scale
for any phases.

Every candidate is read at one shared readout amplitude: the minimum of the
`resonator_candidate_<i>_readout_amplitude` values over the whole candidate set, computed once
before grouping. Each of those values is a single-tone detection optimum, which the task calls the
requested amplitude and records as provenance only. Because the selection compares the f01 moments
of all candidates, a common amplitude keeps the readout drive out of that comparison; it does not
remove differences in resonator response or noise. For requested amplitudes
`[0.8, 0.3, 0.2, 0.4]`, every candidate is read at 0.2. The task rejects a requested amplitude
that is not finite and positive or exceeds 1 before any measurement.

The `readout_grouping` run parameter decides which candidates may share a group:

| Value | Candidates that may share a group |
| --- | --- |
| `frequency_pairs` (default) | Adjacent candidates in frequency order: the candidates are sorted by frequency, ties by candidate index, and paired from the lowest frequency; with an odd count the highest candidate is alone |
| `multiplexed` | Every candidate |

Grouping uses frequencies only. The candidates are not yet assigned to qubits, so a slot's qubit
index says nothing about the candidate it reads, and grouping by qubit index modulo 4, as Qubex
`create_qubit_subgroups` does for assigned qubits, would pair the lowest and highest of four
candidates. Pairing neighbours keeps the tones read together close, so they fit one readout
configuration even when the lowest and highest candidates do not.

`plan_readout_groups` then walks each pair, or all candidates under `multiplexed`, in candidate
index order and adds each candidate to the current group while the group's sum of shared
amplitudes stays at or below 1; otherwise the candidate opens a new group. A pair is split
further only when its tones would exceed full scale, the shared amplitude is never reduced to fit,
and the budget never spans two pairs, because they are separate acquisitions. With the shared
amplitude 0.2 from the example above, `frequency_pairs` reads `RQ00`+`RQ01` and `RQ02`+`RQ03`,
although the requested amplitudes of `RQ00` and `RQ01` sum to 1.1, and `multiplexed` reads all
four slots together. A shared amplitude of 0.5 gives `RQ00`+`RQ01` and `RQ02`+`RQ03` under either
mode. A shared amplitude above 0.5, such as 0.6, reads every candidate in its own acquisition under
either mode.

Each group is one helper call with the same drive target, sweep, timing, shots, interval, and
shared readout amplitude, run in group order. The task passes `readout_grouping="multiplexed"` to
every call, so the helper reads exactly the group's slots and does not partition them again. A candidate keeps its readout slot
and its candidate index whichever group reads it. The helper numbers the candidates of each call from 0, so the task checks
each payload's `candidate_index` against the candidate's position in its group and then maps the
payload back to the candidate's own index. The helper reports the acquisitions it made in
`readout_groups` and each candidate's `readout_group_index`; the task requires
`readout_grouping` `multiplexed`, exactly one acquisition holding the group's slots, and index 0, so a helper that
split a group further is rejected. A failed helper call fails the task, naming the group; a group
result whose target, readout labels, grouping, candidates, or axes disagree with the plan or with
group 0 marks the task failed without outputs, so no group is published alone. The evidence records
the groups under `readout_groups`: the mode, the shared `readout_amplitude` with
`readout_amplitude_policy` `shared_minimum` and its rule, the budget and grouping rule, and each
group's frequency pair, candidates, slots, readout frequencies, applied and requested amplitudes,
and applied sum. Each candidate records its `readout_group`, `readout_group_position`,
`frequency_pair` (null under `multiplexed`), the applied `readout_amplitude`, and its own `requested_readout_amplitude`. The
bound covers the summed readout tones only; it assumes no gain between the pulse amplitude and the
AWG samples.

Each candidate is analyzed from its `phases` array in its group's Qubex result, on the result's
`frequency_range` and `power_range`; the figures in the Qubex result are not read. The task rejects
the result when an axis is not finite and strictly increasing, differs from the requested sweep, or
differs from the candidate's own axes, and rejects a candidate whose `readout_label`,
group position, readout frequency, or applied readout amplitude does not match the request, whose
`phases` is not a finite real array of shape `(power, frequency)`, or whose `data` differs from
`phases`. The task builds each candidate's heatmap from the validated arrays and analyzes it with the
`CheckQubitSpectroscopy` configuration and trimmed retry.
The task ranks the candidates by the f01 `moment` of that analysis (`F01Result.moment`), the raw
score from which the analysis derives `quality_level`. It selects the best candidate and publishes
outputs only when all of these hold:

- its `quality_level` is at least 3; `CheckQubitSpectroscopy` reports levels up to 2 as low
  quality;
- its f01 is at least 2.5 GHz;
- its moment is at least `min_score_ratio` times the runner-up's moment.

The runner-up is the candidate with the next-highest moment among every candidate with an f01 peak,
low-quality ones included, so a weaker alternative is never hidden. Equal moments rank by candidate
index, so the decision does not depend on the order of the candidates. An exact or near tie fails
the ratio test and is rejected as ambiguous. When no other candidate has an f01 peak, or the
runner-up's moment is 0, the ratio is undefined: the evidence records the runner-up as `absent` or
`zero`, the ratio as `null`, and the separation test passes. A candidate whose analysis fails, a
non-finite or negative moment, no response, a best candidate below the quality or frequency gate,
or a malformed result marks the task failed without outputs.

`min_score_ratio` is a run parameter with the default `2.0`, and it must be greater than 1. The
default is a provisional heuristic, not an empirically calibrated threshold. The moment is not
normalized across candidates: it sums the phase magnitude over the detected peak region, weighted
by drive power, so it grows with the region's size and phase contrast. Every candidate is read at
the shared readout amplitude, but a candidate whose resonator responds more strongly or shows less
noise can still score higher for the same qubit response. Candidates can also come from different
readout groups, which are separate acquisitions, and the task does not normalize for either.

The figure order depends on the outcome:

| Outcome | Figure order |
| --- | --- |
| Selected | Selected candidate's marked figure, the summary, then each candidate's marked and raw figures without the selected marked figure |
| Rejected or ambiguous | The summary, then each candidate's marked and raw figures |

Each candidate contributes a marked figure when its analysis ran and a raw figure when its data is
valid, in candidate order.

The selected candidate's figure is its own phase map with the f01 marker of the analysis and the
coarse-amplitude line. Its title names the qid, the candidate index and readout slot, the readout
frequency and amplitude, the f01, moment, and `quality_level`, and the runner-up margin. The
summary figure shows a table of every candidate (slot, readout group, readout frequency, applied and
requested readout amplitude, readout power, status or error, f01, moment, `quality_level`, rank, selection), each
candidate's phase map with its f01 peak, the decision and its reason, the runner-up and ratio, the
rule, and the readout groups with the shared readout amplitude and their amplitude sums. Both
figures carry the same evidence in their JSON under `layout.meta["qubit_frequency_mapping"]`,
including the raw moment of every candidate and the proposal: the values the selected candidate
publishes, or the best candidate's values marked `published: false` on rejection.
`layout.meta["qubit_frequency_mapping_figure"]` is `selected` or `summary`. A failed task's message
is one line that names the reason and every candidate's moment, `quality_level`, and f01.

The decision is deterministic, and the task does not call an AI model. The existing
[AI evaluation](../copilot/evaluation.md) of a task result judges the first figure, so a completed
mapping is judged on the selected candidate's spectrum and a failed one on the summary. The
evidence tool reads the decision evidence from the first JSON figure and adds every candidate's
scores to the evaluation context as a `Candidate comparison:` line, so the comparison is not lost
when the selected figure comes first. **Ask AI** on a task result opens with every figure, the
summary included.

On success the selected candidate supplies `resonator_frequency`, `readout_frequency`, and
`readout_amplitude`, the shared amplitude every candidate was read with, not the selected
candidate's requested amplitude. The f01 estimate supplies
`coarse_qubit_frequency`, `control_frequency`,
`f01_repr_db`, `f01_quality_level`, and `coarse_control_amplitude` with the same conversion as
`CheckQubitSpectroscopy`. `resonator_candidate_index` records the selected peak. Qubits are
inferred independently, so two qubits of one MUX can select the same candidate; QDash does not
check that the selections form a one-to-one mapping.

The helper was added in [amachino/qubex#472](https://github.com/amachino/qubex/pull/472), and its
`readout_grouping` argument is not yet in upstream `develop`. `[tool.uv.sources]` therefore pins
Qubex to commit `dcff0daf2087f7566fdb8c8a125e5ef003c46fbe` of `orangekame3/qubex`, and `uv.lock`
records that commit for `qubex` and its workspace packages. To move the pin, change the `rev` and run
`uv lock`. With a Qubex revision whose helper is missing or lacks `readout_grouping`, the task
registers normally and fails at run time, before any measurement, with an error naming that
prerequisite.

The **Bring-up v2** template (ID `bringupv2`, `templates/bringupv2.py`) runs the pipeline for the
selected `mux_ids` in one `BringUp` step:

| Order | Call | Settings |
| --- | --- | --- |
| 1 | `CheckResonatorSpectroscopy` | `shots: 1024`, `interval: 0`, `detection_only: true`, `update_calibration_parameters: true` |
| 2 | `CheckQubitFrequencyMapping` | `shots: 1024`, `interval: 1024`, `update_calibration_parameters: true` |
| 3 | `CheckControlAmplitude` | `shots: 8192`, as in the **Bring-up** template |
| 4 | `CheckAdaptiveChevron` | `shots: 256`, as in the **Bring-up** template |

`CheckResonatorSpectroscopy` runs on the representative (local slot 0) of each MUX and distributes
the candidates to every qubit of the MUX before the representative continues. Each selected qubit
of the MUX then runs calls 2 to 4 in slot order. The first two calls publish their outputs, because
the mapping reads the candidates from the calibration parameters and `CheckControlAmplitude` reads
the `readout_frequency`, `readout_amplitude`, `control_frequency`, and `coarse_control_amplitude`
the mapping publishes. A failed call skips the qubit's later calls, so a rejected mapping never
leaves `CheckControlAmplitude` or `CheckAdaptiveChevron` to run on values from an earlier run. A
failed detection skips the representative's later calls; the other qubits of that MUX still run the
mapping, which rejects the candidate set because the failed attempt is the latest in the MUX.

`execution_mode` defaults to `parallel_by_mux`, as in the **Bring-up** template: the MUXes of one
hardware stage run in parallel, stages run one after another, and the qubits of each MUX run in slot
order, so two qubits of one MUX are never driven at the same time. `sequential` drives one qubit at
a time. The template rejects other modes, because `parallel_by_round` can start a later slot before
its representative. `exclude_qids` follows the **Bring-up** template. Excluding a MUX representative
runs no detection for that MUX in the run, so its other qubits map against whatever candidate set
`CheckQubitFrequencyMapping` accepts from the calibration parameters, which can come from an earlier
run. The task, not the template, decides whether that set is still usable.

### Replacement within the same parameter

There is no automatic ranking of task names or calibration stages. With publication enabled, a
validated Chevron result can replace a Ramsey result in `qubit_frequency`. A validated Resonator
Spectroscopy result can replace a CKP result in `resonator_frequency`, and a later CKP result can
replace it again. This policy protects measured qubit frequencies from exploration updates; it does
not guarantee that every accepted recalibration improves precision or device performance.

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

Do not copy `coarse_qubit_frequency` into `qubit_frequency`. Bringup tasks may publish a coarse
estimate to `control_frequency`, and legacy snapshots or databases may supply it through the
explicit coarse fallback shown in the task matrix. Ordinary post-bringup tasks do not use the
coarse fallback.

Permitted per-execution overrides remain explicit inputs. An arbitrary drive override does not
become a measured qubit or resonator frequency. Record the actual resolved drive frequencies,
their sources, and overrides in execution history.

Snapshot re-execution uses the recorded effective inputs and permitted overrides, not current database values or current YAML defaults. Preserve enough source information in the snapshot to reproduce the frequency selection.

## Bringup and repeated measurements

Bringup uses the normal task destinations rather than a separate calibration-stage reset or an all-workflow publication checkpoint:

1. Qubit Spectroscopy updates `coarse_qubit_frequency` and seeds `control_frequency` after validation.
2. CheckControlAmplitude consumes `control_frequency`, falling back to the legacy `coarse_qubit_frequency`, and refines both values.
3. Adaptive Chevron consumes `control_frequency`, falling back to the legacy `coarse_qubit_frequency`, and publishes `qubit_frequency` plus `control_frequency` after validation.
4. Subsequent calibration tasks consume the updated calibrated values.

Validated outputs are published as the workflow progresses when persistence is enabled. A failure in a later task does not roll back earlier accepted outputs. Report the outputs already updated and the tasks that did not complete. Failed outputs must not become the normal inputs of downstream tasks.

An initial bringup can reach Adaptive Chevron without an existing `qubit_frequency`, using the
operational seed published by the preceding exploration tasks. Repeating only Qubit Spectroscopy
retains `qubit_frequency` but replaces `control_frequency` with the new coarse estimate. Repeating
bringup can replace both values when Adaptive Chevron succeeds; the start screen identifies
bringup as a recalibration operation.

### Readout transitions

The [task matrix](#resonator-and-readout-frequency) defines readout publication. Repeating
Resonator Spectroscopy resets the operational frequency to the measured resonance; run readout
optimization afterward if the drive should differ. Review other updated outputs, including
amplitude, because retaining a frequency does not preserve every readout setting.

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

The default scan performs 65 Rabi traces. Widen the ranges or change shots and the Rabi time
window through run parameters when the experiment needs it.

Progress uses the effective frequency count times the amplitude count after clipping and
deduplication: normally 65 sweeps, or 39 at reference amplitude 1. The percentage includes the
active sweep; the remaining-time estimate starts after the first sweep and includes inter-sweep
time. The UI omits the inner Rabi point count and per-sweep estimate.

Older snapshots without the newly declared reference inputs cannot silently use current settings; handle missing snapshot inputs according to [Parameter Resolution](./parameter-resolution.md#effective-input-validation).

### Coarse readout R² validation

`CheckCoarseReadoutParams` validates the Rabi fit at the selected readout frequency and amplitude before accepting either output. In the installed Qubex revision pinned by `uv.lock`, `rabi_results` contains the scan results in amplitude-major order; each result exposes `rabi_params[qubit_label].r2`. Use this stored R² without refitting or averaging the scan.

The default threshold is shared with QDash's `CheckRabi`: `0.6`. As with the existing task executor, a value must be strictly greater than the threshold to pass. Missing, non-finite, or greater-than-one R² values also fail validation. Selection metadata that cannot identify the matching scan point is a validation failure, not permission to skip the check.

Do not require every scan point to pass: exploration can include low readout amplitudes and other settings with poor responses. Conversely, a good fit at an unrelated point must not authorize publishing a noisy selected point. Do not silently choose a different candidate when the selected point fails.

Preserve the heatmap and available raw scan data for inspection, mark the task failed, and publish neither frequency nor amplitude on rejection. The selected R² is recorded as task quality metadata when finite. This gate is implemented in the task; it does not establish that the response maximum is the fidelity optimum or guarantee rejection of every possible noise realization.

## Manual correction

A manual correction from a spectroscopy Task Result writes operational values only. The
measured frequency stays as recorded, because experiments own `resonator_frequency`,
`qubit_frequency`, and the exploration estimate `coarse_qubit_frequency`.

| Source task | Correctable parameters | Measured value shown for reference |
| --- | --- | --- |
| `CheckResonatorSpectroscopy` | `readout_frequency`, `readout_amplitude` | `resonator_frequency` |
| `CheckQubitSpectroscopy` | `control_frequency`, `coarse_control_amplitude` | `coarse_qubit_frequency` |

The allowlist is fixed per task in `ManualUpdateService` and does not depend on the source
result's status or recorded output names, so a failed result can still seed the operating
values. Diagnostics such as `optimal_power`, `f01_repr_db`, and `f01_quality_level` are never
written by hand. A point picked on the figure sets the frequency from `x` and derives the
amplitude from `y` with the same conversions as the task: `10**(y/20)` for readout, and
`min(10**((y + 10)/20), 1)` for the coarse control amplitude.

## YAML export

YAML files represent accepted parameter values and the default drive configuration derived from them. They do not export every new measurement automatically.

| YAML file | Exported value |
| --- | --- |
| `qubit_frequency.yaml` | Accepted measured qubit frequency |
| `control_frequency.yaml` | Accepted operational control frequency |
| `resonator_frequency.yaml` | Accepted measured resonator frequency |
| `readout_frequency.yaml` | Accepted operational readout frequency |

On accepted Chevron or Ramsey updates, update both `qubit_frequency.yaml` and
`control_frequency.yaml`. On accepted Resonator Spectroscopy or CKP updates, update both
`resonator_frequency.yaml` and `readout_frequency.yaml`. Readout optimization updates only
`readout_frequency.yaml`.

Seed import is deliberately narrower: only operational frequency and amplitude files may update
the calibration database. It cannot import `qubit_frequency.yaml` or
`resonator_frequency.yaml`; experiments own those measured values.

## Execution Controls and Results

The Task Workbench starts with **Update calibration values** disabled. A run still records its
measurements and artifacts, but its outputs do not become current calibration values. Enabling the
control publishes validated outputs to every destination declared by the task and can update mapped
YAML files when that integration is configured.

**Run again** opens the same workbench with values from the source result. Saving outputs remains
disabled until the operator enables it for that run. Input selection and output publication are
independent; publishing an output does not bypass task validation.

The result's **Output Parameters** table shows **Calibration DB updated**, **Measurement only**, or
**Partially updated** from the recorded destination metadata. For an applied value it shows the
previous value, the new value, and each database destination. Historical `readout_frequency`
records retain the task that produced them; QDash does not reinterpret an older spectroscopy,
CKP, or optimization result as another parameter type.

The user procedure is in [Task Parameters](../../user-guide/task-parameters.md).
