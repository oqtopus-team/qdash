"""Internal session management helpers for strategy.py and scheduled.py.

These functions manage the global CalibService session via session_context.
They are internal API and should not be used directly by external code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService
    from qdash.workflow.service.github import GitHubPushConfig

from qdash.workflow.service.session_context import (
    clear_current_session,
    get_current_session,
    set_current_session,
)


def init_calibration(
    username: str,
    chip_id: str,
    qids: list[str],
    execution_id: str | None = None,
    backend_name: str = "qubex",
    flow_name: str | None = None,
    tags: list[str] | None = None,
    use_lock: bool = True,
    note: dict[str, Any] | None = None,
    enable_github_pull: bool = True,
    github_push_config: GitHubPushConfig | None = None,
    muxes: list[int] | None = None,
    project_id: str | None = None,
) -> CalibService:
    """Initialize a session and set it in global context (internal use)."""
    from qdash.workflow.service.calib_service import CalibService

    session = CalibService(
        username=username,
        chip_id=chip_id,
        qids=qids,
        execution_id=execution_id,
        backend_name=backend_name,
        flow_name=flow_name,
        tags=tags,
        use_lock=use_lock,
        note=note,
        enable_github_pull=enable_github_pull,
        github_push_config=github_push_config,
        muxes=muxes,
        project_id=project_id,
    )
    set_current_session(session)
    return session


def get_session() -> CalibService:
    """Get the current session from global context (internal use)."""
    from qdash.workflow.service.calib_service import CalibService

    session = get_current_session()
    if session is None:
        msg = "No active calibration session."
        raise RuntimeError(msg)
    assert isinstance(session, CalibService), "Session must be a CalibService instance"
    return session


def finish_calibration(
    update_chip_history: bool = True,
    push_to_github: bool | None = None,
    export_note_to_file: bool = False,
) -> dict[str, Any] | None:
    """Finish the current session and clear from global context (internal use)."""
    session = get_session()
    result = session.finish_calibration(
        update_chip_history=update_chip_history,
        push_to_github=push_to_github,
        export_note_to_file=export_note_to_file,
    )
    clear_current_session()
    return result
