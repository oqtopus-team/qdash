"""Router tests for agent interventions: project boundary and editor-only answers."""

from __future__ import annotations

from typing import Any

import pytest

from qdash.api.dependencies import get_agent_intervention_service, get_agent_session_service
from qdash.api.services.agent_intervention_service import AgentInterventionService
from qdash.api.services.agent_intervention_slack import AgentInterventionSlackNotifier
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.config import get_settings
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


class FakeSlack:
    """Records intervention messages in ``calls`` and session start/end in ``session_calls``."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.session_calls: list[dict[str, Any]] = []

    def chat_postMessage(self, *, channel: str, **kwargs: Any) -> dict[str, str]:
        kwargs["channel"] = channel
        lifecycle = str(kwargs.get("text", "")).startswith("Agent session ")
        if lifecycle:
            self.session_calls.append(kwargs)
            return {"channel": kwargs["channel"], "ts": f"{len(self.session_calls)}.500"}
        self.calls.append(kwargs)
        return {"channel": kwargs["channel"], "ts": f"{len(self.calls)}.000"}


def _user(username: str, token: str) -> UserDocument:
    user = UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=token,
        default_project_id="lab-a",
        system_info=SystemInfoModel(),
    )
    user.insert()
    return user


def _member(project_id: str, user: UserDocument, role: ProjectRole) -> None:
    ProjectMembershipDocument(
        project_id=project_id,
        user_id=user.user_id,
        username=user.username,
        role=role,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="owner",
    ).insert()


def _headers(token: str, project_id: str = "lab-a") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Project-Id": project_id}


@pytest.fixture
def slack(test_client) -> FakeSlack:
    from qdash.api.main import app

    fake = FakeSlack()
    settings = get_settings().model_copy(
        update={
            "slack_bot_token": "xoxb-test",
            "slack_agent_notification": True,
            "slack_agent_channel_id": "C-agent",
        }
    )
    interventions = AgentInterventionService(
        notifier=AgentInterventionSlackNotifier(settings=settings, client=fake)
    )
    app.dependency_overrides[get_agent_intervention_service] = lambda: interventions
    app.dependency_overrides[get_agent_session_service] = lambda: AgentSessionService(
        intervention_service=interventions
    )
    owner = _user("owner", "owner-token")
    viewer = _user("viewer", "viewer-token")
    outsider = _user("outsider", "outsider-token")
    for project_id, name in (("lab-a", "Lab A"), ("lab-b", "Lab B")):
        ProjectDocument(
            project_id=project_id,
            name=name,
            owner_user_id=owner.user_id,
            owner_username="owner",
        ).insert()
        ChipDocument(
            project_id=project_id,
            chip_id="chip-001",
            username="owner",
            size=4,
            system_info=SystemInfoModel(),
        ).insert()
    _member("lab-a", owner, ProjectRole.OWNER)
    _member("lab-a", viewer, ProjectRole.VIEWER)
    _member("lab-b", owner, ProjectRole.OWNER)
    _member("lab-b", outsider, ProjectRole.OWNER)
    yield fake
    app.dependency_overrides.pop(get_agent_intervention_service, None)
    app.dependency_overrides.pop(get_agent_session_service, None)


def _open_intervention(test_client) -> tuple[str, dict[str, Any]]:
    session = test_client.post(
        "/agent-sessions",
        headers=_headers("owner-token"),
        json={
            "chip_id": "chip-001",
            "policy": {
                "qids": ["Q00"],
                "allowed_tasks": ["CheckRabi"],
                "allowed_overrides": {"control_amplitude": {"minimum": 0, "maximum": 1}},
            },
        },
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["session_id"]
    created = test_client.post(
        f"/agent-sessions/{session_id}/interventions",
        headers=_headers("owner-token"),
        json={
            "idempotency_key": "int-1",
            "reason": "unknown_outcome",
            "summary": "CheckRabi reported LOW_CONTRAST",
            "question": "Rerun Rabi or stop?",
            "task_name": "CheckRabi",
            "qids": ["Q00"],
            "checkpoint": {
                "qid": "Q00",
                "nodes": [
                    {
                        "id": "rabi",
                        "task_name": "CheckRabi",
                        "candidate_parameter": "control_amplitude",
                    }
                ],
                "idempotency_prefix": "plan-1",
                "node_path": ["rabi"],
                "visit_counts": {"rabi": 1},
                "stopped_node_id": "rabi",
                "max_node_executions": 3,
            },
        },
    )
    assert created.status_code == 201, created.text
    return session_id, created.json()


def test_viewer_reads_but_only_an_editor_answers(test_client, slack: FakeSlack) -> None:
    session_id, created = _open_intervention(test_client)
    intervention_id = created["intervention_id"]
    path = f"/agent-sessions/{session_id}/interventions/{intervention_id}"

    viewed = test_client.get(path, headers=_headers("viewer-token"))
    assert viewed.status_code == 200
    body = viewed.json()
    assert body["status"] == "open"
    assert body["page_path"] == path
    # The background task ran after the response: the Slack message was sent once.
    assert body["notification"]["status"] == "sent"
    assert len(slack.calls) == 1
    listed = test_client.get(
        f"/agent-sessions/{session_id}/interventions", headers=_headers("viewer-token")
    )
    assert listed.json()["total"] == 1

    answer = {
        "idempotency_key": "r-1",
        "expected_state_version": body["session_state_version"],
        "decision": "resume",
        "guidance": "Fit looks fine; rerun.",
    }
    refused = test_client.post(f"{path}/respond", headers=_headers("viewer-token"), json=answer)
    assert refused.status_code == 403
    retry = test_client.post(f"{path}/notification/retry", headers=_headers("viewer-token"))
    assert retry.status_code == 403

    answered = test_client.post(f"{path}/respond", headers=_headers("owner-token"), json=answer)
    assert answered.status_code == 200, answered.text
    assert answered.json()["status"] == "resume_authorized"
    assert answered.json()["response"]["responded_by"] == "owner"
    # The thread got a reply about the decision.
    assert slack.calls[-1]["thread_ts"] == "1.000"

    claimed = test_client.post(
        f"{path}/claim-resume", headers=_headers("owner-token"), json={"claim_key": "c-1"}
    )
    assert claimed.status_code == 200
    session = test_client.get(f"/agent-sessions/{session_id}", headers=_headers("owner-token"))
    assert session.json()["status"] == "active"


def test_other_projects_cannot_see_or_answer(test_client, slack: FakeSlack) -> None:
    session_id, created = _open_intervention(test_client)
    path = f"/agent-sessions/{session_id}/interventions/{created['intervention_id']}"

    other_project = test_client.get(path, headers=_headers("owner-token", "lab-b"))
    assert other_project.status_code == 404
    not_member = test_client.get(path, headers=_headers("outsider-token", "lab-a"))
    assert not_member.status_code == 403
    answered = test_client.post(
        f"{path}/respond",
        headers=_headers("outsider-token", "lab-b"),
        json={"idempotency_key": "r-1", "expected_state_version": 1, "decision": "stop"},
    )
    assert answered.status_code == 404


def _create_session(test_client, token: str, project_id: str = "lab-a", qid: str = "Q00") -> str:
    created = test_client.post(
        "/agent-sessions",
        headers=_headers(token, project_id),
        json={
            "chip_id": "chip-001",
            "policy": {"qids": [qid], "allowed_tasks": ["CheckRabi"], "autonomy": "auto"},
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["session_id"])


def test_list_sessions_filters_settles_and_keeps_projects_apart(
    test_client, slack: FakeSlack
) -> None:
    from qdash.dbmodel.agent_session import AgentSessionDocument
    from qdash.dbmodel.project_membership import ProjectMembershipDocument

    paused, _ = _open_intervention(test_client)
    # The owner's paused session covers Q00, and an auto session must not bypass that pause.
    refused = test_client.post(
        "/agent-sessions",
        headers=_headers("owner-token"),
        json={
            "chip_id": "chip-001",
            "policy": {"qids": ["Q00"], "allowed_tasks": ["CheckRabi"], "autonomy": "auto"},
        },
    )
    assert refused.status_code == 409, refused.text
    assert "is paused for a person" in refused.json()["detail"]
    active = _create_session(test_client, "owner-token", qid="Q01")
    lapsed = _create_session(test_client, "owner-token", qid="Q01")
    other_project = _create_session(test_client, "owner-token", "lab-b")
    # An editor in the same project creates a session of their own.
    membership = ProjectMembershipDocument.find_one(
        {"project_id": "lab-a", "username": "viewer"}
    ).run()
    assert membership is not None
    membership.set({"role": ProjectRole.EDITOR.value})
    theirs = _create_session(test_client, "viewer-token")
    # Stored as active, but past its expiry: the list settles it the way a read does.
    from datetime import timedelta

    from qdash.common.utils.datetime import now

    lapsed_doc = AgentSessionDocument.find_one({"session_id": lapsed}).run()
    assert lapsed_doc is not None
    lapsed_doc.set({"expires_at": now() - timedelta(seconds=1)})

    def listed(**params: Any) -> list[str]:
        response = test_client.get(
            "/agent-sessions", headers=_headers("owner-token"), params=params
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == len(body["items"])
        return [item["session_id"] for item in body["items"]]

    # Newest first, this project only.
    assert listed() == [theirs, lapsed, active, paused]
    assert other_project not in listed()
    assert listed(mine="true") == [lapsed, active, paused]
    assert listed(mine="true", status=["active", "waiting_for_human"]) == [active, paused]
    assert listed(status="expired") == [lapsed]
    assert listed(chip_id="chip-unknown") == []
    assert listed(limit=1) == [theirs]
    stored = AgentSessionDocument.find_one({"session_id": lapsed}).run()
    assert stored is not None
    assert stored.status.value == "expired"

    outsider = test_client.get("/agent-sessions", headers=_headers("outsider-token", "lab-a"))
    assert outsider.status_code == 403
    bad_status = test_client.get(
        "/agent-sessions", headers=_headers("owner-token"), params={"status": "running"}
    )
    assert bad_status.status_code == 422


def test_session_start_and_stop_are_announced_for_the_owning_project(
    test_client, slack: FakeSlack
) -> None:
    """The start message follows creation; an editor's stop ends it with a cancel message."""
    session_id, created = _open_intervention(test_client)
    assert [call["text"].split(":")[0] for call in slack.session_calls] == ["Agent session started"]
    title = slack.session_calls[0]["attachments"][0]["blocks"][0]["text"]["text"]
    assert f"/agent-sessions/{session_id}?project=lab-a" in title

    # A viewer cannot stop it, so nothing ends and nothing more is announced.
    body = {"idempotency_key": "stop-1", "expected_state_version": 1, "decision": "stop"}
    path = f"/agent-sessions/{session_id}/interventions/{created['intervention_id']}/respond"
    assert test_client.post(path, headers=_headers("viewer-token"), json=body).status_code == 403
    assert len(slack.session_calls) == 1

    state = test_client.get(f"/agent-sessions/{session_id}", headers=_headers("owner-token"))
    body["expected_state_version"] = state.json()["state_version"]
    answered = test_client.post(path, headers=_headers("owner-token"), json=body)
    assert answered.status_code == 200, answered.text
    assert [call["text"].split(":")[0] for call in slack.session_calls] == [
        "Agent session started",
        "Agent session cancelled",
    ]
    session = test_client.get(f"/agent-sessions/{session_id}", headers=_headers("owner-token"))
    assert session.json()["end_notification"]["event"] == "cancelled"
    assert session.json()["end_notification"]["status"] == "sent"
    assert session.json()["start_notification"]["status"] == "sent"


