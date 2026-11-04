"""An investigation opens with project-scoped logs, identifiers and honest source revisions."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException

from qdash.api.services.copilot_investigation_service import (
    STACK_TRACE_LIMIT,
    CopilotInvestigationService,
    InvestigationNotFoundError,
    clip,
)
from qdash.api.services.source_access_service import SourceRoot
from qdash.copilot.contracts import InvestigationTarget


def _execution(**overrides):
    values: dict[str, Any] = {
        "name": "daily",
        "flow_name": "daily_flow",
        "chip_id": "64Qv3",
        "status": "failed",
        "start_at": None,
        "end_at": None,
        "message": "Flow run crashed: ConnectionError: box unreachable",
        "task": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _Executions:
    def __init__(self, execution):
        self.execution = execution
        self.calls = []

    def get_execution(self, project_id, execution_id):
        self.calls.append((project_id, execution_id))
        return self.execution


class _Tasks:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def get_task_result(self, project_id, task_id):
        self.calls.append((project_id, task_id))
        if self.result is None:
            raise HTTPException(status_code=404, detail="not found")
        return self.result


class _Source:
    def __init__(self, roots=(), missing=()):
        self.roots = tuple(roots)
        self._missing = list(missing)

    def missing_dependencies(self):
        return self._missing


QDASH = SourceRoot(
    name="qdash",
    path=Path("/src/qdash"),
    kind="qdash",
    revision="abc123",
    revision_source="git",
    dirty=True,
)


def _build(execution, *, result=None, roots=(QDASH,), missing=(), **target):
    tasks = _Tasks(result)
    executions = _Executions(execution)
    service = CopilotInvestigationService(
        cast("Any", executions), cast("Any", tasks), cast("Any", _Source(roots, missing))
    )
    context = service.build(
        project_id="proj",
        target=InvestigationTarget(execution_id="e1", **target),
        user_message="Investigate why execution e1 failed.",
        language_instruction="Answer in English.",
    )
    return context, executions, tasks


def test_execution_failure_without_a_task_result():
    context, executions, tasks = _build(_execution())
    message = context.opening_message
    assert executions.calls == [("proj", "e1")]
    assert tasks.calls == []
    assert not context.has_task_result and context.has_logs
    assert "Execution ID: `e1`" in message
    assert "ConnectionError: box unreachable" in message
    assert "## Task" not in message
    assert message.rstrip().endswith("Investigate why execution e1 failed.")


def test_task_result_logs_and_stack_trace():
    result = SimpleNamespace(
        task_name="CheckRabi",
        qid="3",
        task_id="t1",
        execution_id="e1",
        status="failed",
        message="ValueError: fit did not converge",
        stack_trace='Traceback (most recent call last):\n  File "/app/qdash/x.py", line 4\n```',
    )
    context, _, tasks = _build(_execution(), result=result, task_id="t1")
    message = context.opening_message
    assert tasks.calls == [("proj", "t1")]
    assert context.has_task_result
    assert "CheckRabi on `3`" in message
    assert "ValueError: fit did not converge" in message
    # The trace's own backticks cannot close its block.
    assert "````text" in message


def test_task_without_result_falls_back_to_the_execution_record():
    execution = _execution(
        task=[
            SimpleNamespace(task_id="t9", name="CheckT1", qid="5", status="failed", message="boom")
        ]
    )
    context, _, _ = _build(execution, task_id="t9")
    assert not context.has_task_result
    assert "No task result is recorded" in context.opening_message
    assert "CheckT1" in context.opening_message
    assert "boom" in context.opening_message


def test_missing_logs_and_source_are_stated():
    context, _, _ = _build(_execution(message=""), roots=(), missing=["qubex"])
    message = context.opening_message
    assert not context.has_logs
    assert "No logs were recorded" in message
    assert "No source roots are available" in message
    assert "Not available here: `qubex`" in message


def test_revisions_are_disclosed_without_claiming_a_match():
    message = _build(_execution(), missing=["qubex"])[0].opening_message
    assert "revision `abc123` (from git) with uncommitted local changes" in message
    assert "does not record which source revision an execution ran with" in message
    assert "cannot establish" in message.lower()


def test_instructions_ask_for_a_concise_grounded_diagnosis():
    message = _build(_execution())[0].opening_message
    instructions = message[message.index("## What to do") :]
    # Three compact items replace the former six-section report.
    for item in ("**Likely cause**", "**Evidence**", "**Next step**"):
        assert item in instructions
    for removed in ("Facts and hypotheses", "Suggested fixes", "Next checks", "callers in QDash"):
        assert removed not in instructions
    # Reading starts at the raising frame and stops once the error is explained.
    assert "frame that raised the error" in instructions
    assert "Stop reading once the logs and that code explain the error" in instructions
    assert "ambiguous or contradictory" in instructions
    assert "single most useful check" in instructions
    # Concise does not weaken grounding or the read-only boundary.
    assert "read-only" in instructions
    assert "never apply it" in instructions
    assert "Quote and cite only what you read" in instructions
    assert "`root:path:line`" in instructions
    assert "revision caveat" in instructions
    assert "missing or clipped" in instructions
    assert "unavailable" in instructions


def test_unknown_execution_is_refused():
    with pytest.raises(InvestigationNotFoundError):
        _build(None)


def test_clip_keeps_the_end_of_a_long_trace():
    trace = "start\n" + "x" * (STACK_TRACE_LIMIT * 2) + "\nValueError: last line"
    clipped, was_clipped = clip(trace, STACK_TRACE_LIMIT)
    assert was_clipped
    assert clipped.startswith("start")
    assert clipped.endswith("ValueError: last line")
    assert "characters omitted" in clipped
    assert clip("short", 10) == ("short", False)


def test_task_result_from_another_execution_is_rejected():
    result = SimpleNamespace(execution_id="other-execution")
    with pytest.raises(HTTPException) as exc:
        _build(_execution(), result=result, task_id="t1")
    assert exc.value.status_code == 400
    assert "does not belong" in exc.value.detail
