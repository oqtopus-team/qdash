"""Tests for calibration evaluation runs: selection, execution, records, verdicts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from qdash.api.dependencies import get_evaluation_service, get_knowledge_draft_store
from qdash.api.main import app
from qdash.api.services.evaluation_service import EvaluationService
from qdash.api.services.knowledge_draft_service import KnowledgeDraftStore
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
from tests.qdash.api._knowledge_drafts import GENERATOR, RABI, make_zip

HEADERS = {"Authorization": "Bearer eval_token", "X-Project-Id": "eval_project"}
AUTH = QDashAuth(access_token="eval_token", project_id="eval_project")

# One answer per QCalEval question, as pi-qcaleval parses them, plus the derived success.
DIAGNOSIS: dict[str, Any] = {
    "technical_description": {
        "plot_type": "scatter",
        "x_axis": {"label": "Pulse duration (ns)", "scale": "linear", "range": [0, 200]},
        "y_axis": {"label": "Signal", "scale": "linear", "range": [-1, 1]},
        "main_features": "A damped cosine.",
    },
    "experimental_conclusion": {"classification": "expected", "reason": "Clear oscillation."},
    "experimental_significance": "The drive amplitude is right.",
    "fit_reliability": {"assessment": "reliable", "reason": "The fit tracks the data."},
    "parameter_extraction": {"rabi_frequency": 12.5},
    "calibration_diagnosis": {"status": "SUCCESS", "suggested_range": None, "notes": "Good."},
    "success": True,
}
ANSWERS: dict[str, str] = {
    "technical_description": '{"plot_type": "scatter"}',
    "experimental_conclusion": "Classification: Expected behavior\nReason: Clear oscillation.",
    "experimental_significance": "The drive amplitude is right.",
    "fit_reliability": "Assessment: Reliable\nReason: The fit tracks the data.",
    "parameter_extraction": '{"rabi_frequency": 12.5}',
    "calibration_diagnosis": "Status: SUCCESS\nSuggested range: N/A\nNotes: Good.",
}

RECORD: dict[str, Any] = {
    "task_id": "task-q0-new",
    "task_name": "CheckRabi",
    "target": {"kind": "qubit", "id": "0", "chip_id": "chip-1"},
    "context": "Task: CheckRabi\nTarget: Q00",
    "figures": [{"sha256": "ab" * 32, "mime_type": "image/png", "bytes": 33088}],
    "knowledge": {"chars": 1534, "sha256": "cd" * 32},
    "examples": [
        {
            "id": "short-t1",
            "title": "Short T1",
            "outcome": "suboptimal",
            "status": "SHORT_T1",
            "figures": [
                {
                    "sha256": "ef" * 32,
                    "mime_type": "image/png",
                    "bytes": 2048,
                    "path": "examples/figures/t1.png",
                }
            ],
        }
    ],
    "evaluation": {
        "model": "vllm/nvidia/Ising-Calibration",
        "fallback": False,
        "prompt": "Reference for this experiment ...\nExperiment context:\nTask: CheckRabi",
        "system_prompt": "You evaluate superconducting qubit calibration experiment plots.",
        "diagnosis": DIAGNOSIS,
        "raw": None,
        "answers": ANSWERS,
        "questions": list(ANSWERS),
        "attempts": 6,
        "stop_reason": "stop",
        "calls": [
            {
                "question": question,
                "duration_ms": 5000,
                "stop_reason": "stop",
                "input_tokens": 190,
                "output_tokens": 60,
            }
            for question in ANSWERS
        ],
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
        json={"chip_id": "chip-1", "task": "CheckRabi"},
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["task_ids"] == ["task-q0-new"]
    assert body["skipped"] == {"1": "no figure", "2": "no result"}
    run = body["run"]
    assert run["status"] == "running"
    assert run["total"] == 1
    assert run["pending_count"] == 1
    assert run["question"] is None
    assert (run["knowledge_draft_id"], run["knowledge_draft_name"]) == (None, None)
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


def test_execution_records_the_judging_models_context_window(test_client, service, monkeypatch):
    from qdash.copilot.config.settings import CopilotConfig, ModelConfig

    config = CopilotConfig(
        evaluation_models=[
            ModelConfig(provider="vllm", name="nvidia/Ising-Calibration", num_ctx=16384)
        ]
    )
    monkeypatch.setattr("qdash.api.services.evaluation_service.load_copilot_config", lambda: config)
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    run_id = test_client.post(
        "/evaluations/runs", headers=HEADERS, json={"chip_id": "chip-1", "task": "CheckRabi"}
    ).json()["run"]["run_id"]

    asyncio.run(service.execute_run(run_id, AUTH))

    detail = test_client.get(f"/evaluations/runs/{run_id}", headers=HEADERS).json()
    assert detail["evaluations"][0]["output"]["context_window"] == 16384


def test_execution_records_what_the_model_saw_and_answered(test_client, service):
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    _task_result(task_id="task-q1", qid="1", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    run_id = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={"chip_id": "chip-1", "task": "CheckRabi"},
    ).json()["run"]["run_id"]

    asyncio.run(service.execute_run(run_id, AUTH))

    assert sorted(service.calls) == [("task-q0-new", None), ("task-q1", None)]
    detail = test_client.get(f"/evaluations/runs/{run_id}", headers=HEADERS).json()
    run = detail["run"]
    assert run["status"] == "completed"
    assert run["completed_at"] is not None
    assert (run["completed_count"], run["failed_count"], run["pending_count"]) == (1, 1, 0)
    assert (run["parsed_count"], run["complete_count"], run["success_count"]) == (1, 1, 1)
    assert run["model"] == "vllm/nvidia/Ising-Calibration"
    assert run["evaluator"]["commit"] == "042e454323b2"

    by_qid = {item["qid"]: item for item in detail["evaluations"]}
    good = by_qid["0"]
    assert good["status"] == "completed"
    assert good["input"]["context"] == "Task: CheckRabi\nTarget: Q00"
    assert good["input"]["prompt"].startswith("Reference for this experiment")
    assert good["input"]["question"] is None
    assert good["input"]["knowledge_chars"] == 1534
    assert good["input"]["figures"][0]["bytes"] == 33088
    assert good["input"]["figures"][0]["path"] is None
    assert good["input"]["system_prompt"].startswith("You evaluate")
    example = good["input"]["examples"][0]
    assert (example["id"], example["outcome"], example["status"]) == (
        "short-t1",
        "suboptimal",
        "SHORT_T1",
    )
    assert example["figures"][0]["path"] == "examples/figures/t1.png"
    assert good["output"]["diagnosis"] == DIAGNOSIS
    assert good["output"]["answers"] == ANSWERS
    assert good["output"]["questions"] == list(ANSWERS)
    assert good["output"]["parsed"] is True
    assert good["output"]["complete"] is True
    assert good["output"]["missing_keys"] == []
    assert (good["output"]["attempts"], good["output"]["structured"]) == (6, None)
    assert good["output"]["stop_reason"] == "stop"
    assert len(good["output"]["calls"]) == 6
    assert good["output"]["calls"][3] == {
        "question": "fit_reliability",
        "duration_ms": 5000,
        "stop_reason": "stop",
        "structured": False,
        "input_tokens": 190,
        "output_tokens": 60,
        "missing_keys": [],
    }
    # The run's timing: its own wall time, and the completed evaluations' model time added up.
    assert run["elapsed_ms"] >= 0
    assert run["duration_ms_total"] == 31000
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
    assert detail["run"]["complete_count"] == 0
    output = detail["evaluations"][0]["output"]
    assert output["parsed"] is False
    assert output["complete"] is False
    assert output["missing_keys"] == []
    assert output["diagnosis"] is None
    assert output["raw"] == "The oscillation decays as expected."


def test_a_partial_json_answer_is_parsed_but_counted_as_incomplete(test_client, service):
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    # Of the six questions only the first was answered: the rest errored or ran
    # past the output budget, so the evaluator reports them missing.
    text = '{"plot_type": "scatter"}'
    partial = {
        **RECORD,
        "evaluation": {
            **RECORD["evaluation"],
            "diagnosis": {"technical_description": {"plot_type": "scatter"}, "success": None},
            "raw": text,
            "answers": {"technical_description": text, "experimental_significance": ""},
            "questions": [],
            "missing_keys": [key for key in DIAGNOSIS if key != "technical_description"],
            "attempts": 2,
            "structured": False,
            "calls": [
                {
                    "question": "technical_description",
                    "duration_ms": 195000,
                    "stop_reason": "length",
                    "structured": True,
                },
                {
                    "question": "calibration_diagnosis",
                    "duration_ms": 30000,
                    "stop_reason": "stop",
                    "structured": False,
                    "missing_keys": ["calibration_diagnosis"],
                },
                {"bogus": True},
            ],
        },
    }

    async def evaluate(task_id: str, **_: Any):
        return partial

    service._evaluate = evaluate
    run_id = test_client.post(
        "/evaluations/runs", headers=HEADERS, json={"chip_id": "chip-1", "task": "CheckRabi"}
    ).json()["run"]["run_id"]

    asyncio.run(service.execute_run(run_id, AUTH))

    detail = test_client.get(f"/evaluations/runs/{run_id}", headers=HEADERS).json()
    run = detail["run"]
    assert (run["parsed_count"], run["complete_count"], run["success_count"]) == (1, 0, 0)
    output = detail["evaluations"][0]["output"]
    assert output["parsed"] is True
    assert output["complete"] is False
    assert output["missing_keys"] == [
        "experimental_conclusion",
        "experimental_significance",
        "fit_reliability",
        "parameter_extraction",
        "calibration_diagnosis",
    ]
    assert output["raw"] == text
    # Empty answers are dropped; the question list is empty, so all six count.
    assert output["answers"] == {"technical_description": text}
    assert output["questions"] == []
    assert (output["attempts"], output["structured"]) == (2, False)
    assert [
        (call["question"], call["duration_ms"], call["stop_reason"]) for call in output["calls"]
    ] == [
        ("technical_description", 195000, "length"),
        ("calibration_diagnosis", 30000, "stop"),
    ]
    assert output["calls"][1]["missing_keys"] == ["calibration_diagnosis"]


def test_completeness_follows_the_questions_asked(test_client, service):
    """A subset of questions answered in full is complete; the derived success stays."""
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    subset = {
        **RECORD,
        "evaluation": {
            **RECORD["evaluation"],
            "diagnosis": {
                "calibration_diagnosis": DIAGNOSIS["calibration_diagnosis"],
                "success": True,
            },
            "answers": {"calibration_diagnosis": ANSWERS["calibration_diagnosis"]},
            "questions": ["calibration_diagnosis"],
            "attempts": 1,
            "calls": [
                {"question": "calibration_diagnosis", "duration_ms": 4000, "stop_reason": "stop"}
            ],
        },
    }

    async def evaluate(task_id: str, **_: Any):
        return subset

    service._evaluate = evaluate
    run_id = test_client.post(
        "/evaluations/runs", headers=HEADERS, json={"chip_id": "chip-1", "task": "CheckRabi"}
    ).json()["run"]["run_id"]

    asyncio.run(service.execute_run(run_id, AUTH))

    detail = test_client.get(f"/evaluations/runs/{run_id}", headers=HEADERS).json()
    assert (detail["run"]["complete_count"], detail["run"]["success_count"]) == (1, 1)
    output = detail["evaluations"][0]["output"]
    assert output["complete"] is True
    assert output["missing_keys"] == []
    assert output["questions"] == ["calibration_diagnosis"]


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

    # The chip page narrows a run to chosen entities; a chosen one whose result
    # cannot be evaluated is still reported as skipped.
    by_qid = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={"chip_id": "chip-1", "task": "CheckRabi", "qids": ["0", "2"]},
    )
    assert by_qid.status_code == 202, by_qid.text
    assert by_qid.json()["task_ids"] == ["task-q0"]
    assert by_qid.json()["skipped"] == {"2": "status running"}


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
    assert item["output"]["diagnosis"] == DIAGNOSIS
    assert item["planner"]["answer"] == "fit_quality good; I agree."
    assert item["figure_path"] == ["/figures/x.png"]

    for_task = test_client.get(
        "/evaluations", headers=HEADERS, params={"task_id": "task-q0-new"}
    ).json()
    assert sorted(e["run_id"] for e in for_task["evaluations"]) == sorted(
        [ids["run_id"], scoped_ids["run_id"]]
    )


@pytest.mark.parametrize("mode", ["direct", "planner"])
@pytest.mark.parametrize("with_examples", [False, True])
def test_example_setting_reaches_runtime_and_records_are_persisted(
    test_client, service, mode: str, with_examples: bool
):
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    examples = (
        [
            {
                "id": "short-rabi",
                "title": "Short Rabi decay",
                "outcome": "suboptimal",
                "status": "RAPID_DECAY",
                "figures": [
                    {
                        "sha256": "ef" * 32,
                        "mime_type": "image/png",
                        "bytes": 128,
                        "path": "examples/figures/rabi.png",
                    }
                ],
            }
        ]
        if with_examples
        else []
    )
    calls: list[dict[str, Any]] = []

    async def evaluate(task_id: str, **kwargs: Any):
        calls.append(kwargs)
        return {**RECORD, "task_id": task_id, "examples": examples}

    service._evaluate = evaluate
    response = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={
            "chip_id": "chip-1",
            "task": "CheckRabi",
            "mode": mode,
            "with_examples": with_examples,
        },
    )
    assert response.status_code == 202, response.text
    run = response.json()["run"]
    assert run["with_examples"] is with_examples

    asyncio.run(service.execute_run(run["run_id"], AUTH))

    assert len(calls) == 1
    assert calls[0]["with_examples"] is with_examples
    assert calls[0]["mode"] == mode
    detail = test_client.get(f"/evaluations/runs/{run['run_id']}", headers=HEADERS).json()
    assert detail["run"]["with_examples"] is with_examples
    assert detail["evaluations"][0]["status"] == "completed"
    assert detail["evaluations"][0]["input"]["examples"] == examples


@pytest.fixture
def drafts(tmp_path, monkeypatch):
    """A draft store under tmp_path, parsing with a stand-in knowledge generator."""
    repo = tmp_path / "config" / "task-knowledge"
    repo.mkdir(parents=True)
    (repo / "generate.py").write_text(GENERATOR, encoding="utf-8")
    monkeypatch.setattr(
        "qdash.common.config.loader.ConfigLoader.get_config_dir",
        classmethod(lambda cls: tmp_path / "config"),
    )
    store = KnowledgeDraftStore(tmp_path / "calib_data")
    app.dependency_overrides[get_knowledge_draft_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_knowledge_draft_store, None)


def _upload(test_client, files: dict[str, bytes | str], filename: str = "rabi.zip"):
    return test_client.post(
        "/evaluations/knowledge-drafts",
        headers=HEADERS,
        files={"file": (filename, make_zip(files), "application/zip")},
    )


def test_a_knowledge_draft_is_uploaded_and_served_as_task_knowledge(test_client, project, drafts):
    response = _upload(test_client, RABI)

    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["task_name"] == "CheckRabi"
    assert (draft["filename"], draft["uploaded_by"]) == ("rabi.zip", "eval_user")
    assert draft["warnings"] == []
    assert draft["reference"]["statuses"]["SUCCESS"] == "a damped cosine"
    assert (draft["example_count"], draft["figure_count"]) == (1, 1)

    meta = test_client.get(f"/evaluations/knowledge-drafts/{draft['draft_id']}", headers=HEADERS)
    assert meta.json() == draft

    knowledge = test_client.get(
        f"/evaluations/knowledge-drafts/{draft['draft_id']}/knowledge", headers=HEADERS
    ).json()
    assert knowledge["name"] == "CheckRabi"
    assert knowledge["examples"][0]["figures"][0]["mime_type"] == "image/png"
    assert knowledge["examples"][0]["figures"][0]["base64_data"]

    missing = test_client.get(f"/evaluations/knowledge-drafts/{'0' * 64}", headers=HEADERS)
    assert missing.status_code == 404


def test_an_unusable_zip_is_rejected_on_upload(test_client, project, drafts):
    response = _upload(test_client, {"CheckRabi/task.md": "# CheckRabi", "CheckRabi/x.py": "x"})

    assert response.status_code == 400
    assert "files are allowed" in response.json()["detail"]


def test_a_run_against_a_draft_records_it_and_sends_it_to_the_runtime(test_client, service, drafts):
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    draft_id = _upload(test_client, RABI).json()["draft_id"]
    calls: list[dict[str, Any]] = []

    async def evaluate(task_id: str, **kwargs: Any):
        calls.append(kwargs)
        return {**RECORD, "task_id": task_id}

    service._evaluate = evaluate
    response = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={"chip_id": "chip-1", "task": "CheckRabi", "knowledge_draft_id": draft_id},
    )
    assert response.status_code == 202, response.text
    run = response.json()["run"]
    assert (run["knowledge_draft_id"], run["knowledge_draft_name"]) == (draft_id, "rabi.zip")

    asyncio.run(service.execute_run(run["run_id"], AUTH))

    assert [call["knowledge_draft_id"] for call in calls] == [draft_id]
    detail = test_client.get(f"/evaluations/runs/{run['run_id']}", headers=HEADERS).json()
    assert detail["run"]["knowledge_draft_id"] == draft_id
    assert detail["evaluations"][0]["status"] == "completed"


@pytest.mark.parametrize(
    ("body", "status_code", "detail"),
    [
        ({"task": "CheckT1"}, 400, "describes CheckRabi, not CheckT1"),
        ({"task": "CheckRabi", "mode": "planner"}, 400, "direct mode"),
        ({"task": "CheckRabi", "knowledge_draft_id": "f" * 64}, 404, "not found"),
    ],
)
def test_a_draft_must_match_the_task_and_run_directly(
    test_client, service, drafts, body, status_code, detail
):
    _task_result(task_id="task-q0-new", qid="0", end_at=datetime(2026, 1, 2, tzinfo=UTC))
    draft_id = _upload(test_client, RABI).json()["draft_id"]

    response = test_client.post(
        "/evaluations/runs",
        headers=HEADERS,
        json={"chip_id": "chip-1", "knowledge_draft_id": draft_id, **body},
    )

    assert response.status_code == status_code, response.text
    assert detail in response.json()["detail"]
    assert service.launched == []


def test_a_drafts_zip_downloads_as_uploaded(test_client, project, drafts):
    data = make_zip(RABI)
    draft_id = test_client.post(
        "/evaluations/knowledge-drafts",
        headers=HEADERS,
        files={"file": ("rabi v2.zip", data, "application/zip")},
    ).json()["draft_id"]

    response = test_client.get(f"/evaluations/knowledge-drafts/{draft_id}/archive", headers=HEADERS)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == "attachment; filename*=utf-8''rabi%20v2.zip"
    assert response.content == data
    missing = test_client.get(f"/evaluations/knowledge-drafts/{'0' * 64}/archive", headers=HEADERS)
    assert missing.status_code == 404
