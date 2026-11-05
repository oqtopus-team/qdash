#!/usr/bin/env python3
"""Run a command in its own session and record its pid in a pid file.

The command starts as a new process group leader so that ``task dev-local-down``
can stop the whole group. SIGINT and SIGTERM received by this wrapper are
forwarded to that process group. When the command exits, the pid file is
removed if it still holds the command's pid, and the wrapper exits with the
command's status.

Usage:
    python3 scripts/run-with-pidfile.py .tmp/dev-api-local.pid uv run uvicorn ...
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import FrameType


def remove_pid_file(pid_file: Path, pid: int) -> None:
    """Remove ``pid_file`` only when it still records ``pid``."""
    try:
        if pid_file.read_text().strip() == str(pid):
            pid_file.unlink()
    except FileNotFoundError:
        pass


def run(pid_file: Path, command: list[str]) -> int:
    """Run ``command`` in a new session, tracking it through ``pid_file``.

    Returns the command's exit status.
    """
    child = subprocess.Popen(command, start_new_session=True)  # noqa: S603
    pid_file.write_text(f"{child.pid}\n")

    def forward(signum: int, _frame: FrameType | None) -> None:
        """Forward a received signal to the command's process group."""
        os.killpg(child.pid, signum)

    signal.signal(signal.SIGINT, forward)
    signal.signal(signal.SIGTERM, forward)
    status = child.wait()
    remove_pid_file(pid_file, child.pid)
    return status


def main() -> None:
    """Parse ``<pidfile> <command...>`` from argv and run the command."""
    if len(sys.argv) < 3:
        sys.stderr.write(f"usage: {Path(sys.argv[0]).name} <pidfile> <command...>\n")
        sys.exit(2)
    sys.exit(run(Path(sys.argv[1]), sys.argv[2:]))


if __name__ == "__main__":
    main()
