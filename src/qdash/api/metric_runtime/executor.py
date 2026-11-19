"""Run metric script workers and serve their data requests.

Each validation (``catalog``) or evaluation runs ``qdash.api.metric_runtime.worker`` once.
In the default ``socket`` mode the API is only a client: it sends the job to the dedicated
``metric-runner`` container over a Unix socket and answers the worker's data requests,
relayed by the runner, through a :class:`~qdash.api.metric_runtime.broker.BrokerHandler`
until the runner reports the ``result`` (protocol in
``agent-runtime/metric-runner/protocol.ts``; the worker's own line protocol is in
:mod:`.worker`). The ``local`` mode spawns the worker as a subprocess of the API process
instead and exists for development only. Socket mode never falls back to local mode: an
unreachable runner is an error.

Settings (environment variables read per run, with defaults):

``METRIC_RUNNER_MODE`` (``socket``)
    ``socket`` sends jobs to the metric runner; ``local`` runs the worker inside the API
    process's container (development only, for example the host-side ``dev-api-local``,
    which has no metric runner socket).
``METRIC_RUNNER_SOCKET`` (``/run/metric-runner/metric.sock``)
    The metric runner's socket. When it is missing or refuses the connection, or the runner
    stops before a job ends, runs fail with :class:`RunnerUnavailableError` (HTTP 503).
``METRIC_SCRIPT_TIMEOUT_SECONDS`` (60)
    Wall-clock limit per run; the worker's processes are killed when it expires. The
    worker also sets ``RLIMIT_CPU`` to this value plus one second. The runner caps it at
    its own ``METRIC_RUNNER_MAX_TIMEOUT_SECONDS``.
``METRIC_SCRIPT_MEMORY_MB`` (1024)
    Address space the script may use on top of the interpreter and the preloaded
    numpy/scipy baseline (``RLIMIT_AS``), where the platform supports it. The runner caps
    it at ``METRIC_RUNNER_MAX_MEMORY_MB``.
``METRIC_SCRIPT_CONCURRENCY`` (2)
    Local mode only: workers running at once in this API process. A run that cannot start
    within :data:`QUEUE_WAIT_SECONDS` fails with :class:`QueueFullError` (HTTP 429). In
    socket mode the runner enforces one global limit (``METRIC_RUNNER_CONCURRENCY``)
    across every API process and answers ``queue_full`` instead.

The worker's stdout is bounded to :data:`OUTPUT_LIMIT_BYTES`; script ``print`` output is
kept in a 16 KiB log.

Threat model
------------
Who can run code: project editors and owners (the same people who can save calibration
flows that run on hardware). Viewers can only evaluate scripts that were saved and
validated by an editor; draft evaluation and validation require editor rights.

Socket mode (deployments):

- The API keeps authentication, authorization, period and topology resolution, and all
  database access. It builds the broker, pinned to the caller's project, the evaluated chip
  and the period, before it connects. The request names no user or project; the runner
  cannot widen the scope, and the worker reads data only through the relayed broker.
- The runner (``agent-runtime/metric-runner/runner.ts``) is the only process of the
  ``metric-runner`` container: no network, read-only root, no credentials, and nothing
  shared with the Copilot workspace. It admits jobs into a few global slots, starts each
  worker as the slot's own job uid with no capabilities and ``no_new_privs``, in a fresh
  private job directory, with an environment that holds only ``PATH``, ``PYTHONPATH``,
  ``HOME``/``TMPDIR``, locale and BLAS thread variables. On completion, timeout or
  disconnect it kills every process of the job uid and removes its files before the slot
  is reused.
- Resource bounds: the worker's rlimits (address space, CPU time, file size, process
  count), the runner's wall clock and stdout bound, and the container's CPU, memory and
  pids limits, which every job shares (there is no per-job cgroup). Workers raise their
  ``oom_score_adj``, so the kernel kills a job rather than the runner when the container
  runs out of memory. The API side also gives up :data:`DEADLINE_GRACE_SECONDS` after the
  time limit and closes the connection, which makes the runner kill the job.
- Guardrails: an import allowlist and disabled builtins (:mod:`.policy`), which catch
  mistakes and make intent explicit. They are not a sandbox; the boundary is the job uid
  in the ``metric-runner`` container.

Local mode (development only): the worker runs as the API container's user with the API's
network and filesystem view. Its environment is scrubbed (:func:`scrubbed_env`) and the
rlimits, timeout and output bounds apply, but nothing else separates it from the API. Do
not use it where untrusted editors can save scripts.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from qdash.api.metric_runtime.broker import BrokerHandler

logger = logging.getLogger(__name__)

RunnerMode = Literal["socket", "local"]

OUTPUT_LIMIT_BYTES = 8 * 1024 * 1024
STDERR_LIMIT_BYTES = 64 * 1024
QUEUE_WAIT_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MEMORY_MB = 1024
DEFAULT_CONCURRENCY = 2
DEFAULT_RUNNER_MODE: RunnerMode = "socket"
DEFAULT_SOCKET_PATH = "/run/metric-runner/metric.sock"
WORKER_MODULE = "qdash.api.metric_runtime.worker"
SOURCE_ROOT = str(Path(__file__).resolve().parents[3])
"""Directory containing the ``qdash`` package; prepended to the worker's PYTHONPATH."""

