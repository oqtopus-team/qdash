"""Helpers for asserting on task call lists in workflow tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from qdash.datamodel.task_call import TaskCall


def names(calls: Iterable[TaskCall] | None) -> list[str]:
    """Task names of a call list, in order and with repeats."""
    return [call.name for call in calls or ()]


def call_ids(calls: Iterable[TaskCall] | None) -> list[str]:
    """Resolved call ids of a call list, in order."""
    return [call.resolved_call_id for call in calls or ()]
