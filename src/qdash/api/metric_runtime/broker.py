"""Data broker: answers worker data requests inside the API process.

The worker (:mod:`.worker`) has no database or API access. Every value a script reads
goes through :meth:`MetricDataBroker.handle`, which queries project-scoped repositories
with the caller's project and the evaluated chip only. Operations:

``metrics_config`` (no arguments)
    The metric catalog scripts may read: ``{"qubit_metrics": {name: {title, unit, scale,
    description}}, "coupling_metrics": {...}}`` from ``config/domain/metrics.yaml``.
``topology`` (no arguments)
    ``{"qubits": {qid: {"row", "col"}}, "couplings": [[a, b], ...], "muxes": {id: [...]}}``
    of the chip's topology template, resolved by the service before the worker starts.
``latest`` ``{kind: "qubit" | "coupling", metric}``
    ``{target: {value, task_id, execution_id}}`` of the latest completed, non-excluded
    result per target within the period. One ``MetricsService.get_chip_metrics`` call
    (``selection_mode="latest"``, bounded by ``start_at``/``end_at``) per evaluation,
    cached by the broker.
``history`` ``{kind, metric, target, start, end}``
    ``{"records": [...], "clamped": bool, "start": iso, "end": iso}``: one record per task
    result with ``output_parameters.<metric>`` and ``start_at`` in ``[start, end]``, oldest
    first. Each record is ``{value, unit, timestamp, task_id, execution_id, excluded,
    raw}``.

Caps (exceeding one is reported to the worker as an error and becomes a per-cell error
naming the cap): :data:`MAX_HISTORY_RECORDS` per history call and
:data:`MAX_BROKER_CALLS` per evaluation. A history span longer than
:data:`MAX_HISTORY_DAYS` is clamped to the most recent ``MAX_HISTORY_DAYS`` days of the
requested span; the answer reports ``clamped``.

Time limit: the executor passes each call the seconds left before the run's time limit.
``latest`` and ``history`` run their queries inside ``pymongo.timeout(timeout)`` (client-side
operation timeout: the server gets a matching ``maxTimeMS`` and the driver bounds its socket
waits), and ``history`` also passes ``max_time_ms`` to its ``find``. A call with less than
:data:`MIN_DATA_TIMEOUT_SECONDS` left, or a query that hits the limit, raises
:class:`BrokerTimeoutError`. Python-side processing of rows already fetched is not
interrupted.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, Protocol

import pymongo
from bunnet import SortDirection
from pymongo.errors import PyMongoError

from qdash.api.metric_runtime.sdk import coupling_id, qid, timestamp
from qdash.api.services.metrics_service import (
    _extract_metric_output_info,
    _get_task_timestamp,
)
from qdash.common.config.metrics import load_metrics_config

if TYPE_CHECKING:
    from collections.abc import Iterator

    from qdash.api.services.metrics_service import MetricsService
    from qdash.repository.task_result_history import MongoTaskResultHistoryRepository

logger = logging.getLogger(__name__)

MAX_HISTORY_RECORDS = 5000
MAX_BROKER_CALLS = 2000
MAX_HISTORY_DAYS = 400
MIN_DATA_TIMEOUT_SECONDS = 0.05
"""Least time left for which a data request still issues a query."""
DATA_TIMEOUT_MESSAGE = "The data request exceeded the metric script time limit"


class BrokerLimitError(RuntimeError):
    """A broker cap was exceeded; the message names the cap."""


class BrokerRequestError(ValueError):
    """The worker sent an invalid request."""


class BrokerTimeoutError(RuntimeError):
    """A data request ran out of the run's remaining time."""

    def __init__(self) -> None:
        super().__init__(DATA_TIMEOUT_MESSAGE)


class BrokerHandler(Protocol):
    """Anything that can answer worker data requests (the real broker or a test fake)."""

    def handle(self, op: str, args: dict[str, Any], *, timeout: float) -> Any:
        """Return the answer data for ``op`` or raise to send an error to the worker.

        ``timeout`` is the number of seconds left before the run's time limit; database
        waits must be bounded by it; Python processing cannot be preempted.
        """
        ...


