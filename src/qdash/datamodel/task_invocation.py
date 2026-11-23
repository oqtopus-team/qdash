"""Which planned call a task result executed.

Kept apart from :mod:`qdash.datamodel.task_call` so the task result models in
:mod:`qdash.datamodel.task` can carry it without an import cycle.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskInvocation(BaseModel):
    """The plan identity of one task result.

    ``step_id`` and ``call_id`` name the planned call; ``task_id`` on the task
    result stays the runtime identity of this one execution on one target.
    ``plan_digest`` identifies the validated plan version the call belongs to.
    ``settings`` is the call's effective task settings (the call's own settings
    over the workflow's per-task defaults) as the worker resolved them; the task
    result's run and input parameter snapshots remain the runtime source of truth.
    Results recorded before task calls existed have no invocation.
    """

    model_config = ConfigDict(extra="ignore")

    step_id: str | None = Field(default=None, description="Plan-scoped step identifier.")
    call_id: str = Field(description="Step-scoped call identifier.")
    plan_digest: str | None = Field(default=None, description="Version of the validated plan.")
    settings: dict[str, Any] | None = Field(
        default=None, description="Effective call settings: run, input, update policy."
    )
