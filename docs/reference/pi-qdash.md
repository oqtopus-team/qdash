# pi-qdash

pi-qdash registers the following tools with pi. All tools reuse the current
session profile/chip context when their parameters are omitted.

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
| `qdash_get_pipeline_catalog`, `qdash_plan_pipeline` | Pipeline catalog and validation without execution. |
| `qdash_list_executions`, `qdash_get_execution`, `qdash_wait_execution`, `qdash_compare_executions` | Execution history, status, and comparison. |
| `qdash_get_provenance_stats` | Provenance statistics. |
| `qdash_list_forum_posts`, `qdash_get_forum_post`, `qdash_list_forum_replies` | Forum posts and replies. |
| `qdash_preview_forum_evidence_reply`, `qdash_preview_forum_image_reply` | Read-only Forum reply previews. |
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
| Figure tools | Calibration PNG or JSON figures by path or task result; PNG figures render in the TUI. |
| `qdash_analyze_figure_json` | Numeric summaries of Plotly scatter and heatmap traces. |
| `qdash_build_qcal_evidence` | Task, target, sweep, and run settings as evaluation context plus the figure as image content. `includeMetrics` and `includeInputs` add fitted outputs and inputs to text; details retain all records. |
| `qdash_preview_forum_evidence_reply`, `qdash_preview_forum_image_reply` | Read-only previews of evidence or locally generated analysis images. |
| `qdash_create_forum_evidence_reply`, `qdash_create_forum_image_reply` | Confirmation-gated replies. Image replies accept up to eight PNG, JPEG, GIF, or WebP images of at most 5 MB each. |
| `qdash_create_forum_post`, `qdash_update_forum_post` | Confirmation-gated Forum writes. |

Set `QDASH_WEB_URL` when the web UI is not at the API base URL minus `/api`.

## Fallback tools

| Tool | Result |
| --- | --- |
| `qdash_query` | Read-only queries without a dedicated tool. |
| `qdash_raw_get` | Read-only GET endpoints through qdash-client. |

## Pipeline and flow operations

| Tool | Operation |
| --- | --- |
| `qdash_get_pipeline_catalog` | List supported pipeline steps, dependencies, default tasks, and backend tasks. |
| `qdash_plan_pipeline` | Validate a pipeline spec and return problems with paths and the tasks each step will run; does not execute. |
| `qdash_run_pipeline` (confirmation-gated) | Start a validated spec as one QDash execution. A 422 with problems is returned as text. Completed tasks persist parameters directly, without an agent candidate gate. |
| `qdash_save_flow` (confirmation-gated) | Validate, format, save, and register a Prefect `@flow` workflow. |
| `qdash_execute_flow` (confirmation-gated) | Run a saved flow with parameters. |

## Safety

| Contract | Behavior |
| --- | --- |
| Secret output | API tokens, passwords, and Cloudflare Access secrets are redacted. |
| Write tools | Interactive pi asks for confirmation; non-interactive calls require `confirmWrite: true`. |

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
