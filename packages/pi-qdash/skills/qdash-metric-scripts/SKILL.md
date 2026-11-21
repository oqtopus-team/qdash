---
name: qdash-metric-scripts
description: Write, check, preview and save QDash metric scripts (Python using the qdash_metrics API) and put them on dashboards. Use whenever the user wants a dashboard, a dashboard panel, a custom or derived metric, a per-qubit or per-coupling analysis, a map or table of something across the chip, a median, mean, minimum, count or trend of a metric over a period ("median ZX90 fidelity over the last 14 days per coupling", "show T2/T1 per qubit", "how many readout measurements per qubit this week"), frequency collision checks or a collision map, or when they have a metric script open in the QDash editor, even if they never say "script".
---

<!-- Confirmation gates are implemented by the host harness. Skills should state that a gate exists, not instruct how or when to ask for confirmation. -->

# QDash metric scripts

A metric script is a Python module that QDash runs on its own server, in a bounded worker
process, to turn calibration data into one value per qubit or per directed qubit pair. Custom
dashboards show those values as chip maps and tables. Scripts define the computation; a
dashboard's `metric_script` panel says which script, metric, period and parameters to show.

The full `qdash_metrics` API, with its data semantics, is in
[references/api.md](references/api.md). The three shipped templates are summarised in
[references/templates.md](references/templates.md). Read the API reference before writing
anything beyond a one-line change: the period, pair-direction and unit rules below are where
plausible-looking scripts go wrong.

## Tools

- `qdash_query` actions (read-only): `metric_script_catalog` (the metrics a script can read,
  with unit and scale), `metric_script_templates` / `metric_script_template` (`templateId`),
  `metric_scripts` / `metric_script` (`scriptId`), `dashboards` / `dashboard`
  (`dashboardId`), `dashboard_templates`.
- `qdash_validate_metric_script` `{source}`: compiles the script in the worker and returns its
  metrics or diagnostics with line numbers. Nothing is saved and no data is read.
- `qdash_preview_metric_script` `{source | scriptId, metricId, chipId?, period?, params?}`:
  evaluates one metric on a chip and summarises the cells. It runs the code on the server
  within the time and memory limits but persists nothing; `details.data` has every cell.
- `qdash_save_metric_script` and `qdash_save_dashboard`: confirmation-gated writes
  (the harness asks the user). The script save validates first and refuses source that would
  not validate.

These are deferred tools in the web Agent: load them with `tool_search` when they are not
offered.

## Authoring workflow

1. **Find the data.** Call `qdash_query` `metric_script_catalog` and pick metric names from it.
   `ctx.data[name]` only accepts catalog names; an unknown name fails every cell. Note whether
   the metric is a qubit or a coupling metric, its unit, and its scale.
2. **Start from something that works.** Prefer an existing script (`metric_scripts`, then
   `metric_script`) or a template (`metric_script_template`) over a blank file. The
   `zx90_median` template is the pattern for "aggregate raw observations over a period per
   coupling"; `getting_started` shows latest values, topology and history; `collision` shows
   categorical verdicts with explained cells.
3. **Write the module.** One `@metric` function per value the user wants, with an honest
   `title` and the `unit` the value is in. Return `CellResult` with `assessment["count"]` for
   anything aggregated, so a median of one observation does not look like a median of fifty.
   Expose thresholds the user may want to tune as `Parameter`s instead of constants.
4. **Validate** with `qdash_validate_metric_script` and fix every diagnostic. Validation only
   compiles and registers the metrics; data problems appear only when the script runs.
5. **Preview** with `qdash_preview_metric_script` on the user's chip and the period they asked
   about. Read the status counts, not only the values: many `missing` cells usually mean the
   period holds no data for those targets, many `error` cells mean a bug (the summary gives the
   script line). Say what the period actually resolved to.
6. **Show the code** and the preview summary to the user, then save with
   `qdash_save_metric_script` when they want it kept. New scripts are private unless the user
   asks to share them with the project.
7. **Optionally add it to a dashboard** with `qdash_save_dashboard`: a `metric_script`
   panel pinned to the saved script's `active_revision` (see below). On update, read the
   dashboard first and send the complete panel list; omitted panels are removed.

