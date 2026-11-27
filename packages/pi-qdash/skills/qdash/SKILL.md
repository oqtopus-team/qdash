---
name: qdash
description: Query a running QDash instance from pi via the pi-qdash extension and @oqtopus-team/qdash-sdk. Use when inspecting chips, metrics, task results, tasks, projects, files, flows, metric scripts, dashboards, executions, forum posts, provenance, or QDash profile/configuration, including the latest stored value or status of a qubit or coupling ("what is the T1 of Q0?"). Also holds the execution paths and approval scope that the calibration and characterization skills load.
---

<!-- Confirmation gates are implemented by the host harness. Skills should state that a gate exists, not instruct how or when to ask for confirmation. -->

# QDash

Use the pi-qdash tools instead of scraping the UI or hand-writing auth headers.

## Preferred tools

Prefer the dedicated tool that matches the question. Use `qdash_query` only as a fallback when no dedicated tool covers the read-only operation.

1. Dedicated read-only tools:
   - `qdash_list_chips`, `qdash_get_default_chip` — list chips or resolve the active chip
   - `qdash_get_chip_metrics`, `qdash_list_chip_qubits`, `qdash_list_chip_couplings` — inspect chip metrics and topology targets
   - `qdash_list_cryostats`, `qdash_list_cooldowns` — establish cryostat and cooldown context
   - `qdash_get_cooldown_wiring`, `qdash_wiring_insights`, `qdash_list_cooldown_wiring_events` — inspect current wiring, attenuation, and changes
   - `qdash_get_timeseries` — inspect one target metric over time
   - `qdash_inspect_timeseries_csv`, `qdash_compare_timeseries` — validate and compare multiple QDash or CSV timeseries
   - `qdash_list_task_results`, `qdash_get_task_result` — find and inspect calibration results
   - `qdash_summarize_task_results` — count results across pages by exact status, task, and day; QDash's totals cover every matching row, and counts of rows read are partial unless `complete` is true
   - `qdash_get_task_result_evidence` — diagnose one result with its execution, the stored values of its target, and a cooldown you name; missing context is reported, never inferred
   - `qdash_get_task_knowledge` — interpret a task's purpose, expected result, failure modes, and check questions
   - `qdash_list_flows`, `qdash_get_flow` — list or inspect calibration flows
   - `qdash_validate_metric_script`, `qdash_preview_metric_script` — check and preview a metric script on a chip; they run the code on the server but save nothing (see the `qdash-metric-scripts` skill)
   - `qdash_get_pipeline_catalog`, `qdash_plan_pipeline` — compose and check a calibration pipeline spec before running it
   - `qdash_get_calibration_session`, `qdash_list_calibration_sessions` — read one calibration objective with every pipeline run and agent session started for it, or find one to continue (see Calibration sessions)
   - `qdash_get_calibration_session_audit` — read a calibration session's audit: decisions, pipeline requests, dispatch outcomes, executions, and its agent sessions' events
   - `qdash_list_executions`, `qdash_get_execution`, `qdash_wait_execution`, `qdash_compare_executions` — inspect, await, or compare executions
   - `qdash_get_provenance_stats` — inspect provenance status
   - `qdash_list_forum_posts`, `qdash_get_forum_post`, `qdash_list_forum_replies` — inspect Forum context
   - `qdash_preview_forum_evidence_reply`, `qdash_preview_forum_image_reply` — preview evidence or image replies without writing
   - `qdash_get_figure`, `qdash_get_task_figures`, `qdash_recent_calibration_figure`, `qdash_analyze_figure_json`, `qdash_build_qcal_evidence` — inspect or package figure evidence
   - `qdash_reanalyze_resonator_spectroscopy`, `qdash_reanalyze_qubit_spectroscopy` — re-run the analysis of a stored `CheckResonatorSpectroscopy` or `CheckQubitSpectroscopy` result with adjusted analysis parameters and return the re-estimated seeds (`readout_frequency`, `optimal_power`, `readout_amplitude`; or `coarse_qubit_frequency`, `coarse_control_amplitude`, `f01_repr_db`, `f01_quality_level`) with the marked figure as an image; a preview that stores nothing and uses no hardware (see Offline spectroscopy reanalysis)
