"""Metrics endpoints must not block the event loop with their synchronous work."""

from __future__ import annotations

import asyncio
import io
import threading
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from qdash.api.dependencies import get_metrics_service
from qdash.api.lib.project import get_project_context
from qdash.api.routers import metrics

# Long enough that a blocked loop is unmistakable, short enough to fail fast instead of hanging.
BLOCK_TIMEOUT = 2.0


class _Gate:
    """A blocking call that waits until the test, running on the event loop, releases it."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.released = threading.Event()
        self.released_while_blocked = False
        self.thread: threading.Thread | None = None

    def block(self) -> None:
        self.thread = threading.current_thread()
        self.entered.set()
        # When the handler runs on the event loop, the loop cannot release the gate,
        # so this times out and the test fails.
        self.released_while_blocked = self.released.wait(BLOCK_TIMEOUT)


class _BlockingMetricsService:
    def __init__(self, gate: _Gate) -> None:
        self._gate = gate

    def get_chip_metrics(self, **kwargs: Any) -> dict[str, Any]:
        self._gate.block()
        return {
            "chip_id": kwargs["chip_id"],
            "username": kwargs["username"],
            "qubit_count": 0,
            "qubit_metrics": {},
            "coupling_metrics": {},
        }

    def get_metric_history(self, **kwargs: Any) -> dict[str, Any]:
        self._gate.block()
        return {
            "chip_id": kwargs["chip_id"],
            "qid": kwargs["qid"],
            "metric_name": kwargs["metric"],
            "username": kwargs["username"],
            "history": [],
        }

    def generate_metrics_pdf(self, **kwargs: Any) -> tuple[io.BytesIO, str, None]:
        self._gate.block()
        return io.BytesIO(b"%PDF-1.4 test"), "metrics.pdf", None


ENDPOINTS = [
    pytest.param("GET", "/config", id="config"),
    pytest.param("GET", "/chips/chip-1/metrics", id="chip-metrics"),
    pytest.param("GET", "/chips/chip-1/qubits/0/history?metric=t1", id="qubit-history"),
    pytest.param("GET", "/chips/chip-1/couplings/0-1/history?metric=zx90", id="coupling-history"),
    pytest.param("POST", "/chips/chip-1/metrics/pdf", id="pdf"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url"), ENDPOINTS)
async def test_metrics_endpoint_runs_blocking_work_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch, method: str, url: str
) -> None:
    gate = _Gate()

    def blocking_config() -> SimpleNamespace:
        gate.block()
        return SimpleNamespace(model_dump=lambda: {"qubit_metrics": {}})

    monkeypatch.setattr(metrics, "load_metrics_config", blocking_config)
    app = FastAPI()
    app.include_router(metrics.router)
    app.dependency_overrides[get_metrics_service] = lambda: _BlockingMetricsService(gate)
    app.dependency_overrides[get_project_context] = lambda: SimpleNamespace(
        project_id="project-1", user=SimpleNamespace(username="alice")
    )

    loop_thread = threading.current_thread()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        request = asyncio.create_task(client.request(method, url))
        assert await asyncio.to_thread(gate.entered.wait, BLOCK_TIMEOUT)
        # The loop is free while the handler blocks: it can run this code and release it.
        gate.released.set()
        response = await request

    assert response.status_code == 200
    assert gate.released_while_blocked
    assert gate.thread is not loop_thread
