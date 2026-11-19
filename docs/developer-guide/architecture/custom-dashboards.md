# Custom Dashboards Architecture

Custom dashboards store a layout of typed panels per project and owner; metric panels read live
chip data through the metrics endpoints, and `metric_script` panels evaluate a pinned revision
of a user-authored [metric script](./metric-scripts.md). The user procedures are
[Dashboards](../../user-guide/custom-dashboards.md) and
[Metric Scripts](../../user-guide/metric-scripts.md).

## Responsibility boundary

The API owns persistence, visibility, and validation of dashboards and metric scripts. It stores
no measured values and no computed results: a dashboard describes what to show, a script defines
how to compute it, and every panel evaluates when it renders. The metric script runtime
(`src/qdash/api/metric_runtime/`, described in [Metric Scripts](./metric-scripts.md)) owns code
execution. The UI owns layout editing, the script editor, and rendering of evaluation results.

## Documents

`CustomDashboardDocument` (`src/qdash/dbmodel/custom_dashboard.py`, collection
`custom_dashboard`) holds `project_id`, `dashboard_id` (`dash_<12 hex>`), the owner's `user_id`
and `username` snapshot, `name`, `description`, `visibility`, an optional default `chip_id`, and
`panels`. The unique index is `(project_id, dashboard_id)`.

`MetricScriptDocument` (`src/qdash/dbmodel/metric_script.py`, collection `metric_script`) holds
`project_id`, `script_id` (`ms_<12 hex>`), owner `user_id` and `username`, `name` (at most 120
characters), `description`, `visibility`, and the revision state:

| Field | Meaning |
| --- | --- |
| `source`, `revision`, `status`, `diagnostics` | The latest saved text, its number (incremented on every save), and its validation result (`valid` or `invalid`) |
| `active_revision`, `active_source`, `metrics` | The last revision that validated, its text, and its catalog (`MetricInfo`: id, title, unit, target, hops, parameters, has_legend); `None` until a revision validates |
| `revisions` | `MetricScriptRevision` entries `{revision, source, created_at, status, metrics}` |
| `template_id` | The template the script was created from, if any |

The unique index is `(project_id, script_id)`; `(project_id, template_id)` serves the template
lookup below.

## Panels

The shared panel models live in `src/qdash/datamodel/custom_dashboard.py`:

| Model | Meaning |
| --- | --- |
| `PanelLayoutModel` | `x`, `y`, `w`, `h` on a 12-column grid; `x + w <= 12`, `1 <= h <= 12` |
| `DashboardPanelModel` | `panel_id` (unique within the dashboard), `type`, `title`, `layout`, `config` |
| `QubitMetricPanelConfig`, `CouplingMetricPanelConfig` | `metric` key from the metrics configuration |
| `MetricScriptPanelConfig` | `script_id`, `metric_id`, `script_revision` (required), `period`, `params`, `view` (`map` or `table`), `direction` (`both`, `forward`, `reverse`), `hops` (subset of `[1, 2]`); extra keys are rejected |
| `MarkdownPanelConfig` | `content`, at most 20000 characters |

