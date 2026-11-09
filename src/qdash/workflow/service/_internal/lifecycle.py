"""Execution lifecycle classification and Prefect terminal hooks.

An in-process run classifies how it ended (success, failure, cancellation or an
external termination signal) and closes the Execution it owns accordingly. The
Prefect hooks below close executions from a separate process when the flow
process itself could not, for example after SIGTERM.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator


_CANCELLATION_EXC_NAMES = frozenset({"CancelledRun", "CancelledError"})
_EXTERNAL_TERMINATION_EXC_NAMES = frozenset({"TerminationSignal", "ExternalSignal"})


def _iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    """Yield the exception, its ``__cause__`` chain, and any group members.

    ``__context__`` is deliberately not followed: a genuine failure raised while
    a cancellation is being handled would otherwise be reported as a cancellation.
    """
    seen: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        pending.extend(getattr(current, "exceptions", ()) or ())


def _matches_exception_name(exc: BaseException, names: frozenset[str]) -> bool:
    """Check the exception chain against a set of class names.

    Matching by name avoids a hard import dependency on prefect in non-workflow
    contexts.
    """
    return any(
        cls.__name__ in names
        for member in _iter_exception_chain(exc)
        for cls in type(member).__mro__
    )


def is_cancellation(exc: BaseException) -> bool:
    """Check if an exception represents a cancelled run result.

    Prefect builds ``prefect.exceptions.CancelledRun`` when the result of an
    already cancelled run is retrieved. It is not what a running flow receives
    when the run is cancelled, see :func:`is_external_termination`.
    """
    return _matches_exception_name(exc, _CANCELLATION_EXC_NAMES)


def is_external_termination(exc: BaseException) -> bool:
    """Check if the flow process was interrupted by a signal.

    Prefect installs a SIGTERM handler that raises ``TerminationSignal`` inside
    user code, and it raises the same exception for a runner-driven cancel and
    for a plain SIGTERM. The flow process cannot tell those apart, but the flow
    run's terminal state can, so callers should leave the execution open and let
    ``on_flow_cancellation`` / ``on_flow_crashed`` close it.
    """
    return _matches_exception_name(exc, _EXTERNAL_TERMINATION_EXC_NAMES)


def _run_terminal_hook(
    hook_name: str,
    flow_run: Any,
    status: str,
    message: str,
    *,
    release_lock: bool = True,
) -> None:
    """Close executions belonging to a finished flow run.

    Args:
        hook_name: Name of the calling hook, used as the finalizer's log context.
        flow_run: The Prefect flow run whose parameters identify the project
            and whose id identifies the executions to close.
        status: Terminal status to set on any executions left open.
        message: Message to record on the closed executions.
        release_lock: Whether the finalizer should also release the project's
            execution lock. Must be ``False`` for flows built with
            ``False`` for nested flows that borrow another run's reservation,
            since they never acquired the lock and must not clear one held by
            an unrelated running calibration.

    """
    _logger = logging.getLogger(__name__)
    try:
        params = flow_run.parameters or {}
        project_id = params.get("project_id")
        flow_run_id = str(flow_run.id)

        from qdash.dbmodel.initialize import initialize

        initialize()

        if not project_id:
            # Direct callers may let CalibService resolve the project. Use the
            # recorded execution, not a user's default that may have changed.
            from qdash.dbmodel.execution_history import ExecutionHistoryDocument

            executions = ExecutionHistoryDocument.find({"note.flow_run_id": flow_run_id}).run()
            projects = {execution.project_id for execution in executions if execution.project_id}
            if len(projects) != 1:
                _logger.warning(
                    "%s: cannot identify one project for flow run %s", hook_name, flow_run_id
                )
                return
            project_id = projects.pop()

        from qdash.repository.execution_finalizer import finalize_executions_by_flow_run_id

        finalize_executions_by_flow_run_id(
            project_id=project_id,
            flow_run_id=flow_run_id,
            status=status,
            message=message,
            context=hook_name,
            logger=_logger,
            release_lock=release_lock,
        )
    except Exception:
        _logger.error("%s failed", hook_name, exc_info=True)


def on_flow_cancellation(flow: Any, flow_run: Any, state: Any) -> None:
    """Prefect on_cancellation hook for flow runs.

    Called by Prefect after the flow process is killed (SIGTERM).
    This runs in a *separate* process, so it cannot access in-memory state.
    Instead, it reads the flow_run parameters and updates MongoDB directly.

    Usage::

        @flow(
            on_cancellation=[on_flow_cancellation],
            on_failure=[on_flow_failure],
            on_crashed=[on_flow_crashed],
        )
        def my_flow(username, chip_id, ...):
            ...

    """
    _run_terminal_hook("on_flow_cancellation", flow_run, "cancelled", "Execution was cancelled")


def on_flow_failure(flow: Any, flow_run: Any, state: Any) -> None:
    """Prefect on_failure hook. Closes executions left open by an exception."""
    _run_terminal_hook(
        "on_flow_failure",
        flow_run,
        "failed",
        _terminal_state_message(state, "Flow run failed before the execution was closed"),
    )


def on_flow_crashed(flow: Any, flow_run: Any, state: Any) -> None:
    """Prefect on_crashed hook. Closes executions left open by an infrastructure crash."""
    _run_terminal_hook(
        "on_flow_crashed", flow_run, "failed", "Flow run crashed before the execution was closed"
    )


def _terminal_state_message(state: Any, fallback: str) -> str:
    """Return Prefect's terminal reason without exposing an unbounded payload."""
    message = getattr(state, "message", None)
    if not isinstance(message, str) or not message.strip():
        return fallback
    return message.strip()[:2000]


def on_flow_cancellation_keep_lock(flow: Any, flow_run: Any, state: Any) -> None:
    """Prefect on_cancellation hook for flows that do not acquire the project execution lock.

    Behaves like ``on_flow_cancellation`` but never releases the project
    execution lock, for nested flows that borrow another run's reservation
    and never acquired the lock in the first place.
    """
    _run_terminal_hook(
        "on_flow_cancellation_keep_lock",
        flow_run,
        "cancelled",
        "Execution was cancelled",
        release_lock=False,
    )


def on_flow_failure_keep_lock(flow: Any, flow_run: Any, state: Any) -> None:
    """Prefect on_failure hook for flows that do not acquire the project execution lock.

    Behaves like ``on_flow_failure`` but never releases the project
    execution lock, for nested flows that borrow another run's reservation
    and never acquired the lock in the first place.
    """
    _run_terminal_hook(
        "on_flow_failure_keep_lock",
        flow_run,
        "failed",
        _terminal_state_message(state, "Flow run failed before the execution was closed"),
        release_lock=False,
    )


def on_flow_crashed_keep_lock(flow: Any, flow_run: Any, state: Any) -> None:
    """Prefect on_crashed hook for flows that do not acquire the project execution lock.

    Behaves like ``on_flow_crashed`` but never releases the project
    execution lock, for nested flows that borrow another run's reservation
    and never acquired the lock in the first place.
    """
    _run_terminal_hook(
        "on_flow_crashed_keep_lock",
        flow_run,
        "failed",
        "Flow run crashed before the execution was closed",
        release_lock=False,
    )


__all__ = [
    "is_cancellation",
    "is_external_termination",
    "on_flow_cancellation",
    "on_flow_cancellation_keep_lock",
    "on_flow_crashed",
    "on_flow_crashed_keep_lock",
    "on_flow_failure",
    "on_flow_failure_keep_lock",
]