@contextlib.contextmanager
def data_timeout(timeout: float) -> Iterator[None]:
    """Bound every pymongo operation in the block by ``timeout`` seconds.

    Raises :class:`BrokerTimeoutError` before any query when less than
    :data:`MIN_DATA_TIMEOUT_SECONDS` is left, and in place of pymongo's timeout errors
    (``ExecutionTimeout``, ``NetworkTimeout``, server selection timeouts).
    """
    if timeout < MIN_DATA_TIMEOUT_SECONDS:
        raise BrokerTimeoutError
    try:
        with pymongo.timeout(timeout):
            yield
    except Exception as exc:
        # MetricsService wraps aggregation failures in HTTPException with the driver
        # error as its explicit cause. Preserve timeout semantics through that wrapper.
        cause = exc.__cause__ if exc.__cause__ is not None else exc
        if isinstance(cause, PyMongoError) and cause.timeout:
            raise BrokerTimeoutError from exc
        raise


def metrics_catalog() -> dict[str, dict[str, dict[str, Any]]]:
    """Catalog entries scripts may read, keyed by section and metric name."""
    config = load_metrics_config()

    def section(entries: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "title": meta.title,
                "unit": meta.unit,
                "scale": meta.scale,
                "description": meta.description or "",
            }
            for name, meta in entries.items()
        }

    return {
        "qubit_metrics": section(config.qubit_metrics),
        "coupling_metrics": section(config.coupling_metrics),
    }


def topology_payload(definition: Any) -> dict[str, Any]:
    """Serialize a ``TopologyDefinition`` for the worker."""
    return {
        "qubits": {
            str(key): {"row": position.row, "col": position.col}
            for key, position in definition.qubits.items()
        },
        "couplings": [list(pair) for pair in definition.couplings],
        "muxes": {str(key): list(members) for key, members in definition.muxes.items()},
    }


def _qid_variants(target: str) -> list[str]:
    return sorted({target, f"Q{target.zfill(2)}", f"Q{target.zfill(3)}"})


def _coupling_variants(target: str) -> list[str]:
    a, b = target.split("-")
    return sorted(
        {
            target,
            f"Q{a.zfill(2)}-Q{b.zfill(2)}",
            f"Q{a.zfill(3)}-Q{b.zfill(3)}",
            f"{a.zfill(2)}-{b.zfill(2)}",
        }
    )