`config` is stored as a dictionary so the UI can keep display-only settings on the metric
panels, and `CustomDashboardService.validate_panels`
(`src/qdash/api/services/custom_dashboard_service.py`) validates it against the model for the
panel's `type` on every create and update, and when the visibility of a dashboard changes. For a
`metric_script` panel it also checks that the script is visible to the saver, that a
project-visible dashboard uses only project-visible scripts, that the pinned revision exists and
validated, that `metric_id` is in that revision's catalog, that `params` pass `check_params`
(the metric's `Parameter` declarations), and that `hops` stay within the metric's declared hops.
Violations return 422 naming the panel.

## Revision policy

Panels pin `script_revision`, deliberately: saving a script never changes what an existing
dashboard shows, so a viewer never sees a dashboard change because someone else edited a script.
`_to_response` annotates every `metric_script` panel whose script the caller can view with
`script_name` and `latest_revision` (the script's `active_revision`); the UI shows "Newer
revision rN available" and, in edit mode, an update action that moves the pin and is persisted
with the next save.

The pin is protected on the script side:

- `MetricScriptService._apply_source` keeps at most 50 revisions but never evicts the newest, the
  active one, or any revision a dashboard in the project pins (`pinned_revisions`).
- Deleting a script returns 409 listing the dashboards that reference it.
- Making a script private returns 409 while a project-visible dashboard uses it.
- Duplicating a dashboard copies its pins; copying a script (`POST /metric-scripts/{id}/copy`)
  creates a private script from the active source and retargets nothing.

## Visibility and permissions

`CustomDashboardService` and `MetricScriptService` apply the sharing rules; the routers
(`src/qdash/api/routers/custom_dashboard.py` with prefix `/custom-dashboards`,
`src/qdash/api/routers/metric_script.py` with prefix `/metric-scripts`) only choose the project
dependency.

| Operation | Project dependency | Service rule |
| --- | --- | --- |
| List, get (dashboards and scripts), script catalog and templates | `get_project_context` (any member) | `visibility == "project"` or `user_id` equals the caller's |
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
`src/qdash/api/services/custom_dashboard_templates.py`, keyed by `template_id`; the only one is
`frequency-collision-map`. A create request with `template_id` and no `panels` copies the
template through `instantiate_panels`, which mints a fresh `panel_id` per panel. Its
`metric_script` panels name a script template (`script_template="collision"`) instead of a
script: `MetricScriptService.ensure_template_script` reuses a project-visible script created from
that template whose active revision still defines every metric the panels need, or creates one
owned by the caller and shared with the project, and the panels are pinned to its active
revision. Explicit `panels` take precedence over the template, and an unknown `template_id`
returns 422.

Script templates are Python files in `src/qdash/api/metric_runtime/templates/`, listed in
`TEMPLATES` of `src/qdash/api/metric_runtime/template_library.py` (`getting_started`,
`collision`, `zx90_median`). Creating a script with `template_id` copies the source; the script
owns it from then on. Templates are code, not documents, and there are no user-defined
templates.

## UI

Routes: `/custom-dashboards` (list, with a `tab` query parameter for **Dashboards** and
**Scripts**), `/custom-dashboards/[dashboardId]`, and `/custom-dashboards/scripts/[scriptId]`.
Dashboard code lives in `ui/src/components/features/custom-dashboards/`; panels are laid out with
CSS grid from each panel's `layout`, and edit mode keeps the panel list in local state and
persists it with one `PATCH` of `panels`. `panelConfig.ts` reads and writes panel configs.

Script code lives in `ui/src/components/features/metric-scripts/`:
`MetricScriptEditorPageContent` (Monaco editor, settings, diagnostics, preview) with
`useMetricScriptDocument` (draft, dirty state, save with `expected_revision`, 409 handling), and
the shared renderers under `render/` (`QubitMap`, `PairMap`, `ResultTable`, `CellDetailsDialog`,
`MetricResultView`). `panels/MetricScriptPanel.tsx` evaluates a panel's pinned revision with
`POST /metric-scripts/{id}/evaluate` and renders it with `MetricResultView`. The editor registers
its page with the Agent dock so the Agent can propose edits; see
[Page context and editor edits](../copilot/architecture.md#page-context-and-editor-edits).

## Extending

- A new dashboard template is one `DashboardTemplate` in `TEMPLATES`, with an assertion on its
  panels in `tests/qdash/api/routers/test_custom_dashboard.py`.
- A new script template is one file under `templates/` and one `MetricScriptTemplate` entry;
  every template must pass validation in `tests/qdash/api/metric_runtime/`.
- A new panel type needs a config model in `PANEL_CONFIG_MODELS`, a `PanelType` literal, a
  renderer and editor section in the UI, and a row on the user page.
- Changing either router's schemas requires `task generate`.

## Tests

- `tests/qdash/api/routers/test_custom_dashboard.py`: visibility, ownership, project isolation,
  panel validation, pins, and the template.
- `tests/qdash/api/routers/test_metric_script.py`: script CRUD, last-good revisions, conflicts,
  references from dashboards, and evaluation through the worker.
- `tests/qdash/api/metric_runtime/`: the SDK, the import policy, the worker, and the collision
  template against the numbers of the original collision tests.
- `ui/src/components/features/custom-dashboards/__tests__/` and
  `ui/src/components/features/metric-scripts/__tests__/`: list tabs, panel editor, renderers,
  the editor page, and the document hook.
