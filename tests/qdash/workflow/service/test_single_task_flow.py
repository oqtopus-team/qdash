from __future__ import annotations

from typing import Any

import pytest


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
    assert kwargs["persist_output_parameters"] is persist
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
    assert captured["kwargs"]["persist_output_parameters"] is True
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
    assert captured["kwargs"]["persist_output_parameters"] is True
    assert captured["kwargs"]["force_update_params"] is False


def test_single_task_executor_exempts_reconfigure_from_snapshot(monkeypatch):
    from qdash.workflow.service.single_task_flow import single_task_executor

    captured: dict[str, Any] = {}
    calls: list[str] = []

    class FakeCalibService:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured.update(kwargs)

        def execute_task(self, task_name: str, qid: str) -> dict[str, Any]:
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
        default_run_parameters=defaults,
        persist_output_parameters=False,
        update_params=False,
    )

    assert captured["kwargs"]["source_execution_id"] is None
    assert captured["kwargs"]["source_task_id"] == source_task_id
    assert captured["kwargs"]["snapshot_exempt_tasks"] == {"CheckRabi"}
    assert captured["kwargs"]["backend_name"] == "fake"
    assert captured["kwargs"]["default_run_parameters"] == defaults
    assert captured["kwargs"]["persist_output_parameters"] is False
