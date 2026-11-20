"""MetricDataBroker time limits, with fake repositories (mongomock ignores timeouts)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from pymongo import _csot
from pymongo.errors import ExecutionTimeout, NetworkTimeout, OperationFailure

from qdash.api.metric_runtime import executor
from qdash.api.metric_runtime.broker import (
    DATA_TIMEOUT_MESSAGE,
    BrokerTimeoutError,
    MetricDataBroker,
)
from qdash.api.services.metrics_service import MetricsService

END = datetime(2026, 11, 20, tzinfo=UTC)
START = END - timedelta(days=14)
HISTORY_ARGS = {
    "kind": "qubit",
    "metric": "t1",
    "target": "0",
    "start": START.isoformat(),
    "end": END.isoformat(),
}


class FakeTaskResults:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.kwargs: list[dict[str, Any]] = []
        self.remaining: list[float | None] = []

    def find(self, query: dict[str, Any], **kwargs: Any) -> list[Any]:
        self.kwargs.append(kwargs)
        # The client-side operation timeout pymongo applies to this query.
        self.remaining.append(_csot.remaining())
        if self.error is not None:
            raise self.error
        return []


class FakeMetrics:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.calls = 0

    def get_chip_metrics(self, **_kwargs: Any) -> Any:
        self.calls += 1
        if self.error is not None:
            raise self.error
        value = SimpleNamespace(value=42.0, task_id="task-1", execution_id="exec-1")
        return SimpleNamespace(qubit_metrics={"t1": {"Q00": value}}, coupling_metrics={})


def make_broker(
    task_results: FakeTaskResults | None = None, metrics: FakeMetrics | MetricsService | None = None
) -> MetricDataBroker:
    return MetricDataBroker(
        project_id="proj-1",
        username="alice",
        chip_id="chip-1",
        start=START,
        end=END,
        topology={"qubits": {}, "couplings": [], "muxes": {}},
        metrics_service=metrics or FakeMetrics(),  # type: ignore[arg-type]
        task_result_repository=task_results or FakeTaskResults(),  # type: ignore[arg-type]
    )


def test_history_query_is_bounded_by_the_time_left():
    task_results = FakeTaskResults()
    make_broker(task_results).handle("history", HISTORY_ARGS, timeout=2.5)
    assert task_results.kwargs[0]["max_time_ms"] == 2500
    remaining = task_results.remaining[0]
    assert remaining is not None and 0 < remaining <= 2.5
    # The block ends with the call.
    assert _csot.remaining() is None


@pytest.mark.parametrize(
    "error",
    [ExecutionTimeout("operation exceeded time limit", 50), NetworkTimeout("timed out")],
)
def test_history_timeout_becomes_a_time_limit_error(error):
    broker = make_broker(FakeTaskResults(error))
    with pytest.raises(BrokerTimeoutError, match="time limit"):
        broker.handle("history", HISTORY_ARGS, timeout=2.0)
    answer = executor._answer(
        make_broker(FakeTaskResults(error)),
        {"op": "history", "args": HISTORY_ARGS},
        deadline=time.monotonic() + 2,
    )
    assert answer == {"ok": False, "error": DATA_TIMEOUT_MESSAGE}


def test_latest_aggregate_timeout_becomes_a_time_limit_error():
    metrics = FakeMetrics(ExecutionTimeout("operation exceeded time limit", 50))
    with pytest.raises(BrokerTimeoutError):
        make_broker(metrics=metrics).handle("latest", {"kind": "qubit", "metric": "t1"}, timeout=1)
    assert metrics.calls == 1


def test_other_database_errors_are_not_reported_as_timeouts():
    broker = make_broker(FakeTaskResults(OperationFailure("bad query", 2)))
    with pytest.raises(OperationFailure):
        broker.handle("history", HISTORY_ARGS, timeout=2.0)


def test_no_query_once_too_little_time_is_left():
    task_results, metrics = FakeTaskResults(), FakeMetrics()
    broker = make_broker(task_results, metrics)
    with pytest.raises(BrokerTimeoutError):
        broker.handle("history", HISTORY_ARGS, timeout=0.01)
    with pytest.raises(BrokerTimeoutError):
        broker.handle("latest", {"kind": "qubit", "metric": "t1"}, timeout=0)
    assert task_results.kwargs == [] and metrics.calls == 0


def test_cached_latest_needs_no_query_time():
    metrics = FakeMetrics()
    broker = make_broker(metrics=metrics)
    args = {"kind": "qubit", "metric": "t1"}
    first = broker.handle("latest", args, timeout=1)
    assert broker.handle("latest", args, timeout=0) == first
    assert first == {"0": {"value": 42.0, "task_id": "task-1", "execution_id": "exec-1"}}
    assert metrics.calls == 1


def test_latest_timeout_wrapped_by_metrics_service_keeps_timeout_semantics():
    chips, history = MagicMock(), MagicMock()
    chips.get_qubit_count.return_value = 1

    def query(**kwargs: Any) -> Any:
        remaining = _csot.remaining()
        assert remaining is not None and 0 < remaining <= 1
        raise ExecutionTimeout("query exceeded time limit", 50)

    history.aggregate_latest_metrics.side_effect = query
    metrics = MetricsService(task_result_repository=history, chip_repository=chips)
    with pytest.raises(BrokerTimeoutError, match="time limit"):
        make_broker(metrics=metrics).handle("latest", {"kind": "qubit", "metric": "t1"}, timeout=1)
    chips.get_qubit_count.assert_called_once_with("proj-1", "chip-1")
    history.aggregate_latest_metrics.assert_called_once()
