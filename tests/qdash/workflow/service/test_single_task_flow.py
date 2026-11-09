from __future__ import annotations

from typing import Any

import pytest


class CancelledRun(Exception):
    """Stand-in for prefect.exceptions.CancelledRun, which is matched by class name."""


class ExternalSignal(BaseException):
    """Stand-in for prefect.exceptions.ExternalSignal."""


class TerminationSignal(ExternalSignal):
    """Stand-in for prefect.exceptions.TerminationSignal."""


@pytest.mark.parametrize("persist", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("backend", ["qubex", "fake"])
def test_single_task_publication_follows_persistence_and_integration(
    monkeypatch, persist, enabled, force, backend
):
    """Tasks saves publish without forcing rejected calibration values into YAML."""
    from unittest.mock import MagicMock

    from qdash.workflow.service.single_task_flow import single_task_executor

    service = MagicMock()
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", service)
    monkeypatch.setattr(
        "qdash.workflow.service.single_task_flow.ConfigLoader.load_workflow",
        lambda: {"github": {"enabled": enabled, "branch": "calibration"}},
    )
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.get_run_logger", MagicMock)

    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        backend_name=backend,
        update_calibration_parameters=persist,
        update_params=force,
    )

    kwargs = service.call_args.kwargs
    assert kwargs["github_push_config"].enabled is (persist and enabled and backend == "qubex")
    assert kwargs["github_push_config"].branch == "calibration"
    assert "persist_output_parameters" not in kwargs
    assert kwargs["_task_defaults"]["CheckRabi"]["update_calibration_parameters"] is persist
    assert kwargs["force_update_params"] is force
    assert kwargs["enable_github_pull"] is (enabled and backend == "qubex")
    service.return_value.execute_task.assert_called_once_with("CheckRabi", "0")
    service.return_value.finish_calibration.assert_called_once_with()


def test_single_task_executor_pulls_config_before_reexecute(monkeypatch):
    """Re-execute must pull latest config before a possible params batch push."""
    from qdash.workflow.service.single_task_flow import single_task_executor

    captured: dict[str, Any] = {}

    class FakeCalibService:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["kwargs"] = kwargs

        def execute_task(self, task_name: str, qid: str) -> dict[str, Any]:
            return {"task_name": task_name, "qid": qid}

        def finish_calibration(self) -> None:
            captured["finished"] = True

    monkeypatch.setattr(
        "qdash.workflow.service.single_task_flow.CalibService",
        FakeCalibService,
    )

    result = single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        source_execution_id="exec-001",
        project_id="project-1",
        update_params=True,
    )

    assert result == {"task_name": "CheckRabi", "qid": "0"}
    assert captured["kwargs"]["enable_github_pull"] is True
    assert captured["kwargs"]["enable_github"] is True
    assert captured["kwargs"]["_task_defaults"]["CheckRabi"]["update_calibration_parameters"]
    assert captured["kwargs"]["use_lock"] is True
    assert "execution_id" not in captured["kwargs"]
    assert captured["finished"] is True

    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        source_execution_id="exec-001",
        project_id="project-1",
        update_params=False,
    )

    assert captured["kwargs"]["enable_github"] is True
    assert captured["kwargs"]["_task_defaults"]["CheckRabi"]["update_calibration_parameters"]
    assert captured["kwargs"]["force_update_params"] is False


def test_single_task_executor_preserves_coupling_qid(monkeypatch):
    """A coupling target remains intact through session initialization and execution."""
    from unittest.mock import MagicMock

    from qdash.workflow.service.single_task_flow import single_task_executor

    service = MagicMock()
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", service)
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.get_run_logger", MagicMock)

    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="32-33",
        task_name="CheckCrossResonance",
        backend_name="qubex",
    )

    assert service.call_args.kwargs["qids"] == ["32-33"]
    service.return_value.execute_task.assert_called_once_with("CheckCrossResonance", "32-33")


def test_single_task_executor_exempts_reconfigure_from_snapshot(monkeypatch):
    from qdash.workflow.service.single_task_flow import single_task_executor

    captured: dict[str, Any] = {}
    calls: list[str] = []

    class FakeCalibService:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured.update(kwargs)

        def execute_task(
            self, task_name: str, qid: str, *, parameters: Any = None
        ) -> dict[str, Any]:
            calls.append(task_name)
            return {"task_name": task_name, "qid": qid}

        def finish_calibration(self) -> None:
            pass

    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", FakeCalibService)

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

    assert captured["snapshot_exempt_tasks"] == {"Configure"}
    assert calls == ["Configure", "CheckRabi"]


@pytest.mark.parametrize("source_task_id", [None, "source-task"])
def test_single_task_executor_accepts_quick_run_parameters(monkeypatch, source_task_id):
    from qdash.workflow.service.single_task_flow import single_task_executor

    captured: dict[str, Any] = {}

    class FakeCalibService:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["kwargs"] = kwargs

        def execute_task(self, task_name: str, qid: str) -> dict[str, Any]:
            return {"task_name": task_name, "qid": qid}

        def finish_calibration(self) -> None:
            pass

    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", FakeCalibService)

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

    assert captured["kwargs"]["source_execution_id"] is None
    assert captured["kwargs"]["source_task_id"] == source_task_id
    assert captured["kwargs"]["snapshot_exempt_tasks"] == {"CheckRabi"}
    assert captured["kwargs"]["backend_name"] == "fake"
    assert captured["kwargs"]["_task_defaults"] == {
        "CheckRabi": {
            "run": {"shots": {"value": 100}},
            "input": {},
            "update_calibration_parameters": False,
        }
    }
    assert "persist_output_parameters" not in captured["kwargs"]


