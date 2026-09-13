"""Run the host-side updater with Uvicorn."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import uvicorn


def _runtime_paths() -> tuple[Path, Path, Path]:
    runtime_dir = Path(
        os.environ.get("QDASH_UPDATER_RUNTIME_DIR", "").strip() or ".tmp/qdash-updater"
    ).resolve()
    configured_path = os.environ.get("QDASH_UPDATER_SOCKET", "").strip()
    socket_path = (
        Path(configured_path).resolve() if configured_path else runtime_dir / "updater.sock"
    )
    return socket_path, runtime_dir / "updater.pid", runtime_dir / "updater.log"


def _run_server(socket_path: Path, pid_path: Path) -> None:
    """Run the server and expose its process ID for task-based lifecycle management."""
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        if not socket_path.is_socket():
            raise RuntimeError(f"Updater socket path is not a socket: {socket_path}")
        socket_path.unlink()
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        uvicorn.run("qdash.updater.app:app", uds=str(socket_path))
    finally:
        if _read_pid(pid_path) == os.getpid():
            pid_path.unlink()
        if socket_path.is_socket():
            socket_path.unlink()


def _is_updater_process(pid: int) -> bool:
    """Return whether PID belongs to a live updater process on the Linux deployment host."""
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False
    return b"qdash.updater" in command or b"qdash-updater" in command


def _read_pid(pid_path: Path) -> int | None:
    try:
        return int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _start_daemon(socket_path: Path, pid_path: Path, log_path: Path) -> None:
    """Start a detached copy using the current locked Python environment."""
    existing_pid = _read_pid(pid_path)
    if existing_pid is not None and _is_updater_process(existing_pid):
        print(f"QDash updater is already running: {existing_pid}")
        return
    pid_path.unlink(missing_ok=True)
    if socket_path.exists():
        if not socket_path.is_socket():
            raise SystemExit(f"Updater socket path exists and is not a socket: {socket_path}")
        socket_path.unlink()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            [sys.executable, "-m", "qdash.updater"],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

    for _ in range(50):
        if socket_path.is_socket():
            print(f"QDash updater started: {process.pid}")
            return
        if process.poll() is not None:
            break
        time.sleep(0.2)
    if _is_updater_process(process.pid):
        os.kill(process.pid, signal.SIGTERM)
    pid_path.unlink(missing_ok=True)
    raise SystemExit(f"QDash updater failed to start. See {log_path}.")


def _stop_daemon(socket_path: Path, pid_path: Path) -> None:
    """Stop only the updater process recorded in the runtime directory."""
    pid = _read_pid(pid_path)
    if pid is None or not _is_updater_process(pid):
        pid_path.unlink(missing_ok=True)
        if socket_path.is_socket():
            socket_path.unlink()
        print("QDash updater is not running")
        return

    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not _is_updater_process(pid):
            break
        time.sleep(0.1)
    if _is_updater_process(pid):
        raise SystemExit(f"QDash updater did not stop within 5 seconds: {pid}")
    pid_path.unlink(missing_ok=True)
    if socket_path.is_socket():
        socket_path.unlink()
    print(f"QDash updater stopped: {pid}")


def _show_status(pid_path: Path) -> None:
    pid = _read_pid(pid_path)
    if pid is not None and _is_updater_process(pid):
        print(f"QDash updater is running: {pid}")
        return
    print("QDash updater is not running")


def main() -> None:
    """Start the updater on a local Unix domain socket."""
    parser = argparse.ArgumentParser(description="Run the QDash host updater")
    parser.add_argument(
        "command",
        choices=("run", "start", "stop", "status"),
        nargs="?",
        default="run",
    )
    args = parser.parse_args()
    socket_path, pid_path, log_path = _runtime_paths()
    if args.command == "start":
        _start_daemon(socket_path, pid_path, log_path)
        return
    if args.command == "stop":
        _stop_daemon(socket_path, pid_path)
        return
    if args.command == "status":
        _show_status(pid_path)
        return
    existing_pid = _read_pid(pid_path)
    if existing_pid is not None and _is_updater_process(existing_pid):
        raise SystemExit(f"QDash updater is already running: {existing_pid}")
    _run_server(socket_path, pid_path)


if __name__ == "__main__":
    main()