class MetricDataBroker:
    """Project-scoped data source for one evaluation."""

    def __init__(
        self,
        *,
        project_id: str,
        username: str,
        chip_id: str,
        start: datetime,
        end: datetime,
        topology: dict[str, Any],
        metrics_service: MetricsService,
        task_result_repository: MongoTaskResultHistoryRepository,
    ) -> None:
        self.project_id = project_id
        self.username = username
        self.chip_id = chip_id
        self.start = start
        self.end = end
        self._topology = topology
        self._metrics = metrics_service
        self._task_results = task_result_repository
        self._latest: dict[str, dict[str, dict[str, dict[str, Any]]]] | None = None
        self._catalog: dict[str, dict[str, dict[str, Any]]] | None = None
        self.calls = 0

    def handle(self, op: str, args: dict[str, Any], *, timeout: float) -> Any:
        self.calls += 1
        if self.calls > MAX_BROKER_CALLS:
            raise BrokerLimitError(
                f"Exceeded MAX_BROKER_CALLS = {MAX_BROKER_CALLS} data requests for one "
                "evaluation; read fewer targets or cache values in the script"
            )
        if op == "metrics_config":
            return self.catalog()
        if op == "topology":
            return self._topology
        if op == "latest":
            kind, metric = self._kind(args), self._metric(args)
            if self._latest is not None:
                return self.latest(kind, metric)
            with data_timeout(timeout):
                return self.latest(kind, metric)
        if op == "history":
            kind, metric = self._kind(args), self._metric(args)
            with data_timeout(timeout):
                return self.history(
                    kind,
                    metric,
                    str(args.get("target", "")),
                    str(args.get("start", "")),
                    str(args.get("end", "")),
                    timeout=timeout,
                )
        raise BrokerRequestError(f"Unknown data request '{op}'")

    def catalog(self) -> dict[str, dict[str, dict[str, Any]]]:
        if self._catalog is None:
            self._catalog = metrics_catalog()
        return self._catalog

    @staticmethod
    def _kind(args: dict[str, Any]) -> Literal["qubit", "coupling"]:
        kind = args.get("kind")
        if kind == "qubit":
            return "qubit"
        if kind == "coupling":
            return "coupling"
        raise BrokerRequestError("kind must be 'qubit' or 'coupling'")

    def _metric(self, args: dict[str, Any]) -> str:
        metric = args.get("metric")
        catalog = self.catalog()
        if not isinstance(metric, str) or not any(
            metric in section for section in catalog.values()
        ):
            raise BrokerRequestError(f"Unknown metric '{metric}'")
        return metric

    def _latest_all(self) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
        if self._latest is None:
            response = self._metrics.get_chip_metrics(
                chip_id=self.chip_id,
                project_id=self.project_id,
                username=self.username,
                selection_mode="latest",
                start_at=self.start,
                end_at=self.end,
            )
            result: dict[str, dict[str, dict[str, dict[str, Any]]]] = {
                "qubit": {},
                "coupling": {},
            }
            for kind, metrics in (
                ("qubit", response.qubit_metrics),
                ("coupling", response.coupling_metrics),
            ):
                normalize = qid if kind == "qubit" else coupling_id
                for metric, values in metrics.items():
                    entries: dict[str, dict[str, Any]] = {}
                    for raw_key, value in values.items():
                        try:
                            key = normalize(raw_key)
                        except ValueError:
                            continue
                        if value.value is None:
                            continue
                        entries[key] = {
                            "value": value.value,
                            "task_id": value.task_id,
                            "execution_id": value.execution_id,
                        }
                    result[kind][metric] = entries
            self._latest = result
        return self._latest

    def latest(self, kind: Literal["qubit", "coupling"], metric: str) -> dict[str, Any]:
        return self._latest_all()[kind].get(metric, {})

    def history(
        self,
        kind: Literal["qubit", "coupling"],
        metric: str,
        target: str,
        start: str,
        end: str,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Records of one target; ``timeout`` (seconds) also bounds the query's ``maxTimeMS``."""
        try:
            lower, upper = timestamp(start), timestamp(end)
            normalized = qid(target) if kind == "qubit" else coupling_id(target)
        except ValueError as exc:
            raise BrokerRequestError(str(exc)) from exc
        if lower > upper:
            raise BrokerRequestError("history start must be before end")
        clamped = upper - lower > timedelta(days=MAX_HISTORY_DAYS)
        if clamped:
            lower = upper - timedelta(days=MAX_HISTORY_DAYS)
        variants = _qid_variants(normalized) if kind == "qubit" else _coupling_variants(normalized)
        query: dict[str, Any] = {
            "project_id": self.project_id,
            "chip_id": self.chip_id,
            "task_type": kind,
            "qid": {"$in": variants},
            f"output_parameters.{metric}": {"$exists": True},
            "start_at": {"$gte": lower, "$lte": upper},
        }
        docs = self._task_results.find(
            query,
            sort=[("start_at", SortDirection.ASCENDING)],
            limit=MAX_HISTORY_RECORDS + 1,
            max_time_ms=max(1, int(timeout * 1000)) if timeout is not None else None,
        )
        if len(docs) > MAX_HISTORY_RECORDS:
            raise BrokerLimitError(
                f"history({metric}, {normalized}) matched more than MAX_HISTORY_RECORDS = "
                f"{MAX_HISTORY_RECORDS} results; narrow the period"
            )
        records: list[dict[str, Any]] = []
        for doc in docs:
            output = doc.output_parameters.get(metric)
            value, _calibrated_at, metric_task_id = _extract_metric_output_info(output)
            if value is None:
                continue
            unit = output.get("unit") if isinstance(output, dict) else None
            observed = _get_task_timestamp(doc)
            records.append(
                {
                    "value": value if isinstance(value, (int, float)) else None,
                    "unit": unit if isinstance(unit, str) else None,
                    "timestamp": observed.isoformat(),
                    "task_id": metric_task_id or doc.task_id,
                    "execution_id": doc.execution_id,
                    "excluded": bool(getattr(doc, "excluded", False)),
                    "raw": {
                        "name": doc.name,
                        "qid": doc.qid,
                        "status": doc.status,
                        "error": output.get("error") if isinstance(output, dict) else None,
                        "excluded_reason": getattr(doc, "excluded_reason", "") or "",
                    },
                }
            )
        records.sort(key=lambda record: timestamp(record["timestamp"]))
        return {
            "records": records,
            "clamped": clamped,
            "start": lower.isoformat(),
            "end": upper.isoformat(),
        }
