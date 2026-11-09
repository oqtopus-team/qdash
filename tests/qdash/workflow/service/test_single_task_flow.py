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
        persist_output_parameters=persist,
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
        persist_output_parameters=False,
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


@pytest.mark.parametrize(
    ("persist", "requested", "expected"),
    [
        # Explicit per-task settings override the request fallback.
        (False, True, True),
        (False, None, False),
        # A writing request keeps an explicit per-task False.
        (True, False, False),
        (True, None, True),
    ],
)
@pytest.mark.parametrize("source", ["task_run_parameters", "parameter_overrides"])
def test_single_task_executor_resolves_writeback_per_task(
    monkeypatch, persist, requested, expected, source
):
    from unittest.mock import MagicMock

    from qdash.workflow.service.single_task_flow import single_task_executor

    service = MagicMock()
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", service)
    setting = {} if requested is None else {"update_calibration_parameters": requested}
    request: dict[str, Any] = (
        {"task_run_parameters": {"CheckRabi": setting}}
        if source == "task_run_parameters"
        else {"parameter_overrides": setting}
    )

    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        project_id="project-1",
        backend_name="fake",
        persist_output_parameters=persist,
        **request,
    )

    defaults = service.call_args.kwargs["_task_defaults"]
    assert defaults["CheckRabi"]["update_calibration_parameters"] is expected
    assert service.call_args.kwargs["github_push_config"].enabled is False


@pytest.mark.parametrize("persist", [False, True])
@pytest.mark.parametrize("configured", [None, False, True])
def test_single_task_executor_resolves_reconfigure_writeback(monkeypatch, persist, configured):
    from unittest.mock import MagicMock

    from qdash.workflow.service.single_task_flow import single_task_executor

    service = MagicMock()
    monkeypatch.setattr("qdash.workflow.service.single_task_flow.CalibService", service)

    single_task_executor(
        username="alice",
        chip_id="chip-1",
        qid="0",
        task_name="CheckRabi",
        project_id="project-1",
        persist_output_parameters=persist,
        reconfigure=True,
        task_run_parameters=(
            None
            if configured is None
            else {"Configure": {"update_calibration_parameters": configured}}
        ),
    )

    defaults = service.call_args.kwargs["_task_defaults"]
    assert set(defaults) == ({"CheckRabi"} if configured is None else {"CheckRabi", "Configure"})
    assert defaults["CheckRabi"]["update_calibration_parameters"] is persist
    configure, task = service.return_value.execute_task.call_args_list
    assert configure.args == ("Configure", "0")
    assert configure.kwargs == {
        "parameters": {
            "update_calibration_parameters": persist if configured is None else configured
        }
    }
    assert task.args == ("CheckRabi", "0")
    assert defaults["CheckRabi"]["update_calibration_parameters"] is persist
    assert service.return_value.execute_task.call_args_list[0].args == ("Configure", "0")


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
