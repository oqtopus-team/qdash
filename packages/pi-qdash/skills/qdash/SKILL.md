---
name: qdash
description: Query a running QDash instance from pi via the pi-qdash extension and @oqtopus-team/qdash-client. Use when inspecting chips, metrics, task results, tasks, projects, files, flows, executions, forum posts, provenance, or QDash profile/configuration.
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
   - `qdash_get_timeseries`, `qdash_plot_timeseries` — inspect one target metric over time
   - `qdash_inspect_timeseries_csv`, `qdash_compare_timeseries` — validate and compare multiple QDash or CSV timeseries
   - `qdash_list_task_results`, `qdash_get_task_result` — find and inspect calibration results
   - `qdash_get_task_knowledge` — interpret a task's purpose, expected result, failure modes, and check questions
   - `qdash_list_flows`, `qdash_get_flow` — list or inspect calibration flows
   - `qdash_get_pipeline_catalog`, `qdash_plan_pipeline` — compose and check a calibration pipeline spec before running it
   - `qdash_list_executions`, `qdash_get_execution`, `qdash_wait_execution`, `qdash_compare_executions` — inspect, await, or compare executions
   - `qdash_get_provenance_stats` — inspect provenance status
   - `qdash_list_forum_posts`, `qdash_get_forum_post`, `qdash_list_forum_replies` — inspect Forum context
   - `qdash_preview_forum_evidence_reply`, `qdash_preview_forum_image_reply` — preview evidence or image replies without writing
   - `qdash_get_figure`, `qdash_get_task_figures`, `qdash_recent_calibration_figure`, `qdash_analyze_figure_json`, `qdash_build_qcal_evidence` — inspect or package figure evidence
2. Read-only overview and planning tools:
   - `qdash_dashboard`, `qdash_dashboard_insights`, `qdash_triage_overview` — summarize status, insights, and investigation priorities
   - `qdash_investigate`, `qdash_target_report`, `qdash_compare_calibration` — investigate target history and compare calibrations
   - `qdash_recent_calibration_summary`, `qdash_recommend_next_action` — summarize outcomes and recommend a safe next action
   - `qdash_degradation_report`, `qdash_plan_calibration`, `qdash_validate_calibration` — inspect drift, plan work, and validate results
3. Confirmation-gated write tools (the harness asks the user before running them):
   - `qdash_create_agent_session`, `qdash_submit_agent_action`, `qdash_execute_agent_action` — create or execute a scoped agent workflow
   - `qdash_commit_agent_candidate`, `qdash_commit_agent_candidate_set` — commit reviewed candidate parameters
   - `qdash_apply_agent_candidate_commit` — apply a reviewed candidate commit
   - `qdash_create_forum_post`, `qdash_update_forum_post` — create or update Forum content
   - `qdash_create_forum_evidence_reply`, `qdash_create_forum_image_reply` — publish previously reviewed evidence replies
   - `qdash_run_pipeline` — run a validated pipeline spec as one execution
   - `qdash_save_flow`, `qdash_execute_flow` — save a Prefect flow you wrote as a QDash workflow, and run a saved flow (see Authoring a flow)
4. Agent workflow state tools:
   - `qdash_get_agent_session`, `qdash_get_agent_action`, `qdash_list_agent_actions`, `qdash_wait_agent_action` — inspect agent workflow state
   - `qdash_list_agent_action_candidates`, `qdash_get_agent_candidate_commit`, `qdash_wait_agent_candidate_apply` — inspect candidates and apply status
5. `qdash_query` — fallback for read-only operations without a dedicated tool.
6. `qdash_raw_get` — last-resort read-only GET for an uncovered endpoint.

## Composing a calibration pipeline

A calibration pipeline spec is a JSON description of one calibration run: targets, an ordered list of steps, and run parameters. QDash validates it against the chip, backend, and task catalog and runs it as one execution. The spec can only name the step types and tasks QDash exposes; it cannot contain code.

Workflow:

