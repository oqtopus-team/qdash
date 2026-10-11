"""Tests for calibration evaluation runs: selection, execution, records, verdicts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from qdash.api.dependencies import get_evaluation_service
from qdash.api.main import app
from qdash.api.services.evaluation_service import EvaluationService
from qdash.api.services.pi_chat_service import QDashAuth
from qdash.api.services.pi_evaluation_service import EvaluationRuntimeError
from qdash.datamodel.note import NoteModel
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.dbmodel.user import UserDocument
from qdash.repository.chip import MongoChipRepository
from qdash.repository.task_result_history import MongoTaskResultHistoryRepository

HEADERS = {"Authorization": "Bearer eval_token", "X-Project-Id": "eval_project"}
AUTH = QDashAuth(access_token="eval_token", project_id="eval_project")

RECORD: dict[str, Any] = {
    "task_id": "task-q0-new",
    "task_name": "CheckRabi",
    "target": {"kind": "qubit", "id": "0", "chip_id": "chip-1"},
    "context": "Task: CheckRabi\nTarget: Q00",
    "figures": [{"sha256": "ab" * 32, "mime_type": "image/png", "bytes": 33088}],
    "knowledge": {"chars": 1534, "sha256": "cd" * 32},
    "evaluation": {
        "model": "vllm/nvidia/Ising-Calibration",
        "fallback": False,
        "prompt": "Reference for this experiment ...\nExperiment context:\nTask: CheckRabi",
        "diagnosis": {"fit_quality": "good", "success": True},
        "raw": None,
        "duration_ms": 31000,
        "usage": {"input": 1145, "output": 337},
    },
    "evaluator": {
        "name": "@orangekame3/pi-qcaleval",
        "version": "0.0.1",
        "source": "checkout",
        "commit": "042e454323b2",
    },
}


@pytest.fixture
def project(init_db) -> None:
    user = UserDocument(
        username="eval_user",
        hashed_password="hashed",
        access_token="eval_token",
        default_project_id="eval_project",
        system_info=SystemInfoModel(),
    )
    user.insert()
    ProjectDocument(
        project_id="eval_project",
        name="Eval Project",
        owner_user_id=user.user_id,
        owner_username="eval_user",
    ).insert()
    ProjectMembershipDocument(
        project_id="eval_project",
        user_id=user.user_id,
        username="eval_user",
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="eval_user",
    ).insert()
    ChipDocument(
        project_id="eval_project",
        username="eval_user",
        chip_id="chip-1",
        size=64,
        system_info=SystemInfoModel(),
    ).insert()
    for qid in ("0", "1", "2"):
        QubitDocument(
            project_id="eval_project",
            username="eval_user",
            chip_id="chip-1",
            qid=qid,
            data={},
            system_info=SystemInfoModel(),
        ).insert()


def _task_result(
    *,
    task_id: str,
    qid: str,
    end_at: datetime,
    figure: bool = True,
    status: str = "completed",
) -> None:
    TaskResultHistoryDocument(
        project_id="eval_project",
        username="eval_user",
        task_id=task_id,
        name="CheckRabi",
        upstream_id="",
        status=status,
        message="",
        input_parameters={},
        output_parameters={},
        output_parameter_names=[],
        note={},
        user_note=NoteModel(),
        figure_path=["/figures/x.png"] if figure else [],
        json_figure_path=[],
        raw_data_path=[],
        start_at=end_at,
        end_at=end_at,
        elapsed_time=1.0,
        task_type="qubit",
        system_info=SystemInfoModel(),
        qid=qid,
        execution_id="exec-1",
        tags=[],
        chip_id="chip-1",
    ).insert()


@pytest.fixture
def service(project):
    """The app's evaluation service, with the runtime replaced and launches recorded."""
    calls: list[tuple[str, str | None]] = []
    modes: list[tuple[Any, Any]] = []

    async def evaluate(
        task_id: str, *, auth: QDashAuth, question: str | None = None, **kwargs: Any
    ):
        calls.append((task_id, question))
        modes.append((kwargs.get("mode"), kwargs.get("model")))
        if task_id == "task-q1":
            raise EvaluationRuntimeError("evaluation", "qcal_evaluate: HTTP 400 Non-base64")
        return {**RECORD, "task_id": task_id}

    svc = EvaluationService(
        MongoChipRepository(), MongoTaskResultHistoryRepository(), concurrency=2, evaluate=evaluate
    )
    launched: list[str] = []
    svc.launch = lambda run_id, auth: launched.append(run_id)  # type: ignore[method-assign]
    svc.calls = calls  # type: ignore[attr-defined]
    svc.modes = modes  # type: ignore[attr-defined]
    svc.launched = launched  # type: ignore[attr-defined]
    app.dependency_overrides[get_evaluation_service] = lambda: svc
    yield svc
    app.dependency_overrides.pop(get_evaluation_service, None)