def test_single_task_executor_scopes_request_overrides_to_the_task(monkeypatch):
    from qdash.workflow.service.single_task_flow import single_task_executor

    captured: dict[str, Any] = {}

    class FakeCalibService:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["kwargs"] = kwargs

        def execute_task(self, task_name: str, qid: str) -> dict[str, Any]:
            return {"task_name": task_name, "qid": qid}

        def finish_calibration(self) -> None:
            pass

    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", FakeCalibService)

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

    assert "parameter_overrides" not in captured["kwargs"]
    assert captured["kwargs"]["_task_defaults"] == {
        "CheckRabi": {
            "run": {"shots": {"value": 2000}},
            "input": {"control_amplitude": 0.05},
            "update_calibration_parameters": True,
        }
    }


def _run_single_task(monkeypatch: pytest.MonkeyPatch, **request: Any) -> Any:
    """Run the flow with a mocked CalibService and return the mock."""
    from unittest.mock import MagicMock

    from qdash.workflow.service.single_task_flow import single_task_executor

    service = MagicMock()
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", service)
    monkeypatch.setattr(
        "qdash.workflow.service.single_task_flow.ConfigLoader.load_workflow",
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
    return service


def _writeback(service: Any) -> dict[str, Any]:
    """Return what the run applied to each executed call and to GitHub publication."""
    kwargs = service.call_args.kwargs
    applied = {"CheckRabi": kwargs["_task_defaults"]["CheckRabi"]["update_calibration_parameters"]}
    for call in service.return_value.execute_task.call_args_list:
        if call.args[0] == "Configure":
            applied["Configure"] = call.kwargs["parameters"]["update_calibration_parameters"]
    applied["github"] = kwargs["github_push_config"].enabled
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
    monkeypatch, request_fields, expected, deprecated, reconfigure
):
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        service = _run_single_task(monkeypatch, reconfigure=reconfigure, **request_fields)

    applied = _writeback(service)
    assert applied == {
        "CheckRabi": expected,
        **({"Configure": expected} if reconfigure else {}),
        "github": expected,
    }
    assert "persist_output_parameters" not in service.call_args.kwargs
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
def test_single_task_executor_rejects_conflicts_before_hardware(monkeypatch, request_fields):
    from unittest.mock import MagicMock

    from qdash.workflow.service.single_task_flow import single_task_executor

    service = MagicMock()
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", service)

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
    service.assert_not_called()


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
def test_single_task_executor_migrates_nested_writeback(monkeypatch, request_fields, expected):
    with pytest.warns(DeprecationWarning, match="set the top-level update_calibration_parameters"):
        service = _run_single_task(monkeypatch, **request_fields)

    applied = _writeback(service)
    assert applied["CheckRabi"] is expected
    assert applied["github"] is expected
    if request_fields.get("reconfigure"):
        assert applied["Configure"] is expected
    # The nested value is stripped, so only the control reaches the session.
    defaults = service.call_args.kwargs["_task_defaults"]
    assert "update_calibration_parameters" not in defaults.get("Configure", {})


def test_single_task_executor_ignores_settings_of_calls_it_does_not_run(monkeypatch):
    """A nested value on a call outside this run neither conflicts nor warns."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        service = _run_single_task(
            monkeypatch,
            update_calibration_parameters=True,
            task_run_parameters={"Configure": {"update_calibration_parameters": False}},
        )

    assert _writeback(service) == {"CheckRabi": True, "github": True}
    service.return_value.execute_task.assert_called_once_with("CheckRabi", "0")


@pytest.mark.parametrize(
    ("exc", "handler"),
    [
        (RuntimeError("boom"), "fail_calibration"),
        (CancelledRun("cancelled"), "cancel_calibration"),
        (TerminationSignal("SIGTERM"), "abandon_calibration"),
    ],
)
def test_single_task_executor_routes_aborts_to_one_handler(monkeypatch, exc, handler):
    """Each kind of abort reaches exactly one terminal handler."""
    from unittest.mock import MagicMock

    from qdash.workflow.service.single_task_flow import single_task_executor

    service = MagicMock()
    service.return_value.execute_task.side_effect = exc
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", service)

    with pytest.raises(type(exc)):
        single_task_executor(
            username="alice",
            chip_id="chip-1",
            qid="0",
            task_name="CheckRabi",
        )

    cal = service.return_value
    for name in ("fail_calibration", "cancel_calibration", "abandon_calibration"):
        if name == handler:
            getattr(cal, name).assert_called_once()
        else:
            getattr(cal, name).assert_not_called()


@pytest.mark.parametrize(
    ("exc", "handler"),
    [
        (RuntimeError("boom"), "fail_calibration"),
        (CancelledRun("cancelled"), "cancel_calibration"),
        (TerminationSignal("SIGTERM"), "abandon_calibration"),
    ],
)
def test_single_task_executor_keeps_the_abort_when_cleanup_fails(monkeypatch, exc, handler):
    """A handler that raises must not replace the abort that triggered it."""
    from unittest.mock import MagicMock

    from qdash.workflow.service.single_task_flow import single_task_executor

    service = MagicMock()
    service.return_value.execute_task.side_effect = exc
    getattr(service.return_value, handler).side_effect = RuntimeError("releasing the lock failed")
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", service)

    with pytest.raises(type(exc)) as raised:
        single_task_executor(
            username="alice",
            chip_id="chip-1",
            qid="0",
            task_name="CheckRabi",
        )

    assert raised.value is exc
