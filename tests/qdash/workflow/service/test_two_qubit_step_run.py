"""Tests for the run shared by the two-qubit steps."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.workflow.service.results import TwoQubitResult
from qdash.workflow.service.steps import two_qubit
from qdash.workflow.service.steps.pipeline import StepContext


def _step(rounds: Any) -> Any:
    built = TwoQubitResult(step_id="two_qubit")
    built.successful_couplings = lambda: ["0-1"]  # type: ignore[method-assign]
    return SimpleNamespace(
        _rounds=rounds,
        name="two_qubit",
        resolved_step_id="two_qubit",
        _build_result=MagicMock(return_value=built),
    )


@pytest.fixture(autouse=True)
def _logger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(two_qubit, "get_run_logger", MagicMock)


@pytest.mark.parametrize("manual", [True, False])
def test_records_stage_and_builds_result(monkeypatch: pytest.MonkeyPatch, manual: bool) -> None:
    raw = {"0-1": {"status": "success"}}
    monkeypatch.setattr(two_qubit, "_execute_manual_two_qubit", lambda *a: raw)
    monkeypatch.setattr(two_qubit, "_run_automatic", lambda *a: raw)
    step = _step([[("0", "1")]] if manual else None)
    session = MagicMock()

    result = two_qubit._run_two_qubit_step(step, session, MagicMock(), StepContext(), MagicMock())

    assert result is step._build_result.return_value
    step._build_result.assert_called_once_with(raw)
    session.record_stage_result.assert_called_once_with("two_qubit", raw)


def test_no_automatic_pair_returns_empty_result_without_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(two_qubit, "_run_automatic", lambda *a: None)
    step = _step(None)
    session = MagicMock()

    result = two_qubit._run_two_qubit_step(step, session, MagicMock(), StepContext(), MagicMock())

    assert result.step_id == "two_qubit"
    assert result.couplings == {}
    session.record_stage_result.assert_not_called()
    step._build_result.assert_not_called()