def test_run_queues_the_latest_evaluable_result_per_qubit(test_client, service):
    _task_result(task_id="task-q0-old", qid="0", end_at=datetime(2026, 1, 1, tzinfo=UTC))
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    _task_result(task_id="task-q1", qid="1", end_at=datetime(2026, 1, 2, tzinfo=UTC), figure=False)

    response = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={"chip_id": "chip-1", "task": "CheckRabi", "question": "Is the fit trustworthy?"},
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["task_ids"] == ["task-q0-new"]
    assert body["skipped"] == {"1": "no figure", "2": "no result"}
    run = body["run"]
    assert run["status"] == "running"
    assert run["total"] == 1
    assert run["pending_count"] == 1
    assert run["question"] == "Is the fit trustworthy?"
    assert (run["trigger"], run["mode"], run["planner_model"]) == ("bulk", "direct", None)
    assert run["requested_by"] == "eval_user"
    assert service.launched == [run["run_id"]]

    listed = test_client.get("/evaluations/runs", headers=HEADERS, params={"chip_id": "chip-1"})
    assert [item["run_id"] for item in listed.json()["runs"]] == [run["run_id"]]

    detail = test_client.get(f"/evaluations/runs/{run['run_id']}", headers=HEADERS).json()
    assert [item["qid"] for item in detail["evaluations"]] == ["0"]
    assert detail["evaluations"][0]["status"] == "pending"
    assert detail["evaluations"][0]["task_id"] == "task-q0-new"
    assert detail["evaluations"][0]["figure_path"] == ["/figures/x.png"]


def test_execution_records_what_the_model_saw_and_answered(test_client, service):
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    _task_result(task_id="task-q1", qid="1", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    run_id = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={"chip_id": "chip-1", "task": "CheckRabi", "question": "Why?"},
    ).json()["run"]["run_id"]

    asyncio.run(service.execute_run(run_id, AUTH))

    assert sorted(service.calls) == [("task-q0-new", "Why?"), ("task-q1", "Why?")]
    detail = test_client.get(f"/evaluations/runs/{run_id}", headers=HEADERS).json()
    run = detail["run"]
    assert run["status"] == "completed"
    assert run["completed_at"] is not None
    assert (run["completed_count"], run["failed_count"], run["pending_count"]) == (1, 1, 0)
    assert (run["parsed_count"], run["success_count"]) == (1, 1)
    assert run["model"] == "vllm/nvidia/Ising-Calibration"
    assert run["evaluator"]["commit"] == "042e454323b2"

    by_qid = {item["qid"]: item for item in detail["evaluations"]}
    good = by_qid["0"]
    assert good["status"] == "completed"
    assert good["input"]["context"] == "Task: CheckRabi\nTarget: Q00"
    assert good["input"]["prompt"].startswith("Reference for this experiment")
    assert good["input"]["question"] == "Why?"
    assert good["input"]["knowledge_chars"] == 1534
    assert good["input"]["figures"][0]["bytes"] == 33088
    assert good["output"]["diagnosis"] == {"fit_quality": "good", "success": True}
    assert good["output"]["parsed"] is True
    assert good["output"]["duration_ms"] == 31000
    assert good["evaluator"]["source"] == "checkout"

    failed = by_qid["1"]
    assert failed["status"] == "failed"
    assert failed["error"] == "evaluation: qcal_evaluate: HTTP 400 Non-base64"
    assert failed["output"] is None

    for_task = test_client.get(
        "/evaluations", headers=HEADERS, params={"task_id": "task-q0-new"}
    ).json()
    assert [item["run_id"] for item in for_task["evaluations"]] == [run_id]