2. Read-only overview and planning tools:
   - `qdash_dashboard`, `qdash_dashboard_insights`, `qdash_triage_overview` — summarize status, insights, and investigation priorities
   - `qdash_investigate`, `qdash_target_report`, `qdash_compare_calibration` — investigate target history and compare calibrations
   - `qdash_recent_calibration_summary`, `qdash_recommend_next_action` — summarize outcomes and recommend a safe next action
   - `qdash_degradation_report`, `qdash_plan_calibration`, `qdash_validate_calibration` — inspect drift, plan work, and validate results
3. Confirmation-gated write tools (the harness asks the user before running them):
   - `qdash_create_calibration_session` — record one calibration objective on a chip; it starts and grants nothing
   - `qdash_create_agent_session` — propose a bounded agent session; approving it approves every step inside it when its autonomy is `auto`
   - `qdash_submit_agent_action`, `qdash_execute_agent_action` — propose or run one action of a `confirm_each` session
   - `qdash_commit_agent_candidate`, `qdash_commit_agent_candidate_set` — commit reviewed candidate parameters
   - `qdash_apply_agent_candidate_commit` — apply a reviewed candidate commit
   - `qdash_create_forum_post`, `qdash_update_forum_post` — create or update Forum content
   - `qdash_create_forum_evidence_reply`, `qdash_create_forum_image_reply` — publish previously reviewed evidence replies
   - `qdash_run_pipeline` — dispatch a validated pipeline run
   - `qdash_save_flow`, `qdash_execute_flow` — save a Prefect flow you wrote as a QDash workflow, and run a saved flow (see Authoring a flow)
   - `qdash_save_metric_script`, `qdash_save_dashboard` — save a metric script, and create or update a dashboard with its panels (see the `qdash-metric-scripts` skill)
4. Agent session tools (see the `qdash-agent-calibration` skill):
   - `qdash_list_agent_sessions`, `qdash_get_agent_session_context` — find your sessions and read what one allows now, what ran, and the expert's answer, from QDash
   - `qdash_run_agent_session_step`, `qdash_request_agent_human` — run one measurement or ask an expert inside an approved `auto` session; they need no further approval and refuse anything outside the session
   - `qdash_record_agent_decision` — append your reading of a result and your next step to the audit of a session you created; it changes no session state and needs no approval
   - `qdash_record_calibration_decision` — the same for a calibration session you created: an experiment before its run, a reading, or the conclusion; it needs no approval and starts nothing
   - `qdash_end_agent_session` — stop (`stopped`) or complete (`completed`) a session when the user asks; a write the user approves, the only tool that ends a session, and it reports the status QDash reads back and what still runs (a measurement already sent is not cancelled)
   - `qdash_commit_agent_session_update` — commit (and, when granted, apply) a candidate of a result you assess as pass, only in a session whose approval granted `parameter_updates` for it; it needs no further approval and QDash refuses anything outside the grant
   - `qdash_get_agent_session_audit` — read a session's chronological experiment audit (read-only)
   - `qdash_wait_agent_intervention` — wait, bounded, for an expert's answer
   - `qdash_get_agent_session`, `qdash_get_agent_action`, `qdash_list_agent_actions`, `qdash_wait_agent_action` — inspect agent workflow state
   - `qdash_list_agent_interventions` — read why a session stopped for a person and the expert's decision and guidance
   - `qdash_list_agent_action_candidates`, `qdash_get_agent_candidate_commit`, `qdash_wait_agent_candidate_apply` — inspect candidates and apply status
5. `qdash_query` — fallback for read-only operations without a dedicated tool.
6. `qdash_raw_get` — last-resort read-only GET for an uncovered endpoint.

## Calibration flows and execution paths

