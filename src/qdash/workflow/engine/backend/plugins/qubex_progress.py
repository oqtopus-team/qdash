"""Qubex adapter for forwarding internal tqdm loops as task progress."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from tqdm.auto import tqdm as Tqdm

from qdash.workflow.engine.progress import ProgressReporter, TaskProgress

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)


_reporter: ContextVar[ProgressReporter | None] = ContextVar(
    "qdash_qubex_progress_reporter",
    default=None,
)
_task_name: ContextVar[str] = ContextVar("qdash_qubex_progress_task_name", default="")
_active_bar: ContextVar[object | None] = ContextVar(
    "qdash_qubex_active_progress_bar",
    default=None,
)
_installed = False


class ReportingTqdm(Tqdm):
    """tqdm variant that forwards its rendered progress to QDash."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        reporter = _reporter.get()
        task_name = _task_name.get()
        self._qdash_render_disabled = reporter is not None and bool(kwargs.get("disable", False))
        if self._qdash_render_disabled:
            # qubex disables tqdm for most parameter sweeps. tqdm then also
            # stops maintaining ``n``, so keep it enabled internally while
            # suppressing only its terminal rendering.
            kwargs["disable"] = False
        self._qdash_reporter: ProgressReporter | None = None
        self._qdash_description = ""
        self._qdash_active_token: Token[object | None] | None = None
        self._qdash_last_reported_at = 0.0
        kwargs.setdefault("mininterval", 1.0)
        kwargs.setdefault("miniters", 1)
        try:
            super().__init__(*args, **kwargs)
            if (
                reporter is not None
                and _active_bar.get() is None
                and _select_progress_bar(task_name, self.desc or "")
            ):
                self._qdash_reporter = reporter
                self._qdash_description = _progress_description(task_name, self.desc or "")
                self._qdash_active_token = _active_bar.set(self)
                # tqdm normally emits the next snapshot only after the first
                # iteration. A single qubex sweep point can take minutes, so
                # publish 0 / total immediately to make the active phase visible.
                self.display()
        except Exception:
            self._release_active_bar()
            raise

    def close(self) -> None:
        """Close tqdm and release ownership of the outermost progress stream."""
        try:
            super().close()
        finally:
            self._release_active_bar()

    def _release_active_bar(self) -> None:
        """Release the outermost-bar token exactly once."""
        if self._qdash_active_token is not None:
            _active_bar.reset(self._qdash_active_token)
            self._qdash_active_token = None

    def display(self, msg: str | None = None, pos: int | None = None) -> bool | None:
        """Render normally and forward a throttled progress snapshot."""
        result = (
            None
            if self._qdash_render_disabled
            else cast("bool | None", super().display(msg=msg, pos=pos))
        )
        reporter = self._qdash_reporter
        if reporter is None:
            return result

        now = time.monotonic()
        is_complete = self.total is not None and self.n >= self.total
        if self.n > 0 and not is_complete and now - self._qdash_last_reported_at < 1.0:
            return result

        elapsed = float(self.format_dict.get("elapsed") or 0.0)
        total = int(self.total) if self.total is not None else None
        eta = None
        if total is not None and self.n > 0 and elapsed > 0:
            eta = max(elapsed * (total - self.n) / self.n, 0.0)

        try:
            reporter(
                TaskProgress(
                    current=int(self.n),
                    total=total,
                    description=self._qdash_description,
                    elapsed_seconds=elapsed,
                    eta_seconds=eta,
                    updated_at=datetime.now(UTC).isoformat(),
                )
            )
            self._qdash_last_reported_at = now
        except Exception:
            logger.warning("Failed to report qubex progress", exc_info=True)
        return result


def _select_progress_bar(task_name: str, description: str) -> bool:
    """Select the meaningful outer sweep for spectroscopy tasks."""
    normalized = description.casefold()
    if task_name == "CheckQubitSpectroscopy":
        return normalized.startswith("control power sweep")
    if task_name == "CheckResonatorSpectroscopy":
        ignored = ("electrical delay", "subrange", "within subrange")
        return not any(fragment in normalized for fragment in ignored)
    return True


def _progress_description(task_name: str, description: str) -> str:
    """Supply a stable label when qubex leaves the selected bar unnamed."""
    if task_name == "CheckResonatorSpectroscopy" and not description:
        return "readout power sweep"
    task_labels = {
        "CheckChevron": "Chevron sweep",
        "CheckRabi": "Rabi time sweep",
        "CheckRamsey": "Ramsey delay sweep",
        "CheckT1": "T1 delay sweep",
        "CheckT1Average": "T1 measurement sweep",
        "CheckT2Echo": "T2 echo delay sweep",
        "CheckT2EchoAverage": "T2 echo measurement sweep",
        "CheckPIPulse": "Pi-pulse sweep",
        "CheckHPIPulse": "Half-pi-pulse sweep",
        "CreatePIPulse": "Pi-pulse calibration sweep",
        "CreateHPIPulse": "Half-pi-pulse calibration sweep",
    }
    if task_name in task_labels and (not description or description == "Sweeping parameters"):
        return task_labels[task_name]
    return description


def _install_adapter() -> None:
    """Install the process-wide adapter once, retaining task-local reporters."""
    global _installed
    if _installed:
        return

    from qubex.experiment.services import characterization_service, measurement_service

    characterization_service.__dict__["tqdm"] = ReportingTqdm
    measurement_service.__dict__["tqdm"] = ReportingTqdm
    _installed = True


@contextmanager
def capture_qubex_progress(
    reporter: ProgressReporter,
    *,
    task_name: str = "",
) -> Iterator[None]:
    """Forward qubex tqdm updates to ``reporter`` for the current context."""
    _install_adapter()
    reporter_token = _reporter.set(reporter)
    task_name_token = _task_name.set(task_name)
    try:
        yield
    finally:
        _task_name.reset(task_name_token)
        _reporter.reset(reporter_token)
