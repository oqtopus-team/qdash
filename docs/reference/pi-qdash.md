# pi-qdash

pi-qdash tools reuse the session's profile and chip when callers omit those parameters.

## Configuration

| Tool | Result |
| --- | --- |
| `qdash_config_info` | Profiles and non-secret connection settings. |

## Read-only query tools

| Tools | Result |
| --- | --- |
| `qdash_current_time` | Current UTC time, and the local time and offset in an IANA time zone when one is named. Needs no QDash connection or approval. |
| `qdash_list_chips`, `qdash_get_default_chip` | Chip list and default chip. |
| `qdash_get_chip_metrics`, `qdash_list_chip_qubits`, `qdash_list_chip_couplings` | Chip metrics and targets. |
| `qdash_list_cryostats`, `qdash_list_cooldowns` | Cryostats and cooldowns. |
| `qdash_get_cooldown_wiring`, `qdash_wiring_insights`, `qdash_list_cooldown_wiring_events` | Wiring, attenuation insights, and event history. |
| `qdash_get_timeseries`, `qdash_inspect_timeseries_csv`, `qdash_compare_timeseries` | Timeseries retrieval, local CSV inspection, and comparison. |
| `qdash_list_task_results`, `qdash_get_task_result`, `qdash_get_task_knowledge` | Task results and full or summarized task knowledge. |
| `qdash_list_flows`, `qdash_get_flow` | Saved flows. |
| `qdash_list_executions`, `qdash_get_execution`, `qdash_wait_execution`, `qdash_compare_executions` | Execution history, status, and comparison. |
| `qdash_get_provenance_stats` | Provenance statistics. |
| `qdash_list_forum_posts`, `qdash_get_forum_post`, `qdash_list_forum_replies` | Forum posts and replies. |
| `qdash_list_source_roots`, `qdash_search_source`, `qdash_read_source` | Source trees the server serves with their revisions, literal search of contents or paths, and up to 400 numbered lines of one file. A traceback path such as `/app/qdash/workflow/x.py` is mapped onto its root. |
| `qdash_get_figure`, `qdash_get_task_figures`, `qdash_recent_calibration_figure`, `qdash_analyze_figure_json`, `qdash_build_qcal_evidence` | Figure retrieval, analysis, and evaluation evidence. |

