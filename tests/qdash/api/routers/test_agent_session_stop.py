"""Router tests for stopping an agent session: editors only, own project, announced, audited."""

from __future__ import annotations

from tests.qdash.api.routers import test_agent_intervention as interventions
from tests.qdash.api.routers.test_agent_intervention import (
    FakeSlack,
    _headers,
    _open_intervention,
)

# The intervention tests' fixture: two projects, their members, and a fake Slack.
slack = interventions.slack


def test_an_editor_stops_a_paused_session_and_it_is_announced_and_audited(
    test_client, slack: FakeSlack
) -> None:
    session_id, created = _open_intervention(test_client)
    path = f"/agent-sessions/{session_id}/stop"
    body = {"idempotency_key": "stop-1", "reason": "The user asked to stop"}

    # A viewer may not stop it, and another project cannot see it.
    assert test_client.post(path, headers=_headers("viewer-token"), json=body).status_code == 403
    assert (
        test_client.post(path, headers=_headers("outsider-token", "lab-b"), json=body).status_code
        == 404
    )
    assert (
        test_client.get(f"/agent-sessions/{session_id}", headers=_headers("owner-token")).json()[
            "status"
        ]
        == "waiting_for_human"
    )

    stopped = test_client.post(path, headers=_headers("owner-token"), json=body)
    assert stopped.status_code == 200, stopped.text
    result = stopped.json()
    assert result["outcome"] == "stopped"
    assert result["session"]["status"] == "cancelled"
    assert result["session"]["stop"]["stopped_by"] == "owner"
    assert result["closed_intervention_ids"] == [created["intervention_id"]]
    assert result["in_flight"] == []

    # The end is announced once, and the expert's thread says who stopped it.
    assert [call["text"].split(":")[0] for call in slack.session_calls] == [
        "Agent session started",
        "Agent session cancelled",
    ]
    assert any("owner stopped the session." in call.get("text", "") for call in slack.calls)
    repeat = test_client.post(path, headers=_headers("owner-token"), json=body)
    assert repeat.json()["outcome"] == "already_stopped"
    assert len(slack.session_calls) == 2

    audit = test_client.get(
        f"/agent-sessions/{session_id}/audit", headers=_headers("viewer-token")
    ).json()
    [event] = [item for item in audit["events"] if item["kind"] == "session_stopped"]
    assert event["actor"] == "owner"
    assert event["data"]["reason"] == "The user asked to stop"
    assert event["data"]["status_before"] == "waiting_for_human"
