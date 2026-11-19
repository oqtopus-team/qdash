"""Tasks whose outputs may never become accepted calibration state.

A task class declares ``measurement_only_reason`` (a non-empty string) when its outputs
must stay measurement-only regardless of ``update_calibration_parameters``,
``force_update_params``, the backend default, or the workflow that runs it. The
orchestrator then resolves write-back to ``False`` and ``BackendSaver`` records the outputs
with ``database_updated: false`` and the reason, without touching the calibration
database, backend parameter files, or calibration notes.

A task may also set ``output_provenance`` (a dict) on the instance during postprocess; it
is stored with every output in task-result history.
"""

from __future__ import annotations

from typing import Any

MEASUREMENT_ONLY_ATTRIBUTE = "measurement_only_reason"


def measurement_only_reason(task: Any) -> str | None:
    """Return the declared reason when ``task`` (class or instance) is measurement-only."""
    if task is None:
        return None
    reason = getattr(task, MEASUREMENT_ONLY_ATTRIBUTE, None)
    return reason if isinstance(reason, str) and reason else None


def output_provenance(task: Any) -> dict[str, Any]:
    """Return the per-run provenance a measurement-only task attached to its outputs."""
    provenance = getattr(task, "output_provenance", None)
    return dict(provenance) if isinstance(provenance, dict) else {}
