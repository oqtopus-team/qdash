"""Single-task executor: write-back resolution, snapshot policy and owned lifecycle."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.workflow.service._internal.session import CalibSession
from tests.qdash.workflow.context_helpers import grant_all_contexts


class CancelledRun(Exception):
    """Stand-in for prefect.exceptions.CancelledRun, which is matched by class name."""


class ExternalSignal(BaseException):
    """Stand-in for prefect.exceptions.ExternalSignal."""


class TerminationSignal(ExternalSignal):
    """Stand-in for prefect.exceptions.TerminationSignal."""


class RecordingSession(CalibSession):
    """A real CalibSession lifecycle with hardware, database and handlers stubbed."""

    instances: list[RecordingSession] = []
    error: BaseException | None = None
    failing_handler: str | None = None

    def __init__(self, settings: Any, **kwargs: Any) -> None:
        super().__init__(settings, **kwargs)
        self.initialized_qids: list[str] | None = None
        self.calls: list[tuple[str, str, Any]] = []
        self.finished = False
        for name in ("fail_calibration", "cancel_calibration", "abandon_calibration"):
            handler = MagicMock()
            if name == RecordingSession.failing_handler:
                handler.side_effect = RuntimeError("releasing the lock failed")
            setattr(self, name, handler)
        RecordingSession.instances.append(self)

    def _initialize(self, qids: list[str], *, connect_backend: bool = True) -> None:
        self.initialized_qids = qids
        self._initialized = True

    def execute_task(
        self, task_name: str, qid: str, upstream_id: Any = None, *, parameters: Any = None, **_: Any
    ) -> dict[str, Any]:
        self.calls.append((task_name, qid, parameters))
        if task_name != "Configure" and RecordingSession.error is not None:
            raise RecordingSession.error
        return {"task_name": task_name, "qid": qid}

    def finish_calibration(self, *args: Any, **kwargs: Any) -> None:
        self.finished = True


@pytest.fixture
def sessions(monkeypatch: pytest.MonkeyPatch) -> type[RecordingSession]:
    """Record every session the single-task flow opens."""
    RecordingSession.instances = []
    RecordingSession.error = None
    RecordingSession.failing_handler = None
    grant_all_contexts(monkeypatch)
    monkeypatch.setattr("qdash.workflow.service._internal.runs.CalibSession", RecordingSession)
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.get_run_logger", MagicMock)
    return RecordingSession


def _session(sessions: type[RecordingSession]) -> RecordingSession:
    assert len(sessions.instances) == 1
    return sessions.instances[0]


@pytest.mark.parametrize("persist", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("backend", ["qubex", "fake"])
def test_single_task_publication_follows_persistence_and_integration(
    monkeypatch, sessions, persist, enabled, force, backend
):
    """Task saves publish without forcing rejected calibration values into YAML."""
    from qdash.workflow.service.single_task_flow import single_task_executor

    monkeypatch.setattr(
        "qdash.common.config.loader.ConfigLoader.load_workflow",
        lambda: {"github": {"enabled": enabled, "branch": "calibration"}},
    )

    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        backend_name=backend,
        update_calibration_parameters=persist,
        update_params=force,
    )

    session = _session(sessions)
    settings = session.settings
    assert settings.github.push.enabled is (persist and enabled and backend == "qubex")
    if enabled and backend == "qubex":
        assert settings.github.push.branch == "calibration"
    assert settings.task_defaults["CheckRabi"]["update_calibration_parameters"] is persist
    assert settings.force_update_params is force
    assert settings.github.pull is (enabled and backend == "qubex")
    assert session.calls == [("CheckRabi", "0", None)]
    assert session.finished is True


def test_single_task_executor_owns_its_execution_and_reservation(monkeypatch, sessions):
    """The run reserves its target and closes its Execution without a caller finish."""
    from qdash.workflow.service.single_task_flow import single_task_executor

    result = single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        source_execution_id="exec-001",
        project_id="project-1",
        update_params=True,
    )

    session = _session(sessions)
    assert result == {"task_name": "CheckRabi", "qid": "0"}
    assert session.role.value == "owner"
    assert session.initialized_qids == ["0"]
    assert session.execution_id is None  # Allocated when the Execution opens.
    assert session.settings.project_id == "project-1"
    assert session.settings.snapshot.execution_id == "exec-001"
    assert session.settings.force_update_params is True
    assert session.finished is True


def test_single_task_executor_preserves_coupling_qid(sessions):
    """A coupling target remains intact through session initialization and execution."""
    from qdash.workflow.service.single_task_flow import single_task_executor

    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="32-33",
        task_name="CheckCrossResonance",
        backend_name="qubex",
    )

    session = _session(sessions)
    assert session.initialized_qids == ["32-33"]
    assert session.calls == [("CheckCrossResonance", "32-33", None)]


def test_single_task_executor_exempts_reconfigure_from_snapshot(sessions):
    """Configure runs inside the same owned Execution, before the task."""
    from qdash.workflow.service.single_task_flow import single_task_executor

    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        source_execution_id="exec-001",
        source_task_id="task-001",
        project_id="project-1",
        reconfigure=True,
    )

    session = _session(sessions)
    assert session.settings.snapshot.exempt_tasks == frozenset({"Configure"})
    assert session.settings.snapshot.task_id == "task-001"
    assert [name for name, _, _ in session.calls] == ["Configure", "CheckRabi"]
    assert session.finished is True


@pytest.mark.parametrize("source_task_id", [None, "source-task"])
def test_single_task_executor_accepts_quick_run_parameters(sessions, source_task_id):
    from qdash.workflow.service.single_task_flow import single_task_executor

    defaults = {"CheckRabi": {"shots": {"value": 100}}}
    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        project_id="project-1",
        backend_name="fake",
        source_task_id=source_task_id,
        task_run_parameters=defaults,
        update_calibration_parameters=False,
        update_params=False,
    )

    settings = _session(sessions).settings
    assert settings.snapshot.execution_id is None
    assert settings.snapshot.task_id == source_task_id
    assert settings.snapshot.exempt_tasks == frozenset({"CheckRabi"})
    assert settings.backend_name == "fake"
    assert settings.task_defaults == {
        "CheckRabi": {
            "run": {"shots": {"value": 100}},
            "input": {},
            "update_calibration_parameters": False,
        }
    }


def test_single_task_executor_scopes_request_overrides_to_the_task(sessions):
    from qdash.workflow.service.single_task_flow import single_task_executor

    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        source_execution_id="exec-1",
        source_task_id="source-task",
        project_id="project-1",
        backend_name="fake",
        parameter_overrides={"input": {"control_amplitude": 0.05}, "run": {"shots": 2000}},
    )

    assert _session(sessions).settings.task_defaults == {
        "CheckRabi": {
            "run": {"shots": {"value": 2000}},
            "input": {"control_amplitude": 0.05},
            "update_calibration_parameters": True,
        }
    }


def test_single_task_executor_rejects_an_unauthorized_context(monkeypatch):
    """The worker re-checks the user's project permission before any session exists."""
    from qdash.workflow.service.context import AccessDecision, CalibContextError
    from qdash.workflow.service.single_task_flow import single_task_executor

    class DenyingDirectory:
        def default_project_id(self, username: str) -> str:
            return "project-1"

        def write_access(self, username: str, project_id: str) -> AccessDecision:
            return AccessDecision.DENIED

    monkeypatch.setattr(
        "qdash.workflow.service.context.MongoProjectAccessDirectory", DenyingDirectory
    )
    opened = MagicMock()
    monkeypatch.setattr("qdash.workflow.service._internal.runs.CalibSession", opened)

    with pytest.raises(CalibContextError, match="editor or owner"):
        single_task_executor(username="mallory", chip_id="chip-1", qid="0", task_name="CheckRabi")
    opened.assert_not_called()