PROTOCOL_VERSION = 1
"""Version of the API ⇄ runner protocol (``v`` of the request line)."""
CONNECT_TIMEOUT_SECONDS = 2.0
"""How long connecting to the runner socket may take."""
ADMISSION_TIMEOUT_SECONDS = 30.0
"""How long the runner may take to accept or refuse a job (its queue wait is shorter)."""
DEADLINE_GRACE_SECONDS = 15.0
"""Time after the run's time limit before the API gives up on the runner."""
MESSAGE_LIMIT_BYTES = 1024 * 1024
"""Longest runner line other than ``result``."""
RESULT_SLACK_BYTES = 1024
"""Room for the ``type`` field the runner adds to the worker's result line."""
ANSWER_LIMIT_BYTES = 32 * 1024 * 1024
"""Longest answer line the runner accepts (its ``ANSWER_MAX_BYTES``)."""
_FAILURE_MESSAGE_CHARS = 2000


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
    """No worker slot became free in time."""


class RunnerUnavailableError(MetricRuntimeError):
    """The metric runner cannot be reached or did not take the job; nothing ran."""


class WorkerFailure(MetricRuntimeError):
    """The worker timed out, exceeded its output bound or exited without a result."""


class ScriptFailure(MetricRuntimeError):
    """The script itself failed (compile error, policy violation, invalid declaration)."""


@dataclass(frozen=True)
class RuntimeSettings:
    """Limits of one worker run and where it runs.

    ``concurrency`` and ``queue_wait_seconds`` apply to ``mode="local"`` only; the runner
    enforces its own global limit in socket mode.
    """

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    memory_mb: int = DEFAULT_MEMORY_MB
    concurrency: int = DEFAULT_CONCURRENCY
    queue_wait_seconds: float = QUEUE_WAIT_SECONDS
    output_limit_bytes: int = OUTPUT_LIMIT_BYTES
    mode: RunnerMode = DEFAULT_RUNNER_MODE
    socket_path: str = DEFAULT_SOCKET_PATH


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


def _env_mode() -> RunnerMode:
    raw = (os.environ.get("METRIC_RUNNER_MODE") or "").strip().lower()
    if not raw:
        return DEFAULT_RUNNER_MODE
    if raw in ("socket", "local"):
        return cast("RunnerMode", raw)
    logger.warning("Ignoring invalid METRIC_RUNNER_MODE=%r; using socket", raw)
    return DEFAULT_RUNNER_MODE


