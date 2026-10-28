# Tool Reference

pi-qdash registers the following tools with pi. All tools reuse the current
session profile/chip context when their parameters are omitted.

## Configuration

- `qdash_config_info`: inspect profiles and non-secret connection settings

## Read-only query tools

- `qdash_list_chips`, `qdash_get_default_chip`
- `qdash_get_chip_metrics`, `qdash_list_chip_qubits`, `qdash_list_chip_couplings`
- `qdash_list_cryostats`, `qdash_list_cooldowns`
- `qdash_get_cooldown_wiring`, `qdash_wiring_insights`, `qdash_list_cooldown_wiring_events`
- `qdash_get_timeseries`, `qdash_plot_timeseries`, `qdash_inspect_timeseries_csv`, `qdash_compare_timeseries`
- `qdash_list_task_results`, `qdash_get_task_result`
- `qdash_get_task_knowledge`: fetch full markdown or a concise structured summary for interpreting a task's expected result and failure modes
- `qdash_list_flows`, `qdash_get_flow`
- `qdash_save_flow`, `qdash_execute_flow` (confirmation-gated): save a Prefect flow the agent wrote as a QDash workflow (QDash validates the `@flow` function, formats the file, and registers its deployment), and run a saved flow with parameters
- `qdash_get_pipeline_catalog`, `qdash_plan_pipeline`: list the step types and tasks for a calibration pipeline spec, and validate a spec (problems with paths, resolved tasks per step) without running it
- `qdash_list_executions`, `qdash_get_execution`, `qdash_wait_execution`, `qdash_compare_executions`
- `qdash_get_provenance_stats`
- `qdash_list_forum_posts`, `qdash_get_forum_post`, `qdash_list_forum_replies`
- `qdash_preview_forum_evidence_reply`, `qdash_preview_forum_image_reply`
- `qdash_get_figure`, `qdash_get_task_figures`, `qdash_recent_calibration_figure`, `qdash_analyze_figure_json`, `qdash_build_qcal_evidence`

The three figure tools return an image figure to the model as image content
alongside the text summary, so a vision model can read the curve itself; JSON
figures stay text. The interactive TUI renders the same image, and QDash's chat
shows the figure paths from the tool details inline.

`qdash_get_cooldown_wiring` resolves the active/newest cooldown automatically
from a cryostat or the current/default chip, and returns compact human-readable
wiring markdown with opt-in attenuation insights. `qdash_wiring_insights`
focuses on those insights: it parses the wiring table, totals control/readout
attenuation, highlights unusual totals, and maps control-port anomalies to
qubits using the MUX×4 convention. Raw BlockNote blocks and wiring checkpoint
history are opt-in to keep the normal response focused.

`qdash_inspect_timeseries_csv` profiles an explicitly selected local CSV before
comparison: headers, row count, numeric coverage/ranges/samples, and optional
timestamp validity/range/cadence. It does not guess a timezone or upload data.

`qdash_compare_timeseries` is a generic read-only comparison helper. It can
combine any number of QDash task-result parameters/targets with numeric columns
from one or more local CSV files. CSV schema, exact-match row filters, timestamp
format, timezone offset, units, scale, and offset are supplied by the caller;
no metric, target, sensor name, or timezone is hard-coded. It aligns series on
a bounded common grid and reports pairwise correlations, optional smoothing,
linear detrending, z-score normalization, and an optional shared-period
sinusoidal fit with phase differences and explained fractions. The output
always warns that correlation/shared periodicity do not prove causality and
that short or smoothed records reduce statistical independence. Local CSV
inputs are limited to 10 MB each and are never uploaded. Missing comparison
arguments can be supplied by the schema-validated session preset created with
`/qdash-investigation-setup`; explicit tool arguments always take precedence,
and `useInvestigationContext: false` disables the preset for one call.

## Overview and insight tools

- `qdash_investigate`: natural-language-friendly read-only correlation of recent calibration, target history, failures, and Forum context
- `qdash_compare_calibration`: compare repeated calibration output parameters
- `qdash_dashboard`, `qdash_dashboard_insights`
- `qdash_recent_calibration_summary`
- `qdash_recommend_next_action`
- `qdash_triage_overview`
- `qdash_target_report`: target-level read-only incident/operations report
- `qdash_plan_calibration`: safe dry-run calibration plan; never executes
- `qdash_validate_calibration`: post-task validation gates; read-only
- `qdash_degradation_report`: provenance drift, changes, lock, and downstream recommendations