def _run_single_task(
    monkeypatch: pytest.MonkeyPatch, sessions: type[RecordingSession], **request: Any
) -> RecordingSession:
    """Run the flow with GitHub enabled and return its session."""
    from qdash.workflow.service.single_task_flow import single_task_executor

    monkeypatch.setattr(
        "qdash.common.config.loader.ConfigLoader.load_workflow",
        lambda: {"github": {"enabled": True}},
    )
    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        project_id="project-1",
        backend_name="qubex",
        **request,
    )
    return _session(sessions)


def _writeback(session: RecordingSession) -> dict[str, Any]:
    """Return what the run applied to each executed call and to GitHub publication."""
    settings = session.settings
    applied = {"CheckRabi": settings.task_defaults["CheckRabi"]["update_calibration_parameters"]}
    for name, _, parameters in session.calls:
        if name == "Configure":
            applied["Configure"] = parameters["update_calibration_parameters"]
    applied["github"] = settings.github.push.enabled
    return applied


@pytest.mark.parametrize(
    ("request_fields", "expected", "deprecated"),
    [
        # Omitted keeps the deployment default.
        ({}, True, False),
        ({"update_calibration_parameters": True}, True, False),
        ({"update_calibration_parameters": False}, False, False),
        # Runs queued by an older API server still apply their value, False included.
        ({"persist_output_parameters": True}, True, True),
        ({"persist_output_parameters": False}, False, True),
        (
            {"update_calibration_parameters": False, "persist_output_parameters": False},
            False,
            True,
        ),
    ],
)
@pytest.mark.parametrize("reconfigure", [False, True])
def test_single_task_executor_resolves_one_writeback_control(
    monkeypatch, sessions, request_fields, expected, deprecated, reconfigure
):
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        session = _run_single_task(monkeypatch, sessions, reconfigure=reconfigure, **request_fields)

    applied = _writeback(session)
    assert applied == {
        "CheckRabi": expected,
        **({"Configure": expected} if reconfigure else {}),
        "github": expected,
    }
    messages = [str(w.message) for w in caught if w.category is DeprecationWarning]
    assert any("persist_output_parameters is deprecated" in m for m in messages) is deprecated