When the user asks a one-off question ("what is the median ZX90 fidelity per coupling this
week?"), a draft preview answers it without saving anything. Offer to save only if they want
to see it again.

## Rules that change the numbers

These come from how the runtime reads data; getting them wrong produces a confident wrong map.

- **The period bounds everything.** `latest()` is the newest accepted value inside the period,
  never an older one; `history()` defaults to the period. A relative period ("last 14 days")
  is resolved when the metric is evaluated, so a saved panel moves with time. Absolute
  periods need a timezone.
- **Pairs are directed.** A pair metric runs once for `0>1` and once for `1>0`.
  `ctx.data[coupling_metric][pair]` reads exactly `source-target` with no reverse fallback, so
  a coupling measured only as `1-0` is missing for `0>1`. That is deliberate: ZX90 and CR
  results belong to a direction. `ctx.coupling_strength(a, b)` is the one undirected lookup.
- **Excluded results are skipped** by `history()` unless `include_excluded=True`, and never
  appear in `latest()`. Do not include them unless the user asks to.
- **Units and scale are applied once.** Values arrive as pint Quantities with the catalog unit
  and scale already applied (for example a fidelity stored as 0.99 arrives as 99 %). Convert
  with `.to("percent")` or `.to("MHz")` and take `.magnitude`; never multiply by the scale
  again.
- **Aggregate raw observations.** `history()` returns one record per task result. Compute the
  median or mean of those, not of daily or pre-aggregated values, and report the count.
- **Missing is not zero.** Raise `MissingData` (or let `latest()` raise it) when an input is
  absent; return `None` for a target the metric deliberately skips; return
  `CellResult(None, assessment={...})` to show why a target has no value (for example too few
  samples). Never return 0 as a stand-in.

## Revisions: last-good and pinned

Every save creates a revision. A revision that validates becomes the *active* revision; one
that does not is stored with its diagnostics while the previous active revision stays in use
(last-good). A script with no valid revision cannot be used by panels.

Dashboard panels pin `script_revision`. Saving a script never changes what an existing
dashboard shows; the dashboard response marks panels whose script has a newer active revision
(`latest_revision`), and an editor moves the pin deliberately. When you create or update a
panel, pin the script's current `active_revision` and say which revision it shows. Do not move
someone else's pins as a side effect of saving a script.

Sharing follows two rules: a project-visible dashboard cannot use a private script (QDash
rejects the save), and copying a script makes a private copy of its active revision without
retargeting any panel.

## When the script is open in the editor

If the page context says the user has a metric script open in the Metric script editor, the
editor's current text (saved or not) is in the prompt. Work on that text:

- Check it by passing it as `source` to `qdash_validate_metric_script` and
  `qdash_preview_metric_script`.
- Change it with `propose_code_edit` and the complete new file. The user sees a diff, applies
  it in the editor and saves when ready.
- Do not call `qdash_save_metric_script` for that script unless the user asks you to save; a
  save from the Agent would replace the draft in front of them.

## When a dashboard is open

If the page context says the user has a dashboard open that they may edit, or is
composing a new one, the dashboard's unsaved draft is in the prompt as JSON. Work on that draft:

- Change it with `propose_code_edit` and the complete new draft as JSON. The user sees a diff,
  applies it to the page's draft, reviews the panels and saves when ready.
- Always send the `panels` list, every panel included; a draft without it is refused. For a new
  dashboard that starts from a starter template, set `template_id` and `panels: []`: the page
  previews the template's panels, and Save creates the dashboard with them.
- Keep each unchanged panel's `panel_id` and pinned `script_revision`; move a pin only when the
  user asks.
- A `metric_script` panel references a saved script and revision. When no saved script computes
  what the user asked for, write and preview one as in the authoring workflow, save it with
  `qdash_save_metric_script` (a confirmation-gated write), and only then propose a panel that
  references it. A draft never creates a script on its own; the one exception is a starter
  template, whose shared script QDash adds when the user saves the dashboard, as the page tells
  them before they save.
- Do not call `qdash_save_dashboard` for that dashboard unless the user asks you to save,
  and never change its sharing.

## Limits and failures

Scripts can import only `numpy`, `scipy`, `math`, `statistics` and `qdash_metrics`;
`open`, `exec`, `eval` and similar builtins are disabled, and there is no network or API
access. A run has a wall-clock timeout (60 s by default), a memory cap and bounded output;
history reads are capped at 5,000 records per call, 2,000 data requests per evaluation and a
400-day span.

- A per-cell error (`status: error` with a line number) is a bug or a cap hit for that target;
  the other cells are still valid. Fix the line, or narrow the period for a cap.
- A whole-run failure (HTTP 422 with `message`, `diagnostics`, `log`) means the script did not
  load, the metric or a parameter is invalid, or the run hit the timeout or memory limit.
- HTTP 429 means the evaluation queue is full; wait and retry instead of changing the code.
- HTTP 503 means the metric script runner (the `metric-runner` container) is not available or stopped mid-run; nothing was saved. Tell the user to retry later or ask an administrator; do not change the code.
- HTTP 409 on save means the script changed since the revision you read (`expectedRevision`);
  read it again and merge rather than overwrite.

The import filter is a guardrail for trusted project editors, not a sandbox. Do not try to
work around it; if a script needs something it blocks, tell the user.
