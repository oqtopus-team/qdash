"""Tests for finalizing an execution's leftover tasks with backoff retries."""

from types import MethodType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.workflow.service._internal.session import ExecutionRuntime

FINALIZERS = [
    (
        "_finalize_stale_running_tasks",
        "finalize_running_tasks",
        "Finalized 2 stale task(s) still in RUNNING status for execution exec-1",
        "Failed to finalize stale running tasks: boom",
    ),
    (
        "_finalize_tasks_on_cancel",
        "finalize_tasks_on_cancel",
        "Cancelled 2 non-terminal task(s) for execution exec-1",
        "Failed to finalize tasks on cancel: boom",
    ),
]


def _runtime(project_id: str | None = "proj-1") -> Any:
    runtime = SimpleNamespace(
        execution_service=SimpleNamespace(project_id=project_id), execution_id="exec-1"
    )
    for name in ("_finalize_stale_running_tasks", "_finalize_tasks_on_cancel"):
        setattr(runtime, name, MethodType(getattr(ExecutionRuntime, name), runtime))
    runtime._finalize_tasks_with_retry = MethodType(
        ExecutionRuntime._finalize_tasks_with_retry, runtime
    )
    return runtime


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    repo = MagicMock()
    monkeypatch.setattr("qdash.repository.MongoTaskResultHistoryRepository", lambda: repo)
    return repo


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr("qdash.workflow.service._internal.session.time.sleep", slept.append)
    return slept


@pytest.mark.parametrize(("method", "repo_method", "finalized", "_failure"), FINALIZERS)
def test_retries_with_backoff_until_nothing_is_left(
    repo: MagicMock,
    sleeps: list[float],
    method: str,
    repo_method: str,
    finalized: str,
    _failure: str,
) -> None:
    getattr(repo, repo_method).side_effect = [2, 0]
    logger = MagicMock()

    getattr(_runtime(), method)(logger, message="done")

    assert getattr(repo, repo_method).call_count == 2
    getattr(repo, repo_method).assert_called_with(
        project_id="proj-1", execution_id="exec-1", message="done"
    )
    assert sleeps == [0.5]
    logger.warning.assert_called_once_with(f"[attempt 1/5] {finalized}")
    logger.info.assert_not_called()


@pytest.mark.parametrize(("method", "repo_method", "_finalized", "_failure"), FINALIZERS)
def test_stops_after_last_attempt_without_a_final_sleep(
    repo: MagicMock,
    sleeps: list[float],
    method: str,
    repo_method: str,
    _finalized: str,
    _failure: str,
) -> None:
    getattr(repo, repo_method).return_value = 1

    getattr(_runtime(), method)(MagicMock())

    assert getattr(repo, repo_method).call_count == 5
    assert sleeps == [0.5, 1, 2, 3]


@pytest.mark.parametrize(("method", "repo_method", "_finalized", "failure"), FINALIZERS)
def test_logs_terminal_state_and_swallows_errors(
    repo: MagicMock,
    sleeps: list[float],
    method: str,
    repo_method: str,
    _finalized: str,
    failure: str,
) -> None:
    getattr(repo, repo_method).return_value = 0
    logger = MagicMock()
    getattr(_runtime(), method)(logger)
    logger.info.assert_called_once_with("All tasks in terminal state for execution exec-1")

    getattr(repo, repo_method).side_effect = RuntimeError("boom")
    getattr(_runtime(), method)(logger)
    logger.warning.assert_called_once_with(failure)
    assert sleeps == []


@pytest.mark.parametrize(("method", "repo_method", "_finalized", "_failure"), FINALIZERS)
def test_skips_without_project(
    repo: MagicMock, method: str, repo_method: str, _finalized: str, _failure: str
) -> None:
    getattr(_runtime(project_id=None), method)(MagicMock())

    getattr(repo, repo_method).assert_not_called()
