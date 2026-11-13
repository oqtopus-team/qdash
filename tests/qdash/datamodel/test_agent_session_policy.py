"""Agent session policy: the autonomy grant a person approves once."""

from __future__ import annotations

import pytest

from qdash.datamodel.agent_session import AgentAutonomy, AgentSessionPolicy


def _policy(**overrides: object) -> AgentSessionPolicy:
    data: dict[str, object] = {"qids": ["Q00"], "allowed_tasks": ["CheckRabi"]}
    data.update(overrides)
    return AgentSessionPolicy.model_validate(data)


def test_policy_confirms_each_step_unless_auto_is_granted() -> None:
    policy = _policy()
    assert policy.autonomy == AgentAutonomy.CONFIRM_EACH
    assert policy.max_rounds_per_target == 3

    granted = _policy(autonomy="auto", max_rounds_per_target=5)
    assert granted.autonomy == AgentAutonomy.AUTO
    assert granted.max_rounds_per_target == 5


@pytest.mark.parametrize("rounds", [0, 21])
def test_round_budget_is_bounded(rounds: int) -> None:
    with pytest.raises(ValueError):
        _policy(max_rounds_per_target=rounds)


def test_unknown_autonomy_is_rejected() -> None:
    with pytest.raises(ValueError):
        _policy(autonomy="unattended")
