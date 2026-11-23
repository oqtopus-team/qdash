"""Opt-in, bounded fault injection for validating agents against the fake backend.

The agent calibration validation harness (``agent-runtime/validation/fake-loop/``) needs one
measurement that fails for a reason the agent cannot classify, so it can check that the agent
stops for an expert instead of measuring again. This module provides that failure, and only on
the fake backend: the Qubex hardware backend never calls it.

A fault fires only when every condition holds:

- the worker process runs with ``QDASH_FAKE_FAULT_INJECTION=1``;
- ``<QUBEX_CONFIG_BASE>/<chip_id>/validation/fake-fault.json`` exists for the chip of the run;
- the file names the run's chip, qubit, and task;
- its ``expires_at`` lies in the future, and at most ``MAX_FAULT_LIFETIME`` ahead, so a file
  left behind by an interrupted harness stops firing on its own.

The run then fails before the simulator measures anything, with a message that names the fault
id and says it was injected. Any problem with the file (unreadable, malformed, wrong types)
disables the fault rather than failing the run.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FAULT_INJECTION_ENV = "QDASH_FAKE_FAULT_INJECTION"
"""Worker environment variable that must be ``1`` before any fault file is read."""

FAULT_FILE = Path("validation") / "fake-fault.json"
"""Fault file location relative to the chip's configuration directory."""

MAX_FAULT_LIFETIME = timedelta(hours=1)
"""Longest time ahead a fault file may set ``expires_at``."""

_MAX_FILE_BYTES = 4096


class FakeValidationFault(RuntimeError):
    """The failure a validation fault injects into one fake-backend run."""


@dataclass(frozen=True)
class FakeFaultSpec:
    """One fault: which run it fails and until when."""

    fault_id: str
    chip_id: str
    qid: str
    task_name: str
    expires_at: datetime

    def message(self) -> str:
        """The failure message the run records; it names the fault and that it was injected."""
        return (
            f"Fake backend validation fault {self.fault_id}: the simulator aborted "
            f"{self.task_name} on qubit {self.qid} and returned no data. The failure was "
            "injected for agent validation; its cause is deliberately not reported."
        )


def fault_file_path(chip_dir: Path) -> Path:
    """The fault file of a chip whose configuration directory is ``chip_dir``."""
    return chip_dir / FAULT_FILE


def _parse_expiry(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def parse_fault(data: Any, *, now: datetime) -> FakeFaultSpec | None:
    """Return the fault the decoded file describes, or ``None`` when it is invalid or stale."""
    if not isinstance(data, dict):
        return None
    fields = {}
    for name in ("fault_id", "chip_id", "qid", "task_name"):
        value = data.get(name)
        if not isinstance(value, str) or not value or len(value) > 200:
            return None
        fields[name] = value
    expires_at = _parse_expiry(data.get("expires_at"))
    if expires_at is None or expires_at <= now or expires_at > now + MAX_FAULT_LIFETIME:
        return None
    return FakeFaultSpec(expires_at=expires_at, **fields)


def load_fault(
    chip_dir: Path,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    now: datetime | None = None,
) -> FakeFaultSpec | None:
    """Read the chip's fault file when fault injection is enabled for this process."""
    environment = os.environ if env is None else env
    if environment.get(FAULT_INJECTION_ENV) != "1":
        return None
    path = fault_file_path(chip_dir)
    try:
        if not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Ignoring unreadable fake fault file %s", path)
        return None
    spec = parse_fault(data, now=now or datetime.now(UTC))
    if spec is None:
        logger.warning("Ignoring invalid or expired fake fault file %s", path)
    return spec


def raise_validation_fault(
    *,
    chip_dir: Path,
    chip_id: str,
    task_name: str,
    qid: str,
    env: dict[str, str] | os._Environ[str] | None = None,
    now: datetime | None = None,
) -> None:
    """Raise ``FakeValidationFault`` when an enabled fault names this chip, qubit, and task."""
    spec = load_fault(chip_dir, env=env, now=now)
    if spec is None:
        return
    if (spec.chip_id, spec.qid, spec.task_name) != (chip_id, qid, task_name):
        return
    logger.warning("Injecting fake validation fault %s", spec.fault_id)
    raise FakeValidationFault(spec.message())
