from __future__ import annotations

from typing import Any


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
    assert captured["finished"] is True
