# pi-qdash

pi-qdash tools reuse the session's profile and chip when callers omit those parameters.

## Configuration

| Tool | Result |
| --- | --- |
| `qdash_config_info` | Profiles and non-secret connection settings. |

## Read-only query tools

| Tools | Result |
| --- | --- |
| `qdash_list_chips`, `qdash_get_default_chip` | Chip list and default chip. |
| `qdash_get_chip_metrics`, `qdash_list_chip_qubits`, `qdash_list_chip_couplings` | Chip metrics and targets. |
| `qdash_list_cryostats`, `qdash_list_cooldowns` | Cryostats and cooldowns. |
| `qdash_get_cooldown_wiring`, `qdash_wiring_insights`, `qdash_list_cooldown_wiring_events` | Wiring, attenuation insights, and event history. |
| `qdash_get_timeseries`, `qdash_plot_timeseries`, `qdash_inspect_timeseries_csv`, `qdash_compare_timeseries` | Timeseries retrieval, plotting, local CSV inspection, and comparison. |
| `qdash_list_task_results`, `qdash_get_task_result`, `qdash_get_task_knowledge` | Task results and full or summarized task knowledge. |
| `qdash_list_flows`, `qdash_get_flow` | Saved flows. |
| `qdash_list_executions`, `qdash_get_execution`, `qdash_wait_execution`, `qdash_compare_executions` | Execution history, status, and comparison. |
| `qdash_get_provenance_stats` | Provenance statistics. |
| `qdash_list_forum_posts`, `qdash_get_forum_post`, `qdash_list_forum_replies` | Forum posts and replies. |
| `qdash_list_source_roots`, `qdash_search_source`, `qdash_read_source` | Source trees the server serves with their revisions, literal search of contents or paths, and up to 400 numbered lines of one file. A traceback path such as `/app/qdash/workflow/x.py` is mapped onto its root. |
| `qdash_get_figure`, `qdash_get_task_figures`, `qdash_recent_calibration_figure`, `qdash_analyze_figure_json`, `qdash_build_qcal_evidence` | Figure retrieval, analysis, and evaluation evidence. |

| Tool | Return or limit |
| --- | --- |
| Figure tools | PNG figures return image content with text; JSON figures remain text. The TUI renders images and chat shows figure paths. |
| `qdash_get_cooldown_wiring` | Active or newest cooldown wiring for a cryostat or current chip; attenuation insights and raw blocks are optional. |
| `qdash_wiring_insights` | Control/readout attenuation totals, unusual totals, and MUX×4 qubit mapping for control-port anomalies. |
| `qdash_inspect_timeseries_csv` | Local CSV headers, row count, numeric ranges, and optional timestamp profile; no upload or timezone guess. |
| `qdash_compare_timeseries` | QDash and local CSV series on a bounded grid, with correlations and optional smoothing, detrending, normalization, and shared-period fit. Each CSV is limited to 10 MB and is never uploaded. |
| Timeseries comparison context | `/qdash-investigation-setup` fills omitted comparison arguments; explicit arguments win. Set `useInvestigationContext: false` to disable it for a call. |

## Overview and insight tools

| Tools | Result |
| --- | --- |
| `qdash_investigate`, `qdash_compare_calibration` | Recent calibration correlations and repeated-output comparisons. |
| `qdash_dashboard`, `qdash_dashboard_insights`, `qdash_recent_calibration_summary` | Dashboard and calibration summaries. |
| `qdash_recommend_next_action`, `qdash_triage_overview`, `qdash_target_report` | Conservative next actions, triage, and target reports. |
| `qdash_plan_calibration`, `qdash_validate_calibration` | Dry-run plan and read-only validation gates. |
| `qdash_degradation_report` | Provenance drift, changes, locks, and downstream recommendations. |

| Tool | Return or limit |
| --- | --- |
| `qdash_dashboard`, `qdash_triage_overview` | Compact boxed text in non-interactive runs and custom TUI renderers. |
| `qdash_target_report` | One target's recent results, failures, Forum posts, and a conservative next action; read-only. |
| `qdash_plan_calibration` | Dry-run runbook with safety gates. `color: true` adds ANSI colors for terminal output. |

## Agent calibration workflow tools

| Tools | Result or limit |
| --- | --- |
| `qdash_create_agent_session`, `qdash_get_agent_session` | Create or inspect a session. The `policy` object passes through to QDash; `autonomy: auto` and `max_rounds_per_target` allow an approved plan to run without per-step confirmation. |
| `qdash_submit_agent_action`, `qdash_get_agent_action`, `qdash_list_agent_actions`, `qdash_wait_agent_action` | Submit, inspect, list, and wait for actions. |
| `qdash_list_agent_action_candidates` | List candidates produced by an action. |
| `qdash_execute_agent_action` | Run an action using current calibration inputs; outputs stay staged until commit. `sourceExecutionId` records the source of a decision. |
| `qdash_commit_agent_candidate`, `qdash_commit_agent_candidate_set` | Commit one candidate or a set. |
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

## Pipeline and flow operations