`qdash_dashboard` and `qdash_triage_overview` provide boxed compact text output
for non-interactive runs and custom TUI renderers for nicer interactive tool
results. `qdash_target_report` correlates one qubit/coupling's recent task
results, failures, open Forum posts, and a conservative next-action
recommendation; it is read-only and never executes calibration.
`qdash_plan_calibration` turns that evidence into a confirmation-gated dry-run
runbook with explicit safety gates. Pass `color: true` to emit ANSI-colored
text output in terminal-oriented non-interactive usage.

## Agent calibration workflow tools

- `qdash_create_agent_session`, `qdash_get_agent_session` — the `policy` object is passed to QDash as is;
  `autonomy: auto` plus `max_rounds_per_target` lets an approved plan run without per-step confirmation
  (see the `qdash-calibration-agent` skill, "Autonomous plan").
- `qdash_submit_agent_action`
- `qdash_get_agent_action`, `qdash_list_agent_actions`, `qdash_wait_agent_action`
- `qdash_list_agent_action_candidates`
- `qdash_execute_agent_action` — runs the action's task the way the Task Workbench does: inputs
  from the current calibration state, outputs staged until a candidate is committed.
  `sourceExecutionId` is optional and only records what the action was decided from.
- `qdash_commit_agent_candidate`, `qdash_commit_agent_candidate_set`
- `qdash_get_agent_candidate_commit`, `qdash_apply_agent_candidate_commit`, `qdash_wait_agent_candidate_apply`

## Forum and figure tools

Forum read tools render compact boxed summaries for list/detail/reply views.
Figure tools fetch calibration PNG/JSON figures by path or task result through
qdash-client helpers, and render images in interactive TUI. `qdash_analyze_figure_json`
fetches Plotly JSON figures and summarizes numeric scatter/heatmap traces for
read-only agentic diagnosis; domain-specific conclusions belong in skills.
`qdash_build_qcal_evidence` summarizes a task result as evidence for
pi-qcaleval's `qcal_evaluate`: the text names the task, the target, the sweep
(read from the recorded run parameters, with units and point counts) and the
other run settings, and goes in as `context`; the task figure is returned as
image content so the evaluation can see the plot without a second fetch. The
fitted output parameters and the calibration inputs are left out of the text
unless `includeMetrics` / `includeInputs` is set, since the evaluation model is
meant to read the plot; the details carry them all (`runParameters`, `sweeps`,
`inputParameters`, `metricRecords`).

Forum evidence can be previewed read-only with
`qdash_preview_forum_evidence_reply`, then published through
confirmation-gated `qdash_create_forum_evidence_reply`. Locally generated PNG,
JPEG, GIF, or WebP analysis images can be checked with
`qdash_preview_forum_image_reply`, then uploaded and embedded with
confirmation-gated `qdash_create_forum_image_reply` (up to eight images, 5 MB
each). Other forum writes include `qdash_create_forum_post` and
`qdash_update_forum_post`. The evidence helpers build markdown replies, keep
figures visible in the forum, and mark replies with `— 🤖 by pi-qdash`.

Calibration pipelines are declarative: `qdash_get_pipeline_catalog` lists the
step types QDash accepts (with their dependencies and default task lists) and
the backend's tasks by type, `qdash_plan_pipeline` validates a spec and returns
problems with paths into the spec plus the exact tasks each step will run, and
confirmation-gated `qdash_run_pipeline` starts the validated spec as one QDash
execution. Completed tasks write their calibrated parameters to QDash directly,
with no agent candidate gate, so it is not a fallback for a failed agent action.
The spec is sent as-is; QDash owns validation, and a 422 with
problems is reported as text rather than raised. Follow the execution with
`qdash_wait_execution`.

Links in tool output point at the QDash web UI. Set `QDASH_WEB_URL` when the
UI is not reachable at the API base URL minus `/api` (a deployment where the
API is an internal hostname); otherwise that derivation is used.

## Fallback tools

- `qdash_query`: fallback for read-only queries that do not yet have a dedicated tool
- `qdash_raw_get`: call read-only GET endpoints not covered by `qdash_query` through the qdash-client transport

## Safety

Secrets such as `api_token`, passwords, and Cloudflare Access secrets are
redacted from tool output. Write-oriented agent/forum workflow tools are
approval-gated: interactive pi shows a confirmation prompt, and
non-interactive runs require `confirmWrite: true`.
