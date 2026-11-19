"""Process transport works without a Qibocal request, platform, or backend."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from qdash.workflow.engine.backend.qibocal_process import run_process


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); reap it if it is our child.
    try:
        waited, _ = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        # Not our child: an orphan the init process has not reaped yet is a zombie.
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists():
            return stat.read_text().rsplit(")", 1)[-1].split()[0] != "Z"
        state = subprocess.run(  # noqa: S603 - fixed argv
            ["ps", "-o", "stat=", "-p", str(pid)],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        return bool(state) and not state.startswith("Z")
    return waited == 0


def _wait_dead(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


@pytest.mark.parametrize("exit_code", [0, 7])
def test_exit_code_logs_and_environment(tmp_path: Path, monkeypatch, exit_code: int) -> None:
    monkeypatch.setenv("QDASH_SECRET_FOR_TEST", "not-inherited")
    code = (
        "import json, os, sys\n"
        "print(json.dumps({'env': dict(os.environ), 'isolated': sys.flags.isolated, "
        "'stdin': sys.stdin.read(), 'cwd': os.getcwd()}))\n"
        "print('diagnostic', file=sys.stderr)\n"
        f"sys.exit({exit_code})\n"
    )
    result = run_process(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        stdout_path=tmp_path / "out.log",
        stderr_path=tmp_path / "err.log",
        timeout_seconds=10,
        terminate_grace_seconds=1,
    )
    assert result == exit_code
    output = json.loads((tmp_path / "out.log").read_text())
    assert output["isolated"] == 1
    assert output["stdin"] == ""
    assert Path(output["cwd"]).resolve() == tmp_path.resolve()
    assert "QDASH_SECRET_FOR_TEST" not in output["env"]
    assert output["env"]["MPLBACKEND"] == "Agg"
    assert output["env"]["JAX_PLATFORMS"] == "cpu"
    assert (tmp_path / "err.log").read_text() == "diagnostic\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["err.log", "out.log"]


def test_timeout_kills_term_resistant_process_group(tmp_path: Path) -> None:
    code = (
        "import os, signal, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "Path('pids').write_text(f'{os.getpid()} {child.pid}')\n"
        "print('started', flush=True)\n"
        "time.sleep(60)\n"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run_process(
            [sys.executable, "-I", "-c", code],
            cwd=tmp_path,
            stdout_path=tmp_path / "out.log",
            stderr_path=tmp_path / "err.log",
            timeout_seconds=2,
            terminate_grace_seconds=0.2,
        )
    for pid in (tmp_path / "pids").read_text().split():
        assert _wait_dead(int(pid))
    assert (tmp_path / "out.log").read_text() == "started\n"


def test_launch_failure_retains_logs(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_process(
            [str(tmp_path / "missing")],
            cwd=tmp_path,
            stdout_path=tmp_path / "out.log",
            stderr_path=tmp_path / "err.log",
            timeout_seconds=10,
            terminate_grace_seconds=1,
        )
    assert (tmp_path / "out.log").read_bytes() == b""
    assert (tmp_path / "err.log").read_bytes() == b""