@pytest.mark.parametrize(
    "request_fields",
    [
        {"update_calibration_parameters": True, "persist_output_parameters": False},
        {"update_calibration_parameters": False, "persist_output_parameters": True},
        # A nested value cannot silently override the top-level control...
        {
            "update_calibration_parameters": True,
            "parameter_overrides": {"update_calibration_parameters": False},
        },
        {
            "update_calibration_parameters": False,
            "task_run_parameters": {"CheckRabi": {"update_calibration_parameters": True}},
        },
        # ...including on the Configure call it also controls.
        {
            "update_calibration_parameters": False,
            "reconfigure": True,
            "task_run_parameters": {"Configure": {"update_calibration_parameters": True}},
        },
        {
            "persist_output_parameters": True,
            "parameter_overrides": {"update_calibration_parameters": False},
        },
        # Without a top-level control, nested values must agree across executed calls.
        {
            "reconfigure": True,
            "task_run_parameters": {
                "CheckRabi": {"update_calibration_parameters": False},
                "Configure": {"update_calibration_parameters": True},
            },
        },
        {
            "parameter_overrides": {"update_calibration_parameters": False},
            "task_run_parameters": {"CheckRabi": {"update_calibration_parameters": True}},
        },
        {"parameter_overrides": {"update_calibration_parameters": "false"}},
        {"update_calibration_parameters": "false", "persist_output_parameters": False},
    ],
)
def test_single_task_executor_rejects_conflicts_before_hardware(sessions, request_fields):
    from qdash.workflow.service.single_task_flow import single_task_executor

    with pytest.raises(Exception, match="update_calibration_parameters"):
        single_task_executor(
            username="alice",
            chip_id="chip-1",
            qid="0",
            task_name="CheckRabi",
            project_id="project-1",
            backend_name="fake",
            **request_fields,
        )

    # No calibration session, hence no hardware connection or lock, was created.
    assert sessions.instances == []


