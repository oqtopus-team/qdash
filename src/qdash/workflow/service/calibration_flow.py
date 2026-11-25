"""``@calibration_flow``: a Prefect flow with QDash's terminal hooks and a session name.

.. code-block:: python

    from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context


    @calibration_flow(session_name="Coherence Check")
    def coherence_check(username, chip_id, flow_name=None, project_id=None):
        context = resolve_calib_context(username, chip_id, project_id=project_id)
        session = CalibrationSession.from_context(context)
        return session.run(targets=..., steps=[...])

The decorator is ``prefect.flow`` with ``on_cancellation``, ``on_failure`` and ``on_crashed``
set to QDash's hooks, which close the run's Executions and release its reservation; pass any
of them, or any other ``prefect.flow`` option, to replace it. It injects nothing into the
function: the context and the session are built explicitly in its body.

``session_name`` names the calibration session QDash creates for a launch that does not name
one (an automatic session): the API reads the string literal from the saved source before it
creates the session, and the worker reads it from the flow before it records a scheduled or
directly started flow run. A launch into an existing session keeps that session's name, and
a flow without ``session_name`` keeps the default name (``Workflow <flow name>``). The name is
the session's ``objective``; it is not a step or execution name.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, overload

from qdash.workflow.service._internal.lifecycle import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)

__all__ = ["SESSION_NAME_ATTRIBUTE", "calibration_flow", "session_name_of"]

SESSION_NAME_ATTRIBUTE = "qdash_session_name"
"""The attribute of a ``@calibration_flow`` flow that holds its session name."""

SESSION_NAME_MAX_LENGTH = 500

_F = TypeVar("_F", bound=Callable[..., Any])


def _checked(session_name: object) -> str | None:
    if session_name is None:
        return None
    if not isinstance(session_name, str):
        raise TypeError("session_name must be a string literal")
    name = session_name.strip()
    if not name:
        raise ValueError("session_name must not be empty")
    if len(name) > SESSION_NAME_MAX_LENGTH:
        raise ValueError(f"session_name must be at most {SESSION_NAME_MAX_LENGTH} characters")
    return name


def session_name_of(flow: object) -> str | None:
    """The session name a ``@calibration_flow`` declared, or None for any other flow."""
    value = getattr(flow, SESSION_NAME_ATTRIBUTE, None)
    return value if isinstance(value, str) and value else None


@overload
def calibration_flow(fn: _F, /) -> Any: ...


@overload
def calibration_flow(
    fn: None = None, /, *, session_name: str | None = None, **flow_options: Any
) -> Callable[[_F], Any]: ...


def calibration_flow(
    fn: _F | None = None, /, *, session_name: str | None = None, **flow_options: Any
) -> Any:
    """Decorate a workflow entrypoint as a Prefect flow with QDash's terminal hooks.

    Args:
        fn: The function, when used bare as ``@calibration_flow``.
        session_name: Name of the automatic calibration session of a launch that names
            none. Write it as a string literal so the API can read it without running the
            source.
        **flow_options: Any ``prefect.flow`` option; the hooks given here replace QDash's.
    """
    name = _checked(session_name)
    options: dict[str, Any] = {
        "on_cancellation": [on_flow_cancellation],
        "on_failure": [on_flow_failure],
        "on_crashed": [on_flow_crashed],
        **flow_options,
    }

    def decorate(function: _F) -> Any:
        from prefect import flow

        wrapped = flow(**options)(function)
        setattr(wrapped, SESSION_NAME_ATTRIBUTE, name)
        return wrapped

    if fn is not None:
        return decorate(fn)
    return decorate