def test_a_prose_answer_is_kept_raw_and_counted_as_unparsed(test_client, service):
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    prose = {
        **RECORD,
        "evaluation": {
            **RECORD["evaluation"],
            "diagnosis": None,
            "raw": "The oscillation decays as expected.",
        },
    }

    async def evaluate(task_id: str, **_: Any):
        return prose

    service._evaluate = evaluate
    run_id = test_client.post(
        "/evaluations/runs", headers=HEADERS, json={"chip_id": "chip-1", "task": "CheckRabi"}
    ).json()["run"]["run_id"]

    asyncio.run(service.execute_run(run_id, AUTH))

    detail = test_client.get(f"/evaluations/runs/{run_id}", headers=HEADERS).json()
    assert (detail["run"]["completed_count"], detail["run"]["parsed_count"]) == (1, 0)
    output = detail["evaluations"][0]["output"]
    assert output["parsed"] is False
    assert output["diagnosis"] is None
    assert output["raw"] == "The oscillation decays as expected."


def test_verdicts_are_recorded_counted_and_cleared(test_client, service):
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    run_id = test_client.post(
        "/evaluations/runs", headers=HEADERS, json={"chip_id": "chip-1", "task": "CheckRabi"}
    ).json()["run"]["run_id"]
    asyncio.run(service.execute_run(run_id, AUTH))
    evaluation_id = test_client.get(f"/evaluations/runs/{run_id}", headers=HEADERS).json()[
        "evaluations"
    ][0]["evaluation_id"]

    judged = test_client.put(
        f"/evaluations/{evaluation_id}/verdict",
        headers=HEADERS,
        json={"agree": False, "note": "The fit ignores the last period."},
    )
    assert judged.status_code == 200, judged.text
    verdict = judged.json()["verdict"]
    assert verdict["agree"] is False
    assert verdict["note"] == "The fit ignores the last period."
    assert verdict["username"] == "eval_user"

    run = test_client.get(f"/evaluations/runs/{run_id}", headers=HEADERS).json()["run"]
    assert (run["agree_count"], run["disagree_count"]) == (0, 1)

    cleared = test_client.put(
        f"/evaluations/{evaluation_id}/verdict", headers=HEADERS, json={"agree": None}
    )
    assert cleared.json()["verdict"] is None

    missing = test_client.put(
        "/evaluations/ev_missing/verdict", headers=HEADERS, json={"agree": True}
    )
    assert missing.status_code == 404


def test_requests_without_evaluable_results_are_rejected(test_client, service):
    _task_result(task_id="task-q0", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC), figure=False)

    nothing = test_client.post(
        "/evaluations/runs", headers=HEADERS, json={"chip_id": "chip-1", "task": "CheckRabi"}
    )
    assert nothing.status_code == 400
    assert "no figure" in nothing.json()["detail"]
    assert service.launched == []

    unknown_chip = test_client.post(
        "/evaluations/runs", headers=HEADERS, json={"chip_id": "chip-9", "task": "CheckRabi"}
    )
    assert unknown_chip.status_code == 404

    bad_entity = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={"chip_id": "chip-1", "task": "CheckRabi", "entity_type": "mux"},
    )
    assert bad_entity.status_code == 400

    assert test_client.get("/evaluations/runs/evr_missing", headers=HEADERS).status_code == 404


