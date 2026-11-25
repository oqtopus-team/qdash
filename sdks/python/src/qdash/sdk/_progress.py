"""Progress display for the run handles' ``wait``: one live line per wait.

The display picks its target when a wait starts:

- In a Jupyter kernel, one display output of the cell is created and updated in place; other
  outputs of the cell are left alone. IPython is optional: without it, or when the display
  fails, the line goes to stderr instead.
- On an interactive terminal, the line is rewritten in place on stderr.
- Anywhere else (redirected stderr, CI logs), a line is written only when the run's state or
  progress changes, never for elapsed time alone.

Each poll's read feeds the display: it never sends a request of its own. The state shown is
the whole run's; step and task counts are shown only as the server reported them, never as a
percentage. Elapsed time is the time since the wait started. A failure to write the display
never fails the wait.
"""

from __future__ import annotations

import html
import shutil
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from types import TracebackType
    from typing import TextIO

    from qdash.sdk._generated.types.calibration_run_state_response import (
        CalibrationRunStateResponse,
    )
    from qdash.sdk._generated.types.execution_response_detail import ExecutionResponseDetail
    from qdash.sdk._generated.types.pipeline_progress import PipelineProgress

__all__ = ["ProgressState", "WaitProgress", "state_not_found", "state_of_detail", "state_of_run"]

# Step statuses after which the step does nothing more; mirrors the server's pipeline progress.
_ENDED_STEP_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "canceled", "crashed", "skipped", "not_recorded"}
)
# Step statuses of a step that has not started.
_WAITING_STEP_STATUSES = frozenset({"pending"})
# Task statuses the server counts as finished in ``task_finished``.
_FINISHED_TASK_STATUSES = frozenset({"completed", "failed"})
# Whole run statuses whose reason is worth showing next to them.
_QUIET_REASON_STATUSES = frozenset({"running", "completed"})
_PREFIX = "qdash: "


@dataclass(frozen=True)
class ProgressState:
    """What one read said about the whole run: its status and the progress details shown."""

    status: str
    details: tuple[str, ...] = ()


def state_not_found() -> ProgressState:
    """A read that found no run yet; the wait polls again."""
    return ProgressState("not found yet")


def _pipeline_details(pipeline: PipelineProgress) -> list[str]:
    steps = list(pipeline.steps or [])
    if not steps:
        return []
    statuses = [str(step.status).lower() for step in steps]
    ended = sum(1 for status in statuses if status in _ENDED_STEP_STATUSES)
    details = [f"steps {ended}/{len(steps)} ended"]
    active = [
        step
        for step, status in zip(steps, statuses, strict=True)
        if status not in _ENDED_STEP_STATUSES and status not in _WAITING_STEP_STATUSES
    ]
    if active:
        step = active[0]
        text = f"step {step.index} {step.name} {str(step.status).lower()}"
        if step.task_total:
            text += f", tasks {step.task_finished or 0}/{step.task_total} finished"
            if step.task_failed:
                text += f" ({step.task_failed} failed)"
        if len(active) > 1:
            text += f" (+{len(active) - 1} more)"
        details.append(text)
    return details


def state_of_detail(status: str, detail: ExecutionResponseDetail) -> ProgressState:
    """The state an execution read shows; ``status`` is the whole run's, as the wait decides.

    Pipeline progress gives step counts and the running step's task counts. An execution
    without it is the whole run, so its own recorded tasks are counted.
    """
    if detail.pipeline is not None:
        return ProgressState(status, tuple(_pipeline_details(detail.pipeline)))
    tasks = list(detail.task or [])
    if not tasks:
        return ProgressState(status)
    statuses = [str(task.status or "").lower() for task in tasks]
    finished = sum(1 for s in statuses if s in _FINISHED_TASK_STATUSES)
    text = f"tasks {finished}/{len(tasks)} finished"
    failed = statuses.count("failed")
    if failed:
        text += f" ({failed} failed)"
    return ProgressState(status, (text,))


def state_of_run(state: CalibrationRunStateResponse) -> ProgressState:
    """The state a recorded run read shows: the whole flow run's status and its steps."""
    status = str(state.flow_status)
    details: list[str] = []
    if state.flow_status_reason and status not in _QUIET_REASON_STATUSES:
        details.append(state.flow_status_reason)
    if state.pipeline is not None:
        details.extend(_pipeline_details(state.pipeline))
    elif state.executions:
        open_count = sum(
            1
            for summary in state.executions
            if str(summary.status).lower() not in _ENDED_STEP_STATUSES
        )
        text = f"{len(state.executions)} executions"
        if open_count:
            text += f" ({open_count} open)"
        details.append(text)
    return ProgressState(status, tuple(details))


