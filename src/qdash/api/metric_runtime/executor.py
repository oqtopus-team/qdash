"""Spawn and supervise metric script workers.

Each validation or evaluation runs ``python -u -B -m qdash.api.metric_runtime.worker`` in a
new session with a scrubbed environment and a temporary working directory, then serves
its data requests through a :class:`~qdash.api.metric_runtime.broker.BrokerHandler` until
the worker prints its ``RESULT`` line (protocol in :mod:`.worker`).

Settings (environment variables read per run, with defaults):

``METRIC_SCRIPT_TIMEOUT_SECONDS`` (60)
    Wall-clock limit per run; the worker's process group is killed when it expires. The
    worker also sets ``RLIMIT_CPU`` to this value plus one second.
``METRIC_SCRIPT_MEMORY_MB`` (1024)
    Address space the script may use on top of the interpreter and the preloaded
    numpy/scipy baseline (``RLIMIT_AS``), where the platform supports it.
``METRIC_SCRIPT_CONCURRENCY`` (2)
    Workers running at once in this API process. A run that cannot start within
    :data:`QUEUE_WAIT_SECONDS` fails with :class:`QueueFullError` (HTTP 429).

The worker's stdout is bounded to :data:`OUTPUT_LIMIT_BYTES`; script ``print`` output is
kept in a 16 KiB log.

Threat model
------------
Who can run code: project editors and owners (the same people who can save calibration
flows that run on hardware). Viewers can only evaluate scripts that were saved and
validated by an editor; draft evaluation and validation require editor rights.

What is enforced:

- Resource bounds: wall-clock timeout with process-group kill, CPU time, address space,
  file size and process count rlimits where the OS supports them, bounded protocol output
  and log, a process-wide concurrency limit, and broker caps on data requests.
- Credential separation: the worker environment contains only ``PATH``, ``PYTHONPATH``,
  locale and BLAS thread variables. It receives no ``MONGO_*`` settings, tokens or API
  keys and has no database or API client. Data flows only through the broker, which runs
  in the API process and scopes every query to the caller's project and the evaluated chip.
- Guardrails: an import allowlist and disabled builtins (:mod:`.policy`), which catch
  mistakes and make intent explicit.

What is *not* enforced:

- The import/builtin filter is not a sandbox; determined code can escape it.
- The worker runs as the API container's user. Nothing here blocks network egress or
  reads of files that user can read inside the API container.

Deployments that need stronger isolation should add a container egress policy and a
seccomp/AppArmor profile, or run the API under a dedicated low-privilege user.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdash.api.metric_runtime.broker import BrokerHandler

logger = logging.getLogger(__name__)

OUTPUT_LIMIT_BYTES = 8 * 1024 * 1024
STDERR_LIMIT_BYTES = 64 * 1024
QUEUE_WAIT_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MEMORY_MB = 1024
DEFAULT_CONCURRENCY = 2
WORKER_MODULE = "qdash.api.metric_runtime.worker"
SOURCE_ROOT = str(Path(__file__).resolve().parents[3])
"""Directory containing the ``qdash`` package; prepended to the worker's PYTHONPATH."""