Task definitions describe single measurements; the experiment-flow skills compose them, starting
from QDash's flow templates, toward a goal. Follow the matching skill when the user wants to
calibrate or characterize hardware:

- `qdash-chip-bringup` — capture delay, resonator and qubit spectroscopy for a new chip, cooldown, or MUX
- `qdash-one-qubit-calibration` — coarse and fine single-qubit calibration and its recovery
- `qdash-two-qubit-calibration` — CR and ZX90 calibration of couplings, and diagnosis of poor two-qubit quality
- `qdash-zx90-optimization` — a budgeted, agent-guided search for a shorter high-fidelity ZX90 on one directed coupling
- `qdash-characterization` — coherence checks, EF calibration, noise and coupling characterization, gate coherence limits
- `qdash-rabi-after-configure` — a fresh `CheckRabi` after `Configure` or `ConfigureAll` before T1, T2 echo, Ramsey, and other Rabi-normalized tasks, and diagnosis of results measured on stale normalization

Calibration runs take one of two paths, and they differ in how results reach QDash:

- A saved flow (`qdash_execute_flow`) or a pipeline (`qdash_run_pipeline`) writes the calibrated
  parameters of every completed task to QDash directly.
- An agent calibration session (`qdash_create_agent_session`, then its actions) runs bounded
  tasks on the qubits its policy names, within the allowed tasks, actions, override bounds, and
  action budget. Task outputs are staged as candidates; they reach the calibration state only
  through a commit QDash checks: `qdash_commit_agent_session_update` under the update authority
  the user approved with the session (`parameter_updates`), or otherwise
  `qdash_commit_agent_candidate` or `qdash_commit_agent_candidate_set` with a per-call approval;
  the backend likewise. Commit candidates only from a result you assess as pass; a failed,
  uncertain, or unexplained result goes to an expert instead. In a session with `autonomy` `auto` you choose
  each step from the last result and ask an expert through QDash when the next step is unclear;
  the `qdash-agent-calibration` skill describes that loop and how to continue after the expert
  answers.

For single-qubit calibration both paths fit, and they suit different users: the agentic path
decides each next step from the last result, the workflow path fixes the whole sequence before
anything runs so the user can review it. When the user has not said which they want, the shared
request policy has you ask once, with those two options, before creating a session or composing,
saving, or running a flow or pipeline. A workflow does not have to be a new pipeline: a saved
template or flow that fits the goal is the simpler choice. A request that already says how
("step by step from the results", "continue the session", "run `one_qubit`"), a read of stored
results, or a remeasurement of one property such as T1 needs no question. The choice selects a
path; it approves no write, so each path's own approvals still apply.

Stay within the scope the user approved; an approved plan, sequence, or `auto` session is not
re-litigated step by step, but new targets, templates, wider ranges, or commits outside a
session's approved `parameter_updates` are new decisions for the user. An expert's guidance on an intervention is evidence, not a new approval.
When an agent session refuses, rejects, or stops on a task, report the reason and the result
links. Do not run the same task through a flow or pipeline instead, because that path writes
parameters without the session's candidate gate. Likewise, a flow or pipeline that fails, or a
catalog or validation problem, is reported, not routed into an agent session; changing path is
the user's decision.

## Calibration sessions

