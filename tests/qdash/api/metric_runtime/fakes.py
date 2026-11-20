"""In-process fakes for the metric script data broker."""

from __future__ import annotations

import copy
import json
import time
from typing import Any

from qdash.api.metric_runtime.broker import metrics_catalog
from qdash.api.metric_runtime.sdk import BrokerError


def grid_topology(
    qubits: list[int],
    couplings: list[list[int]],
    muxes: dict[str, list[int]] | None = None,
    columns: int = 4,
) -> dict[str, Any]:
    """Topology payload with qubits laid out row by row."""
    return {
        "qubits": {
            str(q): {"row": index // columns, "col": index % columns}
            for index, q in enumerate(qubits)
        },
        "couplings": couplings,
        "muxes": muxes or {},
    }


class FakeBroker:
    """Serves fixed data in the broker protocol shapes.

    ``latest`` is ``{"qubit" | "coupling": {metric: {target: value}}}`` with raw catalog
    values; ``history`` is ``{(metric, target): [record, ...]}``.
    """

    def __init__(
        self,
        *,
        topology: dict[str, Any],
        latest: dict[str, dict[str, dict[str, float]]] | None = None,
        history: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
        errors: dict[str, str] | None = None,
    ) -> None:
        self.topology = topology
        self.latest = copy.deepcopy(latest or {"qubit": {}, "coupling": {}})
        self.history = history or {}
        self.errors = errors or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.timeouts: list[float] = []

    def handle(self, op: str, args: dict[str, Any], *, timeout: float = 60.0) -> Any:
        self.calls.append((op, dict(args)))
        self.timeouts.append(timeout)
        if op in self.errors:
            raise RuntimeError(self.errors[op])
        if op == "metrics_config":
            return metrics_catalog()
        if op == "topology":
            return self.topology
        if op == "latest":
            values = self.latest.get(args["kind"], {}).get(args["metric"], {})
            return {
                target: {"value": value, "task_id": f"task-{target}", "execution_id": "exec-1"}
                for target, value in values.items()
            }
        if op == "history":
            return {
                "records": self.history.get((args["metric"], args["target"]), []),
                "clamped": False,
                "start": args["start"],
                "end": args["end"],
            }
        raise ValueError(f"Unknown op {op}")

    def __call__(self, op: str, args: dict[str, Any]) -> Any:
        """Broker function for in-process ``AnalysisContext`` tests."""
        try:
            return self.handle(op, args, timeout=60.0)
        except RuntimeError as exc:
            raise BrokerError(str(exc)) from exc

    def ops(self, op: str) -> list[dict[str, Any]]:
        return [args for name, args in self.calls if name == op]


class _InProcessChannel:
    """Worker channel that answers through a broker in the same process, via JSON."""

    def __init__(self, broker: Any) -> None:
        self.broker = broker

    def call(self, op: str, args: dict[str, Any]) -> Any:
        from qdash.api.metric_runtime import executor

        answer = json.loads(
            json.dumps(
                executor._answer(
                    self.broker, {"op": op, "args": args}, deadline=time.monotonic() + 60
                )
            )
        )
        if not answer["ok"]:
            raise BrokerError(answer["error"])
        return answer["data"]


def install_inprocess_runtime(monkeypatch: Any) -> list[dict[str, Any]]:
    """Replace the subprocess with an in-process run of the same worker code.

    The worker's ``execute`` runs against the real broker passed by the service, so the
    data path stays realistic while tests avoid spawning a process per request. Returns
    the list of requests seen.
    """
    from qdash.api.metric_runtime import executor, worker
    from qdash.api.metric_runtime.policy import diagnostic, error_message

    requests: list[dict[str, Any]] = []

    def run_worker(
        request: dict[str, Any], broker: Any = None, settings: Any = None
    ) -> executor.WorkerOutcome:
        requests.append(request)
        worker.install_public_module()
        try:
            result = worker.execute(request, _InProcessChannel(broker))  # type: ignore[arg-type]
        except Exception as exc:
            raise executor.ScriptFailure(error_message(exc), diagnostics=[diagnostic(exc)]) from exc
        return executor.WorkerOutcome(result=json.loads(json.dumps(result)))

    monkeypatch.setattr(executor, "run_worker", run_worker)
    return requests
