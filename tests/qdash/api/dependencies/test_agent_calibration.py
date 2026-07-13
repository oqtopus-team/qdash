"""Tests for the agent calibration deployment gate."""

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import HTTPException, Request, status

from qdash.api.dependencies.agent_calibration import require_agent_calibration_enabled
from qdash.config import Settings


def _request(*, enabled: bool) -> Request:
    settings = Settings.model_construct(enable_agent_calibration=enabled)
    return cast(
        "Request",
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))),
    )


def test_agent_calibration_gate_rejects_disabled_deployment() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_agent_calibration_enabled(_request(enabled=False))

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_agent_calibration_gate_allows_enabled_deployment() -> None:
    require_agent_calibration_enabled(_request(enabled=True))