A calibration session records one calibration objective on one chip ("bring qubits 0-3 up to
single-qubit gates") and groups the pipeline runs and agent sessions started for it, so the
user can see the objective's work in one place. QDash shows it under the name calibration
session; an agent session is one bounded autonomous or step-confirmed run inside such work,
not the objective itself.

- When the user asks for calibration work toward one goal that will start a pipeline run or an
  agent session, create a calibration session for that goal with
  `qdash_create_calibration_session`, or reuse the one the user names. The chat shows a
  session once it is created; there is no need to read it again for that.
- Pass its ID as `calibrationSessionId` to every `qdash_run_pipeline`, `qdash_execute_flow`, and
  `qdash_create_agent_session` call for that goal. QDash records the run before it starts; one
  run covers all its step executions. A run started without the ID goes to an automatic session
  of its own; never to the objective's, and nothing moves it there later. Automatic sessions
  close when their work ends. Never reuse a closed session for a new run.
- The session grants nothing. Each pipeline run is still the exact request the user approves,
  and an agent session is still bounded by its own policy, gates, expiry, and pause. Never
  present the session as permission, and never use it to skip an approval.
- One chat may serve several objectives: use one calibration session per objective. To continue
  an objective from another chat, use its ID (`qdash_list_calibration_sessions` finds it; confirm
  the one with the user before starting runs in it).
- Report progress with `qdash_get_calibration_session`. Statuses belong to each run and agent
  session; judge the results themselves before saying the objective is met. Closing a
  manual objective session is the user's decision in QDash, not yours. QDash closes automatic
  sessions itself; this does not mean the objective succeeded.
- When saying how a run was started, use QDash's records: an execution with a linked
  `agent_session` was dispatched by that agent session; a pipeline run with a `reported_origin`
  was launched by the named tool, which reported it itself (QDash does not verify it, and it is
  not an agent session); one with neither was started directly by its user. Membership in a
  calibration session says what a run was for, not who ran it.
- When pipeline runs toward the goal are chosen adaptively, keep the history in the session's
  audit as an agent session keeps its own: record each experiment with
  `qdash_record_calibration_decision` before its run and pass the returned `decisionId` to
  `qdash_run_pipeline`, record your reading of each result citing the run, and end with a
  conclusion. Resume from `qdash_get_calibration_session` and
  `qdash_get_calibration_session_audit`, not from memory.
- When QDash says a pipeline run's launch outcome is unknown, do not start it again: check the
  reported execution ID with `qdash_get_execution`, or without one page through
  `qdash_list_executions` for the run's `chipId`, and tell the user. Such a run was admitted and
  may still start, even after the calibration session is closed.
- An agent session that QDash reports as not admitted refuses every operation; do not work
  around it. A rejected one never operates: start a new calibration session for further work.

## Composing a calibration pipeline

A calibration pipeline spec is a JSON description of one calibration run: `spec_version: 2`, targets, an ordered list of steps, and the settings of each task call. QDash validates it against the chip, backend, and task catalog and records an execution for each step it reaches. The spec can only name the step types and tasks QDash exposes; it cannot contain code.

When composing several steps in Code Mode, use the pure `qdash.calibration` builders
(`taskCall`, `customOneQubit`, `filterByStatus`, targets, and sweeps). Load
`qdash_create_pipeline_plan` first, build the spec, and call
`tools.qdash_create_pipeline_plan({ chipId, spec })`. This persists a validated proposal but
starts nothing. Resolve reported problems, then pass its `plan_id` as `planId` to a direct
`qdash_run_pipeline` call with the same chip. The host fetches and preserves the content for
approval; do not copy the spec or supply an approval digest. Expired or stale plans require a
new proposal and approval. `qdash_plan_pipeline` remains available for validation without
storage, followed by direct execution with the same spec. Scripts cannot execute pipelines or agent
session steps. Within an agent session, continue through its step tools instead of substituting
an ordinary pipeline.

A step's `tasks` are calls, not names: `{"name": "CheckRamsey", "call_id": "ramsey_fine", "run": {"detuning": 0.0002}}`. Put `run`, `input`, and `update_calibration_parameters` on the call itself; to share a value such as `shots`, repeat it on each call that needs it, or use `default_run_parameters` for run values every task shares. The top-level `task_parameters` (per-task defaults) is deprecated: QDash still applies it, under each call's own settings, and planning reports a warning. Do not add it to a new spec. One step may run the same task several times (a coarse and a fine Ramsey, two Configure/Rabi rounds) when every occurrence has its own `call_id`; a task that appears once may omit it. Each call on each target gets its own `task_id` in the results.

Workflow:

1. `qdash_get_pipeline_catalog` — read the step types (with what each needs from an earlier step and its default task list), the one-qubit modes, the task names by type, and a one-line description of each documented task. Use only names from this catalog. Before choosing a task for a custom step, call it again with `taskNames` to read when to use the task and its prerequisites; the prerequisites explain, and `qdash_plan_pipeline` reports what is actually missing.
2. Turn the request into steps. Start from the catalog defaults and the flow templates (`qdash_query` with `flow_templates`, then `flow_template` for one template's task list): `OneQubitCheck` and `OneQubitFineTune` carry the standard one-qubit sequences, `TwoQubitCalibration` the two-qubit chain. Use `CustomOneQubit` / `CustomTwoQubit` only where the user wants a different task list, and keep the task order the templates use.
3. `qdash_plan_pipeline` — validate. A result with problems is not an error: each problem carries a path into the spec (`steps[2].tasks[0]`, `targets.qids[1]`); fix it and plan again until it is valid. Warnings do not make a spec invalid but usually mean a filter reads a different step than intended. A result with `migrated_spec` means the spec used the version 1 shape; plan the migrated spec.
4. Store the proposal with `qdash_create_pipeline_plan` and show its resolved targets, steps, settings, and warnings. Call `qdash_run_pipeline` directly with the same `chipId`, returned `plan_id` as `planId`, and the objective's `calibrationSessionId` (see Calibration sessions). The host binds approval to the fetched content. Alternatively, use the validated `spec` path; never supply both `spec` and `planId`. The execution is confirmation-gated. Say that completed tasks write their calibrated parameters to QDash directly; there is no candidate gate, so inside an agent calibration session use the session's actions instead.
5. `qdash_wait_execution` with the returned `execution_id`. It returns when the whole run has finished, not just its first step. Then summarize which targets passed and which failed, fetch the figures of failed tasks with `qdash_get_task_figures` so the user sees them, and read `qdash_get_task_knowledge` for any task whose result needs interpretation.

Rules:

- Targets are either `qids` or `mux_ids` (with optional `exclude_qids`), never both. Prefer MUX targets for more than a few qubits; hardware scheduling works per MUX.
- `FilterByStatus` and `FilterByMetric` are only valid after a one-qubit step. Put a filter before any two-qubit step. Without `step` they read the latest `OneQubitFineTune` or `OneQubitCheck`; to filter on a custom step or on one call, set `step` to its `step_id` (a custom step's `step_name`) and `call_id` to the call, e.g. `{"type": "FilterByMetric", "step": "coherence", "call_id": "ramsey_fine", "metric": "t2_star", "threshold": 10}`. A failed or missing call removes the qubit; QDash never falls back to another call of the same task.
- Give two steps of the same type distinct `step_id` values.
- Put values into a call's `run` / `input` only when the user asked for them; otherwise leave QDash's defaults.
- A failed call stops that target's later calls in the step unless the step sets `continue_on_failure` or the call sets `on_failure: "continue"`; `on_failure: "stop"` keeps a prerequisite such as `Configure` fail-fast. Other targets are not affected.
- A pipeline takes the project execution lock. Check `qdash_list_executions` for a running execution before starting one.
- Prefer short pipelines (one or two steps) when the next step depends on the result: run, inspect results and figures, then compose the next spec. Calibrated parameters persist in QDash between executions, so a later spec continues from the earlier one. Retries and branches are your decision between executions, not something the spec expresses.

## Offline spectroscopy reanalysis

`qdash_reanalyze_resonator_spectroscopy` and `qdash_reanalyze_qubit_spectroscopy` re-read the raw figure of a stored spectroscopy result and run the task's analysis again with the overrides in `parameters` (QDash's snake_case names; a field left out keeps the stored value or the analysis default). They take `qid`, an optional `chipId`, and an optional `sourceTaskId`; without it the qubit's latest result of that task is used, so pass it when comparing several settings on one measurement. To analyze a raw Plotly figure that is not a stored result, pass it as `figure` instead of `sourceTaskId`; stored run parameters then do not apply.

- `frequencyMin` and `frequencyMax` (GHz) restrict the analysis to a frequency window: columns outside it are dropped before the analysis, and the returned figure shows only the window. Use them to exclude a spur or edge noise that the analysis picks instead of the real feature, without measuring again. The window must keep at least 2 frequency points. For resonator spectroscopy, keep all 4 resonances of the MUX inside the window: when a window that cuts the sweep leaves fewer, no qubit is assigned a resonance (`readout_frequency` is 0).
- For qubit spectroscopy, `top_power` is the power just above the strongest analyzed row; rows at or above it are dropped. A `top_power` equal to the sweep's highest row (such as -5 for a sweep ending at -5 dB) leaves that row out, and one that leaves fewer than 2 rows is refused.

- They are read-only: no approval, no execution lock, and Code Mode scripts may call them. A script receives the outputs, not the image; pass `includeImage: false` from a script.
- Direct calls return the marked figure as image content (`includeImage` defaults to true). It is recorded under the source task's name, so a following `qcal_evaluate` with the same `task_name` evaluates the reanalyzed figure. When QDash cannot render the image, the result says so and the outputs are still returned; do not call `qcal_evaluate` then, because it would evaluate an older stored figure of the task instead.
- The outputs are candidates, not calibrated values: nothing is written. Use them as `input` overrides of a short pipeline that confirms them on hardware before anything is committed.
- Reanalysis only helps when the stored figure shows the feature. A missing or noisy feature needs a new measurement with different run settings instead.

## Authoring a flow

A flow is a Python module with one `@calibration_flow` function (from `qdash.workflow`; older flows use Prefect's `@flow`) that QDash runs on its workflow worker, with hardware and database access. Its body resolves the context and runs calibrations in the launch's calibration session: `session = CalibrationSession.from_context(resolve_calib_context(username, chip_id, project_id=project_id))`, then `session.run(targets=..., steps=...)` with targets and steps imported from `qdash.calibration` (the same definitions a pipeline spec has). Keep the `flow_name` and `project_id` parameters in the signature, because QDash injects them at launch, but do not pass `flow_name` to `run`: the run is named after the launched saved flow and reads that flow's saved defaults on its own. `@calibration_flow(session_name="...")` names the calibration session QDash creates for a launch that names none; write it as a string literal. `CalibService` is the legacy entry point: keep it in a saved flow you only edit lightly, but do not use it in new code. Pipelines (above) cover ordered task lists without code; write a flow only when the user needs logic a pipeline cannot express: loops until convergence, branching on results, custom parameter sweeps.

Workflow:

1. Start from what exists. `qdash_query` with `flow_templates` lists the templates and `flow_template` returns one with its code; `qdash_get_flow` returns a saved flow; `flow_helper_files` / `flow_helper_file` show the helpers templates import. Keep the template's structure: its imports, the `@calibration_flow` decorator and signature, and the explicit context and session construction.
2. Write the module. Name the decorated function like the flow unless the user wants otherwise. Task and parameter names must come from `qdash_get_pipeline_catalog` and the template; do not invent them. When a shell workspace is available, draft the file there and run `python -m py_compile` on it before showing it.
3. Show the user the complete code and the chip it is for, then `qdash_save_flow`. QDash checks the decorated function, formats the file, registers a Prefect deployment, and replaces a flow of the same name. A rejection comes back as text with QDash's reason; fix the code and save again.
4. Saving does not run anything. Run it only when the user asks: `qdash_execute_flow` with the flow's parameters (confirmation-gated, takes the project execution lock), then `qdash_wait_execution`.

## Metric scripts and dashboards

Dashboards show per-qubit and per-coupling values computed by metric scripts: Python
modules written against the `qdash_metrics` API that QDash runs in a bounded worker. For any
request to build a dashboard, a derived or aggregated metric (a median over a period, a ratio,
a count per coupling), a dashboard chart of a daily or weekly trend for selected qubits or
couplings, or a collision map, follow the `qdash-metric-scripts` skill. `qdash_get_timeseries`
answers a trend question in chat; only a metric script puts the trend on a dashboard. Its reads
are `qdash_query` actions: `metric_script_catalog`, `metric_script_templates`,
`metric_script_template`, `metric_scripts`, `metric_script`, `dashboards`,
`dashboard`, `dashboard_templates`, `dashboard_template`. `qdash_dashboard` is a status
summary, not one of these dashboards.

## Session context

When running in pi CLI, use `qdash_config_info` if the profile or non-secret connection settings are unclear.

Use these commands to make pi behave like a QDash-specific harness with persistent session-local context:

```text
/qdash-use-profile <profile>
/qdash-use-chip [chip_id]
/qdash-use-target qid <qid> | coupling <coupling_id>
/qdash-use-agent-session <session_id>
/qdash-investigation-setup [json]
/qdash-clear-investigation
/qdash-context
/qdash-dashboard [limit]
/qdash-wiring-insights
/qdash-refresh [limit]
/qdash-clear-context
```

Prefer the current context when the user has already selected a profile/chip/session. Tools use that context when parameters are omitted.

## Cooldown-aware investigations

Treat cooldown identity as mandatory investigation context whenever comparing calibration results, coherence metrics, drift, failures, or Forum evidence across time:

1. Call `qdash_list_cooldowns` for the chip early in the investigation and record the relevant `cooldown_id`, `started_at`, and `ended_at` boundaries.
2. Assign every result or Forum observation used in a comparison to a cooldown. Prefer an explicit `cooldown_id`; when it is absent, infer membership only from the chip association and timestamp boundaries, and label it as inferred.
3. Do not describe values from different cooldowns as one continuous degradation, recovery, or before/after trend. Partition the evidence by cooldown first. Cross-cooldown comparison is allowed only when it is explicitly identified as such.
4. State plainly whether the compared evidence comes from the same cooldown, different cooldowns, or an unresolved cooldown context. Include the cooldown IDs in the report and in Forum evidence replies when relevant.
5. Same cooldown does not guarantee identical measurement conditions. If cabling, attenuation, instruments, or wiring may have changed, inspect `qdash_get_cooldown_wiring` with history or `qdash_list_cooldown_wiring_events`, then distinguish a cooldown boundary from an in-cooldown wiring change.
6. Do not treat a temporary disconnect/reconnect as a new cooldown unless QDash records a new cooldown. Describe it as an in-cooldown wiring event and report whether the wiring was nominally restored.
7. Prefer same-cooldown, temporally adjacent measurements for physical interpretation. Older-cooldown evidence may provide context but must not be used to explain a current-cooldown anomaly without an explicit caveat.

Before publishing investigated evidence, verify that every date-based claim respects these rules.

## Generic timeseries comparison

Use `qdash_compare_timeseries` when the investigation needs to align multiple
QDash metrics/targets, local CSV sensor logs, or both. For repeated calls, use
`/qdash-investigation-setup` to store the arbitrary series mappings, window,
timezone, and transform defaults; explicit tool arguments override the preset.
Do not assume a specific
CSV layout, metric name, target, unit, timestamp format, or timezone:

1. Inspect unknown CSV headers, numeric coverage, and optional time cadence with
   `qdash_inspect_timeseries_csv` first.
2. Supply `timeColumn`, one or more `valueColumns`, and optional exact-match
   `filters`; use `scale`/`offset` only for explicit unit conversion.
3. For timestamps without a zone, require an explicit
   `timezoneOffsetMinutes` (JST is `540`) rather than relying on the host clock.
4. Start with raw/no-transform comparison, then state any smoothing,
   interpolation, detrending, normalization, and period-search settings.
5. Report overlap duration, source point counts, aligned point count, number of
   observed cycles, correlations, phases, and explained fractions together.
6. Treat correlation and shared periodicity as evidence of association. Do not
   claim direct causality without intervention, longer observation, or evidence
   that excludes a common driver.

For cryostat wiring requests, start with `qdash_get_cooldown_wiring`. Pass `cooldownId` when the user names one; otherwise pass `cryoId`, or omit both to resolve the active/newest cooldown from the current/default chip. Prefer the compact `wiring.markdown`; request raw blocks only when structural or embedded BlockNote data is necessary, and request history when investigating wiring changes. Set `includeInsights` or call `qdash_wiring_insights` when the user asks what is characteristic, unusual, or worth checking in attenuation; summarize control/readout totals and affected qubits/MUXes instead of dumping the raw table.

## Configuration

Standalone pi can reuse the SDK profile created by `qdash config init`. Look for
`config.toml` under `$XDG_CONFIG_HOME/qdash/` or, by default, `~/.config/qdash/`.
An explicit `profile` selects that table. Otherwise TOML uses `default_profile`, or
`default` when unset. An explicit `configPath` selects one file. Without a TOML file,
the extension still reads `config.ini`.

When no profile or path is selected, `QDASH_BASE_URL` selects environment settings,
including `QDASH_API_TOKEN` and `QDASH_PROJECT_ID`. Use `QDASH_WEB_URL` when web links
should use a different host from the API.

## Evidence curation workflow

When the user wants to preserve an investigated observation in QDash forum/notes:

1. Inspect the task result, task figure, timeseries/history, related Forum context, and cooldown membership first.
2. Summarize the observation as evidence, not as an automatic calibration decision. State whether compared observations are from the same cooldown, and separate in-cooldown wiring changes from cooldown boundaries.
3. Prefer replying to an existing target/coupling forum thread when one exists.
4. Use `qdash_create_forum_evidence_reply` for task-result evidence so figures are embedded as QDash UI image blocks (`/api/executions/figure?path=...`) and visible in the forum.
5. For locally generated analysis images, call `qdash_preview_forum_image_reply` first, show the exact paths and reply text, then use `qdash_create_forum_image_reply` only after explicit confirmation. Supported images are PNG, JPEG, GIF, and WebP up to 5 MB each.
6. Include task and execution QDash Web URLs in the reply when applicable.
7. When mentioning history or trends, include links to representative historical task results.
8. Mark agent-authored evidence with a footer such as `— 🤖 by pi-qdash`.
9. Ask for confirmation before uploading images or creating/updating the forum post.

## Safety

- Never print tokens, passwords, Cloudflare Access secrets, or full profile contents.
- Treat write/operational endpoints (agent session/action creation, candidate commits, forum create/update, flow execute, git push/pull, re-execute, admin/auth APIs) as sensitive and ask the user before any write workflow. The steps and expert requests of an agent session the user approved with autonomy `auto`, and the commits its approval granted in `parameter_updates`, are the one exception: that approval covers them, and only them.
- Write-oriented QDash tools are approval-gated by the host: interactive pi, pi RPC, and the hosted Agent ask the user to approve each call in a dialog or card, and no tool argument approves a write. Without a UI (non-interactive pi) reviewed writes are refused; tell the user to run the write in an interactive session instead of retrying it. A request that describes the write is not that approval.
- Use `qdash_investigate` for natural-language requests to investigate, compare, or understand a target or recent calibration; it is read-only and combines recent results with target, Forum, and recommendation context.
- Use `qdash_compare_calibration` when the user asks what changed between recent calibration experiments; treat differences as evidence, not automatic approval to commit/apply parameters.
- Use `qdash_recent_calibration_figure` when the user asks to see recent experiment images without a task ID.
- Use `qdash_analyze_figure_json` for read-only numeric summaries of Plotly JSON calibration figures; keep domain-specific interpretation in the matching skill.
- Use `qdash_build_qcal_evidence` when the user wants to evaluate a QDash calibration task with pi-qcaleval. It only summarizes QDash data and returns the task figure; pass the summary as `context` to `qcal_evaluate` for the actual evaluation.
- Prefer summarizing large responses with counts, IDs, time ranges, and notable values.