class MetricRuntimeError(Exception):
    """Base class of executor failures."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: list[dict[str, Any]] | None = None,
        log: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or []
        self.log = log


class QueueFullError(MetricRuntimeError):
    """No worker slot became free within :data:`QUEUE_WAIT_SECONDS`."""


class WorkerFailure(MetricRuntimeError):
    """The worker timed out, exceeded its output bound or exited without a result."""


class ScriptFailure(MetricRuntimeError):
    """The script itself failed (compile error, policy violation, invalid declaration)."""


@dataclass(frozen=True)
class RuntimeSettings:
    """Limits of one worker run."""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    memory_mb: int = DEFAULT_MEMORY_MB
    concurrency: int = DEFAULT_CONCURRENCY
    queue_wait_seconds: float = QUEUE_WAIT_SECONDS
    output_limit_bytes: int = OUTPUT_LIMIT_BYTES


def _env_number(name: str, default: float, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r", name, raw)
        return default
    return max(minimum, value)


def load_settings() -> RuntimeSettings:
    """Read the runtime settings from the environment."""
    return RuntimeSettings(
        timeout_seconds=_env_number("METRIC_SCRIPT_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, 1),
        memory_mb=int(_env_number("METRIC_SCRIPT_MEMORY_MB", DEFAULT_MEMORY_MB, 128)),
        concurrency=int(_env_number("METRIC_SCRIPT_CONCURRENCY", DEFAULT_CONCURRENCY, 1)),
    )


@dataclass
class WorkerOutcome:
    """A successful worker run."""

    result: dict[str, Any]
    log: str = ""
    log_truncated: bool = False
    skipped_limits: list[str] = field(default_factory=list)


_slots_lock = threading.Lock()
_slots: dict[int, threading.BoundedSemaphore] = {}


def _semaphore(concurrency: int) -> threading.BoundedSemaphore:
    with _slots_lock:
        if concurrency not in _slots:
            _slots[concurrency] = threading.BoundedSemaphore(concurrency)
        return _slots[concurrency]


def scrubbed_env() -> dict[str, str]:
    """The worker's whole environment: no database settings, tokens or API keys."""
    python_path = [SOURCE_ROOT]
    inherited = os.environ.get("PYTHONPATH")
    if inherited:
        python_path.extend(part for part in inherited.split(os.pathsep) if part)
    locale = os.environ.get("LANG") or "C.UTF-8"
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "PYTHONPATH": os.pathsep.join(dict.fromkeys(python_path)),
        "LANG": locale,
        "LC_ALL": os.environ.get("LC_ALL") or locale,
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        with contextlib.suppress(ProcessLookupError):
            process.kill()


class _StderrCollector(threading.Thread):
    """Drain the worker's stderr, keeping only the first bytes for diagnostics."""

    def __init__(self, stream: IO[bytes]) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self.data = bytearray()

    def run(self) -> None:
        while True:
            chunk = self._stream.read(4096)
            if not chunk:
                return
            if len(self.data) < STDERR_LIMIT_BYTES:
                self.data.extend(chunk[: STDERR_LIMIT_BYTES - len(self.data)])

    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace")


def _answer(broker: BrokerHandler | None, payload: dict[str, Any]) -> dict[str, Any]:
    if broker is None:
        return {"ok": False, "error": "Data access is not available while validating a script"}
    op = str(payload.get("op", ""))
    args = payload.get("args")
    try:
        data = broker.handle(op, args if isinstance(args, dict) else {})
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        message = str(detail) if detail is not None else str(exc)
        logger.debug("Broker request %s failed: %s", op, message)
        return {"ok": False, "error": message or type(exc).__name__}
    return {"ok": True, "data": data}


def run_worker(
    request: dict[str, Any],
    broker: BrokerHandler | None = None,
    settings: RuntimeSettings | None = None,
) -> WorkerOutcome:
    """Run one worker request to completion.

    Raises:
        QueueFullError: If no worker slot frees up in time.
        WorkerFailure: On timeout, output overflow or a crash without result.
        ScriptFailure: If the worker reports a script-level failure.
    """
    settings = settings or load_settings()
    slots = _semaphore(settings.concurrency)
    if not slots.acquire(timeout=settings.queue_wait_seconds):
        raise QueueFullError("Metric script evaluation queue is full; try again shortly")
    try:
        return _run(request, broker, settings)
    finally:
        slots.release()