1. `qdash_get_pipeline_catalog` — read the step types (with what each needs from an earlier step and its default task list), the one-qubit modes, and the task names by type. Use only names from this catalog.
2. Turn the request into steps. Start from the catalog defaults and the flow templates (`qdash_query` with `flow_templates`, then `flow_template` for one template's task list): `OneQubitCheck` and `OneQubitFineTune` carry the standard one-qubit sequences, `TwoQubitCalibration` the two-qubit chain. Use `CustomOneQubit` / `CustomTwoQubit` only where the user wants a different task list, and keep the task order the templates use.
3. `qdash_plan_pipeline` — validate. A result with problems is not an error: each problem carries a path into the spec (`steps[2].tasks[0]`, `targets.qids[1]`); fix it and plan again until it is valid.
4. Show the user the resolved steps and task counts from the plan, then `qdash_run_pipeline` with the same `chipId` and `spec`. The execution is confirmation-gated. Say that completed tasks write their calibrated parameters to QDash directly; there is no candidate gate, so inside an agent calibration session use the session's actions instead.
5. `qdash_wait_execution` with the returned `execution_id`. It returns when the whole run has finished, not just its first step. Then summarize which targets passed and which failed, fetch the figures of failed tasks with `qdash_get_task_figures` so the user sees them, and read `qdash_get_task_knowledge` for any task whose result needs interpretation.

Rules:

- Targets are either `qids` or `mux_ids` (with optional `exclude_qids`), never both. Prefer MUX targets for more than a few qubits; hardware scheduling works per MUX.
- `FilterByStatus` and `FilterByMetric` are only valid after a one-qubit step. Put a filter before any two-qubit step.
- Put values into `task_run_parameters` only when the user asked for them; otherwise leave QDash's defaults.
- A pipeline takes the project execution lock. Check `qdash_list_executions` for a running execution before starting one.
- Prefer short pipelines (one or two steps) when the next step depends on the result: run, inspect results and figures, then compose the next spec. Calibrated parameters persist in QDash between executions, so a later spec continues from the earlier one. Retries and branches are your decision between executions, not something the spec expresses.

## Authoring a flow

A flow is a Python module with one `@flow` function that QDash runs on its workflow worker, with hardware and database access. Pipelines (above) cover ordered task lists without code; write a flow only when the user needs logic a pipeline cannot express: loops until convergence, branching on results, custom parameter sweeps.

Workflow:

1. Start from what exists. `qdash_query` with `flow_templates` lists the templates and `flow_template` returns one with its code; `qdash_get_flow` returns a saved flow; `flow_helper_files` / `flow_helper_file` show the helpers templates import. Keep the template's structure: its imports, the `@flow` signature, and the terminal handling at the end of the run.
2. Write the module. Name the `@flow` function like the flow unless the user wants otherwise. Task and parameter names must come from `qdash_get_pipeline_catalog` and the template; do not invent them. When a shell workspace is available, draft the file there and run `python -m py_compile` on it before showing it.
3. Show the user the complete code and the chip it is for, then `qdash_save_flow`. QDash checks the `@flow` function, formats the file, registers a Prefect deployment, and replaces a flow of the same name. A rejection comes back as text with QDash's reason; fix the code and save again.
4. Saving does not run anything. Run it only when the user asks: `qdash_execute_flow` with the flow's parameters (confirmation-gated, takes the project execution lock), then `qdash_wait_execution`.

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

The extension uses `@oqtopus-team/qdash-client` and supports:

- `QDASH_*` environment variables (`QDASH_BASE_URL`, `QDASH_API_TOKEN`, `QDASH_PROJECT_ID`, etc.)
- `QDASH_WEB_URL`: the QDash web UI address used for links in tool output, when it differs from the API base URL (for example inside a deployment where the API is reached by an internal hostname)
- `$XDG_CONFIG_HOME/qdash/config.ini`
- `~/.config/qdash/config.ini`
- explicit `profile` / `configPath` parameters

If `QDASH_BASE_URL` is set and no profile is specified, the tools default to environment variables. Otherwise they use profile `default`.

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
- Treat write/operational endpoints (agent session/action creation, candidate commits, forum create/update, flow execute, git push/pull, re-execute, admin/auth APIs) as sensitive and ask the user before any write workflow.
- Write-oriented QDash tools are approval-gated. In interactive pi, let the extension prompt for confirmation. In non-interactive runs, set `confirmWrite: true` only after explicit user confirmation.
- Use `qdash_investigate` for natural-language requests to investigate, compare, or understand a target or recent calibration; it is read-only and combines recent results with target, Forum, and recommendation context.
- Use `qdash_compare_calibration` when the user asks what changed between recent calibration experiments; treat differences as evidence, not automatic approval to commit/apply parameters.
- Use `qdash_recent_calibration_figure` when the user asks to see recent experiment images without a task ID.
- Use `qdash_analyze_figure_json` for read-only numeric summaries of Plotly JSON calibration figures; keep domain-specific interpretation in the matching skill.
- Use `qdash_build_qcal_evidence` when the user wants to evaluate a QDash calibration task with pi-qcaleval. It only summarizes QDash data and returns the task figure; pass the summary as `context` to `qcal_evaluate` for the actual evaluation.
- Prefer summarizing large responses with counts, IDs, time ranges, and notable values.
