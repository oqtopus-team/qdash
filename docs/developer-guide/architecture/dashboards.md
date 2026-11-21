# Dashboards Architecture

Dashboards store a layout of typed panels per project and owner; metric panels read live
chip data through the metrics endpoints, and `metric_script` panels evaluate a pinned revision
of a user-authored [metric script](./metric-scripts.md). The user procedures are
[Dashboards](../../user-guide/dashboards.md) and
[Metric Scripts](../../user-guide/metric-scripts.md).

## Responsibility boundary

The API owns persistence, visibility, and validation of dashboards and metric scripts. It stores
no measured values and no computed results: a dashboard describes what to show, a script defines
how to compute it, and every panel evaluates when it renders. The metric script runtime owns
code execution: the API's executor and data broker (`src/qdash/api/metric_runtime/`) and the
`metric-runner` container, described in [Metric Scripts](./metric-scripts.md).
The UI owns layout editing, the script editor, and rendering of evaluation results.

## Documents

`DashboardDocument` (`src/qdash/dbmodel/dashboard.py`, collection
`dashboard`) holds `project_id`, `dashboard_id` (`dash_<12 hex>`), the owner's `user_id`
and `username` snapshot, `name`, `description`, `visibility`, an optional default `chip_id`,
`panels`, and `version`, a write counter that every update compares and increments. The unique
index is `(project_id, dashboard_id)`.

`MetricScriptDocument` (`src/qdash/dbmodel/metric_script.py`, collection `metric_script`) holds
`project_id`, `script_id` (`ms_<12 hex>`), owner `user_id` and `username`, `name` (at most 120
characters), `description`, `visibility`, and the revision state:

| Field | Meaning |
| --- | --- |
| `source`, `revision`, `status`, `diagnostics` | The latest saved text, its number (incremented on every save), and its validation result (`valid` or `invalid`) |
| `active_revision`, `active_source`, `metrics` | The last revision that validated, its text, and its catalog (`MetricInfo`: id, title, unit, target, hops, parameters, has_legend); `None` until a revision validates |
| `revisions` | `MetricScriptRevision` entries `{revision, source, created_at, status, metrics}` |
| `pins` | `ScriptPin` entries `{revisions, shared, writer}` keyed by `dashboard_id`: the revisions each dashboard pins, whether that dashboard is project-visible, and the token of the dashboard write that last widened the pin |
| `version` | Write counter; every save, pin change, and deletion compares it and every write increments it |
| `template_id` | The template the script was created from, if any |

The unique index is `(project_id, script_id)`; `(project_id, template_id)` serves the template
lookup below.

## Panels

The shared panel models live in `src/qdash/datamodel/dashboard.py`:

| Model | Meaning |
| --- | --- |
| `PanelLayoutModel` | `x`, `y`, `w`, `h` on a 12-column grid; `x + w <= 12`, `1 <= h <= 12` |
| `DashboardPanelModel` | `panel_id` (unique within the dashboard), `type`, `title`, `layout`, `config` |
| `QubitMetricPanelConfig`, `CouplingMetricPanelConfig` | `metric` key from the metrics configuration |
| `MetricScriptPanelConfig` | `script_id`, `metric_id`, `script_revision` (required), `period`, `params`, `view` (`map`, `table` or `timeseries`), `targets` (series metrics: up to 16 cell keys such as `5` or `5>6`, normalized on save), `direction` (`both`, `forward`, `reverse`), `hops` (subset of `[1, 2]`); extra keys are rejected |
| `MarkdownPanelConfig` | `content`, at most 20000 characters |