def load_settings() -> RuntimeSettings:
    """Read the runtime settings from the environment."""
    return RuntimeSettings(
        timeout_seconds=_env_number("METRIC_SCRIPT_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, 1),
        memory_mb=int(_env_number("METRIC_SCRIPT_MEMORY_MB", DEFAULT_MEMORY_MB, 128)),
        concurrency=int(_env_number("METRIC_SCRIPT_CONCURRENCY", DEFAULT_CONCURRENCY, 1)),
        mode=_env_mode(),
        socket_path=(os.environ.get("METRIC_RUNNER_SOCKET") or "").strip() or DEFAULT_SOCKET_PATH,
    )


@dataclass
class WorkerOutcome:
    """A successful worker run."""

    result: dict[str, Any]
    log: str = ""
    log_truncated: bool = False
    skipped_limits: list[str] = field(default_factory=list)


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


def _time_limit_message(settings: RuntimeSettings) -> str:
    return (
        f"Metric script exceeded the {settings.timeout_seconds:g} s time limit "
        "(METRIC_SCRIPT_TIMEOUT_SECONDS) and was stopped"
    )


def _output_limit_message(settings: RuntimeSettings) -> str:
    return (
        f"Metric script output exceeded {settings.output_limit_bytes // (1024 * 1024)} MiB "
        "and was stopped"
    )


def _outcome(final: dict[str, Any]) -> WorkerOutcome:
    """Turn the worker's ``RESULT`` object into an outcome or a :class:`ScriptFailure`."""
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


def run_worker(
    request: dict[str, Any],
    broker: BrokerHandler | None = None,
    settings: RuntimeSettings | None = None,
) -> WorkerOutcome:
    """Run one worker request to completion, in the runner or locally per ``settings.mode``.

    Raises:
        RunnerUnavailableError: If the metric runner cannot be reached (socket mode).
        QueueFullError: If no worker slot frees up in time.
        WorkerFailure: On timeout, output overflow or a crash without result.
        ScriptFailure: If the worker reports a script-level failure.
    """
    settings = settings or load_settings()
    if settings.mode == "local":
        return _run_local_bounded(request, broker, settings)
    return _run_socket(request, broker, settings)


# -- socket mode: a client of the metric-runner container -----------------------------


class _Expired(Exception):
    """A deadline passed while waiting for the runner."""


class _RunnerConnection:
    """Newline-delimited JSON over one runner connection, with bounded lines."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buffer = bytearray()
        self._scanned = 0
        self._eof = False

    def send_line(self, line: bytes, deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _Expired
        self._sock.settimeout(remaining)
        try:
            self._sock.sendall(line + b"\n")
        except TimeoutError as exc:
            raise _Expired from exc

    def read_line(self, limit: int, deadline: float) -> bytes | None:
        """The next line without its newline, or ``None`` once the runner closed.

        Lines already received are returned even after ``deadline``; waiting for more
        data past it raises :class:`_Expired`.
        """
        while True:
            newline = self._buffer.find(b"\n", self._scanned)
            if newline != -1:
                if newline > limit:
                    raise WorkerFailure("Metric script runner sent an oversized message")
                line = bytes(self._buffer[:newline])
                del self._buffer[: newline + 1]
                self._scanned = 0
                return line
            self._scanned = len(self._buffer)
            if len(self._buffer) > limit:
                raise WorkerFailure("Metric script runner sent an oversized message")
            if self._eof:
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _Expired
            self._sock.settimeout(remaining)
            try:
                chunk = self._sock.recv(64 * 1024)
            except TimeoutError as exc:
                raise _Expired from exc
            except OSError:
                chunk = b""
            if not chunk:
                self._eof = True
            else:
                self._buffer.extend(chunk)

    def read_message(self, limit: int, deadline: float) -> dict[str, Any] | None:
        line = self.read_line(limit, deadline)
        if line is None:
            return None
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkerFailure("Metric script runner sent a malformed message") from exc
        if not isinstance(message, dict) or not isinstance(message.get("type"), str):
            raise WorkerFailure("Metric script runner sent a malformed message")
        if message["type"] != "result" and len(line) > MESSAGE_LIMIT_BYTES:
            raise WorkerFailure("Metric script runner sent an oversized message")
        return message


def _connect(path: str) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(CONNECT_TIMEOUT_SECONDS)
    try:
        sock.connect(path)
    except OSError as exc:
        sock.close()
        logger.warning("Metric script runner at %s is not reachable: %s", path, exc)
        raise RunnerUnavailableError(
            "The metric script runner is not available; try again shortly or ask an "
            "administrator to check the metric-runner service"
        ) from exc
    return sock


def _text(value: Any) -> str:
    return str(value)[:_FAILURE_MESSAGE_CHARS] if value is not None else ""


def _refusal(message: dict[str, Any]) -> MetricRuntimeError:
    """The runner's ``error`` line (sent instead of ``accepted``) as an exception."""
    code = message.get("code")
    detail = _text(message.get("message"))
    if code == "queue_full":
        return QueueFullError("Metric script evaluation queue is full; try again shortly")
    logger.warning("Metric script runner refused a job (%s): %s", code, detail)
    return WorkerFailure(f"Metric script runner refused the request: {detail or code}")


def _failure(message: dict[str, Any], settings: RuntimeSettings) -> MetricRuntimeError:
    """The runner's ``failed`` line as an exception, worded like local mode.

    ``runner_error`` (the runner could not prepare or start the worker) is an
    infrastructure fault, not a script result, so it is reported like an unreachable
    runner (HTTP 503) and never recorded as an invalid revision.
    """
    code = message.get("code")
    if code == "timeout":
        return WorkerFailure(_time_limit_message(settings))
    if code == "output_limit":
        return WorkerFailure(_output_limit_message(settings))
    text = _text(message.get("message")) or "Metric script worker failed without a result"
    if code == "runner_error":
        logger.warning("Metric script runner could not run the job: %s", text)
        return RunnerUnavailableError(
            f"{text}; try again shortly or ask an administrator to check the metric-runner service"
        )
    lines = _text(message.get("stderr_tail")).strip().splitlines()
    tail = f": {lines[-1]}" if lines else ""
    logger.info("Metric script job failed (%s): %s", code, text)
    return WorkerFailure(f"{text}{tail}")


def _relay_call(
    connection: _RunnerConnection,
    message: dict[str, Any],
    broker: BrokerHandler | None,
    deadline: float,
) -> None:
    """Answer one ``call`` from the broker; refuse it once the deadline has passed."""
    if time.monotonic() >= deadline:
        with contextlib.suppress(OSError, _Expired):
            connection.send_line(
                json.dumps(
                    {"type": "answer", "ok": False, "error": "Time limit exceeded"}
                ).encode(),
                time.monotonic() + 1,
            )
        raise _Expired
    answer = _answer(broker, {"op": message.get("op"), "args": message.get("args")})
    try:
        encoded = json.dumps({"type": "answer", **answer}, allow_nan=False).encode()
    except (TypeError, ValueError):
        encoded = json.dumps(
            {"type": "answer", "ok": False, "error": "Non-finite broker data"}
        ).encode()
    if len(encoded) > ANSWER_LIMIT_BYTES:
        encoded = json.dumps(
            {"type": "answer", "ok": False, "error": "Broker data is too large"}
        ).encode()
    try:
        # Deliver a finished answer even if the broker took past the deadline; the next
        # read or call then stops the job.
        connection.send_line(encoded, max(deadline, time.monotonic() + 1))
    except OSError as exc:
        # The runner ended the job; its last line (if any) is still readable.
        logger.debug("Metric script runner closed while answering: %s", exc)


def _run_socket(
    request: dict[str, Any], broker: BrokerHandler | None, settings: RuntimeSettings
) -> WorkerOutcome:
    try:
        line = json.dumps(
            {
                "v": PROTOCOL_VERSION,
                **request,
                "memory_mb": settings.memory_mb,
                "timeout_seconds": settings.timeout_seconds,
            },
            allow_nan=False,
        ).encode()
    except ValueError as exc:
        raise WorkerFailure("Metric script parameters must be finite numbers") from exc
    sock = _connect(settings.socket_path)
    try:
        return _converse(_RunnerConnection(sock), line, broker, settings)
    finally:
        # Closing is the cancel signal: the runner kills a job whose client is gone.
        sock.close()


def _converse(
    connection: _RunnerConnection,
    request_line: bytes,
    broker: BrokerHandler | None,
    settings: RuntimeSettings,
) -> WorkerOutcome:
    admission = time.monotonic() + ADMISSION_TIMEOUT_SECONDS
    unavailable = (
        "The metric script runner did not take the job; try again shortly or ask an "
        "administrator to check the metric-runner service"
    )
    try:
        connection.send_line(request_line, admission)
        reply = connection.read_message(MESSAGE_LIMIT_BYTES, admission)
    except (_Expired, OSError) as exc:
        logger.warning("Metric script runner did not answer the request: %r", exc)
        raise RunnerUnavailableError(unavailable) from exc
    if reply is None:
        logger.warning("Metric script runner closed the connection before accepting a job")
        raise RunnerUnavailableError(unavailable)
    if reply["type"] == "error":
        raise _refusal(reply)
    if reply["type"] != "accepted":
        raise WorkerFailure(f"Metric script runner sent an unexpected '{reply['type']}' message")
    logger.debug("Metric script job %s accepted", reply.get("job_id"))

    deadline = time.monotonic() + settings.timeout_seconds + DEADLINE_GRACE_SECONDS
    limit = max(settings.output_limit_bytes + RESULT_SLACK_BYTES, MESSAGE_LIMIT_BYTES)
    try:
        while True:
            message = connection.read_message(limit, deadline)
            if message is None:
                # The runner ends every job it accepted with `result` or `failed`; a bare
                # close means it stopped (crash or shutdown), not that the script failed.
                logger.warning(
                    "Metric script runner closed job %s without a result", reply.get("job_id")
                )
                raise RunnerUnavailableError(
                    "The metric script runner stopped before the job finished; try again "
                    "shortly or ask an administrator to check the metric-runner service"
                )
            kind = message["type"]
            if kind == "call":
                _relay_call(connection, message, broker, deadline)
            elif kind == "result":
                return _outcome(message)
            elif kind == "failed":
                raise _failure(message, settings)
            else:
                raise WorkerFailure(f"Metric script runner sent an unexpected '{kind}' message")
    except _Expired as exc:
        logger.warning(
            "Metric script job %s gave no result within the time limit plus %g s; cancelling",
            reply.get("job_id"),
            DEADLINE_GRACE_SECONDS,
        )
        raise WorkerFailure(_time_limit_message(settings)) from exc


# -- local mode: a subprocess of the API process (development only) -----------------


_slots_lock = threading.Lock()
_slots: dict[int, threading.BoundedSemaphore] = {}
_local_mode_warned = threading.Event()


def _semaphore(concurrency: int) -> threading.BoundedSemaphore:
    with _slots_lock:
        if concurrency not in _slots:
            _slots[concurrency] = threading.BoundedSemaphore(concurrency)
        return _slots[concurrency]


def scrubbed_env() -> dict[str, str]:
    """The local worker's whole environment: no database settings, tokens or API keys."""
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


def _run_local_bounded(
    request: dict[str, Any], broker: BrokerHandler | None, settings: RuntimeSettings
) -> WorkerOutcome:
    if not _local_mode_warned.is_set():
        _local_mode_warned.set()
        logger.warning(
            "METRIC_RUNNER_MODE=local: metric scripts run inside the API process; "
            "for development only"
        )
    slots = _semaphore(settings.concurrency)
    if not slots.acquire(timeout=settings.queue_wait_seconds):
        raise QueueFullError("Metric script evaluation queue is full; try again shortly")
    try:
        return _run_local(request, broker, settings)
    finally:
        slots.release()


def _run_local(
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
        raise WorkerFailure(_time_limit_message(settings))
    if overflow:
        raise WorkerFailure(_output_limit_message(settings))
    if final is None:
        detail = stderr.text().strip().splitlines()
        tail = f": {detail[-1]}" if detail else ""
        raise WorkerFailure(
            f"Metric script worker exited with code {process.returncode} without a result{tail}"
        )
    return _outcome(final)


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