def _run(
    request: dict[str, Any], broker: BrokerHandler | None, settings: RuntimeSettings
) -> WorkerOutcome:
    payload = {
        **request,
        "memory_mb": settings.memory_mb,
        "timeout_seconds": settings.timeout_seconds,
    }
    with tempfile.TemporaryDirectory(prefix="qdash-metric-") as workdir:
        process = subprocess.Popen(  # noqa: S603 - fixed interpreter and module
            [sys.executable, "-u", "-B", "-m", WORKER_MODULE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=scrubbed_env(),
            cwd=workdir,
            start_new_session=True,
        )
        assert process.stdin and process.stdout and process.stderr
        stderr = _StderrCollector(process.stderr)
        stderr.start()
        timed_out = threading.Event()

        def expire() -> None:
            timed_out.set()
            _kill_group(process)

        timer = threading.Timer(settings.timeout_seconds, expire)
        timer.daemon = True
        timer.start()
        final: dict[str, Any] | None = None
        overflow = False
        try:
            process.stdin.write(json.dumps(payload).encode() + b"\n")
            process.stdin.flush()
            received = 0
            while True:
                remaining = settings.output_limit_bytes - received
                line = process.stdout.readline(remaining + 1)
                if not line:
                    break
                received += len(line)
                if received > settings.output_limit_bytes:
                    overflow = True
                    _kill_group(process)
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n")
                if text.startswith("CALL "):
                    try:
                        call = json.loads(text[5:])
                    except json.JSONDecodeError:
                        call = {}
                    answer = _answer(broker, call)
                    try:
                        encoded = json.dumps(answer, allow_nan=False)
                    except ValueError:
                        encoded = json.dumps({"ok": False, "error": "Non-finite broker data"})
                    process.stdin.write(encoded.encode() + b"\n")
                    process.stdin.flush()
                elif text.startswith("RESULT "):
                    final = json.loads(text[7:])
                    break
        except (BrokenPipeError, ConnectionResetError, json.JSONDecodeError) as exc:
            logger.debug("Metric worker protocol ended early: %s", exc)
        finally:
            timer.cancel()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_group(process)
                process.wait()
            _kill_group(process)
            stderr.join(timeout=1)
            for stream in (process.stdin, process.stdout, process.stderr):
                with contextlib.suppress(BrokenPipeError, OSError):
                    stream.close()
    if timed_out.is_set() and final is None:
        raise WorkerFailure(
            f"Metric script exceeded the {settings.timeout_seconds:g} s time limit "
            "(METRIC_SCRIPT_TIMEOUT_SECONDS) and was stopped"
        )
    if overflow:
        raise WorkerFailure(
            f"Metric script output exceeded {settings.output_limit_bytes // (1024 * 1024)} MiB "
            "and was stopped"
        )
    if final is None:
        detail = stderr.text().strip().splitlines()
        tail = f": {detail[-1]}" if detail else ""
        raise WorkerFailure(
            f"Metric script worker exited with code {process.returncode} without a result{tail}"
        )
    log = str(final.get("log") or "")
    if not final.get("ok"):
        raise ScriptFailure(
            str(final.get("error") or "Metric script failed"),
            diagnostics=[d for d in final.get("diagnostics") or [] if isinstance(d, dict)],
            log=log,
        )
    return WorkerOutcome(
        result=final.get("result") or {},
        log=log,
        log_truncated=bool(final.get("log_truncated")),
        skipped_limits=list(final.get("skipped_limits") or []),
    )


def catalog(source: str, settings: RuntimeSettings | None = None) -> WorkerOutcome:
    """Compile ``source`` in a worker and return its metric metadata (no data access)."""
    return run_worker({"mode": "catalog", "source": source}, None, settings)


def evaluate(
    *,
    source: str,
    metric_id: str,
    chip_id: str,
    start: str,
    end: str,
    params: dict[str, Any],
    broker: BrokerHandler,
    settings: RuntimeSettings | None = None,
) -> WorkerOutcome:
    """Evaluate one metric of ``source`` over the chip, reading data through ``broker``."""
    return run_worker(
        {
            "mode": "evaluate",
            "source": source,
            "metric_id": metric_id,
            "chip_id": chip_id,
            "start": start,
            "end": end,
            "params": params,
        },
        broker,
        settings,
    )
