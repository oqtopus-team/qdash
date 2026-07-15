"""Tests for agent session API schemas."""

import math

import pytest
from pydantic import ValidationError

from qdash.api.schemas.agent_session import (
    ApplyAgentCandidateRequest,
    SubmitAgentActionRequest,
)
from qdash.datamodel.agent_session import AgentActionType, NumericBounds


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_submit_agent_action_rejects_non_finite_overrides(value: float) -> None:
    with pytest.raises(ValidationError):
        SubmitAgentActionRequest(
            idempotency_key="action-1",
            expected_state_version=0,
            action_type=AgentActionType.RUN_TASK,
            task_name="CheckRabi",
            qids=["Q00"],
            parameter_overrides={"drive_amplitude": value},
        )


def test_apply_agent_candidate_defaults_github_push_to_false() -> None:
    request = ApplyAgentCandidateRequest(
        idempotency_key="apply-1",
        expected_state_version=0,
    )

    assert request.push_to_github is False
    assert request.model_copy(update={"push_to_github": True}).push_to_github is True


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_numeric_bounds_rejects_non_finite_values(value: float) -> None:
    assert NumericBounds(minimum=0.0, maximum=1.0).contains(value) is False