@pytest.mark.parametrize(
    ("request_fields", "expected"),
    [
        # A redundant nested value equal to the top-level control is accepted.
        (
            {
                "update_calibration_parameters": False,
                "reconfigure": True,
                "parameter_overrides": {"update_calibration_parameters": False},
                "task_run_parameters": {
                    "CheckRabi": {"update_calibration_parameters": False},
                    "Configure": {"update_calibration_parameters": False},
                },
            },
            False,
        ),
        # Nested-only values become the control of every executed call.
        ({"parameter_overrides": {"update_calibration_parameters": False}}, False),
        (
            {
                "reconfigure": True,
                "task_run_parameters": {"CheckRabi": {"update_calibration_parameters": False}},
            },
            False,
        ),
        (
            {
                "reconfigure": True,
                "task_run_parameters": {"Configure": {"update_calibration_parameters": False}},
            },
            False,
        ),
    ],
)
def test_single_task_executor_migrates_nested_writeback(
    monkeypatch, sessions, request_fields, expected
):
    with pytest.warns(DeprecationWarning, match="set the top-level update_calibration_parameters"):
        session = _run_single_task(monkeypatch, sessions, **request_fields)

    applied = _writeback(session)
    assert applied["CheckRabi"] is expected
    assert applied["github"] is expected
    if request_fields.get("reconfigure"):
        assert applied["Configure"] is expected
    # The nested value is stripped, so only the control reaches the session.
    defaults = session.settings.task_defaults
    assert "update_calibration_parameters" not in defaults.get("Configure", {})


def test_single_task_executor_ignores_settings_of_calls_it_does_not_run(monkeypatch, sessions):
    """A nested value on a call outside this run neither conflicts nor warns."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        session = _run_single_task(
            monkeypatch,
            sessions,
            update_calibration_parameters=True,
            task_run_parameters={"Configure": {"update_calibration_parameters": False}},
        )

    assert _writeback(session) == {"CheckRabi": True, "github": True}
    assert session.calls == [("CheckRabi", "0", None)]


@pytest.mark.parametrize(
    ("exc", "handler"),
    [
        (RuntimeError("boom"), "fail_calibration"),
        (CancelledRun("cancelled"), "cancel_calibration"),
        (TerminationSignal("SIGTERM"), "abandon_calibration"),
    ],
)
@pytest.mark.parametrize("reconfigure", [False, True])
def test_single_task_executor_routes_aborts_to_one_handler(sessions, exc, handler, reconfigure):
    """Each kind of abort reaches exactly one terminal handler, Configure included."""
    from qdash.workflow.service.single_task_flow import single_task_executor

    sessions.error = exc
    with pytest.raises(type(exc)):
        single_task_executor(
            username="alice",
            chip_id="chip-1",
            qid="0",
            task_name="CheckRabi",
            reconfigure=reconfigure,
        )

    session = _session(sessions)
    assert session.finished is False
    for name in ("fail_calibration", "cancel_calibration", "abandon_calibration"):
        assert getattr(session, name).called is (name == handler)


@pytest.mark.parametrize(
    ("exc", "handler"),
    [
        (RuntimeError("boom"), "fail_calibration"),
        (CancelledRun("cancelled"), "cancel_calibration"),
        (TerminationSignal("SIGTERM"), "abandon_calibration"),
    ],
)
def test_single_task_executor_keeps_the_abort_when_cleanup_fails(sessions, exc, handler):
    """A handler that raises must not replace the abort that triggered it."""
    from qdash.workflow.service.single_task_flow import single_task_executor

    sessions.error = exc
    sessions.failing_handler = handler
    with pytest.raises(type(exc)) as raised:
        single_task_executor(
            username="alice",
            chip_id="chip-1",
            qid="0",
            task_name="CheckRabi",
        )

    assert raised.value is exc
