"""One call of a calibration task inside a step."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from qdash.calibration.sweep import Sweep

__all__ = ["CALL_ID_PATTERN", "TASK_NAME_PATTERN", "OnFailure", "TaskCall"]

TASK_NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,127}$"
"""Task names are class-style identifiers such as ``CheckRamsey``."""

CALL_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$"
"""Call ids accept task names (``CheckRamsey``) as well as ``ramsey_fine``."""

OnFailure = Literal["continue", "stop"]

RUN_DESCRIPTION = (
    "Run parameters. A plain value, "
    '{"value": ..., "value_type": ...}, or a sweep declaration '
    '{"value": [start, stop, step_or_num], "value_type": "np.arange" | '
    '"np.linspace" | "np.logspace" | "range"} or '
    '{"value": [points...], "value_type": "list"}.'
)
INPUT_DESCRIPTION = "Calibration input overrides, as plain values."
UPDATE_DESCRIPTION = (
    "False records outputs as measurement history only. None inherits the next "
    "layer and finally the workflow's policy."
)
CALL_ID_DESCRIPTION = (
    "Identifier of this call, unique within its step. Defaults to the task "
    "name; required on every occurrence of a task that appears more than once."
)
ON_FAILURE_DESCRIPTION = (
    '"stop" skips this target\'s later calls in the step when this call fails; '
    '"continue" runs them. None inherits the step\'s continue_on_failure.'
)


def _mapping(label: str, value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return {str(name): data for name, data in value.items()}


def keep_run(value: Any) -> dict[str, Any] | None:
    """Run values as written: plain values, wrapped values or sweeps (sent as their JSON)."""
    return _mapping("run", value)


def keep_input(value: Any) -> dict[str, Any] | None:
    """Calibration input overrides as written; sweeps belong under ``run``."""
    entries = _mapping("input", value)
    for name, data in (entries or {}).items():
        if isinstance(data, Sweep):
            raise ValueError(
                f"input[{name!r}] uses a sweep; put generated experiment ranges under 'run'"
            )
    return entries


class TaskCall(BaseModel):
    """One call of a task in a step, with its own settings and identity.

    ``call_id`` defaults to the task name; every occurrence of a task that appears more than
    once in a step needs its own. ``run`` holds run parameters, plain or as a
    :mod:`~qdash.calibration.sweep` declaration; ``input`` overrides calibration inputs;
    ``update_calibration_parameters=False`` records outputs as history only; ``on_failure``
    decides whether the same target's later calls run after this one fails.

    ``run`` and ``input`` keep the values as written; a sweep is sent as its JSON. The
    worker's validated call (``qdash.datamodel.task_call.TaskCall``) is a subclass with the
    same fields and defaults that normalizes them to canonical settings, as the server does
    for a spec the SDK sends.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        pattern=TASK_NAME_PATTERN,
        description='Registered task name, e.g. "CheckRamsey".',
    )
    call_id: str | None = Field(
        default=None, pattern=CALL_ID_PATTERN, description=CALL_ID_DESCRIPTION
    )
    run: dict[str, Any] | None = Field(default=None, description=RUN_DESCRIPTION)
    input: dict[str, Any] | None = Field(default=None, description=INPUT_DESCRIPTION)
    update_calibration_parameters: bool | None = Field(default=None, description=UPDATE_DESCRIPTION)
    on_failure: OnFailure | None = Field(default=None, description=ON_FAILURE_DESCRIPTION)

    # Kept as written, so the SDK sends what the author wrote; the server and the worker's
    # subclass normalize both forms to the same canonical settings.
    _normalize_run = field_validator("run", mode="before")(keep_run)
    _normalize_input = field_validator("input", mode="before")(keep_input)

    @property
    def resolved_call_id(self) -> str:
        """The call id, or the task name when none was given."""
        return self.call_id or self.name

    def to_spec(self) -> dict[str, Any]:
        """The call as the pipeline spec's JSON, with only the fields that were set."""
        return self.model_dump(mode="json", exclude_unset=True)
