"""Runtime path helpers for the host-side updater."""

import os
from pathlib import Path


def updater_runtime_dir() -> Path:
    """Return a host-user-owned runtime directory outside the repository checkout."""
    configured = os.environ.get("QDASH_UPDATER_RUNTIME_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    configured_state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    state_home = (
        Path(configured_state_home).expanduser()
        if configured_state_home
        else Path.home() / ".local" / "state"
    )
    return (state_home / "qdash" / "updater").resolve()


def ensure_private_directory(path: Path) -> None:
    """Create an updater directory that is accessible only to its host user."""
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
