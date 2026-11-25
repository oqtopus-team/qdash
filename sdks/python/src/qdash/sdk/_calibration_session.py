"""``CalibrationSession``: a named calibration objective on one chip, and the runs started in it.

A calibration session is a persistent record on the server. It groups the runs started for one
objective; it holds no hardware, keeps no connection open and is not a transaction. The QDash
client (:class:`~qdash.sdk.QDash`) is the connection; a session is created or opened through
it and never closes it.

.. code-block:: python

    from qdash.calibration import CustomOneQubit, QubitTargets, TaskCall
    from qdash.sdk import CalibrationSession, QDash

    client = QDash.from_env()
    session = CalibrationSession.create(client, chip_id="64Qv3", name="Coherence check")
    result = session.run(
        targets=QubitTargets(["0", "1"]),
        steps=[CustomOneQubit(step_name="t1", tasks=[TaskCall(name="CheckT1")])],
    )
    print(result.status, result.execution_ids)
    session.close()

The same targets and steps run in a saved workflow through ``qdash.workflow.CalibrationSession``
and return the same :class:`~qdash.calibration.CalibrationResult`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qdash.calibration import (
    CalibrationResult,
    CalibrationRunError,
    CalibrationValidation,
    pipeline_spec,
)
from qdash.sdk._http import api_errors, read_options
from qdash.sdk._runs import FLOW_TERMINAL_STATUSES
from qdash.sdk.errors import QDashConfigError, QDashNotFoundError, QDashTransportError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from qdash.sdk._generated.types.calibration_run_state_response import (
        CalibrationRunStateResponse,
    )
    from qdash.sdk._generated.types.calibration_session_detail_response import (
        CalibrationSessionDetailResponse,
    )
    from qdash.sdk._generated.types.calibration_session_response import (
        CalibrationSessionResponse,
    )
    from qdash.sdk._generated.types.execute_pipeline_response import ExecutePipelineResponse
    from qdash.sdk._results import ExecutionResult
    from qdash.sdk._runs import Executions
    from qdash.sdk._session import QDash

__all__ = ["CalibrationLaunch", "CalibrationSession", "CalibrationSessionClosedError"]

_NAME_MAX_LENGTH = 500


class CalibrationSessionClosedError(RuntimeError):
    """The session is closed, so it admits no new run; nothing was sent.

    A closed session is never reopened: create a new one for further work.
    """


def _non_empty(label: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _state_result(state: CalibrationRunStateResponse) -> CalibrationResult:
    steps: dict[str, Any] = {}
    if state.pipeline is not None:
        for step in state.pipeline.steps:
            # Every step occurrence, transforms included; a server without ``key`` falls
            # back to the step_id or name.
            steps[getattr(step, "key", None) or step.step_id or step.name] = step
    return CalibrationResult(
        status=str(state.flow_status),
        calibration_session_id=state.calibration_session_id,
        run_id=state.run_id,
        execution_ids=tuple(summary.execution_id for summary in state.executions or []),
        steps=steps,
        details=state,
    )


class CalibrationLaunch:
    """A run dispatched into a calibration session, returned by
    :meth:`CalibrationSession.submit`.

    The run is followed through its recorded run in the session, whose state the server reads
    from Prefect: every step execution counts, and a run that fails before creating one is
    still seen to end. :meth:`wait` never cancels the run.
    """

    def __init__(self, executions: Executions, response: ExecutePipelineResponse) -> None:
        self._executions = executions
        self.response = response

    @property
    def calibration_session_id(self) -> str:
        session_id: str = self.response.calibration_session_id  # type: ignore[assignment]
        return session_id

    @property
    def run_id(self) -> str:
        run_id: str = self.response.pipeline_run_id  # type: ignore[assignment]
        return run_id

    @property
    def execution_id(self) -> str:
        """The first execution the server created for the run."""
        return self.response.execution_id

    def __repr__(self) -> str:
        return (
            f"CalibrationLaunch(calibration_session_id={self.calibration_session_id!r}, "
            f"run_id={self.run_id!r})"
        )

    def _state(self) -> CalibrationRunStateResponse:
        return self._executions.calibration_run(self.calibration_session_id, self.run_id)

    def get(self) -> CalibrationResult:
        """The run as it is now; ``status`` may still be ``running`` or ``dispatching``."""
        return _state_result(self._state())

    def wait(
        self, *, timeout_seconds: float = 3600.0, poll_interval_seconds: float = 5.0
    ) -> CalibrationResult:
        """Poll until the whole run ends and return the completed result.

        Raises :class:`~qdash.calibration.CalibrationRunError`, with the result read, for a
        run that ended ``failed``, ``cancelled``, ``crashed`` or ``not_launched``. Raises
        ``TimeoutError`` when the run has not ended within ``timeout_seconds``; the run keeps
        going, nothing is cancelled and the session stays open. ``unknown`` and
        ``unavailable`` states, and a run the server does not list yet, are polled again.
        """
        last: list[str] = ["the run was not found"]

        def read() -> CalibrationRunStateResponse | None:
            try:
                state = self._state()
            except QDashNotFoundError:
                last[0] = "the run was not found"
                return None
            status = str(state.flow_status)
            last[0] = f"{status}: {state.flow_status_reason or ''}".rstrip(": ")
            return state if status in FLOW_TERMINAL_STATUSES else None

        state = self._executions.poll(
            read,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            describe=lambda: (
                f"Calibration run {self.run_id!r} did not end within {timeout_seconds} "
                f"seconds; last read: {last[0]}. The run was not cancelled."
            ),
        )
        result = _state_result(state)
        if not result.succeeded:
            reason = f" ({state.flow_status_reason})" if state.flow_status_reason else ""
            raise CalibrationRunError(
                f"Calibration run {self.run_id!r} ended {result.status}{reason}", result
            )
        return result

    def executions(self) -> list[ExecutionResult]:
        """Every execution recorded for the run as it is now, oldest first."""
        from qdash.sdk._results import ExecutionResult

        state = self._state()
        steps = {
            step.execution_id: step
            for step in (state.pipeline.steps if state.pipeline is not None else [])
            if step.execution_id
        }
        return [
            ExecutionResult(
                self._executions,
                summary.execution_id,
                self._executions.get(summary.execution_id),
                step=steps.get(summary.execution_id),
            )
            for summary in state.executions or []
        ]


class CalibrationSession:
    """A calibration session on the server, reached through a QDash client.

    Create one with :meth:`create` or open an existing one with :meth:`open`; the constructor
    is not public. :meth:`run` launches a calibration into the session and waits for it,
    :meth:`submit` launches it and returns at once, and :meth:`validate` checks one without
    running it. Every launch names this session, so repeated launches stay grouped in it.
    :meth:`close` ends the objective: the session then admits no new run. Neither closes the
    client.
    """

    def __init__(
        self,
        client: QDash,
        record: CalibrationSessionResponse | CalibrationSessionDetailResponse,
        *,
        _token: object = None,
    ) -> None:
        if _token is not _INTERNAL:
            raise TypeError(
                "use CalibrationSession.create(client, chip_id=..., name=...) or "
                "CalibrationSession.open(client, session_id=...)"
            )
        self._client = client
        self._record = record

    @staticmethod
    def _require_project(client: QDash, action: str) -> None:
        if not client.project_id:
            raise QDashConfigError(
                f"{action} needs a project: set QDASH_PROJECT_ID, project_id in the profile, "
                "or QDash(..., project_id=...)"
            )

    @classmethod
    def create(cls, client: QDash, *, chip_id: str, name: str) -> CalibrationSession:
        """Create a calibration session for ``name`` on ``chip_id``.

        ``name`` is the session's objective as the server stores it (at most 500
        characters), shown with every run. Sends one ``POST /calibration-sessions`` in the
        client's project, which needs editor access; it is not retried. The session belongs to
        the signed-in user, and only that user can launch runs into it.
        """
        _non_empty("chip_id", chip_id)
        _non_empty("name", name)
        if len(name.strip()) > _NAME_MAX_LENGTH:
            raise ValueError(f"name must be at most {_NAME_MAX_LENGTH} characters")
        cls._require_project(client, "creating a calibration session")
        with api_errors():
            record = client.api.calibration_session.create_calibration_session(
                chip_id=chip_id, objective=name
            )
        if record.chip_id != chip_id:
            raise QDashTransportError(
                f"created a calibration session on chip {chip_id!r} but the response describes "
                f"chip {record.chip_id!r}; check the base URL and any proxy settings"
            )
        return cls(client, record, _token=_INTERNAL)

    @classmethod
    def open(cls, client: QDash, *, session_id: str) -> CalibrationSession:
        """Open the existing calibration session ``session_id``, as it is.

        Reads the session; raises ``QDashNotFoundError`` when the project has none by that ID.
        A closed session opens closed: it can be read, but :meth:`run` and :meth:`submit`
        raise :class:`CalibrationSessionClosedError`. Opening never reopens it.
        """
        _non_empty("session_id", session_id)
        record = cls._read(client, session_id)
        return cls(client, record, _token=_INTERNAL)

    @staticmethod
    def _read(client: QDash, session_id: str) -> CalibrationSessionDetailResponse:
        with api_errors():
            record = client.api.calibration_session.get_calibration_session(
                session_id, request_options=read_options(client.config)
            )
        if record.calibration_session_id != session_id:
            raise QDashTransportError(
                f"requested calibration session {session_id!r} but the response describes "
                f"{record.calibration_session_id!r}; check the base URL and any proxy settings"
            )
        return record

    @property
    def session_id(self) -> str:
        return self._record.calibration_session_id

    @property
    def chip_id(self) -> str:
        return self._record.chip_id

    @property
    def name(self) -> str:
        """The session's objective."""
        return self._record.objective

    @property
    def status(self) -> str:
        """``open`` or ``closed``, as last read; :meth:`refresh` reads it again."""
        return str(self._record.status)

    @property
    def closed(self) -> bool:
        return self.status == "closed"

    @property
    def record(self) -> CalibrationSessionResponse | CalibrationSessionDetailResponse:
        """The session as the API last returned it."""
        return self._record

    def __repr__(self) -> str:
        return (
            f"CalibrationSession(session_id={self.session_id!r}, chip_id={self.chip_id!r}, "
            f"status={self.status!r})"
        )

    def refresh(self) -> CalibrationSessionDetailResponse:
        """Read the session again, with its runs, and return it."""
        record = self._read(self._client, self.session_id)
        self._record = record
        return record

    def close(self, *, note: str = "", acknowledge_unknown_runs: bool = False) -> None:
        """End the objective: the session admits no new run.

        Closing cancels nothing: a run still in it makes the server refuse
        (``QDashConflictError``) rather than stop it. It does not close the client. Closing
        a session that is already closed is refused by the server too. Sent once.
        """
        self._require_project(self._client, "closing a calibration session")
        with api_errors():
            record = self._client.api.calibration_session.close_calibration_session(
                self.session_id,
                closing_note=note,
                acknowledge_unknown_runs=acknowledge_unknown_runs,
            )
        self._record = record

    def validate(
        self,
        targets: Any,
        steps: Sequence[Any],
        *,
        default_run_parameters: Mapping[str, Any] | None = None,
        name: str | None = None,
        tags: Sequence[str] | None = None,
        backend_name: str | None = None,
    ) -> CalibrationValidation:
        """Check a calibration on the session's chip without running it.

        The server reports every problem, including preflight checks that read calibration
        data; ``valid`` is false when there is any. Nothing is dispatched or recorded.
        """
        spec = pipeline_spec(
            targets, steps, name=name, default_run_parameters=default_run_parameters, tags=tags
        )
        response = self._client.pipelines.validate(
            spec, chip_id=self.chip_id, backend_name=backend_name
        )
        return CalibrationValidation(
            valid=bool(response.valid),
            problems=tuple(f"{p.path}: {p.message}" for p in response.problems or []),
            warnings=tuple(f"{w.path}: {w.message}" for w in response.warnings or []),
            details=response,
        )

    def submit(
        self,
        targets: Any,
        steps: Sequence[Any],
        *,
        default_run_parameters: Mapping[str, Any] | None = None,
        name: str | None = None,
        tags: Sequence[str] | None = None,
        backend_name: str | None = None,
        idempotency_key: str | None = None,
        decision_id: str | None = None,
    ) -> CalibrationLaunch:
        """Launch a calibration into this session and return without waiting.

        The server validates the calibration, records the run in this session and launches
        it; a calibration with problems is refused with ``QDashValidationError``. A retry with
        the same ``idempotency_key`` returns the recorded run instead of starting another.
        ``decision_id`` names a recorded decision of this session the run carries out. A
        response that does not confirm the session raises ``RuntimeError``: the run may have
        started without it, so reconcile before retrying. The request is sent once.

        Raises :class:`CalibrationSessionClosedError`, sending nothing, when the session was
        closed when last read; the server refuses a session closed since then.
        """
        if self.closed:
            raise CalibrationSessionClosedError(
                f"calibration session {self.session_id!r} is closed; create a new session"
            )
        spec = pipeline_spec(
            targets, steps, name=name, default_run_parameters=default_run_parameters, tags=tags
        )
        run = self._client.pipelines.execute(
            spec,
            chip_id=self.chip_id,
            backend_name=backend_name,
            calibration_session_id=self.session_id,
            idempotency_key=idempotency_key,
            decision_id=decision_id,
        )
        return CalibrationLaunch(self._client._executions, run.response)

    def run(
        self,
        targets: Any,
        steps: Sequence[Any],
        *,
        default_run_parameters: Mapping[str, Any] | None = None,
        name: str | None = None,
        tags: Sequence[str] | None = None,
        backend_name: str | None = None,
        idempotency_key: str | None = None,
        decision_id: str | None = None,
        timeout_seconds: float = 3600.0,
        poll_interval_seconds: float = 5.0,
    ) -> CalibrationResult:
        """Launch a calibration into this session and wait until the whole run ends.

        :meth:`submit` followed by :meth:`CalibrationLaunch.wait`: returns the completed
        result, raises :class:`~qdash.calibration.CalibrationRunError` for a run that did not
        complete, and raises ``TimeoutError`` without cancelling anything when the run has not
        ended within ``timeout_seconds``.
        """
        launch = self.submit(
            targets,
            steps,
            default_run_parameters=default_run_parameters,
            name=name,
            tags=tags,
            backend_name=backend_name,
            idempotency_key=idempotency_key,
            decision_id=decision_id,
        )
        return launch.wait(
            timeout_seconds=timeout_seconds, poll_interval_seconds=poll_interval_seconds
        )


_INTERNAL = object()
