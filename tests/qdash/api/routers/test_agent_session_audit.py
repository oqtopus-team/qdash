"""Router tests for the agent session audit: project boundary, roles, and export."""

from __future__ import annotations

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


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


def _setup(test_client) -> str:
    owner = _user("owner", "owner-token")
    editor = _user("editor", "editor-token")
    viewer = _user("viewer", "viewer-token")
    outsider = _user("outsider", "outsider-token")
    for project_id in ("lab-a", "lab-b"):
        ProjectDocument(
            project_id=project_id,
            name=project_id,
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
    _member("lab-a", editor, ProjectRole.EDITOR)
    _member("lab-a", viewer, ProjectRole.VIEWER)
    _member("lab-b", outsider, ProjectRole.OWNER)
    created = test_client.post(
        "/agent-sessions",
        headers=_headers("owner-token"),
        json={
            "chip_id": "chip-001",
            "policy": {"qids": ["Q00"], "allowed_tasks": ["CheckRabi"]},
            "model_name": "provider/model",
        },
    )
    assert created.status_code == 201, created.text
    session_id: str = created.json()["session_id"]
    proposed = test_client.post(
        f"/agent-sessions/{session_id}/actions",
        headers=_headers("owner-token"),
        json={
            "idempotency_key": "a-1",
            "expected_state_version": 0,
            "action_type": "run_task",
            "task_name": "CheckRabi",
            "qids": ["Q00"],
            "diagnosis": "Rabi after the frequency commit.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    return session_id


def _decision(action_id: str | None = None) -> dict[str, object]:
    return {
        "idempotency_key": "d-1",
        "assessment": "inconclusive",
        "interpretation": "Not dispatched yet; nothing to judge.",
        "next_action": "stop",
        **({"evidence_action_ids": [action_id]} if action_id else {}),
    }


def test_creator_records_members_read_and_export(test_client) -> None:
    session_id = _setup(test_client)
    base = f"/agent-sessions/{session_id}"

    assert (
        test_client.post(
            f"{base}/decisions", headers=_headers("viewer-token"), json=_decision()
        ).status_code
        == 403
    )
    # An editor who did not create the session does not write in it.
    assert (
        test_client.post(
            f"{base}/decisions", headers=_headers("editor-token"), json=_decision()
        ).status_code
        == 403
    )
    recorded = test_client.post(
        f"{base}/decisions", headers=_headers("owner-token"), json=_decision()
    )
    assert recorded.status_code == 201, recorded.text
    replay = test_client.post(
        f"{base}/decisions", headers=_headers("owner-token"), json=_decision()
    )
    assert replay.json()["decision_id"] == recorded.json()["decision_id"]

    listed = test_client.get(f"{base}/decisions", headers=_headers("viewer-token"))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    page = test_client.get(f"{base}/audit?limit=2", headers=_headers("viewer-token"))
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["schema_version"] == "qdash.agent-session-audit.v1"
    assert body["total_events"] == 3
    assert len(body["events"]) == 2
    assert body["complete"] is False
    rest = test_client.get(
        f"{base}/audit", params={"cursor": body["next_cursor"]}, headers=_headers("viewer-token")
    )
    assert [event["kind"] for event in rest.json()["events"]] == ["decision"]
    assert rest.json()["complete"] is True

    exported = test_client.get(f"{base}/audit/export", headers=_headers("viewer-token"))
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    assert exported.json()["complete"] is True
    assert [event["sequence"] for event in exported.json()["events"]] == [0, 1, 2]
    assert "owner-token" not in exported.text


def test_other_projects_and_outsiders_cannot_read_or_write(test_client) -> None:
    session_id = _setup(test_client)
    base = f"/agent-sessions/{session_id}"

    for path in (f"{base}/audit", f"{base}/audit/export", f"{base}/decisions"):
        response = test_client.get(path, headers=_headers("outsider-token", "lab-b"))
        assert response.status_code == 404, path
        # Without membership the project header alone grants nothing.
        assert test_client.get(path, headers=_headers("outsider-token")).status_code == 403
    written = test_client.post(
        f"{base}/decisions", headers=_headers("outsider-token", "lab-b"), json=_decision()
    )
    assert written.status_code == 404
    assert (
        test_client.get(f"{base}/audit?cursor=garbage", headers=_headers("owner-token")).status_code
        == 400
    )
