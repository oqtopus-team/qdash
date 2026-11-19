"""Metric script worker process: ``python -m qdash.api.metric_runtime.worker``.

The metric runner in agent-exec (or the executor's development-only local mode) spawns
one worker per validation or evaluation. The worker holds no credentials, database
connection or API client; everything it reads comes through the data broker protocol
below.

Protocol (line-delimited UTF-8 JSON over the worker's stdin and stdout):

1. The parent writes one request line to stdin::

       {"mode": "catalog" | "evaluate", "source": "...", "memory_mb": 1024,
        "timeout_seconds": 60, "metric_id": "...", "chip_id": "...",
        "start": iso, "end": iso, "params": {...}}

   (``metric_id`` … ``params`` only for ``evaluate``.)
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
skipped (macOS rejects ``RLIMIT_AS``, for example).

Evaluation follows qdash-playground ``worker.execute`` (Apache License 2.0): one metric
over every target, each cell evaluated in its own ``try`` so one failure never hides the
other cells.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import sys
import types
from typing import IO, Any

from qdash.api.metric_runtime import sdk
from qdash.api.metric_runtime.policy import diagnostic, error_message

LOG_LIMIT = 16 * 1024
FILE_SIZE_LIMIT = 1024 * 1024
MAX_CHECKS = 200
MAX_ESTIMATES = 200
MAX_TEXT = 4000


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


def apply_limits(memory_mb: int, timeout_seconds: float) -> list[str]:
    """Apply rlimits where available; return the names that could not be applied.

    ``memory_mb`` is the address space the script may add on top of the interpreter and
    the preloaded numpy/scipy, which already reserve a large virtual size on Linux.
    """
    skipped: list[str] = []
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX platforms
        return ["resource"]
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
            if isinstance(result, bool):
                raise TypeError("Metric functions must return a number, not a bool")
            quantity = (
                result
                if isinstance(result, sdk.Quantity)
                else sdk.Quantity(result, sdk.unit_name(definition.unit))
            )
            number = float(quantity.to(sdk.unit_name(definition.unit)).magnitude)
            if not math.isfinite(number):
                raise ValueError("Result is not finite")
            cell["value"] = number
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
    topology = ctx.topology
    targets: list[str | sdk.QubitPair]
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
