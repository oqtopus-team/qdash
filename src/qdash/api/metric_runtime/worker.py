"""Metric script worker process: ``python -m qdash.api.metric_runtime.worker``.

The metric runner in the ``metric-runner`` container (or the executor's development-only
local mode) spawns one worker per validation or evaluation. The worker holds no credentials, database
connection or API client; everything it reads comes through the data broker protocol
below.

Protocol (line-delimited UTF-8 JSON over the worker's stdin and stdout):

1. The parent writes one request line to stdin::

       {"mode": "catalog" | "evaluate", "source": "...", "memory_mb": 1024,
        "timeout_seconds": 60, "metric_id": "...", "chip_id": "...",
        "start": iso, "end": iso, "params": {...}, "targets": ["0>1", ...]}

   (``metric_id`` … ``targets`` only for ``evaluate``; ``targets`` only for series
   metrics, which evaluate the listed qubits or directed pairs and nothing else.)
2. While running, the worker may send data requests as lines on stdout::

       CALL {"op": "metrics_config" | "topology" | "latest" | "history", "args": {...}}

   and blocks until the parent answers with exactly one line on stdin::

       {"ok": true, "data": ...}   or   {"ok": false, "error": "message"}

3. The worker finishes with one final line and exits::

       RESULT {"ok": true, "result": {...}, "log": "...", "log_truncated": false}
       RESULT {"ok": false, "error": "...", "diagnostics": [...], "log": "...", ...}

Before user code runs, the worker moves the protocol streams to private file descriptors
and points fds 0 and 1 at ``/dev/null``, so script output (including output from C
extensions) cannot corrupt the protocol. Python-level ``print`` output goes to a
:class:`BoundedLog` (16 KiB). Resource limits (address space, CPU time, file size,
process count) are applied where the platform supports them; unsupported limits are
skipped (macOS rejects ``RLIMIT_AS``, for example). The worker also raises its OOM score
to bias victim selection toward it (:func:`apply_limits`).

Evaluation follows qdash-playground ``worker.execute`` (Apache License 2.0): one metric
over every target, each cell evaluated in its own ``try`` so one failure never hides the
other cells. A ``result="series"`` metric is evaluated only for the selected targets
(:data:`~qdash.api.metric_runtime.sdk.MAX_SERIES_TARGETS` at most), and each target's
:class:`~qdash.api.metric_runtime.sdk.SeriesResult` is checked by :func:`serialize_series`.
The cells of all selected targets together must fit
:data:`~qdash.api.metric_runtime.sdk.MAX_SERIES_RESULT_BYTES` as protocol JSON; the evaluation
fails with an error that says so instead of dropping points or text.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import sys
import types
from datetime import datetime, timedelta
from typing import IO, Any

from qdash.api.metric_runtime import sdk
from qdash.api.metric_runtime.policy import diagnostic, error_message

LOG_LIMIT = 16 * 1024
FILE_SIZE_LIMIT = 1024 * 1024
MAX_CHECKS = 200
MAX_ESTIMATES = 200
MAX_TEXT = 4000
MAX_REASON = 200
MAX_SERIES_REFERENCES = 100
"""Input references kept per series cell (the most recent); the rest are counted as cut."""
OOM_SCORE_ADJ = 1000
OOM_SCORE_ADJ_PATH = "/proc/self/oom_score_adj"


class BoundedLog:
    """Keep the last ``limit`` bytes of script output, even when it prints without bound."""

    def __init__(self, limit: int = LOG_LIMIT) -> None:
        self.limit = limit
        self.value = ""
        self.truncated = False

    def write(self, value: str) -> int:
        encoded = (self.value + value[-self.limit :]).encode()
        self.truncated = self.truncated or len(encoded) > self.limit or len(value) > self.limit
        self.value = encoded[-self.limit :].decode(errors="ignore")
        return len(value)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def getvalue(self) -> str:
        return ("[Earlier log output truncated]\n" if self.truncated else "") + self.value


class Channel:
    """Worker side of the data broker protocol."""

    def __init__(self, output: IO[str], answers: IO[str]) -> None:
        self._output, self._answers = output, answers

    def send(self, prefix: str, payload: dict[str, Any]) -> None:
        self._output.write(f"{prefix} {json.dumps(payload, allow_nan=False)}\n")
        self._output.flush()

    def call(self, op: str, args: dict[str, Any]) -> Any:
        self.send("CALL", {"op": op, "args": args})
        line = self._answers.readline()
        if not line:
            raise sdk.BrokerError("The data broker closed the connection")
        answer = json.loads(line)
        if not answer.get("ok"):
            raise sdk.BrokerError(str(answer.get("error") or "Data broker request failed"))
        return answer.get("data")


def install_public_module() -> types.ModuleType:
    """Register ``qdash_metrics`` with only the public SDK names."""
    module = types.ModuleType("qdash_metrics", sdk.__doc__)
    for name in sdk.PUBLIC_NAMES:
        setattr(module, name, getattr(sdk, name))
    module.__all__ = list(sdk.PUBLIC_NAMES)  # type: ignore[attr-defined]
    sys.modules["qdash_metrics"] = module
    return module


def _address_space_in_use() -> int:
    """Current virtual memory size in bytes on Linux, else 0."""
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("VmSize:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def raise_oom_score(path: str = OOM_SCORE_ADJ_PATH) -> bool:
    """Raise this process's OOM selection bias; return whether the setting was written.

    Raising ``oom_score_adj`` needs no privilege on Linux. Elsewhere, or when ``/proc`` is
    not writable, nothing happens.
    """
    try:
        with open(path, "w", encoding="ascii") as adj:
            adj.write(str(OOM_SCORE_ADJ))
    except OSError:
        return False
    return True


def apply_limits(memory_mb: int, timeout_seconds: float) -> list[str]:
    """Apply per-job limits where available; return the names that could not be applied.

    ``memory_mb`` is the address space the script may add on top of the interpreter and
    the preloaded numpy/scipy, which already reserve a large virtual size on Linux.
    ``RLIMIT_AS`` bounds virtual memory, not the resident set: it is the first, per-job
    line, which turns most oversized allocations into a ``MemoryError`` inside the script.
    The hard line is the memory cgroup of the runner's container, shared by every job and
    the supervisor. ``oom_score_adj`` (``1000``) biases victim selection toward workers,
    but does not guarantee supervisor survival or isolate OOM failures to one job.
    """
    skipped: list[str] = []
    if not raise_oom_score():
        skipped.append("oom_score_adj")
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX platforms
        return [*skipped, "resource"]
    memory = _address_space_in_use() + int(memory_mb) * 1024 * 1024
    cpu = math.ceil(float(timeout_seconds)) + 1
    for name, value in (
        ("RLIMIT_AS", memory),
        ("RLIMIT_CPU", cpu),
        ("RLIMIT_FSIZE", FILE_SIZE_LIMIT),
        ("RLIMIT_NPROC", 0),
    ):
        limit = getattr(resource, name, None)
        if limit is None:
            skipped.append(name)
            continue
        try:
            _soft, hard = resource.getrlimit(limit)
            target = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(limit, (target, target))
        except (ValueError, OSError):
            skipped.append(name)
    return skipped


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------


def _finite_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _check_value(value: Any) -> float | str | None:
    if value is None or isinstance(value, str):
        return value[:MAX_TEXT] if isinstance(value, str) else None
    if isinstance(value, sdk.Quantity):
        return str(value)[:MAX_TEXT]
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return _finite_or_none(value)
    try:
        return _finite_or_none(float(value))
    except (TypeError, ValueError):
        return str(value)[:MAX_TEXT]


def serialize_assessment(assessment: Any) -> tuple[str | None, dict[str, Any] | None]:
    """Return ``(label, {checks, estimates, count})`` from a CellResult assessment.

    Raises:
        ValueError: If the assessment does not follow the documented shape.
    """
    if assessment is None:
        return None, None
    if not isinstance(assessment, dict):
        raise ValueError("CellResult.assessment must be a dict")
    label = assessment.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError("assessment['label'] must be a string")
    checks = []
    for item in list(assessment.get("checks") or [])[:MAX_CHECKS]:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("assessment['checks'] must contain (label, value) pairs")
        checks.append({"label": str(item[0])[:MAX_TEXT], "value": _check_value(item[1])})
    estimates = [str(note)[:MAX_TEXT] for note in list(assessment.get("estimates") or [])]
    count = assessment.get("count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)):
        raise ValueError("assessment['count'] must be an int or None")
    return (
        label[:MAX_TEXT] if label is not None else None,
        {"checks": checks, "estimates": estimates[:MAX_ESTIMATES], "count": count},
    )


def _reference(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric": str(raw.get("metric", "")),
        "target": str(raw.get("target", "")),
        "task_id": raw.get("task_id"),
        "execution_id": raw.get("execution_id"),
        "timestamp": raw.get("timestamp"),
        "value": _finite_or_none(raw.get("value")),
        "unit": raw.get("unit"),
    }


def _cell_base(target: str | sdk.QubitPair) -> dict[str, Any]:
    if isinstance(target, sdk.QubitPair):
        return {
            "key": f"{target.source}>{target.target}",
            "qid": None,
            "source": target.source,
            "target": target.target,
            "hops": target.hops,
        }
    return {"key": target, "qid": target, "source": None, "target": None, "hops": None}


def _number_in_unit(value: Any, unit: str) -> float:
    """``value`` (a number or Quantity) in ``unit``, finite; raises on anything else."""
    if isinstance(value, bool):
        raise TypeError("Metric functions must return a number, not a bool")
    quantity = (
        value if isinstance(value, sdk.Quantity) else sdk.Quantity(value, sdk.unit_name(unit))
    )
    number = float(quantity.to(sdk.unit_name(unit)).magnitude)
    if not math.isfinite(number):
        raise ValueError("Result is not finite")
    return number


def _series_time(value: Any, what: str, ctx: sdk.AnalysisContext) -> datetime:
    if not isinstance(value, (str, datetime)):
        raise TypeError(f"{what} must be an ISO 8601 string or a datetime")
    moment = sdk.timestamp(value)
    if not ctx.start <= moment <= ctx.end:
        raise ValueError(
            f"{what} {moment.isoformat()} is outside the period "
            f"{ctx.start.isoformat()} .. {ctx.end.isoformat()}"
        )
    return moment


def serialize_series(points: Any, unit: str, ctx: sdk.AnalysisContext) -> list[dict[str, Any]]:
    """Check the points of a :class:`~sdk.SeriesResult` and return them as JSON objects.

    Nothing is sorted, resampled, clipped or dropped: a point that breaks a rule raises, and
    the target becomes an error cell that names the point.

    Raises:
        TypeError, ValueError: If the points do not follow the ``SeriesPoint`` rules.
    """
    if not isinstance(points, (list, tuple)):
        raise TypeError("SeriesResult.points must be a list of SeriesPoint")
    if len(points) > sdk.MAX_SERIES_POINTS:
        raise ValueError(
            f"The series has {len(points)} points, more than MAX_SERIES_POINTS = "
            f"{sdk.MAX_SERIES_POINTS}; use a coarser time bin or a shorter period"
        )
    serialized: list[dict[str, Any]] = []
    previous = None
    for index, point in enumerate(points):
        where = f"points[{index}]"
        if not isinstance(point, sdk.SeriesPoint):
            raise TypeError(f"{where} must be a SeriesPoint")
        moment = _series_time(point.timestamp, f"{where}.timestamp", ctx)
        if previous is not None and moment <= previous:
            raise ValueError(f"{where}.timestamp must be later than the previous point's")
        previous = moment
        if (point.start is None) != (point.end is None):
            raise ValueError(f"{where}: give both start and end, or neither")
        start = end = None
        if point.start is not None:
            start = _series_time(point.start, f"{where}.start", ctx)
            end = _series_time(point.end, f"{where}.end", ctx)
            if not start <= moment <= end:
                raise ValueError(f"{where}: start <= timestamp <= end must hold")
        value = None if point.value is None else _number_in_unit(point.value, unit)
        count = point.count
        if count is not None and (isinstance(count, bool) or not isinstance(count, int)):
            raise ValueError(f"{where}.count must be an int or None")
        if count is not None and count < 0:
            raise ValueError(f"{where}.count must not be negative")
        status = point.status
        if status is None:
            status = "ok" if value is not None else ("insufficient" if count else "no_data")
        if status not in sdk.SERIES_STATUSES:
            raise ValueError(f"{where}.status must be one of {', '.join(sdk.SERIES_STATUSES)}")
        if (status == "ok") != (value is not None):
            raise ValueError(f"{where}: status 'ok' needs a value, and a gap must have none")
        if value is not None and count == 0:
            raise ValueError(f"{where}: a value cannot rest on count 0")
        if point.reason is not None and not isinstance(point.reason, str):
            raise ValueError(f"{where}.reason must be a string")
        serialized.append(
            {
                "timestamp": moment.isoformat(),
                "start": start.isoformat() if start is not None else None,
                "end": end.isoformat() if end is not None else None,
                "value": value,
                "count": count,
                "status": status,
                "reason": point.reason[:MAX_REASON] if point.reason is not None else None,
            }
        )
    return serialized


def evaluate_series_cell(
    definition: sdk.Metric, target: str | sdk.QubitPair, ctx: sdk.AnalysisContext
) -> dict[str, Any]:
    """Evaluate one selected target of a series metric; never raises for script errors."""
    cell: dict[str, Any] = {
        **_cell_base(target),
        "status": "ok",
        "value": None,
        "color": None,
        "label": None,
        "message": None,
        "diagnostic": None,
        "assessment": None,
        "series": None,
    }
    ctx.references = []
    try:
        result = definition.function(target, ctx)
        if result is None:
            cell.update(status="empty", message="Function returned None")
        elif not isinstance(result, sdk.SeriesResult):
            raise TypeError(
                f"Series metrics must return a SeriesResult (or None), not {type(result).__name__}"
            )
        else:
            label = result.label
            if label is not None and not isinstance(label, str):
                raise ValueError("SeriesResult.label must be a string")
            _ignored, assessment = serialize_assessment(result.assessment)
            series = serialize_series(result.points, definition.unit, ctx)
            cell["label"] = label[:MAX_TEXT] if label is not None else None
            cell["assessment"] = assessment
            cell["series"] = series
            if not any(point["status"] == "ok" for point in series):
                gaps = dict.fromkeys(sdk.SERIES_STATUSES[1:], 0)
                for point in series:
                    gaps[point["status"]] += 1
                cell["status"] = "missing"
                cell["message"] = (
                    "The series has no points"
                    if not series
                    else "No point has a value: "
                    + ", ".join(f"{count} {name}" for name, count in gaps.items() if count)
                )
    except sdk.MissingData as exc:
        cell.update(status="missing", series=None, message=str(exc)[:MAX_TEXT])
    except Exception as exc:
        cell.update(
            status="error",
            series=None,
            message=error_message(exc)[:MAX_TEXT],
            diagnostic=diagnostic(exc),
        )
    references = [_reference(ref) for ref in ctx.references]
    cell["references_truncated"] = len(references) > MAX_SERIES_REFERENCES
    cell["references"] = references[-MAX_SERIES_REFERENCES:]
    return cell


def series_period_message(start: datetime, end: datetime) -> str | None:
    """Why ``[start, end]`` is too long for a series metric, or ``None`` when it fits."""
    span = end - start
    if span <= timedelta(days=sdk.MAX_SERIES_PERIOD_DAYS):
        return None
    days = span / timedelta(days=1)
    return (
        f"The period {start.isoformat()} .. {end.isoformat()} spans {days:.1f} days; a series "
        f"metric covers at most MAX_SERIES_PERIOD_DAYS = {sdk.MAX_SERIES_PERIOD_DAYS} days, "
        "the longest history the data broker reads. Shorten the period or split it into "
        "several panels"
    )


def check_series_period(start: datetime, end: datetime) -> None:
    """Refuse a series period longer than :data:`~sdk.MAX_SERIES_PERIOD_DAYS` before any read.

    Raises:
        ValueError: If the period is too long.
    """
    message = series_period_message(start, end)
    if message is not None:
        raise ValueError(message)


def encoded_size(value: Any) -> int:
    """Bytes ``value`` takes on the protocol stream, encoded exactly as :meth:`Channel.send`.

    The protocol JSON escapes non-ASCII text, so the encoded string is ASCII and its length
    is its size in bytes.
    """
    return len(json.dumps(value, allow_nan=False)) + 2


def series_size_message(size: int, key: str) -> str:
    """The error for series cells that outgrow :data:`~sdk.MAX_SERIES_RESULT_BYTES`."""
    limit = sdk.MAX_SERIES_RESULT_BYTES // (1024 * 1024)
    return (
        f"The series results reach {size / (1024 * 1024):.1f} MiB of JSON by target {key}, "
        f"more than MAX_SERIES_RESULT_BYTES = {limit} MiB for all selected targets together. "
        "Every field counts (point reasons, labels, assessment checks and estimates, "
        "references), and a non-ASCII character takes 6 to 12 bytes. Shorten that text, "
        "or select fewer targets, a coarser time bin or a shorter period"
    )


def select_targets(
    definition: sdk.Metric, topology: sdk.Topology, requested: Any
) -> list[str | sdk.QubitPair]:
    """The selected targets of a series metric, checked against the chip and declared hops.

    Raises:
        ValueError: On no, too many, duplicate, malformed or unknown targets, a pair that
            is not coupled at the metric's hops, or a qubit ID for a pair metric.
    """
    if not isinstance(requested, list) or not requested:
        raise ValueError(
            f"Series metric '{definition.id}' needs targets: select 1 to "
            f"{sdk.MAX_SERIES_TARGETS} {'qubits' if definition.target == 'qubit' else 'directed pairs'}"
        )
    if len(requested) > sdk.MAX_SERIES_TARGETS:
        raise ValueError(
            f"{len(requested)} targets selected; a series metric evaluates at most "
            f"MAX_SERIES_TARGETS = {sdk.MAX_SERIES_TARGETS}"
        )
    selected: list[str | sdk.QubitPair] = []
    seen: set[str] = set()
    if definition.target == "qubit":
        on_chip = set(topology.qubits)
        for raw in requested:
            if not isinstance(raw, str) or ">" in raw or "-" in raw:
                raise ValueError(f"Target {raw!r} is not a qubit ID; this is a qubit metric")
            key = sdk.qid(raw)
            if key not in on_chip:
                raise ValueError(f"Qubit {key} is not on this chip")
            if key in seen:
                raise ValueError(f"Target {key} is selected twice")
            seen.add(key)
            selected.append(key)
        return selected
    declared = {(pair.source, pair.target): pair for pair in topology.pairs(definition.hops)}
    every = {(pair.source, pair.target): pair for pair in topology.pairs((1, 2))}
    for raw in requested:
        ends = raw.replace(">", "-").split("-") if isinstance(raw, str) else []
        if len(ends) != 2:
            raise ValueError(
                f"Target {raw!r} is not a directed pair; write 'source>target' such as '0>1'"
            )
        pair_key = (sdk.qid(ends[0]), sdk.qid(ends[1]))
        label = f"{pair_key[0]}>{pair_key[1]}"
        if pair_key not in declared:
            if pair_key in every:
                raise ValueError(
                    f"Pair {label} is {every[pair_key].hops} hops apart; metric "
                    f"'{definition.id}' declares hops {list(definition.hops)}"
                )
            raise ValueError(f"Pair {label} is not within 2 hops on this chip")
        if label in seen:
            raise ValueError(f"Target {label} is selected twice")
        seen.add(label)
        selected.append(declared[pair_key])
    return selected


def evaluate_cell(
    definition: sdk.Metric, target: str | sdk.QubitPair, ctx: sdk.AnalysisContext
) -> dict[str, Any]:
    """Evaluate one target; never raises for script errors."""
    cell: dict[str, Any] = {
        **_cell_base(target),
        "status": "ok",
        "value": None,
        "color": None,
        "label": None,
        "message": None,
        "diagnostic": None,
        "assessment": None,
    }
    ctx.references = []
    try:
        result = definition.function(target, ctx)
        assessment: Any = None
        if isinstance(result, sdk.SeriesResult):
            raise TypeError(
                "This metric returned a SeriesResult; declare it with @metric(result='series')"
            )
        if isinstance(result, sdk.CellResult):
            assessment = result.assessment
            cell["color"] = sdk.color(result.color) if result.color is not None else None
            result = result.value
        cell["label"], cell["assessment"] = serialize_assessment(assessment)
        if result is None:
            cell["status"] = "missing" if assessment is not None else "empty"
            if assessment is None:
                cell["message"] = "Function returned None"
        else:
            cell["value"] = _number_in_unit(result, definition.unit)
    except sdk.MissingData as exc:
        cell.update(status="missing", value=None, message=str(exc)[:MAX_TEXT])
    except Exception as exc:
        cell.update(
            status="error",
            value=None,
            color=None,
            message=error_message(exc)[:MAX_TEXT],
            diagnostic=diagnostic(exc),
        )
    cell["references"] = [_reference(ref) for ref in ctx.references]
    return cell


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def catalog(request: dict[str, Any]) -> dict[str, Any]:
    """Compile the script and return its metric metadata."""
    definitions = sdk.load_source(request["source"])
    return {"metrics": [definition.metadata() for definition in definitions.values()]}


def evaluate(request: dict[str, Any], channel: Channel) -> dict[str, Any]:
    """Evaluate one metric over every qubit or directed pair of the chip."""
    definitions = sdk.load_source(request["source"])
    metric_id = request["metric_id"]
    definition = definitions.get(metric_id)
    if definition is None:
        known = ", ".join(definitions)
        raise ValueError(f"Metric '{metric_id}' is not defined; expected one of: {known}")
    effective = sdk.resolve_parameters(definition.parameters, request.get("params"))
    ctx = sdk.AnalysisContext(
        channel.call,
        request["chip_id"],
        sdk.timestamp(request["start"]),
        sdk.timestamp(request["end"]),
        effective,
    )
    if definition.result == "series":
        check_series_period(ctx.start, ctx.end)
    topology = ctx.topology
    targets: list[str | sdk.QubitPair]
    requested = request.get("targets")
    if definition.result == "series":
        targets = select_targets(definition, topology, requested)
        series_cells = []
        total = 0
        size = 0
        for target in targets:
            cell = evaluate_series_cell(definition, target, ctx)
            total += len(cell["series"] or [])
            if total > sdk.MAX_TOTAL_SERIES_POINTS:
                raise ValueError(
                    f"The selected targets return more than MAX_TOTAL_SERIES_POINTS = "
                    f"{sdk.MAX_TOTAL_SERIES_POINTS} points together; select fewer targets, "
                    "a coarser time bin or a shorter period"
                )
            size += encoded_size(cell)
            if size > sdk.MAX_SERIES_RESULT_BYTES:
                raise ValueError(series_size_message(size, cell["key"]))
            series_cells.append(cell)
        return {
            "metric": definition.metadata(),
            "params": effective,
            "legend": None,
            "cells": series_cells,
            "notices": list(ctx.notices),
        }
    if requested:
        raise ValueError(
            f"targets apply only to series metrics; '{definition.id}' is evaluated for every "
            "qubit or pair of the chip"
        )
    if definition.target == "pair":
        targets = list(topology.pairs(definition.hops))
    else:
        targets = list(topology.qubits)
    legend = None
    if definition.legend is not None:
        declared = definition.legend(ctx) if callable(definition.legend) else definition.legend
        if not isinstance(declared, sdk.Legend):
            raise ValueError("The legend function must return a Legend")
        legend = declared.serialize(definition.unit, definition.unit)
    cells = [evaluate_cell(definition, target, ctx) for target in targets]
    return {
        "metric": definition.metadata(),
        "params": effective,
        "legend": legend,
        "cells": cells,
        "notices": list(ctx.notices),
    }


def execute(request: dict[str, Any], channel: Channel) -> dict[str, Any]:
    """Run one request; raises on script-level failures."""
    if request.get("mode") == "catalog":
        return catalog(request)
    if request.get("mode") == "evaluate":
        return evaluate(request, channel)
    raise ValueError(f"Unknown worker mode: {request.get('mode')!r}")


def _private_streams() -> tuple[IO[str], IO[str]]:
    """Move the protocol to private fds and point fds 0/1 at /dev/null."""
    output = os.fdopen(os.dup(1), "w", encoding="utf-8")
    answers = os.fdopen(os.dup(0), "r", encoding="utf-8")
    null_out = os.open(os.devnull, os.O_WRONLY)
    null_in = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null_out, 1)
    os.dup2(null_in, 0)
    os.close(null_out)
    os.close(null_in)
    return output, answers


def main() -> None:
    # Files the script creates (numpy.save, matplotlib caches) stay private to the
    # job's uid, even in a shared /tmp, until the supervisor sweeps them.
    os.umask(0o077)
    output, answers = _private_streams()
    channel = Channel(output, answers)
    log = BoundedLog()
    payload: dict[str, Any]
    try:
        request = json.loads(answers.readline())
        install_public_module()
        # Preload the allowed libraries before limits apply so that imports are cheap and
        # never need a new process or file write.
        import numpy  # noqa: F401
        import scipy  # noqa: F401

        skipped = apply_limits(
            int(request.get("memory_mb", 1024)), float(request.get("timeout_seconds", 60))
        )
        sys.stdin = open(os.devnull)  # noqa: SIM115 - scripts never read stdin
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            result = execute(request, channel)
        payload = {"ok": True, "result": result, "skipped_limits": skipped}
    except BaseException as exc:
        payload = {
            "ok": False,
            "error": error_message(exc)[:MAX_TEXT],
            "diagnostics": [diagnostic(exc)],
        }
    payload["log"] = log.getvalue()
    payload["log_truncated"] = log.truncated
    try:
        channel.send("RESULT", payload)
    except ValueError:
        channel.send(
            "RESULT",
            {
                "ok": False,
                "error": "The result could not be serialized as JSON",
                "diagnostics": [],
                "log": log.getvalue(),
                "log_truncated": log.truncated,
            },
        )


if __name__ == "__main__":
    main()
