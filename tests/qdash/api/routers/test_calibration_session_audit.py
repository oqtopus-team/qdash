"""A calibration session's audit and its projection in the grouped Execution list.

The audit uses the agent session audit's event schema, snapshots, cursors, and decision
recording. Its decisions are the only records it writes; every other event comes from an
existing record (the session, its pipeline runs, their step executions and task results, and
its agent sessions). Nothing is grouped or related by time, name, or tag.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from qdash.common.utils.datetime import now
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import (
    CalibrationDecisionDocument,
    CalibrationPipelineRunDocument,
)
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
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
MODEL = {"provider": "local", "model_id": "qwen"}


def _decide(test_client, session_id: str, key: str, *, user: str = "owner", **fields: Any) -> Any:
    body = {
        "idempotency_key": key,
        "interpretation": fields.pop("interpretation", "Reading of the evidence"),
        "next_action": fields.pop("next_action", "next_task"),
        **fields,
    }
    return test_client.post(
        f"/calibration-sessions/{session_id}/decisions", headers=_headers(user), json=body
    )


def _plan(candidate: str, stage: str, target: str = "0", shots: int = 2048) -> dict[str, Any]:
    return {
        "candidate_id": candidate,
        "stage": stage,
        "target": target,
        "requested_changes": [{"task_name": "CheckT1", "parameter": "shots", "value": shots}],
    }


def _propose(test_client, session_id: str, key: str, plan: dict[str, Any]) -> str:
    response = _decide(test_client, session_id, key, experiment=plan, model=MODEL)
    assert response.status_code == 201, response.text
    return str(response.json()["decision_id"])


def _execute(
    test_client,
    session_id: str,
    key: str,
    flow_run_id: str,
    *,
    decision_id: str | None = None,
    origin: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "chip_id": CHIP,
        "spec": good_spec(),
        "calibration_session_id": session_id,
        "idempotency_key": key,
    }
    if decision_id is not None:
        body["decision_id"] = decision_id
    if origin is not None:
        body["reported_origin"] = origin
    with prefect([flow_run_id]):
        response = test_client.post("/calibration-pipelines/execute", headers=_headers(), json=body)
    assert response.status_code == 202, response.text
    _release_locks()
    return dict(response.json())


def _task(
    task_id: str,
    execution_id: str,
    *,
    name: str = "CheckT1",
    qid: str = "0",
    status: str = "completed",
    chip_id: str = CHIP,
    outputs: dict[str, Any] | None = None,
    run: dict[str, Any] | None = None,
    project_id: str = "lab-a",
) -> None:
    moment = now()
    TaskResultHistoryDocument(
        project_id=project_id,
        username="owner",
        task_id=task_id,
        name=name,
        upstream_id="",
        status=status,
        message="",
        input_parameters={},
        output_parameters=outputs or {},
        output_parameter_names=list(outputs or {}),
        run_parameters=run or {},
        note={},
        figure_path=[],
        json_figure_path=[],
        raw_data_path=[],
        start_at=moment,
        end_at=moment + timedelta(seconds=30),
        elapsed_time=30.0,
        task_type="qubit" if "-" not in qid else "coupling",
        system_info=SystemInfoModel(),
        qid=qid,
        execution_id=execution_id,
        tags=[],
        chip_id=chip_id,
    ).insert()


def _plain_execution(execution_id: str, *, minutes_ago: int = 0, chip_id: str = CHIP) -> None:
    ExecutionHistoryDocument(
        project_id="lab-a",
        username="owner",
        name="manual-flow",
        execution_id=execution_id,
        calib_data_path="/tmp",
        note={},
        status="completed",
        tags=[],
        chip_id=chip_id,
        start_at=now() - timedelta(minutes=minutes_ago),
        message="",
        system_info=SystemInfoModel(),
    ).insert()


def _groups(test_client, **params: Any) -> dict[str, Any]:
    response = test_client.get(
        "/executions/groups", headers=_headers(), params={"chip_id": CHIP, **params}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def _row_executions(item: dict[str, Any]) -> list[str]:
    if item["kind"] == "execution":
        return [item["execution"]["execution_id"]]
    if item["kind"] == "agent_session":
        return [child["execution"]["execution_id"] for child in item["children"]]
    ids = [e["execution_id"] for run in item["pipeline_runs"] for e in run["executions"]]
    for nested in item["nested_agent_sessions"]:
        ids += [child["execution"]["execution_id"] for child in nested["children"]]
    return ids


def _audit(test_client, session_id: str, **params: Any) -> dict[str, Any]:
    response = test_client.get(
        f"/calibration-sessions/{session_id}/audit", headers=_headers(), params=params
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def _detail(test_client, session_id: str) -> dict[str, Any]:
    response = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers())
    assert response.status_code == 200, response.text
    return dict(response.json())


def _agent(test_client, session_id: str | None) -> str:
    body: dict[str, Any] = {"chip_id": CHIP, "policy": POLICY}
    if session_id is not None:
        body["calibration_session_id"] = session_id
    created = test_client.post("/agent-sessions", headers=_headers(), json=body)
    assert created.status_code == 201, created.text
    return str(created.json()["session_id"])


# ---------------------------------------------------------------------- grouped list


@pytest.mark.usefixtures("lab")
class TestGroupedList:
    def test_runs_and_agents_group_under_their_session_before_paging(self, test_client):
        session_id = _create_session(test_client)
        first = _execute(test_client, session_id, "run-a", "flow-a")
        _step_execution(first["execution_id"], "flow-a", 1, "completed")
        _step_execution("a-step3", "flow-a", 3, "failed")
        second = _execute(test_client, session_id, "run-b", "flow-b")
        _step_execution(second["execution_id"], "flow-b", 1, "running")
        nested = _agent(test_client, session_id)
        _plain_execution("agent-exec", minutes_ago=1)
        _agent_action(nested, "completed", execution_id="agent-exec")
        alone = _agent(test_client, None)
        # A standalone agent session, as recorded before automatic calibration sessions.
        make_standalone_agent_session("lab-a", alone)
        _plain_execution("alone-exec", minutes_ago=2)
        AgentSessionDocument.get_motor_collection().update_one(
            {"session_id": alone}, {"$set": {"created_at": now() - timedelta(minutes=3)}}
        )
        from qdash.dbmodel.agent_session import AgentActionDocument

        template = AgentActionDocument.find_one({"session_id": nested}).run()
        assert template is not None
        AgentActionDocument.get_motor_collection().insert_one(
            {
                **template.model_dump(exclude={"id"}),
                "action_id": "action-alone",
                "session_id": alone,
                "execution_id": "alone-exec",
            }
        )
        for index in range(3):
            _plain_execution(f"manual-{index}", minutes_ago=10 + index)

        whole = _groups(test_client)
        kinds = [item["kind"] for item in whole["items"]]
        assert kinds == [
            "calibration_session",
            "agent_session",
            "execution",
            "execution",
            "execution",
        ]
        assert whole["total"] == 5
        assert whole["calibration_sessions"] == 1
        assert whole["agent_sessions"] == 1
        all_ids = [e for item in whole["items"] for e in _row_executions(item)]
        assert len(all_ids) == len(set(all_ids)) == whole["total_executions"]
        assert whole["grouped_executions"] == whole["total_executions"] - 3

        row = whole["items"][0]
        summary = row["calibration_session"]
        assert summary["counts"] == {
            "pipeline_runs": 2,
            "agent_sessions": 1,
            "executions": 4,
            "executions_in_filter": 4,
            "running": 1,
            "failed": 1,
            "unknown_dispatch": 0,
            "decisions": 0,
        }
        assert summary["targets"] == ["0", "1"]
        assert summary["recommendation"] is None
        assert [run["run_id"] for run in row["pipeline_runs"]] == [
            first["pipeline_run_id"],
            second["pipeline_run_id"],
        ]
        assert row["nested_agent_sessions"][0]["agent_session"]["session_id"] == nested

        # Paging one row at a time never splits a session or repeats an execution.
        seen: list[str] = []
        for skip in range(whole["total"]):
            page = _groups(test_client, skip=skip, limit=1)
            assert page["total"] == whole["total"]
            [item] = page["items"]
            seen += _row_executions(item)
        assert sorted(seen) == sorted(all_ids)

    def test_unadmitted_agent_and_ambiguous_runs_stay_outside(self, test_client):
        session_id = _create_session(test_client)
        other = _create_session(test_client)
        pending = _agent(test_client, session_id)
        AgentSessionDocument.get_motor_collection().update_one(
            {"session_id": pending}, {"$set": {"calibration_admission": "pending"}}
        )
        executed = _execute(test_client, session_id, "run-a", "flow-a")
        [run] = CalibrationPipelineRunDocument.find_all().run()
        run.model_copy(
            update={
                "id": None,
                "run_id": "cpr-clash",
                "calibration_session_id": other,
                "idempotency_key": "x",
            }
        ).insert()
        _step_execution(executed["execution_id"], "flow-a", 1, "completed")
        items = _groups(test_client)["items"]
        kinds = sorted(item["kind"] for item in items)
        # Two runs claim one flow run: its execution is an ordinary row. The pending agent
        # session never operated in the calibration session and stays its own row.
        assert kinds == ["agent_session", "calibration_session", "calibration_session", "execution"]
        for item in items:
            if item["kind"] == "calibration_session":
                assert _row_executions(item) == []

    def test_day_filter_and_other_chip(self, test_client):
        session_id = _create_session(test_client)
        _create_session(test_client, chip_id=OTHER_CHIP)
        response = _execute(test_client, session_id, "run-a", "flow-a")
        _step_execution(response["execution_id"], "flow-a", 1, "completed")
        today = now().strftime("%Y%m%d")
        listed = _groups(test_client, date=today)
        [row] = listed["items"]
        assert row["calibration_session"]["counts"]["executions_in_filter"] == 1
        empty = _groups(test_client, date="20000101")
        assert empty["items"] == [] and empty["total"] == 0

    def test_sessions_interleave_with_manual_rows_and_page_without_loss(self, test_client):
        """Two sessions and manual rows order by latest activity; every page size agrees."""
        older = _create_session(test_client)
        newer = _create_session(test_client)
        old_run = _execute(test_client, older, "run-old", "flow-old")
        _step_execution(old_run["execution_id"], "flow-old", 1, "completed")
        new_run = _execute(test_client, newer, "run-new", "flow-new")
        _step_execution(new_run["execution_id"], "flow-new", 1, "completed")
        _step_execution("new-step3", "flow-new", 3, "completed")
        collection = ExecutionHistoryDocument.get_motor_collection()
        moment = now()
        collection.update_one(
            {"execution_id": old_run["execution_id"]},
            {"$set": {"start_at": moment - timedelta(minutes=30)}},
        )
        for execution_id, minutes in ((new_run["execution_id"], 5), ("new-step3", 4)):
            collection.update_one(
                {"execution_id": execution_id},
                {"$set": {"start_at": moment - timedelta(minutes=minutes)}},
            )
        from qdash.dbmodel.calibration_session import CalibrationSessionDocument

        # Creation counts as activity, so both sessions were opened before any execution.
        for session_id, minutes in ((older, 60), (newer, 50)):
            CalibrationSessionDocument.get_motor_collection().update_one(
                {"calibration_session_id": session_id},
                {"$set": {"created_at": moment - timedelta(minutes=minutes)}},
            )
        _plain_execution("m-latest", minutes_ago=1)
        _plain_execution("m-middle", minutes_ago=20)
        _plain_execution("m-oldest", minutes_ago=40)

        whole = _groups(test_client)
        order = [
            item["calibration_session"]["calibration_session_id"]
            if item["kind"] == "calibration_session"
            else item["execution"]["execution_id"]
            for item in whole["items"]
        ]
        assert order == ["m-latest", newer, "m-middle", older, "m-oldest"]
        assert whole["total"] == 5 and whole["calibration_sessions"] == 2
        all_ids = [e for item in whole["items"] for e in _row_executions(item)]
        assert len(all_ids) == len(set(all_ids)) == whole["total_executions"] == 6
        for limit in (1, 2, 3, 5):
            seen_rows: list[str] = []
            seen: list[str] = []
            for skip in range(0, whole["total"], limit):
                page = _groups(test_client, skip=skip, limit=limit)
                assert page["total"] == whole["total"]
                assert page["total_executions"] == whole["total_executions"]
                for item in page["items"]:
                    seen_rows.append(item["kind"])
                    seen += _row_executions(item)
            assert len(seen_rows) == whole["total"]
            assert seen == all_ids
        beyond = _groups(test_client, skip=whole["total"], limit=5)
        assert beyond["items"] == [] and beyond["total"] == whole["total"]

    def test_day_filter_counts_only_that_day_but_lists_every_execution(self, test_client):
        session_id = _create_session(test_client)
        run = _execute(test_client, session_id, "run-a", "flow-a")
        _step_execution(run["execution_id"], "flow-a", 1, "completed")
        _step_execution("step3", "flow-a", 3, "completed")
        three_days_ago = now() - timedelta(days=3)
        from qdash.dbmodel.calibration_session import CalibrationSessionDocument

        CalibrationSessionDocument.get_motor_collection().update_one(
            {"calibration_session_id": session_id}, {"$set": {"created_at": three_days_ago}}
        )
        ExecutionHistoryDocument.get_motor_collection().update_one(
            {"execution_id": run["execution_id"]}, {"$set": {"start_at": three_days_ago}}
        )
        _plain_execution("old-manual", minutes_ago=3 * 24 * 60)
        for day, in_filter, manual in (
            (now().strftime("%Y%m%d"), 1, []),
            (three_days_ago.strftime("%Y%m%d"), 1, ["old-manual"]),
        ):
            listed = _groups(test_client, date=day)
            sessions = [i for i in listed["items"] if i["kind"] == "calibration_session"]
            [row] = sessions
            assert row["calibration_session"]["counts"]["executions"] == 2
            assert row["calibration_session"]["counts"]["executions_in_filter"] == in_filter
            assert sorted(_row_executions(row)) == sorted([run["execution_id"], "step3"])
            plain = [
                i["execution"]["execution_id"] for i in listed["items"] if i["kind"] == "execution"
            ]
            assert plain == manual
        assert _groups(test_client, date="20000101")["total"] == 0
        assert (
            test_client.get(
                "/executions/groups",
                headers=_headers(),
                params={"chip_id": CHIP, "limit": 101},
            ).status_code
            == 422
        )

    def test_manual_rows_and_flat_list_keep_their_shape(self, test_client):
        _plain_execution("manual-1")
        assert [i["kind"] for i in _groups(test_client)["items"]] == ["execution"]
        flat = test_client.get("/executions", headers=_headers(), params={"chip_id": CHIP})
        assert [e["execution_id"] for e in flat.json()["executions"]] == ["manual-1"]


# ---------------------------------------------------------------------- audit


@pytest.mark.usefixtures("lab")
class TestAudit:
    def test_intent_dispatch_measurement_and_conclusion_correlate(self, test_client):
        session_id = _create_session(test_client)
        baseline_task = "baseline-task"
        _plain_execution("old-exec", minutes_ago=60)
        _task(baseline_task, "old-exec", run={"shots": {"value": 1024}})
        baseline = _decide(
            test_client,
            session_id,
            "d-baseline",
            experiment=_plan("incumbent", "baseline", shots=1024),
            evidence_task_ids=[baseline_task],
            model=MODEL,
        )
        assert baseline.status_code == 201, baseline.text
        intent = _propose(test_client, session_id, "d-c1", _plan("c1", "confirmation"))
        run = _execute(
            test_client, session_id, "run-c1", "flow-c1", decision_id=intent, origin=AGENT_TOOL
        )
        _step_execution(run["execution_id"], "flow-c1", 1, "completed")
        _task(
            "t-c1",
            run["execution_id"],
            run={"shots": {"value": 2048}},
            outputs={"t1": {"value": 50.0, "error": 2.0, "unit": "us"}},
        )

        detail = _detail(test_client, session_id)
        rows = {row["candidate_id"]: row for row in detail["experiments"]}
        assert rows["incumbent"]["pipeline_run_id"] is None
        assert rows["incumbent"]["measured"]["evidence_status"] == "complete"
        c1 = rows["c1"]
        assert c1["pipeline_run_id"] == run["pipeline_run_id"]
        assert c1["measured"]["evidence_status"] == "complete"
        assert c1["measured"]["task_seconds"] == 30.0
        [check] = c1["parameter_checks"]
        assert check == {
            "task_name": "CheckT1",
            "call_id": None,
            "parameter": "shots",
            "requested": 2048,
            "in_spec": 2048,
            "executed": 2048,
            "consistent": True,
            "missing": [],
        }
        [carrier] = [d for d in detail["decisions"] if d["decision_id"] == intent]
        assert carrier["carried_out_by_run_ids"] == [run["pipeline_run_id"]]

        # Screening alone cannot back a recommendation; a confirmation run can.
        refused = _decide(
            test_client,
            session_id,
            "d-final-bad",
            next_action="complete",
            evidence_decision_ids=[baseline.json()["decision_id"]],
            conclusion={"outcome": "recommend_candidate", "recommended_candidate_id": "incumbent"},
        )
        assert refused.status_code == 422
        final = _decide(
            test_client,
            session_id,
            "d-final",
            next_action="complete",
            evidence_run_ids=[run["pipeline_run_id"]],
            conclusion={"outcome": "recommend_candidate", "recommended_candidate_id": "c1"},
            model=MODEL,
        )
        assert final.status_code == 201, final.text
        snapshot_run = final.json()["evidence_snapshot"]["pipeline_runs"][0]
        assert snapshot_run["target"] == "0"
        assert snapshot_run["tasks"][0]["executed_run_parameters"]["shots"] == {"value": 2048}

        detail = _detail(test_client, session_id)
        assert detail["recommendation"]["decision_id"] == final.json()["decision_id"]
        latest = detail["latest_requested_run"]
        assert "last_hardware_write" not in detail
        assert latest["execution_outcome"] == "completed"
        assert latest["candidate_id"] == "c1"
        assert latest["candidate_is_recommended"] is True
        # A completed execution is not an authoritative write record; the view says so.
        assert any("hardware" in fact for fact in latest["missing"])

        audit = _audit(test_client, session_id)
        assert audit["schema_version"] == "qdash.calibration-session-audit.v1"
        assert audit["complete"] is True
        kinds = [(e["kind"], e.get("decision_id")) for e in audit["events"]]
        position = {kind: index for index, kind in enumerate(kinds)}
        assert position[("decision", intent)] < position[("pipeline_requested", intent)]
        requested = next(e for e in audit["events"] if e["kind"] == "pipeline_requested")
        assert requested["pipeline_run_id"] == run["pipeline_run_id"]
        assert requested["actor"] == "owner"
        assert requested["actor_kind"] == "agent"
        assert requested["data"]["actor_kind_basis"] == "client_reported_origin"
        # The host's approval never reaches QDash; the audit says so instead of claiming it.
        assert "host_approval" in requested["missing"]
        calls = {c["call_id"]: c for c in requested["data"]["requested_task_calls"]}
        assert calls["t1_short"]["run"] == {"shots": 2048}
        assert calls["t1_long"]["run"] == {"shots": 4096}
        measurement = next(e for e in audit["events"] if e["kind"] == "measurement")
        assert measurement["provenance"] == "server_record"
        assert measurement["decision_id"] == intent
        decisions = [e for e in audit["events"] if e["kind"] == "decision"]
        assert {e["provenance"] for e in decisions} == {"agent_reported"}
        assert [e["sequence"] for e in audit["events"]] == list(range(len(audit["events"])))

        # Grouped row shows the recommendation as a decision, never as a status. The baseline's
        # evidence ran outside the session, so its execution stays an ordinary row.
        row, plain = _groups(test_client)["items"]
        assert plain["kind"] == "execution" and plain["execution"]["execution_id"] == "old-exec"
        assert row["calibration_session"]["recommendation"]["recommended_candidate_id"] == "c1"
        assert row["calibration_session"]["counts"]["decisions"] == 3
        assert row["pipeline_runs"][0]["decision_id"] == intent

    def test_recommendation_differs_from_latest_requested_run_and_unknown_paths(self, test_client):
        session_id = _create_session(test_client)
        incumbent = _propose(test_client, session_id, "d-inc", _plan("incumbent", "baseline"))
        inc_run = _execute(test_client, session_id, "run-inc", "flow-inc", decision_id=incumbent)
        # The response echoes the link so a client detects a server that dropped it.
        assert inc_run["decision_id"] == incumbent
        replay = _execute(test_client, session_id, "run-inc", "flow-unused", decision_id=incumbent)
        assert replay["replayed"] is True and replay["decision_id"] == incumbent
        _step_execution(inc_run["execution_id"], "flow-inc", 1, "completed")
        _task("t-inc", inc_run["execution_id"], run={"shots": {"value": 2048}})
        candidate = _propose(test_client, session_id, "d-c2", _plan("c2", "screening"))
        cand_run = _execute(test_client, session_id, "run-c2", "flow-c2", decision_id=candidate)
        _step_execution(cand_run["execution_id"], "flow-c2", 1, "completed")
        _task("t-c2", cand_run["execution_id"], run={"shots": {"value": 4096}})
        keep = _decide(
            test_client,
            session_id,
            "d-keep",
            next_action="complete",
            evidence_run_ids=[inc_run["pipeline_run_id"], cand_run["pipeline_run_id"]],
            conclusion={"outcome": "keep_baseline", "recommended_candidate_id": "incumbent"},
        )
        assert keep.status_code == 201, keep.text
        detail = _detail(test_client, session_id)
        latest = detail["latest_requested_run"]
        assert latest["candidate_id"] == "c2"
        assert latest["candidate_is_recommended"] is False
        # The requested shots (2048) differ from what the candidate's task executed (4096).
        [c2] = [row for row in detail["experiments"] if row["candidate_id"] == "c2"]
        assert c2["parameter_checks"][0]["consistent"] is False

        # A proposed experiment that no run carries out (declined or never dispatched).
        _propose(test_client, session_id, "d-c3", _plan("c3", "screening"))
        [c3] = [
            row
            for row in _detail(test_client, session_id)["experiments"]
            if row["candidate_id"] == "c3"
        ]
        assert c3["pipeline_run_id"] is None
        assert c3["measured"]["evidence_status"] == "not_run"

        # An agent tool run without a recorded intent, and a running latest run.
        running = _execute(test_client, session_id, "run-x", "flow-x", origin=AGENT_TOOL)
        assert running["decision_id"] is None
        _step_execution(running["execution_id"], "flow-x", 1, "running")
        audit = _audit(test_client, session_id)
        requested = next(
            e
            for e in audit["events"]
            if e["kind"] == "pipeline_requested"
            and e["pipeline_run_id"] == running["pipeline_run_id"]
        )
        assert "decision" in requested["missing"]
        latest = _detail(test_client, session_id)["latest_requested_run"]
        assert latest["pipeline_run_id"] == running["pipeline_run_id"]
        assert latest["execution_outcome"] == "running"
        assert latest["finished_at"] is None
        assert latest["candidate_id"] is None and latest["candidate_is_recommended"] is None

    def test_legacy_run_without_spec_and_refused_dispatch(self, test_client):
        session_id = _create_session(test_client)
        run = _execute(test_client, session_id, "run-a", "flow-a")
        CalibrationPipelineRunDocument.get_motor_collection().update_one(
            {"run_id": run["pipeline_run_id"]}, {"$unset": {"spec": ""}}
        )
        from unittest.mock import AsyncMock, patch

        from qdash.api.services.flow_service.prefect_gateway import SystemDeploymentUnavailable

        with patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.read_deployment_id",
            new=AsyncMock(side_effect=SystemDeploymentUnavailable("missing")),
        ):
            refused = test_client.post(
                "/calibration-pipelines/execute",
                headers=_headers(),
                json={
                    "chip_id": CHIP,
                    "spec": good_spec(),
                    "calibration_session_id": session_id,
                    "idempotency_key": "run-b",
                },
            )
        assert refused.status_code == 503
        audit = _audit(test_client, session_id)
        legacy = next(
            e
            for e in audit["events"]
            if e["kind"] == "pipeline_requested" and e["pipeline_run_id"] == run["pipeline_run_id"]
        )
        assert legacy["missing"] == ["requested_spec"]
        statuses = {
            e["pipeline_run_id"]: e["status"]
            for e in audit["events"]
            if e["kind"] == "pipeline_dispatch"
        }
        assert sorted(statuses.values()) == ["dispatched", "rejected"]
        # The refused request is the latest requested run; it never executed.
        latest = _detail(test_client, session_id)["latest_requested_run"]
        assert latest["dispatch_status"] == "rejected"
        assert latest["execution_outcome"] == "refused"
        assert latest["execution_ids"] == []

    def test_latest_requested_run_follows_request_order_not_completion(self, test_client):
        """A run requested first may finish last; neither order proves the last write."""
        session_id = _create_session(test_client)
        dec_a = _propose(test_client, session_id, "d-a", _plan("ca", "confirmation"))
        run_a = _execute(test_client, session_id, "run-a", "flow-a", decision_id=dec_a)
        dec_b = _propose(test_client, session_id, "d-b", _plan("cb", "screening"))
        run_b = _execute(test_client, session_id, "run-b", "flow-b", decision_id=dec_b)
        _step_execution(run_a["execution_id"], "flow-a", 1, "completed")
        _step_execution(run_b["execution_id"], "flow-b", 1, "completed")
        _task("t-a", run_a["execution_id"], run={"shots": {"value": 2048}})
        _task("t-b", run_b["execution_id"], run={"shots": {"value": 2048}})
        finished = now()
        collection = ExecutionHistoryDocument.get_motor_collection()
        # B (requested second) completed first; A (requested first) completed an hour later.
        collection.update_one(
            {"execution_id": run_b["execution_id"]},
            {"$set": {"end_at": finished - timedelta(hours=1)}},
        )
        collection.update_one(
            {"execution_id": run_a["execution_id"]}, {"$set": {"end_at": finished}}
        )
        recommended = _decide(
            test_client,
            session_id,
            "d-rec",
            next_action="complete",
            evidence_run_ids=[run_a["pipeline_run_id"], run_b["pipeline_run_id"]],
            conclusion={"outcome": "recommend_candidate", "recommended_candidate_id": "ca"},
        )
        assert recommended.status_code == 201, recommended.text
        latest = _detail(test_client, session_id)["latest_requested_run"]
        # The latest *requested* run is B, even though A finished after it.
        assert latest["pipeline_run_id"] == run_b["pipeline_run_id"]
        assert latest["decision_id"] == dec_b
        assert latest["candidate_id"] == "cb"
        # Successful execution, but no authoritative write event exists.
        assert latest["execution_outcome"] == "completed"
        assert any("hardware" in fact for fact in latest["missing"])
        # The comparison is between records (requested candidate vs recommendation) only.
        assert latest["candidate_is_recommended"] is False
        assert set(latest) >= {"requested_at", "dispatch_status", "finished_at"}
        assert not {"state", "matches_recommendation"} & set(latest)

    @pytest.mark.parametrize(
        ("statuses", "outcome"),
        [
            ([], "no_execution"),
            (["failed"], "failed"),
            (["cancelled"], "failed"),
            (["completed", "failed"], "partial"),
            (["completed", "running"], "running"),
        ],
    )
    def test_latest_requested_run_outcomes(self, test_client, statuses, outcome):
        session_id = _create_session(test_client)
        run = _execute(test_client, session_id, "run-o", "flow-o")
        ExecutionHistoryDocument.get_motor_collection().delete_many(
            {"execution_id": run["execution_id"]}
        )
        for index, value in enumerate(statuses, start=1):
            _step_execution(f"{run['execution_id']}-{index}", "flow-o", index, value)
        latest = _detail(test_client, session_id)["latest_requested_run"]
        assert latest["dispatch_status"] == "dispatched"
        assert latest["execution_outcome"] == outcome
        assert len(latest["execution_ids"]) == len(statuses)

    def test_evidence_and_authorization_are_checked(self, test_client):
        session_id = _create_session(test_client)
        other = _create_session(test_client)
        foreign_run = _execute(test_client, other, "run-o", "flow-o")
        assert (
            _decide(
                test_client, session_id, "k1", evidence_run_ids=[foreign_run["pipeline_run_id"]]
            ).status_code
            == 409
        )
        _plain_execution("other-chip-exec", chip_id=OTHER_CHIP)
        _task("t-other-chip", "other-chip-exec", chip_id=OTHER_CHIP)
        assert (
            _decide(test_client, session_id, "k2", evidence_task_ids=["t-other-chip"]).status_code
            == 409
        )
        _task("t-q1", "other-chip-exec", qid="1")
        assert (
            _decide(
                test_client,
                session_id,
                "k3",
                evidence_task_ids=["t-q1"],
                experiment=_plan("c", "baseline", target="0"),
            ).status_code
            == 409
        )
        assert (
            _decide(test_client, session_id, "k4", evidence_decision_ids=["nope"]).status_code
            == 409
        )
        assert _decide(test_client, session_id, "k5", user="colleague").status_code == 403
        assert _decide(test_client, session_id, "k6", user="viewer").status_code == 403
        other_project = test_client.post(
            f"/calibration-sessions/{session_id}/decisions",
            headers=_headers(project_id="lab-b"),
            json={"idempotency_key": "k", "interpretation": "x", "next_action": "next_task"},
        )
        assert other_project.status_code == 404
        # A conclusion needs next_action complete or stop; an experiment a proposing step.
        assert (
            _decide(
                test_client,
                session_id,
                "k7",
                conclusion={"outcome": "inconclusive"},
                evidence_run_ids=[],
            ).status_code
            == 422
        )
        assert (
            _decide(
                test_client,
                session_id,
                "k8",
                next_action="complete",
                experiment=_plan("c", "screening"),
            ).status_code
            == 422
        )
        assert CalibrationDecisionDocument.find_all().count() == 0

        # A run may name only a decision of its own session that proposed an experiment.
        foreign_decision = _propose(test_client, other, "d-o", _plan("c", "screening"))
        with prefect(["flow-z"]) as create:
            response = test_client.post(
                "/calibration-pipelines/execute",
                headers=_headers(),
                json={
                    "chip_id": CHIP,
                    "spec": good_spec(),
                    "calibration_session_id": session_id,
                    "idempotency_key": "run-z",
                    "decision_id": foreign_decision,
                },
            )
        assert response.status_code == 422
        create.assert_not_awaited()
        assert (
            CalibrationPipelineRunDocument.find({"calibration_session_id": session_id}).count() == 0
        )
        out_of_target = _propose(
            test_client, session_id, "d-far", _plan("c", "screening", target="5")
        )
        with prefect(["flow-z"]) as create:
            response = test_client.post(
                "/calibration-pipelines/execute",
                headers=_headers(),
                json={
                    "chip_id": CHIP,
                    "spec": good_spec(),
                    "calibration_session_id": session_id,
                    "idempotency_key": "run-z",
                    "decision_id": out_of_target,
                },
            )
        assert response.status_code == 422
        create.assert_not_awaited()

    def test_recording_is_idempotent_and_allowed_after_close(self, test_client):
        session_id = _create_session(test_client)
        first = _decide(test_client, session_id, "same", model=MODEL)
        again = _decide(test_client, session_id, "same", model={"provider": "x", "model_id": "y"})
        assert again.status_code == 201
        assert again.json()["decision_id"] == first.json()["decision_id"]
        # The model is provenance: the replay keeps the first record's.
        assert again.json()["model"]["model_id"] == MODEL["model_id"]
        assert _decide(test_client, session_id, "same", interpretation="other").status_code == 409

        closed = test_client.post(
            f"/calibration-sessions/{session_id}/close", headers=_headers(), json={}
        )
        assert closed.status_code == 200, closed.text
        after = _decide(test_client, session_id, "after-close", next_action="stop")
        assert after.status_code == 201
        assert after.json()["session_status_at_record"] == "closed"
        audit = _audit(test_client, session_id)
        assert audit["events"][-1]["kind"] in {"session_closed", "decision"}
        assert any(e["kind"] == "session_closed" for e in audit["events"])
        # Closing records no recommendation, and a decision without a model says so.
        assert _detail(test_client, session_id)["recommendation"] is None
        unreported = next(
            e for e in audit["events"] if e["decision_id"] == after.json()["decision_id"]
        )
        assert unreported["provenance"] == "client_reported"
        assert "model" in unreported["missing"]

    def test_pages_export_and_admitted_agent_events(self, test_client):
        session_id = _create_session(test_client)
        agent_id = _agent(test_client, session_id)
        for index in range(4):
            _decide(test_client, session_id, f"note-{index}")
        whole = _audit(test_client, session_id)
        inlined = [e for e in whole["events"] if e["agent_session_id"] == agent_id]
        assert {e["kind"] for e in inlined} >= {"agent_session_linked", "session_created"}
        own = test_client.get(f"/agent-sessions/{agent_id}/audit", headers=_headers()).json()
        # The agent session's own audit is unchanged: no calibration events, no agent id set.
        assert own["schema_version"] == "qdash.agent-session-audit.v1"
        assert all(e["agent_session_id"] is None for e in own["events"])
        assert {e["event_id"] for e in own["events"]} <= {
            e["event_id"].split(f"agent_session:{agent_id}:", 1)[-1] for e in inlined
        }

        first = _audit(test_client, session_id, limit=2)
        assert first["next_cursor"] and not first["complete"]
        second = _audit(test_client, session_id, limit=2, cursor=first["next_cursor"])
        assert second["snapshot_id"] == first["snapshot_id"]
        _decide(test_client, session_id, "late")
        changed = test_client.get(
            f"/calibration-sessions/{session_id}/audit",
            headers=_headers(),
            params={"cursor": second["next_cursor"], "limit": 2},
        )
        assert changed.status_code == 409
        foreign = _create_session(test_client)
        misused = test_client.get(
            f"/calibration-sessions/{foreign}/audit",
            headers=_headers(),
            params={"cursor": first["next_cursor"]},
        )
        assert misused.status_code == 400
        garbage = test_client.get(
            f"/calibration-sessions/{session_id}/audit",
            headers=_headers(),
            params={"cursor": "not-a-cursor"},
        )
        assert garbage.status_code == 400
        for limit in (0, 501):
            bounded = test_client.get(
                f"/calibration-sessions/{session_id}/audit",
                headers=_headers(),
                params={"limit": limit},
            )
            assert bounded.status_code == 422
        export = test_client.get(
            f"/calibration-sessions/{session_id}/audit/export", headers=_headers()
        )
        assert export.status_code == 200
        assert "attachment" in export.headers["content-disposition"]
        assert export.json()["complete"] is True

    def test_walking_every_page_equals_the_export(self, test_client):
        """Cursor pages of one snapshot concatenate to the export: no gap, no repeat."""
        session_id = _create_session(test_client)
        decision = _propose(test_client, session_id, "d-a", _plan("ca", "screening"))
        run = _execute(test_client, session_id, "run-a", "flow-a", decision_id=decision)
        _step_execution(run["execution_id"], "flow-a", 1, "completed")
        _task("t-a", run["execution_id"], run={"shots": {"value": 2048}})
        _agent(test_client, session_id)
        for index in range(3):
            _decide(test_client, session_id, f"note-{index}")
        export = test_client.get(
            f"/calibration-sessions/{session_id}/audit/export", headers=_headers()
        ).json()
        for limit in (1, 2, 7):
            events: list[dict[str, Any]] = []
            page = _audit(test_client, session_id, limit=limit)
            snapshot = page["snapshot_id"]
            events += page["events"]
            while page["next_cursor"]:
                page = _audit(test_client, session_id, limit=limit, cursor=page["next_cursor"])
                assert page["snapshot_id"] == snapshot
                events += page["events"]
            assert page["complete"] is True
            assert [e["event_id"] for e in events] == [e["event_id"] for e in export["events"]]
            assert [e["sequence"] for e in events] == list(range(len(events)))
        assert snapshot == export["snapshot_id"]
