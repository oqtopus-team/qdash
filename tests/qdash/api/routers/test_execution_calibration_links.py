"""The calibration session and reported origin the Execution list and detail show.

Membership comes only from QDash's records: a pipeline run recorded in the session (by
project, chip, and flow run) or an action of an agent session admitted to it. The origin is
what a pipeline's caller reported and is never shown as an agent link.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_session import CalibrationAdmission
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import CalibrationPipelineRunDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.pipeline_launch import PipelineLaunchDocument
from tests.qdash.api._legacy_records import make_standalone_agent_session
from tests.qdash.api.routers.test_calibration_pipeline import good_spec
from tests.qdash.api.routers.test_calibration_sessions import (
    CHIP,
    OTHER_CHIP,
    POLICY,
    _agent_action,
    _create_session,
    _headers,
    _release_locks,
    _step_execution,
    lab,  # noqa: F401 - the pytest fixture every test here uses
    prefect,
)

AGENT_TOOL = {"source": "agent_tool", "tool": "qdash_run_pipeline", "client": "pi-qdash"}


def _execute(
    test_client,
    *,
    session_id: str | None = None,
    key: str | None = None,
    origin: dict[str, Any] | None = None,
):
    body: dict[str, Any] = {"chip_id": CHIP, "spec": good_spec()}
    if session_id is not None:
        body["calibration_session_id"] = session_id
        body["idempotency_key"] = key or "run-1"
    if origin is not None:
        body["reported_origin"] = origin
    return test_client.post("/calibration-pipelines/execute", headers=_headers(), json=body)


def _plain_execution(
    execution_id: str,
    *,
    flow_run_id: str | None = None,
    chip_id: str = CHIP,
    project_id: str = "lab-a",
    minutes_ago: int = 0,
) -> None:
    """An ordinary execution, as a saved flow or a manual run records it."""
    ExecutionHistoryDocument(
        project_id=project_id,
        username="owner",
        name="manual-flow",
        execution_id=execution_id,
        calib_data_path="/tmp",
        note={"flow_run_id": flow_run_id} if flow_run_id else {},
        status="completed",
        tags=[],
        chip_id=chip_id,
        start_at=now() - timedelta(minutes=minutes_ago),
        message="",
        system_info=SystemInfoModel(),
    ).insert()


def _list(test_client, *, project_id: str = "lab-a", chip_id: str = CHIP) -> dict[str, Any]:
    response = test_client.get(
        "/executions", headers=_headers(project_id=project_id), params={"chip_id": chip_id}
    )
    assert response.status_code == 200, response.text
    return {row["execution_id"]: row for row in response.json()["executions"]}


def _groups(test_client) -> list[dict[str, Any]]:
    response = test_client.get("/executions/groups", headers=_headers(), params={"chip_id": CHIP})
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


def _detail(test_client, execution_id: str, project_id: str = "lab-a") -> dict[str, Any]:
    response = test_client.get(
        f"/executions/{execution_id}", headers=_headers(project_id=project_id)
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.mark.usefixtures("lab")
class TestOrdinaryExecutions:
    def test_a_manual_execution_shows_no_session_origin_or_agent(self, test_client):
        _plain_execution("manual-1", flow_run_id="flow-manual")
        _plain_execution("manual-2", minutes_ago=5)
        rows = _list(test_client)
        assert list(rows) == ["manual-1", "manual-2"]
        for row in rows.values():
            assert row["calibration_session"] is None
            assert row["reported_origin"] is None
            assert row["agent_session"] is None
        detail = _detail(test_client, "manual-1")
        assert detail["calibration_session"] is None
        assert detail["reported_origin"] is None
        assert detail["agent_session"] is None
        [item] = [i for i in _groups(test_client) if i["execution"]["execution_id"] == "manual-1"]
        assert item["kind"] == "execution"
        assert item["execution"]["calibration_session"] is None

    def test_a_pipeline_without_session_belongs_to_its_automatic_session(self, test_client):
        with prefect(["flow-plain"]):
            response = _execute(test_client)
        assert response.status_code == 202, response.text
        automatic = response.json()["calibration_session_id"]
        assert automatic.startswith("cs-auto-")
        _step_execution(response.json()["execution_id"], "flow-plain", 1, "completed")
        row = _list(test_client)[response.json()["execution_id"]]
        assert row["calibration_session"]["calibration_session_id"] == automatic
        assert row["calibration_session"]["pipeline_run_id"] == response.json()["pipeline_run_id"]
        # Grouping reports no origin: nothing was reported.
        assert row["reported_origin"] is None
        assert PipelineLaunchDocument.find_all().count() == 0


@pytest.mark.usefixtures("lab")
class TestPipelineMembership:
    def test_every_step_of_a_session_pipeline_links_back_and_stays_manual(self, test_client):
        session_id = _create_session(test_client)
        with prefect(["flow-a"]):
            response = _execute(test_client, session_id=session_id)
        assert response.status_code == 202, response.text
        run_id = response.json()["pipeline_run_id"]
        first = response.json()["execution_id"]
        _step_execution(first, "flow-a", 1, "completed")
        _step_execution("step-3", "flow-a", 3, "running")

        rows = _list(test_client)
        for execution_id in (first, "step-3"):
            link = rows[execution_id]["calibration_session"]
            assert link == {
                "calibration_session_id": session_id,
                "chip_id": CHIP,
                "objective": "Bring up qubits 0 and 1",
                "status": "open",
                "via": "pipeline_run",
                "pipeline_run_id": run_id,
                "agent_session_id": None,
            }
            # Membership is no claim about who ran it.
            assert rows[execution_id]["agent_session"] is None
            assert rows[execution_id]["reported_origin"] is None
            assert _detail(test_client, execution_id)["calibration_session"] == link

        # The grouped list holds every step inside the calibration session's row, not as rows.
        items = _groups(test_client)
        assert [i for i in items if i["kind"] == "execution"] == []
        [row] = items
        assert row["kind"] == "calibration_session"
        assert row["calibration_session"]["calibration_session_id"] == session_id
        [run] = row["pipeline_runs"]
        assert run["run_id"] == run_id
        steps = {e["execution_id"]: e for e in run["executions"]}
        assert set(steps) == {first, "step-3"}
        assert steps["step-3"]["calibration_session"]["pipeline_run_id"] == run_id

    def test_other_chip_project_or_flow_run_is_not_a_member(self, test_client):
        session_id = _create_session(test_client)
        with prefect(["flow-a"]):
            assert _execute(test_client, session_id=session_id).status_code == 202
        _step_execution("same-flow-other-chip", "flow-a", 1, "completed", chip_id=OTHER_CHIP)
        _step_execution("same-flow-other-project", "flow-a", 1, "completed", project_id="lab-b")
        _plain_execution("other-flow", flow_run_id="flow-b")
        assert (
            _list(test_client, chip_id=OTHER_CHIP)["same-flow-other-chip"]["calibration_session"]
            is None
        )
        assert (
            _list(test_client, project_id="lab-b")["same-flow-other-project"]["calibration_session"]
            is None
        )
        assert _list(test_client)["other-flow"]["calibration_session"] is None

    def test_two_runs_claiming_one_flow_run_relate_nothing(self, test_client):
        first = _create_session(test_client)
        second = _create_session(test_client)
        with prefect(["flow-a"]):
            assert _execute(test_client, session_id=first).status_code == 202
        [run] = CalibrationPipelineRunDocument.find_all().run()
        clash = run.model_copy(
            update={
                "id": None,
                "run_id": "cpr-clash",
                "calibration_session_id": second,
                "idempotency_scope": "key:clash",
            }
        )
        clash.insert()
        _step_execution("step-1", "flow-a", 1, "completed")
        assert _list(test_client)["step-1"]["calibration_session"] is None
        assert _detail(test_client, "step-1")["calibration_session"] is None


@pytest.mark.usefixtures("lab")
class TestReportedOrigin:
    def test_agent_tool_pipeline_is_reported_not_verified(self, test_client):
        with prefect(["flow-tool"]):
            response = _execute(test_client, origin=AGENT_TOOL)
        assert response.status_code == 202, response.text
        execution_id = response.json()["execution_id"]
        _step_execution(execution_id, "flow-tool", 1, "completed")
        _step_execution("step-3", "flow-tool", 3, "running")
        [launch] = PipelineLaunchDocument.find_all().run()
        assert launch.requested_by == "owner"
        assert launch.flow_run_id == "flow-tool"

        rows = _list(test_client)
        for row_id in (execution_id, "step-3"):
            assert rows[row_id]["reported_origin"] == AGENT_TOOL
            # A report is not an agent session link, and the user stays the recorded one.
            assert rows[row_id]["agent_session"] is None
            assert rows[row_id]["username"] == "owner"
            # The run's automatic session holds it; the report changes nothing about that.
            assert (
                rows[row_id]["calibration_session"]["calibration_session_id"]
                == response.json()["calibration_session_id"]
            )
        assert _detail(test_client, "step-3")["reported_origin"] == AGENT_TOOL

    def test_agent_tool_pipeline_in_a_session_keeps_both(self, test_client):
        session_id = _create_session(test_client)
        with prefect(["flow-tool"]):
            response = _execute(test_client, session_id=session_id, origin=AGENT_TOOL)
        assert response.status_code == 202, response.text
        _step_execution(response.json()["execution_id"], "flow-tool", 1, "completed")
        row = _list(test_client)[response.json()["execution_id"]]
        assert row["reported_origin"] == AGENT_TOOL
        assert row["calibration_session"]["calibration_session_id"] == session_id
        [run] = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()[
            "pipeline_runs"
        ]
        assert run["reported_origin"] == AGENT_TOOL

    def test_a_manual_session_run_reports_no_origin(self, test_client):
        session_id = _create_session(test_client)
        with prefect(["flow-manual"]):
            assert _execute(test_client, session_id=session_id).status_code == 202
        [run] = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()[
            "pipeline_runs"
        ]
        assert run["reported_origin"] is None

    def test_an_origin_outside_the_schema_is_refused(self, test_client):
        with prefect() as create:
            for origin in (
                {"source": "agent_session", "tool": "x"},
                {**AGENT_TOOL, "verified": True},
                {**AGENT_TOOL, "tool": "bad tool"},
            ):
                assert _execute(test_client, origin=origin).status_code == 422
        create.assert_not_awaited()


@pytest.mark.usefixtures("lab")
class TestAgentSessionMembership:
    def _agent(self, test_client, session_id: str) -> str:
        created = test_client.post(
            "/agent-sessions",
            headers=_headers(),
            json={"chip_id": CHIP, "policy": POLICY, "calibration_session_id": session_id},
        )
        assert created.status_code == 201, created.text
        return str(created.json()["session_id"])

    def _measured(self, agent_id: str, execution_id: str = "agent-exec") -> None:
        _plain_execution(execution_id, flow_run_id=f"flow-{execution_id}")
        _agent_action(
            agent_id, "completed", operation_id=f"flow-{execution_id}", execution_id=execution_id
        )

    def test_an_admitted_agent_measurement_links_to_its_session(self, test_client):
        session_id = _create_session(test_client)
        agent_id = self._agent(test_client, session_id)
        agent = AgentSessionDocument.find_one({"session_id": agent_id}).run()
        assert agent is not None and agent.calibration_admission == CalibrationAdmission.ADMITTED
        self._measured(agent_id)

        row = _list(test_client)["agent-exec"]
        assert row["agent_session"]["linked"] is True
        assert row["calibration_session"]["via"] == "agent_session"
        assert row["calibration_session"]["agent_session_id"] == agent_id
        assert row["calibration_session"]["pipeline_run_id"] is None
        assert (
            _detail(test_client, "agent-exec")["calibration_session"] == row["calibration_session"]
        )

        # The admitted agent session is nested in its calibration session's row.
        items = _groups(test_client)
        assert [i for i in items if i["kind"] == "agent_session"] == []
        [parent] = [i for i in items if i["kind"] == "calibration_session"]
        [group] = parent["nested_agent_sessions"]
        assert group["agent_session"]["calibration_session"]["calibration_session_id"] == (
            session_id
        )
        [child] = group["children"]
        assert child["execution"]["calibration_session"] == row["calibration_session"]
        assert parent["calibration_session"]["counts"]["agent_sessions"] == 1
        assert parent["calibration_session"]["counts"]["executions"] == 1

        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()
        [listed] = detail["agent_sessions"]
        assert [e["execution_id"] for e in listed["executions"]] == ["agent-exec"]

    def test_an_unadmitted_or_standalone_agent_relates_nothing(self, test_client):
        session_id = _create_session(test_client)
        agent_id = self._agent(test_client, session_id)
        AgentSessionDocument.get_motor_collection().update_one(
            {"session_id": agent_id},
            {"$set": {"calibration_admission": CalibrationAdmission.PENDING.value}},
        )
        self._measured(agent_id)
        row = _list(test_client)["agent-exec"]
        assert row["agent_session"]["linked"] is True
        assert row["calibration_session"] is None
        [group] = [i for i in _groups(test_client) if i["kind"] == "agent_session"]
        assert group["agent_session"]["calibration_session"] is None

        _release_locks()
        alone = test_client.post(
            "/agent-sessions", headers=_headers(), json={"chip_id": CHIP, "policy": POLICY}
        )
        assert alone.status_code == 201, alone.text
        # A standalone session recorded before automatic sessions existed relates nothing.
        make_standalone_agent_session("lab-a", alone.json()["session_id"])
        self._measured(alone.json()["session_id"], "alone-exec")
        assert _list(test_client)["alone-exec"]["calibration_session"] is None

    def test_an_agent_session_created_alone_relates_its_automatic_session(self, test_client):
        alone = test_client.post(
            "/agent-sessions", headers=_headers(), json={"chip_id": CHIP, "policy": POLICY}
        )
        assert alone.status_code == 201, alone.text
        automatic = alone.json()["calibration_session_id"]
        self._measured(alone.json()["session_id"], "alone-exec")
        row = _list(test_client)["alone-exec"]
        assert row["calibration_session"]["calibration_session_id"] == automatic
        assert row["calibration_session"]["via"] == "agent_session"

    def test_a_tag_alone_relates_nothing(self, test_client):
        session_id = _create_session(test_client)
        ExecutionHistoryDocument(
            project_id="lab-a",
            username="owner",
            name="manual-flow",
            execution_id="tagged",
            calib_data_path="/tmp",
            note={},
            status="completed",
            tags=[f"calibration-session:{session_id}", "agent-session:nope"],
            chip_id=CHIP,
            start_at=now(),
            message="",
            system_info=SystemInfoModel(),
        ).insert()
        row = _list(test_client)["tagged"]
        assert row["calibration_session"] is None
        assert row["agent_session"] is None


@pytest.mark.usefixtures("lab")
class TestSessionList:
    def test_pages_newest_first(self, test_client):
        created = [_create_session(test_client) for _ in range(3)]
        first = test_client.get(
            "/calibration-sessions", headers=_headers(), params={"limit": 2}
        ).json()
        assert [i["calibration_session_id"] for i in first["items"]] == created[::-1][:2]
        assert first["has_more"] is True
        second = test_client.get(
            "/calibration-sessions", headers=_headers(), params={"limit": 2, "skip": 2}
        ).json()
        assert [i["calibration_session_id"] for i in second["items"]] == [created[0]]
        assert second["has_more"] is False
        assert second["skip"] == 2
