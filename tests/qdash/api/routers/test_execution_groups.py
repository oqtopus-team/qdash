"""Router tests for the grouped Execution list and the agent session graph."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import AgentActionDocument, AgentSessionDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument
from tests.qdash.api._legacy_records import make_standalone_agent_session

START = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)


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


def _execution(execution_id: str, start: datetime, **fields: object) -> None:
    ExecutionHistoryDocument(
        project_id=fields.get("project_id", "lab-a"),
        username="owner",
        name=str(fields.get("name", "manual")),
        execution_id=execution_id,
        calib_data_path="",
        note=fields.get("note", {}),
        status=str(fields.get("status", "completed")),
        tags=fields.get("tags", []),
        chip_id="chip-001",
        start_at=start,
        end_at=start + timedelta(seconds=5),
        message="",
        system_info=SystemInfoModel(),
    ).insert()


def _setup(test_client) -> tuple[str, str]:
    owner = _user("owner", "owner-token")
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
    _member("lab-a", viewer, ProjectRole.VIEWER)
    _member("lab-b", outsider, ProjectRole.OWNER)
    created = test_client.post(
        "/agent-sessions",
        headers=_headers("owner-token"),
        json={
            "chip_id": "chip-001",
            "policy": {"qids": ["Q00"], "allowed_tasks": ["CheckRabi"]},
        },
    )
    assert created.status_code == 201, created.text
    session_id: str = created.json()["session_id"]
    # A standalone agent session, as recorded before automatic calibration sessions.
    make_standalone_agent_session("lab-a", session_id)
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session_id}, {"$set": {"created_at": START - timedelta(hours=1)}}
    )
    proposed = test_client.post(
        f"/agent-sessions/{session_id}/actions",
        headers=_headers("owner-token"),
        json={
            "idempotency_key": "a-1",
            "expected_state_version": 0,
            "action_type": "run_task",
            "task_name": "CheckRabi",
            "qids": ["Q00"],
        },
    )
    assert proposed.status_code == 201, proposed.text
    action_id: str = proposed.json()["action_id"]
    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": action_id},
        {"$set": {"operation_id": "flow-1", "execution_status": "queued"}},
    )
    _execution(
        "agent-exec-1",
        START + timedelta(minutes=1),
        name="agent:CheckRabi",
        note={"flow_run_id": "flow-1"},
        tags=[f"agent-session:{session_id}"],
    )
    _execution("manual-1", START)
    _execution("manual-2", START + timedelta(minutes=2))
    return session_id, action_id


def test_viewer_reads_grouped_list_graph_and_detail_link(test_client) -> None:
    session_id, action_id = _setup(test_client)

    listed = test_client.get(
        "/executions/groups", params={"chip_id": "chip-001"}, headers=_headers("viewer-token")
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    rows = [
        item["execution"]["execution_id"]
        if item["kind"] == "execution"
        else item["agent_session"]["session_id"]
        for item in body["items"]
    ]
    assert rows == ["manual-2", session_id, "manual-1"]
    assert (body["total"], body["total_executions"], body["grouped_executions"]) == (3, 3, 1)
    group = body["items"][1]
    assert group["agent_session"]["status"] == "active"
    assert group["children"][0]["execution"]["execution_id"] == "agent-exec-1"

    # The ungrouped list is unchanged.
    flat = test_client.get(
        "/executions", params={"chip_id": "chip-001"}, headers=_headers("viewer-token")
    )
    assert flat.json()["total"] == 3
    assert len(flat.json()["executions"]) == 3

    graph = test_client.get(
        f"/executions/groups/agent-sessions/{session_id}", headers=_headers("viewer-token")
    )
    assert graph.status_code == 200, graph.text
    nodes = graph.json()["nodes"]
    assert [node["node_id"] for node in nodes] == [f"action:{action_id}"]
    assert nodes[0]["measurement"]["execution_id"] == "agent-exec-1"

    detail = test_client.get("/executions/agent-exec-1", headers=_headers("viewer-token"))
    assert detail.status_code == 200
    assert detail.json()["agent_session"] == {
        "session_id": session_id,
        "linked": True,
        "action_id": action_id,
        "status": "active",
        "created_by": "owner",
        "model_name": "",
    }
    manual = test_client.get("/executions/manual-1", headers=_headers("viewer-token"))
    assert manual.json()["agent_session"] is None


def test_other_projects_cannot_read_groups_or_graphs(test_client) -> None:
    session_id, _ = _setup(test_client)
    path = f"/executions/groups/agent-sessions/{session_id}"
    assert test_client.get(path, headers=_headers("outsider-token", "lab-b")).status_code == 404
    # Without membership the project header alone grants nothing.
    assert test_client.get(path, headers=_headers("outsider-token")).status_code == 403
    other = test_client.get(
        "/executions/groups",
        params={"chip_id": "chip-001"},
        headers=_headers("outsider-token", "lab-b"),
    )
    assert other.status_code == 200
    assert other.json()["items"] == [] and other.json()["total"] == 0
    bad_day = test_client.get(
        "/executions/groups",
        params={"chip_id": "chip-001", "date": "20261120", "timezone": "Nowhere/City"},
        headers=_headers("owner-token"),
    )
    assert bad_day.status_code == 400