| Tool | Return or limit |
| --- | --- |
| `qdash_list_task_results` | One page, newest first: `{ items, total, skip, limit, status_counts }`, with no output parameters in `items`. `limit` is an integer from 1 to 100 and `skip` 0 or more; other values fail before any request with advice to page by `skip`. `qid` and `couplingId` both filter by one exact stored ID. |
| `qdash_get_chip_metrics` | `qubit_metrics[metric][qid]` and `coupling_metrics[metric][couplingId]` hold `{ value, task_id, execution_id, stddev }`; `value` can be `null`, a target without a value is absent, and values carry no timestamp. |
| `qdash_get_timeseries` | `{ data }`, where `data[qid]` lists points oldest first with `value`, `error`, `unit`, `calibrated_at`, `execution_id`, and `task_id`. `data` is an object even with `qid` set; a target without points is absent. `parameter` is the exact stored name, with no aliases. |
| Checked responses | The three tools above and the matching `qdash_query` actions check each response against its documented shape (`extensions/lib/query-contracts.ts`) and fail with the differing path instead of returning a malformed response. |
| `qdash_list_executions` | One chip's executions, newest first: `{ executions, total }`. `chipId` defaults to the active or default chip. Only `skip`, `limit` (1 to 100), `date` (YYYYMMDD), and `timezone` filter it; `flowName`, `status`, or an out-of-range value fails before any request, as does the `qdash_query` `executions` action. |
| `qdash_query` `qubit_history`, `coupling_history` | Every result of one task (`task` or `taskName`) for one target, newest first: `{ name, data }` keyed by task ID. They take no `date`; a `date` fails before any request, with advice to use `task_results` with `startFrom` and `startTo` for one period. |
| `qdash_compare_calibration` | The SDK's [`compareLatest`](./clients/typescript.md#compare-a-target-s-latest-results): for each task name, the two newest of up to `limit` (default 20, clamped to 2 to 100) list rows, compared by output-parameter `value` read from each result's detail. A task whose detail read fails or does not match its row is `unavailable` with `changes: null`; a task with one result is listed in `insufficient`. |
| Figure tools | PNG figures return image content with text; JSON figures remain text. The TUI renders images and chat shows figure paths. |
| `qdash_get_cooldown_wiring` | Active or newest cooldown wiring for a cryostat or current chip; attenuation insights and raw blocks are optional. |
| `qdash_wiring_insights` | Control/readout attenuation totals, unusual totals, and MUX×4 qubit mapping for control-port anomalies. |
| `qdash_current_time` | Read from the operating system clock of the host running the tool (the pi CLI machine or the web Agent's container) at every call; not the QDash server's or the measurement hardware's clock, and not checked against a time service. Without `timeZone` the answer is UTC; the host's or container's zone and the user's language are never used as the user's zone. An unknown or non-IANA name such as `+09:00` is refused. |
| `qdash_inspect_timeseries_csv` | Local CSV headers, row count, numeric ranges, and optional timestamp profile; no upload or timezone guess. |
| `qdash_compare_timeseries` | QDash and local CSV series on a bounded grid, with correlations and optional smoothing, detrending, normalization, and shared-period fit. Each CSV is limited to 10 MB and is never uploaded. |
| Timeseries comparison context | `/qdash-investigation-setup` fills omitted comparison arguments; explicit arguments win. Set `useInvestigationContext: false` to disable it for a call. |

## Overview and insight tools

| Tools | Result |
| --- | --- |
| `qdash_investigate`, `qdash_compare_calibration` | Recent calibration correlations and repeated-output comparisons. |
| `qdash_dashboard`, `qdash_dashboard_insights`, `qdash_recent_calibration_summary` | Status, insight, and calibration summaries. They do not read or change custom dashboards. |
| `qdash_recommend_next_action`, `qdash_triage_overview`, `qdash_target_report` | Conservative next actions, triage, and target reports. |
| `qdash_plan_calibration`, `qdash_validate_calibration` | Dry-run plan and read-only validation gates. |
| `qdash_degradation_report` | Provenance drift, changes, locks, and downstream recommendations. |

| Tool | Return or limit |
| --- | --- |
| `qdash_dashboard`, `qdash_triage_overview` | Compact boxed text in non-interactive runs and custom TUI renderers. |
| `qdash_target_report` | One target's recent results, failures, Forum posts, and a conservative next action; read-only. |
| `qdash_plan_calibration` | Dry-run runbook with safety gates. `color: true` adds ANSI colors for terminal output. |

## Agent calibration loop tools

These tools carry the model-driven loop of the `qdash-agent-calibration` skill. All are deferred.

| Tool | Result or limit |
| --- | --- |
| `qdash_list_agent_sessions` | Sessions of the current project, newest first: status, chip, qubits, tasks, autonomy, actions used, expiry, and the intervention a paused session waits on. Defaults to your own `active` and `waiting_for_human` sessions; `chipId`, `statuses`, `mine`, and `limit` (default 10, at most 100) narrow it. Read-only. |
| `qdash_get_agent_session_context` | One session's state from QDash: scope, budget, expiry, `state` (`ready`, `in_flight`, `waiting_for_expert`, `resume_needs_plan_runner`, `confirm_each`, `budget_exhausted`, `expired`, `ended`), `may_run_step`, `next`, every action with its execution and the candidates of up to 10 recent completed runs, each with its `standing` (`accepted`, `not_in_scope` for an output the session neither grants from that task nor bounds, which is reference only and blocks nothing, `outside_bounds`, or `quality_gate`) and whether the update grant names it, and the newest intervention with its question, attempts, the expert's decision and guidance, and the actions since the answer. Read-only. |
| `qdash_run_agent_session_step` (session-granted) | Propose one `run_task` on one qubit with optional overrides and dispatch it; the rationale is recorded as the action's diagnosis. Runs only in an `active` session with `autonomy: auto` that the signed-in user created (`GET /auth/me`), with budget left and nothing in flight; another user's session, or a user QDash cannot confirm, is refused before any write. It refuses before QDash a task, qubit, override, or reconfiguration outside the session, a task and qubit at `max_rounds_per_target`, and an exact repeat of a finished measurement unless `repeatOfActionId` names it. The proposal and dispatch are sent with `autonomous: true`, so QDash repeats those checks against its own records; a QDash refusal (403 or 409) is returned as `Not run:` text, and a server whose action has no `autonomous` field gets no dispatch. An authorized action that was never dispatched is dispatched instead of proposing a new one. Before the dispatch it records a decision with the optional `assessment` (`pass`, `fail`, `inconclusive`) and `interpretation` (default: the rationale) on `evidenceActionIds` (default: the finished results no decision cites yet), linked to the proposed action; the first step, with no evidence and no interpretation, records none. It dispatches only after QDash confirms the decision: a refused decision (including a full audit), no answer, or a 5xx returns `Not dispatched:` text, leaves the action authorized, and a later call with the same task, qubit, and overrides reuses the action without recording the decision twice. Without the session's decision list, a step that follows a finished result is refused before it proposes anything. Commits nothing. |
| `qdash_request_agent_human` (session-granted) | Record an intervention with `reason`, `summary`, `question`, and the actions in `attemptActionIds` (at most 20, with their executions). QDash pauses the session and notifies Slack when configured. Runs only in an `auto` session the signed-in user created that is active and idle or out of budget, and is sent with `autonomous: true`; uses no action budget. Then records a `request_human` decision with the summary, the optional `assessment`, and the attempts, linked to the intervention; a decision QDash does not store is reported as not recorded (`decisionRecorded: false`) and does not undo the pause or the notification. |
| `qdash_commit_agent_session_update` (session-granted) | Commit one accepted candidate (`actionId`, `parameterName`) in a session whose `policy.parameter_updates` grants that parameter and the action's task, and apply it when the grant includes `apply_backend`. Runs only for the session's creator, in an active `auto` session with nothing in flight, for a completed action. Records a `pass` decision with `interpretation` and optional `evaluationIds` on that action first, then sends the commit with `autonomous: true` and the `decision_id`, and the apply with `autonomous: true` and no GitHub push. A missing grant (including a QDash release that does not return it), a rejected or missing candidate, an unrecorded decision, or a QDash refusal returns `Not committed:` text. A replayed call returns the same commit. |
| `qdash_record_agent_decision` (session-granted) | Append a decision to the session's audit: optional `assessment`, `interpretation` (2000 characters), `nextAction` (`next_task`, `repeat`, `adjust_and_retry`, `rollback`, `propose_commit`, `request_human`, `skip_target`, `complete`, `stop`), and optional `nextDetail`, `evidenceActionIds`, `evaluationIds`, `nextActionId`, `interventionId`, `supersedesDecisionId`. Runs only for the session's creator, in any session status and autonomy; changes no session state. A replayed call returns the same record. |
| `qdash_end_agent_session` (reviewed write) | End a session with `outcome` `stopped` (a stop request; QDash sets `cancelled`) or `completed` (an authorized `complete_session`, which needs no action budget), and a `reason` (2000 characters) recorded in the audit. The user approves each call. Then reads the session back and reports the status QDash holds, the measurements, commits, and backend applies that passed the session gate before the end and still run (QDash does not cancel them), the expert questions the stop closed, and the session page `/agent-sessions/<id>?project=<project>`. For the session's creator it also records the `stop` or `complete` decision. A refused end is reported as not ended; an unanswered one as not confirmed. A decision with `nextAction` `stop` or `complete` alone changes no session state. |
| `qdash_get_agent_session_audit` | One page of a snapshot of the session's chronological audit (default 50 events, at most 200), with each event's source and missing facts, the `snapshot_id`, and the cursor of the next page until the snapshot is complete. When the records changed since the first page, it tells the model to discard the pages and start again without a cursor. Read-only. |
| `qdash_wait_agent_intervention` | Wait until the session leaves `waiting_for_human` or its intervention is answered, then return the same result as `qdash_get_agent_session_context`. Timeout defaults to 900 seconds and is capped at 3600; the poll interval defaults to 15 seconds and is at least 5. Each poll is bounded by the remaining time (at least one second) and by cancellation, and a poll's late answer is dropped. A timeout is an error that says the session stays paused. Read-only. |

A session-granted tool runs without a per-call confirmation in both pi CLI and QDash chat, because the user who created the `auto` session approved it; its idempotency key derives from the tool call id, so a replayed call reuses the action or intervention it created. Neither tool answers, resumes, or reactivates an intervention, and no pi-qdash tool does.

## Agent calibration workflow tools

| Tools | Result or limit |
| --- | --- |
| `qdash_create_agent_session`, `qdash_get_agent_session` | Create or inspect a session. The `policy` object passes through to QDash; `autonomy: auto` and `max_rounds_per_target` allow an approved plan to run without per-step confirmation, and `parameter_updates` (`parameters`, `tasks`, `apply_backend`) grants commits of passing results without per-commit confirmation and needs no bounds. `evaluation` is `off` (default) or `required`. The policy takes no numeric bounds or quality gates: `allowed_overrides`, `task_quality_gates`, and `quality_gates` are refused before the confirmation and before any QDash call, even when empty, so a session created here overrides no task input and accepts each granted output on its task's own completion checks. `parameter_updates.tasks` outside `allowed_tasks` is also refused before the confirmation. The confirmation lists the granted fields, the evaluation mode, that the policy holds no bounds or gates, and that each granted parameter's task's own checks decide. An `auto` session is refused while one of the user's sessions on the chip is paused for the same qubits. The session, and each action, decision, and intervention the loop tools record, carries the provider and model ID of the host's current model, never a tool argument; see [Model identity](../developer-guide/agent/agentic-calibration.md#experiment-audit). |
| `qdash_submit_agent_action`, `qdash_get_agent_action`, `qdash_list_agent_actions`, `qdash_wait_agent_action` | Submit, inspect, list, and wait for actions. An authorized `request_human` action records an intervention and pauses the session until an expert answers in QDash. |
| `qdash_list_agent_interventions` | List a session's interventions: the reason, question, expert decision and guidance, and resume blockers; read-only. |
| `qdash_list_agent_action_candidates` | List candidates produced by an action. |
| `qdash_execute_agent_action` | Run an action using current calibration inputs; outputs stay staged until commit. `sourceExecutionId` records the source of a decision. |
| `qdash_commit_agent_candidate`, `qdash_commit_agent_candidate_set` | Commit one candidate or a set with per-call confirmation. |
| `qdash_get_agent_candidate_commit`, `qdash_apply_agent_candidate_commit`, `qdash_wait_agent_candidate_apply` | Inspect, apply, and wait for candidate commits. |

## Forum and figure tools

| Tool | Return or limit |
| --- | --- |
| Forum read tools | Compact boxed list, detail, and reply summaries. |
| `qdash_analyze_figure_json` | Numeric summaries of Plotly scatter and heatmap traces. |
| `qdash_build_qcal_evidence` | Task, target, sweep, and run settings as evaluation context plus the figure as image content. `includeMetrics` and `includeInputs` add fitted outputs and inputs to text; details retain all records. |
| `qdash_preview_forum_evidence_reply`, `qdash_preview_forum_image_reply` | Read-only previews of evidence or locally generated analysis images. |
| `qdash_create_forum_evidence_reply`, `qdash_create_forum_image_reply` | Confirmation-gated replies. Image replies accept up to eight PNG, JPEG, GIF, or WebP images of at most 5 MB each. |
| `qdash_create_forum_post`, `qdash_update_forum_post` | Confirmation-gated Forum writes. |

Set `QDASH_WEB_URL` when the web UI is not at the API base URL minus `/api`.

## Fallback tools

| Tool | Result |
| --- | --- |
| `qdash_query` | Read-only queries without a dedicated tool. `files_tree` and `file_content` cover only the calibration config directory. `files_tree` takes no `path`; supplying one returns source-tool guidance. `file_content` preserves successful config reads and returns guidance only for source-looking paths that produce HTTP 400 or 404. Other errors, including HTTP 403 and server errors, propagate. |
| `qdash_raw_get` | Read-only GET endpoints through qdash-client. |

## Calibration session tools

A calibration session records one calibration objective on one chip and groups the pipeline runs and agent sessions started with its ID; it grants nothing. All five tools are deferred. See [Calibration Sessions](../developer-guide/agent/calibration-sessions.md) and [Calibration Session Audit](../developer-guide/agent/calibration-session-audit.md).

| Tool | Result or limit |
| --- | --- |
| `qdash_create_calibration_session` (confirmation-gated) | Create a session for `objective` (at most 500 characters) on `chipId` or the default chip and return its ID. The confirmation says that it starts and grants nothing. |
| `qdash_get_calibration_session` | One session: objective, status, each pipeline run with its dispatch status, who requested it and any reported launch origin, and every step execution, each agent session with its status and executions, and what still runs or waits; then the recorded experiments with measured gate time, fidelity, CR duration and amplitude, and hardware time, requested changes the task did not execute, the recommendation, and the latest requested run with its recorded execution outcome and whether its requested candidate is the recommended one; it never states the hardware state, since QDash records no authoritative hardware write. Read-only. |
| `qdash_record_calibration_decision` (session-granted) | Append a decision to the session's audit: optional `assessment`, `interpretation` (2000 characters), `nextAction` (the agent decision values), optional `nextDetail`, `evidenceRunIds`, `evidenceTaskIds`, `evidenceDecisionIds`, `supersedesDecisionId`, an `experiment` (`candidateId`, `stage`, `target`, `requestedChanges` with `taskName`, `parameter`, `value`, optional `previous` and `callId`) with `next_task`, `repeat`, or `adjust_and_retry`, or a `conclusion` (`outcome`, `recommendedCandidateId`) with `complete` or `stop`. QDash records it only for the session's creator, in any status, and checks every reference; the model comes from the host. The idempotency key derives from the tool call id, so a replayed call returns the same record. Starts nothing. |
| `qdash_get_calibration_session_audit` | One page of a snapshot of the session's audit (default 100 events, at most 500) as numbered lines with each event's kind, source, and facts not recorded, and the cursor of the next page. Read-only. |
| `qdash_list_calibration_sessions` | Sessions of the current project, newest first; `chipId`, `mine`, `openOnly`, and `limit` (default 20, at most 100) narrow it. Read-only. |

`qdash_run_pipeline` and `qdash_create_agent_session` take an optional `calibrationSessionId`; QDash accepts it only for an open session on the same chip that the signed-in user created. `qdash_run_pipeline` also takes `decisionId`, only with `calibrationSessionId`: the decision of that session the run carries out, shown in its confirmation. QDash refuses a decision whose coupling target (such as `0-1`) has no two-qubit step in the spec, or no manual round measuring that pair in that direction.

## Pipeline and flow operations

| Tool | Operation |
| --- | --- |
| `qdash_get_pipeline_catalog` | List supported pipeline steps, dependencies, default task calls, step metrics, backend tasks, the accepted spec version, and the first sentence of each documented task's description. `taskNames` adds the full description, when to use, and prerequisites for the named tasks, lists named tasks without declared documentation, and lists each named task's declared inputs and outputs with units from `GET /tasks`, or says why that list could not be read. |
| `qdash_plan_pipeline` | Validate a version 2 pipeline spec and return problems with paths, warnings, and the calls each step will run with their call ids and effective settings; for a version 1 spec it points to the converted spec. Does not execute. |
| `qdash_run_pipeline` (confirmation-gated) | Start a validated spec as one QDash execution and return its execution ID without waiting. A 422 with problems is returned as text. Completed tasks persist parameters directly, without an agent candidate gate. Nothing starts while one of your agent sessions on the chip waits for an expert and covers a target of the spec; MUX targets count as overlapping. Nothing starts either when QDash cannot list the sessions, including a release without `GET /agent-sessions` (404 or 405). With `calibrationSessionId`, QDash records the run in that calibration session under the idempotency key `qdash_run_pipeline:<tool call id>`, so a replayed call reports the run it started (`Already started`) instead of starting another; a run whose launch outcome QDash reports as unknown is reported with advice to check the executions, never retried. Every launch sends the tool's own `reported_origin` (`agent_tool`, `qdash_run_pipeline`, `pi-qdash`), which no argument sets; QDash shows it as reported, not verified. |
| `qdash_save_flow` (confirmation-gated) | Validate, format, save, and register a Prefect `@flow` workflow. |
| `qdash_execute_flow` (confirmation-gated) | Run a saved flow with parameters and return its execution ID without waiting. The name is letters, digits and underscores. Nothing starts while one of your agent sessions waits for an expert on the flow's `chip_id` and `qids` parameters; when they are absent, any such session blocks. Nothing starts either when QDash cannot list the sessions, including a release without `GET /agent-sessions` (404 or 405). |

## Metric scripts and dashboards

These tools are deferred. Validation and previews execute the script on the QDash server within its time and memory limits but save nothing, so they are direct tools, not script-callable reads. The `qdash-metric-scripts` skill describes the authoring workflow and the `qdash_metrics` API.

| Tool | Operation |
| --- | --- |
| `qdash_validate_metric_script` | Compile `source` in the worker and return its metrics (id, title, unit, target, result kind, hops, parameters) or diagnostics with line numbers. |
| `qdash_preview_metric_script` | Evaluate one metric of draft `source`, or of a saved `scriptId` (optionally a `revision`), on a chip (default: the session chip) over a `period` (`{kind: "relative", days}` or `{kind: "absolute", start, end}`, default the last 14 days) with `params`. A series metric needs `targets` (1 to 16 qubit IDs or directed pairs such as `"0>1"`) and is evaluated for those only. The text gives the metric, resolved period, status counts, legend, up to 12 sample cells with labels and counts, the first five errors with script lines, and truncation and log notices; for a series metric it gives each target's point counts by status, value range, points resting on one observation, and its first and last points. `details.data` holds the full response. HTTP 422 details (`message`, `diagnostics`, `log`), 429 (queue full) and 503 (metric script runner not available) are returned as text. |
| `qdash_save_metric_script` (confirmation-gated) | Create a script, or save a new revision of `scriptId` guarded by `expectedRevision` (409 on a concurrent save). Validates first and refuses source that would not validate without asking for confirmation. Reports the revision, status, active revision, diagnostics, and the editor page URL. |
| `qdash_save_dashboard` (confirmation-gated) | Create a dashboard (optionally from a `templateId`; the confirmation and the result name any project-visible starter script that creation adds), or update `dashboardId` guarded by `expectedVersion` (409 when the dashboard changed); `panels` replaces the whole list. Local checks reject missing names, grid overflow, and `metric_script` panels without an integer `script_revision`, with an unknown `view`, or with `targets` that do not fit the view (a `timeseries` view needs 1 to 16, `map` and `table` take none) before confirmation. Reports pins with newer active revisions and the dashboard page URL. |

`qdash_query` reads them with the actions `metric_script_catalog`, `metric_script_templates` (without source), `metric_script_template` (`templateId`), `metric_scripts`, `metric_script` (`scriptId`), `dashboards`, `dashboard` (`dashboardId`), `dashboard_templates`, and `dashboard_template` (`templateId`: the panels a starter template would create now and the shared scripts creation would add, without writing). A single script or dashboard (`metric_script`, `dashboard`) carries `_links` to its web page.

## Safety

| Contract | Behavior |
| --- | --- |
| Secret output | API tokens, passwords, and Cloudflare Access secrets are redacted. |
| Write tools | Interactive pi and pi RPC ask for confirmation of each call, showing all of its arguments (and, for `qdash_create_agent_session`, the session grant). Interactive pi shows them in a scrollable review: `y` approves only after the last line has been shown, and `n` or Esc declines. pi RPC sends the complete text to the client's confirmation. Without a UI (`pi -p`, `--mode json`) a reviewed write is refused. The approval covers that call once: arguments that change after the dialog showed them, a cancelled turn, or arguments that are not plain JSON data stop the call. No argument approves a write; a `confirmWrite` a model sets is ignored. The session-granted tools `qdash_run_agent_session_step` and `qdash_request_agent_human` (`SESSION_GRANTED_WRITE_TOOL_NAMES`) ask nothing and act only inside an `auto` session the signed-in user created and approved; `qdash_commit_agent_session_update` also needs that approval's `parameter_updates` grant; `qdash_record_agent_decision` asks nothing and only appends to the audit of a session the signed-in user created. `qdash_end_agent_session` is a reviewed write. |
| Saved profile and chip | The profile and chip selection outside a session is saved in `qdash-context.json` in pi's agent directory: `PI_CODING_AGENT_DIR` when set, otherwise `~/.pi/agent`. |
| Investigation guidance | While a `qdash_*` tool is selected, the system prompt has a `qdash_guidance` section with evidence rules, rules for plain-language requests, and the `qdash` skill's tool routing for the tools the model can call directly or load with `tool_search`. While `codemode` or `tool_search` is active, the section also gives QDash chat's script and deferred-tool rules. |

## Scripts and deferred tools

pi-qdash applies the tool policy QDash chat uses (`extensions/lib/tool-policy.ts`) to pi's built-in `codemode` and `tool_search` tools.

| Contract | Behavior |
| --- | --- |
| Activation | For a new user, pi-qdash activates pi's `tool_search` when it has deferred tools, and `codemode`, if pi registered them and neither is `hidden`. `PI_QDASH_CODEMODE=off` skips `codemode` by default. |
| Selection | A selection the user makes is kept across reloads, new sessions, forks, and resumes, in the order below. |
| Without `tool_search` | When no `tool_search` tool is registered or it is inactive, deferred tools are registered again as direct tools, so the model can still call them without loading. |
| Deferred tools | Tools in `DEFERRED_TOOL_NAMES` (cryostat and wiring, forum, pipelines, agent workflow state, metric scripts and dashboards, source code, configuration, and similar) use `exposure: "deferred"`. The model loads them with `tool_search`; the routing guide marks them with `*`. |
| Script data | In a `codemode` script, the audited reads in `NESTED_READ_TOOL_NAMES` resolve to their redacted response data as JSON. A tool with a checked response declares that shape as its output schema, so `describeTool()` and the script tool listing show it. A call returning more than 512 KiB of JSON fails with a request to narrow it. |
| Script limits | Scripts without `timeout_ms` get 120 seconds; longer deadlines are cut to 300 seconds. |
| Namespace | Every `qdash_*` tool pi-qdash registers belongs to the `qdash` tool namespace (`QDASH_TOOL_NAMESPACE`), unless it states its own. pi's `codemode` lists it under `## qdash` with a one-line description when it lists QDash tools, `describeNamespace("qdash")` returns its instructions and the tools scripts can call, and `searchTools()` searches both. QDash chat declares the same namespace. |
| Blocked from scripts | Write tools, figure tools, `qdash_raw_get`, and other unaudited QDash tools are model-only or blocked. While pi-qdash is loaded, a script may call another extension's tool only when it declares `readOnlyHint` and is not destructive; `bash`, `powershell`, `write`, and `edit` are always blocked. Call these tools directly. |
| Name collisions | A tool another extension registers under a `qdash_*` or reviewed write name is blocked from scripts, whatever its annotations. A QDash name keeps script access only while pi's `getAllTools()` reports the `parameters` object pi-qdash registered, from pi-qdash's extension entry file (`extensions/lib/extension-identity.ts`). |
| Missing identity | Without pi's registry or a file source for a tool, scripts reach no QDash tool. A second loaded copy of pi-qdash sees the first copy's tools as foreign, so load one copy. |

At each session start, pi-qdash decides `codemode` and `tool_search` separately; the first rule that applies wins:

1. A reload keeps the active tools.
2. The session's branch: pi's own tool loadout records, which pi restores itself, or the latest `pi-qdash-tool-selection` entry, which pi-qdash appends when a run starts or the session ends with a selection the branch does not record.
3. For a new session or fork whose branch records nothing, the selection the replaced session had when it ended. Persisted sessions pair by session file and in-memory forks by session manager. A new in-memory session with no matching session file or manager uses its own settings and defaults.
4. A `defaultTools` setting entry: `codemode` or `+codemode` activates, `-codemode` leaves it inactive; the same for `tool_search`.
5. The default activation above.

## Evaluation hydration

When pi-qcaleval is installed, pi-qdash fills each `qcal_evaluate` call the model makes before it runs, with the rules QDash chat uses (`extensions/lib/qcal-hydration.ts`).

| Argument | Source |
| --- | --- |
| `images` | Newest figure of the session's active branch that belongs to `task_name`. A figure recorded for another task is skipped, and so is an unlabeled figure older than it. Placeholders and base64 that is not a PNG, JPEG, GIF, or WebP image are dropped. |
| `knowledge`, `criteria` | Missing `knowledge` is filled from the task's QDash reference. Valid explicit `criteria` are preserved; otherwise the reference supplies them. |
| `examples` | The task's labeled examples when `use_examples` is `true` and the call passes none. |
| Record | `details.hydration` lists the figure origin and count, the figure's task result, the reference source, and the example count; it holds no bytes or text. |

The reference and examples come from one knowledge request as the configured QDash user. Figure tools record `taskId` and `taskName` in their details so the figure can be matched.

## Commands

| Command | Effect |
| --- | --- |
| `/qdash-setup [profile] [chip_id]` | Set session profile and chip, refresh footer status, and open the dashboard. |
| `/qdash-use-profile <profile>` | Select the active profile. |
| `/qdash-use-chip [chip_id]` | Select the active chip. |
| `/qdash-use-target qid <qid> \| coupling <coupling_id>` | Select an investigation target. |
| `/qdash-use-agent-session <session_id>` | Select an agent session. |
| `/qdash-investigation-setup [json]` | Set a session-local timeseries comparison preset. Local CSV paths do not enter global profile/chip context. |
| `/qdash-clear-investigation` | Clear the comparison preset without changing the profile or chip. |
| `/qdash-context` | Show current session context. |
| `/qdash-dashboard [limit]` | Show the dashboard. |
| `/qdash-target-report qid <qid> \| coupling <coupling_id>` | Show a target report. |
| `/qdash-plan-calibration` | Show a dry-run calibration plan. |
| `/qdash-degradation-report` | Show the degradation report. |
| `/qdash-wiring-insights` | Show wiring insights. |
| `/qdash-refresh [limit]` | Refresh the dashboard. |
| `/qdash-clear-context` | Clear session context. |
| `/qdash-config [profile]` | Show non-secret configuration. |

## Skills

| Skill | Purpose |
| --- | --- |
| `/skill:qdash` | Choose QDash tools and avoid exposing secrets. |
| `/skill:qdash-chip-bringup` | Run first-time bring-up from capture delay correction through resonator and qubit spectroscopy with the `box_setup`, `bringup`, and `check_waveform` flow templates. |
| `/skill:qdash-one-qubit-calibration` | Choose, run, and recover single-qubit calibration with the `coarse_one`, `fine_one`, `one_qubit`, full calibration, and `simple` flow templates. |
| `/skill:qdash-two-qubit-calibration` | Choose a two-qubit template by pair selection, run the CR and ZX90 chain, and diagnose poor two-qubit quality. |
| `/skill:qdash-zx90-optimization` | Search one directed coupling for a shorter, high-fidelity ZX90 within user-approved bounds and hardware-time budget: one `CheckCrossResonance` run key changed per ordinary pipeline, a progress message before and after each experiment and during long waits, and a final comparison against the incumbent. The search advances only within active chat turns, each pipeline needs its own write approval, and the skill cannot cancel an execution. |
| `/skill:qdash-characterization` | Measure or remeasure coherence, EF transitions, noise, coupling, and gate coherence limits with the `coherence_check`, `characterization`, `ef_calibration`, and `coherence_limit` flow templates. |
| `/skill:qdash-rabi-after-configure` | Check that a `CheckRabi` runs after the latest `Configure` or `ConfigureAll` and before T1, T2 echo, Ramsey, and other Rabi-normalized tasks, and trace the Rabi inputs of suspect results. |
| `/skill:qdash-timeseries-diagnosis` | Investigate multi-metric drift and local sensor series. |
| `/skill:qdash-metric-scripts` | Write, validate, preview, and save metric scripts and put them on dashboards; `references/api.md` documents the `qdash_metrics` API. |