| Tool | Operation |
| --- | --- |
| `qdash_get_pipeline_catalog` | List supported pipeline steps, dependencies, default task calls, step metrics, backend tasks, and the accepted spec version. |
| `qdash_plan_pipeline` | Validate a version 2 pipeline spec and return problems with paths, warnings, and the calls each step will run with their call ids and effective settings; for a version 1 spec it points to the converted spec. Does not execute. |
| `qdash_run_pipeline` (confirmation-gated) | Start a validated spec as one QDash execution. A 422 with problems is returned as text. Completed tasks persist parameters directly, without an agent candidate gate. |
| `qdash_save_flow` (confirmation-gated) | Validate, format, save, and register a Prefect `@flow` workflow. |
| `qdash_execute_flow` (confirmation-gated) | Run a saved flow with parameters. |

## Metric scripts and custom dashboards

These tools are deferred. Validation and previews execute the script on the QDash server within its time and memory limits but save nothing, so they are direct tools, not script-callable reads. The `qdash-metric-scripts` skill describes the authoring workflow and the `qdash_metrics` API.

| Tool | Operation |
| --- | --- |
| `qdash_validate_metric_script` | Compile `source` in the worker and return its metrics (id, title, unit, target, hops, parameters) or diagnostics with line numbers. |
| `qdash_preview_metric_script` | Evaluate one metric of draft `source`, or of a saved `scriptId` (optionally a `revision`), on a chip (default: the session chip) over a `period` (`{kind: "relative", days}` or `{kind: "absolute", start, end}`, default the last 14 days) with `params`. The text gives the metric, resolved period, status counts, legend, up to 12 sample cells with labels and counts, the first five errors with script lines, and truncation and log notices; `details.data` holds the full response. HTTP 422 details (`message`, `diagnostics`, `log`) and 429 (queue full) are returned as text. |
| `qdash_save_metric_script` (confirmation-gated) | Create a script, or save a new revision of `scriptId` guarded by `expectedRevision` (409 on a concurrent save). Validates first and refuses source that would not validate without asking for confirmation. Reports the revision, status, active revision, diagnostics, and the editor page URL. |
| `qdash_save_custom_dashboard` (confirmation-gated) | Create a dashboard (optionally from a `templateId`), or update `dashboardId`; `panels` replaces the whole list. Local checks reject missing names, grid overflow, and `metric_script` panels without an integer `script_revision` before confirmation. Reports pins with newer active revisions and the dashboard page URL. |

`qdash_query` reads them with the actions `metric_script_catalog`, `metric_script_templates` (without source), `metric_script_template` (`templateId`), `metric_scripts`, `metric_script` (`scriptId`), `custom_dashboards`, `custom_dashboard` (`dashboardId`), and `custom_dashboard_templates`. A single script or dashboard (`metric_script`, `custom_dashboard`) carries `_links` to its web page.

## Safety

| Contract | Behavior |
| --- | --- |
| Secret output | API tokens, passwords, and Cloudflare Access secrets are redacted. |
| Write tools | Interactive pi asks for confirmation; non-interactive calls require `confirmWrite: true`. |
| Saved profile and chip | The profile and chip selection outside a session is saved in `qdash-context.json` in pi's agent directory: `PI_CODING_AGENT_DIR` when set, otherwise `~/.pi/agent`. |
| Investigation guidance | While a `qdash_*` tool is selected, the system prompt has a `qdash_guidance` section with evidence rules and the `qdash` skill's tool routing for the tools the model can call directly or load with `tool_search`. While `codemode` or `tool_search` is active, the section also gives QDash chat's script and deferred-tool rules. |

## Scripts and deferred tools

pi-qdash applies the tool policy QDash chat uses (`extensions/lib/tool-policy.ts`) to pi's built-in `codemode` and `tool_search` tools.

| Contract | Behavior |
| --- | --- |
| Activation | For a new user, pi-qdash activates pi's `tool_search` when it has deferred tools, and `codemode`, if pi registered them and neither is `hidden`. `PI_QDASH_CODEMODE=off` skips `codemode` by default. |
| Selection | A selection the user makes is kept across reloads, new sessions, forks, and resumes, in the order below. |
| Without `tool_search` | When no `tool_search` tool is registered or it is inactive, deferred tools are registered again as direct tools, so the model can still call them without loading. |
| Deferred tools | Tools in `DEFERRED_TOOL_NAMES` (cryostat and wiring, forum, pipelines, agent workflow state, metric scripts and dashboards, source code, configuration, and similar) use `exposure: "deferred"`. The model loads them with `tool_search`; the routing guide marks them with `*`. |
| Script data | In a `codemode` script, the audited reads in `NESTED_READ_TOOL_NAMES` resolve to their redacted response data as JSON. A call returning more than 512 KiB of JSON fails with a request to narrow it. |
| Script limits | Scripts without `timeout_ms` get 120 seconds; longer deadlines are cut to 300 seconds. |
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
| `/skill:qdash-calibration-agent` | Confirmation-gated calibration workflows. |
| `/skill:qdash-two-qubit-calibration-diagnosis` | Diagnose two-qubit calibration from read-only evidence. |
| `/skill:qdash-timeseries-diagnosis` | Investigate multi-metric drift and local sensor series. |
| `/skill:qdash-metric-scripts` | Write, validate, preview, and save metric scripts and put them on custom dashboards; `references/api.md` documents the `qdash_metrics` API. |