def test_both_ways_of_asking_for_an_expert_open_a_forum_thread_in_the_project(
    test_client, slack: FakeSlack
) -> None:
    session_id, created = _open_intervention(test_client)
    path = f"/agent-sessions/{session_id}/interventions/{created['intervention_id']}"
    # The background task ran after the response.
    viewed = test_client.get(path, headers=_headers("owner-token")).json()
    assert viewed["forum_thread"]["status"] == "created"
    post_id = viewed["forum_thread"]["post_id"]

    other = _create_session(test_client, "owner-token", qid="Q01")
    version = test_client.get(f"/agent-sessions/{other}", headers=_headers("owner-token")).json()[
        "state_version"
    ]
    action = test_client.post(
        f"/agent-sessions/{other}/actions",
        headers=_headers("owner-token"),
        json={
            "idempotency_key": "human-1",
            "expected_state_version": version,
            "action_type": "request_human",
            "diagnosis": "The resonator dip moved; please check the wiring.",
        },
    )
    assert action.status_code == 201, action.text
    requested = test_client.get(
        f"/agent-sessions/{other}/interventions/{action.json()['intervention_id']}",
        headers=_headers("owner-token"),
    ).json()
    assert requested["forum_thread"]["status"] == "created"

    threads = test_client.get(
        "/forum/posts", headers=_headers("owner-token"), params={"label": "agent"}
    ).json()
    assert threads["total"] == 2
    assert post_id in {thread["id"] for thread in threads["posts"]}
    assert {thread["username"] for thread in threads["posts"]} == {"qdash"}
    assert all(
        thread["labels"] == ["agent", "calibration", "question"] for thread in threads["posts"]
    )
    elsewhere = test_client.get("/forum/posts", headers=_headers("owner-token", "lab-b")).json()
    assert elsewhere["total"] == 0
