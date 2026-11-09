"""Helpers for asserting on task call lists in workflow tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qdash.datamodel.task_call import TaskSettings
from qdash.datamodel.task_settings import normalize_task_parameters

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from qdash.datamodel.task_call import TaskCall


def names(calls: Iterable[TaskCall] | None) -> list[str]:
    """Task names of a call list, in order and with repeats."""
    return [call.name for call in calls or ()]


def call_ids(calls: Iterable[TaskCall] | None) -> list[str]:
    """Resolved call ids of a call list, in order."""
    return [call.resolved_call_id for call in calls or ()]


def effective_settings(
    calls: Iterable[TaskCall] | None,
    task_parameters: Mapping[str, Any] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Each call's resolved id and its settings merged over ``task_parameters``.

    The result is a list in call order, so repeated tasks keep one entry per call.
    """
    defaults = normalize_task_parameters(dict(task_parameters or {}))
    return [(call.resolved_call_id, call.effective_settings(defaults)) for call in calls or ()]


def settings(
    run: Mapping[str, Any] | None = None,
    input: Mapping[str, Any] | None = None,
    update_calibration_parameters: bool | None = None,
) -> dict[str, Any]:
    """Canonical settings for plain values, as a call reports them."""
    return TaskSettings(
        run=dict(run) if run is not None else None,
        input=dict(input) if input is not None else None,
        update_calibration_parameters=update_calibration_parameters,
    ).settings()