def format_elapsed(seconds: float) -> str:
    """``45s``, ``1m05s`` or ``1h02m03s``."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _line(label: str, state: ProgressState | None, outcome: str | None, elapsed: float) -> str:
    parts: list[str] = []
    if state is not None:
        parts.append(state.status)
        parts.extend(state.details)
    if outcome is not None:
        parts.append(outcome)
    parts.append(f"elapsed {format_elapsed(elapsed)}")
    return f"{label}: " + " | ".join(parts)


class _Renderer(Protocol):
    def show(self, line: str, key: object, *, final: bool) -> None: ...


class _LineRenderer:
    """Redirected stderr: one line per change of ``key``, never for elapsed time alone."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._last: object = None

    def show(self, line: str, key: object, *, final: bool) -> None:
        if key == self._last:
            return
        self._last = key
        self._stream.write(_PREFIX + line + "\n")
        self._stream.flush()


class _TerminalRenderer:
    """Interactive stderr: the line is rewritten in place, and ended with a newline.

    The live line is cut to the terminal's width so that a carriage return can rewrite it;
    the final line is written whole, so the outcome is never cut off.
    """

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def show(self, line: str, key: object, *, final: bool) -> None:
        text = _PREFIX + line
        if not final:
            width = shutil.get_terminal_size(fallback=(120, 24)).columns
            if width > 1 and len(text) >= width:
                text = text[: width - 2] + "~"
        self._stream.write("\r" + text + "\x1b[K" + ("\n" if final else ""))
        self._stream.flush()


class _NotebookRenderer:
    """A Jupyter cell: one display output, created once and then updated in place."""

    def __init__(self, display: Callable[..., Any]) -> None:
        self._display = display
        self._handle: Any = None
        self._last: str | None = None

    def show(self, line: str, key: object, *, final: bool) -> None:
        if line == self._last:
            return
        self._last = line
        bundle = {
            "text/plain": _PREFIX + line,
            "text/html": (
                '<div style="font-family: var(--jp-code-font-family, monospace); '
                f'white-space: pre-wrap">{html.escape(_PREFIX + line)}</div>'
            ),
        }
        if self._handle is None:
            self._handle = self._display(bundle, raw=True, display_id=True)
            if self._handle is None:
                raise RuntimeError("the notebook returned no display handle")
        else:
            self._handle.update(bundle, raw=True)


def _notebook_display() -> Callable[..., Any] | None:
    """IPython's ``display`` when running in a Jupyter kernel, else None."""
    ipython = sys.modules.get("IPython")
    if ipython is None:
        # A kernel always imports IPython first, so an unimported IPython means no notebook.
        return None
    try:
        shell = ipython.get_ipython()
        if shell is None or getattr(shell, "kernel", None) is None:
            return None
        from IPython.display import display
    except Exception:
        return None
    return display


def _isatty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError, ValueError):
        return False


def _renderer() -> _Renderer:
    display = _notebook_display()
    if display is not None:
        return _NotebookRenderer(display)
    stream = sys.stderr
    if _isatty(stream):
        return _TerminalRenderer(stream)
    return _LineRenderer(stream)


class WaitProgress:
    """The progress display of one wait; a context manager that ends it however the wait ends.

    :meth:`update` takes each read's state. Leaving the block shows the final line: the last
    state read and, when the wait raised, why it stopped waiting (the run itself is never
    cancelled by it). A disabled display does nothing at all.
    """

    def __init__(self, label: str, *, enabled: bool, clock: Callable[[], float]) -> None:
        self._label = label
        self._enabled = enabled
        self._clock = clock
        self._renderer: _Renderer | None = None
        self._start = 0.0
        self._state: ProgressState | None = None

    def __enter__(self) -> WaitProgress:
        if self._enabled:
            self._start = self._clock()
            try:
                self._renderer = _renderer()
            except Exception:
                self._renderer = None
        return self

    def update(self, state: ProgressState) -> None:
        """Show what a read said about the run."""
        self._state = state
        self._show(None, final=False)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        outcome: str | None = None
        if exc_type is not None:
            if issubclass(exc_type, TimeoutError):
                outcome = "stopped waiting: timed out (the run was not cancelled)"
            elif issubclass(exc_type, KeyboardInterrupt):
                outcome = "stopped waiting: interrupted (the run was not cancelled)"
            else:
                outcome = f"stopped waiting: {exc_type.__name__}"
        self._show(outcome, final=True)
        self._renderer = None

    def _show(self, outcome: str | None, *, final: bool) -> None:
        renderer = self._renderer
        if renderer is None:
            return
        line = _line(self._label, self._state, outcome, self._clock() - self._start)
        key: Sequence[object] = (self._state, outcome)
        try:
            renderer.show(line, key, final=final)
        except Exception:
            # The display must never fail the wait; a broken notebook display falls back to
            # stderr lines, and a broken stream ends the display.
            if isinstance(renderer, _NotebookRenderer):
                self._renderer = _LineRenderer(sys.stderr)
                self._show(outcome, final=final)
            else:
                self._renderer = None