def test_task_ids_restrict_the_run_and_running_results_are_skipped(test_client, service):
    _task_result(task_id="task-q0", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    _task_result(task_id="task-q1", qid="1", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    _task_result(
        task_id="task-q2", qid="2", end_at=datetime(2026, 1, 2, tzinfo=UTC), status="running"
    )

    unrestricted = test_client.post(
        "/evaluations/runs", headers=HEADERS, json={"chip_id": "chip-1", "task": "CheckRabi"}
    )
    assert unrestricted.status_code == 202, unrestricted.text
    assert unrestricted.json()["task_ids"] == ["task-q0", "task-q1"]
    assert unrestricted.json()["skipped"] == {"2": "status running"}

    restricted = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={"chip_id": "chip-1", "task": "CheckRabi", "task_ids": ["task-q1"]},
    )
    assert restricted.status_code == 202, restricted.text
    assert restricted.json()["task_ids"] == ["task-q1"]
    # Entities outside the requested task results are out of scope, not skipped,
    # including those with no result at all.
    assert restricted.json()["skipped"] == {}


def test_a_single_planner_run_records_the_planner_turn(test_client, service):
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    _task_result(task_id="task-q1", qid="1", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    with_planner = {
        **RECORD,
        "mode": "planner",
        "planner": {
            "model": "openai-compatible/qwen",
            "answer": "fit_quality good, success true; I agree.",
            "tool_calls": ["qdash_build_qcal_evidence", "qcal_evaluate"],
            "duration_ms": 45000,
        },
    }

    async def evaluate(task_id: str, **kwargs: Any):
        service.modes.append((kwargs.get("mode"), kwargs.get("model")))
        return with_planner

    service._evaluate = evaluate
    created = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={
            "chip_id": "chip-1",
            "task": "CheckRabi",
            "task_ids": ["task-q0-new"],
            "trigger": "single",
            "mode": "planner",
        },
    )
    assert created.status_code == 202, created.text
    run = created.json()["run"]
    assert (run["trigger"], run["mode"]) == ("single", "planner")
    assert run["planner_model"] and "/" in run["planner_model"]
    assert created.json()["task_ids"] == ["task-q0-new"]

    asyncio.run(service.execute_run(run["run_id"], AUTH))

    mode, model = service.modes[-1]
    assert mode == "planner"
    assert set(model) == {"provider", "name"}
    detail = test_client.get(f"/evaluations/runs/{run['run_id']}", headers=HEADERS).json()
    planner = detail["evaluations"][0]["planner"]
    assert planner["model"] == "openai-compatible/qwen"
    assert planner["tool_calls"] == ["qdash_build_qcal_evidence", "qcal_evaluate"]
    assert planner["answer"].startswith("fit_quality good")

    bad = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={"chip_id": "chip-1", "task": "CheckRabi", "mode": "autopilot"},
    )
    assert bad.status_code == 422


def test_chat_evaluations_are_filed_as_runs_of_one(test_client, service):
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    recorder = service.chat_recorder(
        project_id="eval_project",
        username="eval_user",
        session_id="s1",
        planner_model="openai-compatible/qwen",
    )

    ids = recorder.record({**RECORD, "task_id": "task-q0-new", "mode": "planner"})
    assert ids is not None
    assert recorder.record({**RECORD, "task_id": "task-unknown"}) is None
    assert recorder.record({**RECORD, "task_id": ""}) is None
    recorder.finish("fit_quality good; I agree.")

    # In a chat about a task result, a judgement of its opening figures is filed under it.
    scoped = service.chat_recorder(
        project_id="eval_project",
        username="eval_user",
        session_id="s2",
        planner_model="openai-compatible/qwen",
        task_id="task-q0-new",
    )
    scoped_ids = scoped.record({**RECORD, "task_id": ""})
    assert scoped_ids is not None
    assert scoped.record({**RECORD, "task_id": "task-unknown"}) is None

    detail = test_client.get(f"/evaluations/runs/{ids['run_id']}", headers=HEADERS).json()
    run = detail["run"]
    assert (run["trigger"], run["mode"], run["status"], run["total"]) == (
        "chat",
        "planner",
        "completed",
        1,
    )
    assert run["planner_model"] == "openai-compatible/qwen"
    assert run["model"] == "vllm/nvidia/Ising-Calibration"
    item = detail["evaluations"][0]
    assert item["evaluation_id"] == ids["evaluation_id"]
    assert item["qid"] == "0"
    assert item["status"] == "completed"
    assert item["input"]["prompt"].startswith("Reference for this experiment")
    assert item["output"]["diagnosis"] == {"fit_quality": "good", "success": True}
    assert item["planner"]["answer"] == "fit_quality good; I agree."
    assert item["figure_path"] == ["/figures/x.png"]

    for_task = test_client.get(
        "/evaluations", headers=HEADERS, params={"task_id": "task-q0-new"}
    ).json()
    assert sorted(e["run_id"] for e in for_task["evaluations"]) == sorted(
        [ids["run_id"], scoped_ids["run_id"]]
    )