`config` is stored as a dictionary so the UI can keep display-only settings on the metric
panels, and `DashboardService.validate_panels`
(`src/qdash/api/services/dashboard_service.py`) validates it against the model for the
panel's `type` on every create and update, and when the visibility of a dashboard changes. For a
`metric_script` panel it also checks that the script is visible to the saver, that a
project-visible dashboard uses only project-visible scripts, that the pinned revision exists and
validated, that `metric_id` is in that revision's catalog, that `params` pass `check_params`
(the metric's `Parameter` declarations), and that `hops` stay within the metric's declared hops.
`_check_view` matches the view to the metric's `result`: a series metric needs `timeseries` and
1 to 16 targets of its kind, and a scalar metric needs `map` or `table` and no targets, so a
series is never reduced to one value per target. Whether the targets are on the chip is checked
when the panel is evaluated, because a dashboard's chip can change.
Violations return 422 naming the panel.

## Revision policy

Panels pin `script_revision`, deliberately: saving a script never changes what an existing
dashboard shows, so a viewer never sees a dashboard change because someone else edited a script.
`_to_response` annotates every `metric_script` panel whose script the caller can view with
`script_name` and `latest_revision` (the script's `active_revision`); the UI shows "Newer
revision rN available" and, in edit mode, an update action that moves the pin and is persisted
with the next save.

The script document is the only authority on which revisions are pinned. Eviction, unsharing,
and deletion read `pins` from the script they change, and every change to `pins` is an atomic
update of that document that increments its `version`. QDash does not use Mongo transactions,
so one document has to decide alone; the dashboard document never decides whether a revision may
go.

- A script save is an atomic compare-and-set on the stored `version`
  (`MongoMetricScriptRepository.save_if_unchanged`). Every write to a script document
  increments `version`: saves, `add_pin`, `narrow_pin`, and `clear_dashboard_pins`. When another
  save, or a dashboard pinning or unpinning a revision, landed after the document was read, the
  update returns 409 and writes nothing, even without `expected_revision`. A saved revision's source is
  therefore never rewritten, and a save never evicts a revision pinned after its read.
- `MetricScriptService._apply_source` keeps at most 50 revisions but never evicts the newest, the
  active one, or any revision in `pins`. When everything left is pinned, the save returns 409
  naming the number of pinned revisions instead of growing the document; unpinning dashboards
  from old revisions makes room again. Metadata saves are not affected.
- Deleting a script returns 409 listing the dashboards in `pins`, and the delete itself matches
  `version` (`delete_if_unchanged`), so a dashboard that pins the script after the check makes
  the delete fail with 409.
- Making a script private returns 409 while a pin has `shared` set, decided from the same
  document the save then compares.
- Duplicating a dashboard copies its pins; copying a script (`POST /metric-scripts/{id}/copy`)
  creates a private script from the active source and retargets nothing.

`DashboardService` writes a dashboard in this order:

1. `add_pin` adds the panels' revisions to the pin of every script they use, sets `shared` for a
   project-visible dashboard, and records a fresh `writer` token. Its filter requires every
   revision to be stored and, for `shared`, the script to be project-visible, so a dashboard save
   that lost to an eviction or an unshare returns 422 asking to reload the dashboard. An update
   also claims the pins of scripts that its new panels no longer use.
2. The dashboard is inserted, or replaced through a compare-and-set on its `version`
   (`MongoDashboardRepository.save_if_unchanged`); a lost race returns 409. An update that
   carries `expected_version` is compared against that version: a mismatch returns 409 before
   step 1, and the compare-and-set covers a save that lands later. Without it, the update is
   compared against the version the request read. Responses include `version`, so a client that
   read a dashboard can send it back.
3. After an update, `narrow_pin` sets each pin to exactly the stored panels, or removes it, but
   only if its `writer` is still this write's token. A later write of the same dashboard claimed
   the pin otherwise and narrows it itself.

A pin is in the script document before any stored dashboard depends on it, so a concurrent script
save either sees the pin or fails its compare-and-set. A failed request, a lost race, or a crash
between the steps can leave a surplus pin, never a missing one. A subsequent update, including
a metadata save, narrows pins on the scripts involved in that update; surplus pins on other scripts remain
until the dashboard is deleted. A process crash before inserting a dashboard can leave orphan
pins that require administrative cleanup after confirming no writer is still running.
An insert exception does not prove that insertion failed: the acknowledgement may be lost.
The service releases new-dashboard pins only if insertion was never attempted. Update and
delete exceptions likewise retain pins; only acknowledged writes allow narrowing or clearing.
Deleting a dashboard, or an update that finds its
dashboard deleted, removes the dashboard's pins from every script (`clear_dashboard_pins`);
dashboard IDs are never reused.

Panel saves normalize validated settings, including defaults, while retaining accepted extra
settings on non-script panels. A revision number is a positive JSON integer wherever a request
names one: `script_revision` in a panel, `expected_revision` on a script save, and `revision`
on an evaluation. Booleans, strings, and floats such as `1.0` are rejected with 422 before any
pin changes, and `script_revision` must also fit in a BSON 64-bit integer. Script IDs are exact
strings, without whitespace trimming. Dashboards ship without a data migration: every
script and dashboard document is created by code that maintains `pins` and `version`.

## Visibility and permissions

`DashboardService` and `MetricScriptService` apply the sharing rules; the routers
(`src/qdash/api/routers/dashboard.py` with prefix `/dashboards`,
`src/qdash/api/routers/metric_script.py` with prefix `/metric-scripts`) only choose the project
dependency.

| Operation | Project dependency | Service rule |
| --- | --- | --- |
| List, get (dashboards and scripts), script catalog, templates and template preview | `get_project_context` (any member) | `visibility == "project"` or `user_id` equals the caller's |
| Evaluate a saved script revision | `get_project_context` | The script is visible; the revision validated |
| Create, duplicate, copy | `get_project_context_editor` | The source is visible; the copy is private and owned by the caller |
| Validate and evaluate draft source | `get_project_context_editor` | Runs unsaved code, so editors only |
| Update, delete | `get_project_context_editor` | Owner of the document or project role `OWNER`; otherwise 403 |

A document that is not visible to the caller returns 404, not 403, so private documents do not
reveal their existence. Every query filters by `project_id`, so dashboards and scripts never
cross projects. Ownership compares `user_id`, which survives a username change. Responses carry
`can_edit` so the UI can hide controls without re-deriving the rule.

## Templates

Dashboard templates are `DashboardTemplate` values in
`src/qdash/api/services/dashboard_templates.py`, keyed by `template_id`; the only one is
`frequency-collision-map`. A create request with `template_id` and no `panels` copies the
template through `instantiate_panels`, which mints a fresh `panel_id` per panel. Its
`metric_script` panels name a script template (`script_template="collision"`) instead of a
script: `MetricScriptService.ensure_template_script` reuses a project-visible script created from
that template whose active revision still defines every metric the panels need, or creates one
owned by the caller and shared with the project, and the panels are pinned to its active
revision. Explicit `panels` take precedence over the template, and an unknown `template_id`
returns 422.

`GET /dashboards/templates/{template_id}/preview` (`preview_template`, any member) returns
the panels a create would copy in now and writes nothing. It resolves script panels with
`MetricScriptService.find_template_script`, the read-only lookup `ensure_template_script` also
uses, so a preview pins them to the script a create would reuse. When the project has no such
script, `instantiate_panels(..., partial=True)` leaves those panels without a script reference,
each `TemplatePreviewPanel` names its `script_template_id`, and `scripts_to_create` lists the
starter scripts a create would add, with their source. An unknown template returns 404.

Script templates are Python files in `src/qdash/api/metric_runtime/templates/`, listed in
`TEMPLATES` of `src/qdash/api/metric_runtime/template_library.py` (`getting_started`,
`collision`, `zx90_median`). Creating a script with `template_id` copies the source; the script
owns it from then on. Templates are code, not documents, and there are no user-defined
templates.

## UI

Routes: `/dashboards` (list, with a `tab` query parameter for **Dashboards** and
**Scripts**), `/dashboards/new` (a new dashboard as a local draft until **Save** creates
it), `/dashboards/[dashboardId]`, and `/dashboards/scripts/[scriptId]`.
Dashboard code lives in `ui/src/components/features/dashboards/`; panels are laid out with
CSS grid from each panel's `layout`, and edit mode keeps the panel list in local state and
persists it with one `PATCH` of `panels` and the `expected_version` read when editing started; a
409 leaves the draft in place. `DashboardPageContent` serves both routes; with no
`dashboardId` it starts in edit mode and **Save** creates a private dashboard, with
`template_id` only while the draft has no panels. While it does, the page shows the template
preview read-only; a panel whose script is still to be created passes `starterScript` to
`MetricScriptPanel`, which evaluates the starter source with `POST /metric-scripts/evaluate`
instead of a saved revision, and the page says that **Save** adds the shared script. It
registers the draft with the Agent dock
(`dashboardDraft.ts` writes and checks it) so the Agent can propose a new draft that the user
applies and saves; see
[Page context and editor edits](../copilot/architecture.md#page-context-and-editor-edits).
`panelConfig.ts` reads and writes panel configs;
`metricChoices.ts` flattens the configured chip metrics and the catalogs of the visible scripts
into the grouped **Show** list of `PanelEditorDialog`, from which the panel type follows.

Script code lives in `ui/src/components/features/metric-scripts/`:
`MetricScriptEditorPageContent` (Monaco editor, settings, diagnostics, preview) with
`useMetricScriptDocument` (draft, dirty state, save with `expected_revision`, 409 handling), and
the shared renderers under `render/` (`QubitMap`, `PairMap`, `ResultTable`, `CellDetailsDialog`,
`SeriesChart`, `MetricResultView`). `MetricResultView` shows an alert instead of a view that
cannot show the result (`viewMismatch`). `SeriesChart` draws series results with the shared
Plotly `Plot` and `chartTheme` series colors: `seriesTraces.ts` builds one trace per target with
gaps as `null` and `connectgaps: false`, UTC times, and the bin and observation count in the
tooltip; targets without values are listed under the chart with their status. `targets.ts`
parses typed targets the way the API normalizes them. `panels/MetricScriptPanel.tsx` evaluates a panel's pinned revision with
`POST /metric-scripts/{id}/evaluate` and renders it with `MetricResultView`. The editor registers
its page with the Agent dock so the Agent can propose edits; see
[Page context and editor edits](../copilot/architecture.md#page-context-and-editor-edits).

## Extending

- A new dashboard template is one `DashboardTemplate` in `TEMPLATES`, with an assertion on its
  panels in `tests/qdash/api/routers/test_dashboard.py`.
- A new script template is one file under `templates/` and one `MetricScriptTemplate` entry;
  every template must pass validation in `tests/qdash/api/metric_runtime/`.
- A new panel type needs a config model in `PANEL_CONFIG_MODELS`, a `PanelType` literal, a
  renderer and editor section in the UI, and a row on the user page.
- Changing either router's schemas requires `task generate`.

## Tests

- `tests/qdash/api/routers/test_dashboard.py`: visibility, ownership, project isolation,
  panel validation, the template, and pins kept in step with dashboard writes, including
  concurrent updates and deletes of one dashboard and stale `expected_version` saves.
- `tests/qdash/api/routers/test_metric_script.py`: script CRUD, last-good revisions, conflicts,
  references from dashboards, pins racing script saves, unsharing and deletion, and evaluation
  through the worker.
- `tests/qdash/repository/test_metric_script_repository.py`: the compare-and-set save and the
  pin operations.
- `tests/qdash/api/metric_runtime/`: the SDK, the import policy, the worker, and the collision
  template against the numbers of the original collision tests.
- `ui/src/components/features/dashboards/__tests__/` and
  `ui/src/components/features/metric-scripts/__tests__/`: list tabs, panel editor, renderers,
  the editor page, and the document hook.
