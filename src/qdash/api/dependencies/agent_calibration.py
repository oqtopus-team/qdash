"""Runtime gate for the opt-in agent calibration API."""

from fastapi import HTTPException, Request, status

from qdash.config import Settings, get_settings


def require_agent_calibration_enabled(request: Request) -> None:
    """Reject agent calibration requests unless the deployment opted in."""
    settings: Settings | None = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = get_settings()
    if not settings.enable_agent_calibration:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent calibration is not enabled on this QDash deployment",
        )
