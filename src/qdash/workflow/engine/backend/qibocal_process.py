"""Parent-side process transport for the isolated Qibocal environment.

The caller owns the directory and artifact paths. This module only opens stdio logs,
starts argv in a minimal environment, and waits or stops the process group. It knows
nothing about protocol requests, platform snapshots, calibration, or result JSON.
Parent-death detection belongs to the child runner because a killed parent cannot clean up.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def run_process(
    command: list[str],
    *,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: float,
    terminate_grace_seconds: float,
) -> int:
    """Return the exit code, retaining both logs even on failure.

    Nonzero exit codes are interpreted by the caller. TimeoutExpired and cancellation
    (including BaseException) propagate after group cleanup. No artifacts are removed.
    The caller supplies the interpreter's isolation flag as part of argv.
    """
    env = {
        "PATH": os.defpath,
        "HOME": os.environ.get("HOME", str(cwd)),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),  # noqa: S108
        "LANG": "C.UTF-8",
        "MPLBACKEND": "Agg",
        "JAX_PLATFORMS": "cpu",
    }
    logger.info("Starting Qibocal runner: %s", " ".join(command))
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            shell=False,
            start_new_session=True,
        )
        try:
            return process.wait(timeout=timeout_seconds)
        except BaseException:
            # Includes TimeoutExpired and Prefect/KeyboardInterrupt cancellation.
            _stop(process, terminate_grace_seconds)
            raise


def _stop(process: subprocess.Popen[bytes], grace_seconds: float) -> None:
    """Terminate the runner's process group, then kill it after the grace period."""
    if process.poll() is not None:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, sig)
        try:
            process.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            continue
    logger.error("Qibocal runner pid=%s did not exit after SIGKILL", process.pid)
