# pi-qdash

pi-qdash gives pi CLI and QDash Agent tools for calibration data and approved operations.
Omitted profile and chip arguments use the session selection.

## Configuration

For standalone use, install pi and the extension:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi install npm:@oqtopus-team/pi-qdash
```

Start `pi`, then run `/qdash-setup <profile> <chip_id>` with your saved profile and chip.
`/qdash-dashboard` should show that chip's current data; check `/qdash-config` if it cannot connect.
QDash web Agent includes the extension already.

`qdash_config_info` shows non-secret connection settings. Use
[client profiles](./clients/typescript.md#connect-to-a-deployment) for credentials.
Set `QDASH_WEB_URL` if the web UI is not the API base URL without `/api`.

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

Lists are paginated: task results and executions accept `skip` and `limit` (1–100).
Executions require one chip and support `date` (`YYYYMMDD`) and `timezone`, not flow/status filters.
Task history has no date filter; use task results with `startFrom` and `startTo` for a period.
See [client contracts](./clients/typescript.md#high-level-client) for response shapes.

Timeseries parameters use exact stored names. Local CSV comparison never uploads files; each file
is limited to 10 MB. `qdash_current_time` reads the tool host's clock, not hardware time; give an
IANA zone explicitly for local time. Source reads return at most 400 numbered lines.

## Overview and insight tools

| Tools | Result |
| --- | --- |
| `qdash_investigate`, `qdash_compare_calibration` | Recent calibration correlations and repeated-output comparisons. |
| `qdash_dashboard`, `qdash_dashboard_insights`, `qdash_recent_calibration_summary` | Status, insight, and calibration summaries. They do not read or change custom dashboards. |
| `qdash_recommend_next_action`, `qdash_triage_overview`, `qdash_target_report` | Conservative next actions, triage, and target reports. |
| `qdash_plan_calibration`, `qdash_validate_calibration` | Dry-run plan and read-only validation gates. |
| `qdash_degradation_report` | Provenance drift, changes, locks, and downstream recommendations. |

These are read-only summaries. The dashboard tools above do not change custom dashboards.
`qdash_compare_calibration` follows [compareLatest](./clients/typescript.md#compare-a-target-s-latest-results).

## Agent calibration loop tools

| Tool | Purpose |
| --- | --- |
| `qdash_list_agent_sessions` | List sessions; defaults to your active or paused sessions |
| `qdash_get_agent_session_context` | Read scope, budget, candidates, intervention, and permitted next step |
| `qdash_run_agent_session_step` | Run one authorized task on one qubit; record its decision before dispatch |
| `qdash_request_agent_human` | Pause and ask an expert; consumes no action budget |
| `qdash_commit_agent_session_update` | Commit an accepted candidate under the session's parameter-update grant |
| `qdash_record_agent_decision` | Append audit reasoning; changes no session state |
| `qdash_end_agent_session` | Request completion or stop, with per-call confirmation |
| `qdash_get_agent_session_audit` | Read an audit snapshot; default 50 events, maximum 200 per page |
| `qdash_wait_agent_intervention` | Wait for an answer; timeout defaults to 900 seconds, maximum 3600 |

Session-granted execution requires the signed-in creator's approved `auto` session, remaining
budget, and no work in flight. Commits additionally require a matching `parameter_updates` grant;
backend application requires `apply_backend`. Missing grants or unconfirmed decisions block the
write. Replayed calls reuse their records.

A timeout leaves the session paused. Ending a session does not cancel work already admitted.
No pi-qdash tool answers or resumes an intervention; the expert does that in QDash.
See [Agent Calibration](../user-guide/agent-calibration.md).

## Agent calibration workflow tools

| Tools | Purpose |
| --- | --- |
| `qdash_create_agent_session`, `qdash_get_agent_session` | Create an approved scope or inspect it |
| `qdash_submit_agent_action`, `qdash_get_agent_action`, `qdash_list_agent_actions`, `qdash_wait_agent_action` | Propose and track actions |
| `qdash_list_agent_interventions` | Read expert questions and answers |
| `qdash_list_agent_action_candidates` | Inspect staged outputs |
| `qdash_execute_agent_action` | Measure using current inputs; leave outputs staged |
| `qdash_commit_agent_candidate`, `qdash_commit_agent_candidate_set` | Commit reviewed candidates |
| `qdash_get_agent_candidate_commit`, `qdash_apply_agent_candidate_commit`, `qdash_wait_agent_candidate_apply` | Inspect and apply a commit |

The creation tool accepts no numeric override bounds or quality gates. Its approved task checks
determine candidate acceptance; `evaluation` can be `off` or `required`. The confirmation shows
the full grant. Ordinary write tools require per-call review.

## Calibration session tools

A calibration session groups work toward an objective; it grants no execution permission.

| Tool | Purpose |
| --- | --- |
| `qdash_create_calibration_session` | Create an objective on a chip, after confirmation |
| `qdash_get_calibration_session` | Read runs, experiments, recommendation, and outcomes |
| `qdash_record_calibration_decision` | Append the creator's decision and evidence |
| `qdash_get_calibration_session_audit` | Read an audit snapshot; default 100, maximum 500 events per page |
| `qdash_list_calibration_sessions` | List objectives; default 20, maximum 100 |

Use `calibrationSessionId` to associate a run with your open session on the same chip.
Otherwise QDash creates an automatic session. Audit records distinguish measured evidence from
reported reasoning; they do not establish the current hardware state.

## Pipeline and flow operations

| Tool | Purpose |
| --- | --- |
| `qdash_get_pipeline_catalog` | Get step types, task documentation, and spec schema |
| `qdash_plan_pipeline` | Validate a version 2 spec without running it |
| `qdash_run_pipeline` | Start a validated pipeline after confirmation |
| `qdash_save_flow` | Validate, save, and register a workflow after confirmation |
| `qdash_execute_flow` | Run a saved workflow after confirmation |

Launch tools return an execution ID without waiting. Pipelines save accepted outputs directly;
they do not use agent candidate gates. An overlapping session waiting for an expert blocks a
launch, as does an inability to check sessions. Replayed launch calls reuse their run; an unknown
launch outcome must be investigated, never retried blindly.

## Metric scripts and dashboards

| Tool | Purpose |
| --- | --- |
| `qdash_validate_metric_script` | Compile draft source and return metrics or diagnostics |
| `qdash_preview_metric_script` | Evaluate a draft or saved metric without saving |
| `qdash_save_metric_script` | Save after validation and confirmation; `expectedRevision` guards edits |
| `qdash_save_dashboard` | Save after confirmation; `expectedVersion` guards edits |

Validation and preview execute code on the server, so call them directly, not inside scripts.
Series previews need 1–16 targets. Dashboard panels pin a script revision; updating `panels`
replaces the entire list. HTTP 409 means a concurrent save: reload before editing again.
`qdash_query` reads script and dashboard catalogs, templates, and saved records.

## Forum and figure tools

| Tool | Purpose |
| --- | --- |
| `qdash_analyze_figure_json` | Summarize Plotly scatter and heatmap data |
| `qdash_build_qcal_evidence` | Assemble task context and figures for evaluation |
| `qdash_preview_forum_evidence_reply`, `qdash_preview_forum_image_reply` | Preview a reply without publishing |
| `qdash_create_forum_evidence_reply`, `qdash_create_forum_image_reply` | Publish after confirmation |
| `qdash_create_forum_post`, `qdash_update_forum_post` | Create or update a post after confirmation |

Image replies accept at most eight PNG, JPEG, GIF, or WebP files, at most 5 MB each.

## Fallback tools

`qdash_query` provides other reads. Its file actions cover calibration configuration only;
use source tools for code. `qdash_raw_get` reaches other read-only GET endpoints.

## Safety

Credentials are redacted. Reviewed writes show all arguments and require confirmation; without
a UI they are refused. A model's `confirmWrite` argument grants nothing. Changed arguments or a
cancelled turn invalidate approval. Session-granted writes remain limited to their approved scope.

## Scripts and deferred tools

`tool_search` loads specialist tools. `codemode` batches audited reads as JSON; writes, figures,
shell tools, and unaudited calls are blocked. Call them directly. A script result is limited to
512 KiB; the default timeout is 120 seconds, capped at 300.

Tool selections persist across sessions. `PI_QDASH_CODEMODE=off` disables default activation.
Without `tool_search`, deferred tools become directly available. Load only one copy of pi-qdash;
script access fails closed when tool identity cannot be verified.

## Evaluation hydration

With pi-qcaleval installed, pi-qdash supplies missing task knowledge, matching figures, and requested
examples to `qcal_evaluate`. It skips figures belonging to other tasks. Explicit valid criteria
are preserved; `details.hydration` records origins without image bytes or knowledge text.

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
| `/skill:qdash` | Select tools and protect credentials |
| `/skill:qdash-agent-calibration` | Work within an approved agent session |
| `/skill:qdash-chip-bringup` | Prepare capture delay and spectroscopy |
| `/skill:qdash-one-qubit-calibration` | Calibrate and recover one-qubit tasks |
| `/skill:qdash-two-qubit-calibration` | Calibrate directed pairs |
| `/skill:qdash-zx90-optimization` | Search within approved bounds; each pipeline needs approval |
| `/skill:qdash-characterization` | Measure coherence, transitions, noise, and coupling |
| `/skill:qdash-rabi-after-configure` | Check the Rabi prerequisite and trace inputs |
| `/skill:qdash-timeseries-diagnosis` | Investigate drift and sensor data |
| `/skill:qdash-metric-scripts` | Author metrics and dashboards |
