# Dashboards Architecture

A dashboard stores a project-scoped layout, not measurement data. Panels read live metrics or
evaluate a pinned revision of a [metric script](./metric-scripts.md).

## Responsibility boundary

The API owns persistence, permissions, panel validation, and revisions. The metric runner owns
script execution. The UI renders saved panel configuration and offers explicit save operations.
User procedures live in [Dashboards](../../user-guide/dashboards.md).

## Documents

`DashboardDocument` stores owner, visibility, optional chip, panels, and a write version.
Each panel has a unique ID, typed configuration, and a position on a 12-column grid.
The models in `src/qdash/datamodel/dashboard.py` validate layout and configuration together.

## Revision policy

A script panel pins a revision. Saving a script must not silently change an existing dashboard;
updating a pin is an explicit dashboard edit. Script pins also prevent eviction of a referenced
revision.

Dashboard writes widen script pins before saving the dashboard, then narrow them to the saved
panels. Conditional versions protect concurrent writes. A failed write may leave an extra pin,
never a missing pin; orphan pins can require cleanup after a crash.

## Visibility and permissions

Apply project membership and ownership in the services, not just in UI controls. Shared dashboards
must reference scripts their viewers can access. Script unsharing or deletion must respect active
pins. Stale writes fail instead of overwriting another editor's changes.

## Templates

Templates copy panel definitions and mint new panel IDs. Script-backed templates create the
required scripts and pin their saved revisions. Template previews must not persist resources.

## Extending

A panel type needs a model in `PANEL_CONFIG_MODELS`, service validation, rendering in
`ui/src/components/features/dashboards/`, and tests. A new template needs a catalog entry and
validation of its instantiated panels. Do not add a second path around revision or sharing checks.

## Implementation and tests

| File | Responsibility |
| --- | --- |
| `src/qdash/api/services/dashboard_service.py` | Permissions, saves, and pins |
| `src/qdash/api/services/dashboard_templates.py` | Template catalog |
| `src/qdash/api/services/metric_script_service.py` | Script lifecycle |
| `src/qdash/dbmodel/dashboard.py` | Stored dashboards |

Run `uv run pytest tests/qdash/api/routers/test_dashboard.py tests/qdash/api/routers/test_metric_script.py`
and affected dashboard UI tests. Cover stale saves, sharing, revision eviction, and pin races.
