"""What ``CalibrationSession.run`` and ``validate`` return, in the SDK and in a workflow.

``run`` returns a :class:`CalibrationResult` only for a run that completed. A run that did
not complete raises: the SDK raises :class:`CalibrationRunError` with the result it read, and
a workflow lets the step's own exception propagate, so Prefect's failure and cancellation
handling sees it. Neither side turns a failure into a returned value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["CalibrationResult", "CalibrationRunError", "CalibrationValidation"]


@dataclass(frozen=True)
class CalibrationResult:
    """The outcome of one calibration run.

    ``status`` is the whole run's end state: ``completed`` for a result that ``run`` returned,
    or what the SDK read for a run that did not complete (attached to
    :class:`CalibrationRunError`). ``calibration_session_id`` and ``run_id`` name the
    persisted session and run the run was recorded in, or None when there is none (a workflow
    run outside a flow run). ``execution_ids`` lists the run's step executions, oldest first.

    Every step the run reached, calibration or transform, is recorded in its own Execution,
    so ``execution_ids`` lists the filters and schedules too.

    ``steps`` maps steps to their data: in a workflow, each calibration step's ``step_id`` to
    its typed result (``OneQubitResult`` or ``TwoQubitResult`` from
    ``qdash.workflow.service.results``), with each transform step's recorded outcome under
    ``details["transforms"]`` by its step key; from the SDK, every planned step's key (a
    calibration step's ``step_id``, a transform's name, suffixed with its position when
    repeated) to its progress as the server reported it, including a transform's recorded
    outcome. ``details`` is the full source: the workflow's result dictionary, or the SDK's
    run state response.
    """

    status: str
    calibration_session_id: str | None = None
    run_id: str | None = None
    execution_ids: tuple[str, ...] = ()
    candidate_qids: tuple[str, ...] = ()
    candidate_couplings: tuple[str, ...] = ()
    steps: Mapping[str, Any] = field(default_factory=dict)
    details: Any = field(default=None, repr=False, compare=False)

    @property
    def succeeded(self) -> bool:
        """Whether the whole run completed."""
        return self.status.lower() == "completed"

    def __getitem__(self, key: str) -> Any:
        """Read the workflow's result dictionary, as ``CalibService.run`` returned it."""
        if isinstance(self.details, Mapping):
            return self.details[key]
        raise KeyError(key)


class CalibrationRunError(RuntimeError):
    """A run ended without completing: failed, cancelled, crashed or never launched.

    ``result`` is what was read when it ended, with its ``status``.
    """

    def __init__(self, message: str, result: CalibrationResult) -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class CalibrationValidation:
    """Whether a calibration would be accepted, without running it.

    ``problems`` lists each problem as ``"path: message"`` (empty when ``valid``);
    ``warnings`` lists what could not be checked. ``details`` is the source: the server's
    validation response in the SDK, None in a workflow.
    """

    valid: bool
    problems: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    details: Any = field(default=None, repr=False, compare=False)
