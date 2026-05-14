from __future__ import annotations

import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import patch

from qdash.api.services.task_result_service import TaskResultService
from qdash.common.utils.datetime import end_of_day, parse_date, start_of_day
from qdash.copilot.config import AnalysisConfig, CopilotConfig, ModelConfig
from qdash.datamodel.note import AiTriageReviewModel
from qdash.datamodel.system_info import SystemInfoModel

if TYPE_CHECKING:
    from qdash.repository.protocols import ChipRepository, TaskResultHistoryRepository


class _TaskResultDoc(SimpleNamespace):
    saved: bool = False

    def save(self) -> None:
        self.saved = True


class _ChipRepo:
    def get_qubit_ids(self, project_id: str, chip_id: str) -> list[str]:
        return ["0", "1", "2"]

    def get_coupling_ids(self, project_id: str, chip_id: str) -> list[str]:
        return ["0-1"]

    def get_historical_qubit_ids(self, project_id: str, chip_id: str, date: str) -> list[str]:
        return ["0", "1"]

    def get_historical_coupling_ids(self, project_id: str, chip_id: str, date: str) -> list[str]:
        return ["0-1"]


class _TaskResultRepo:
    def __init__(self, docs: list[_TaskResultDoc]) -> None:
        self.docs = docs
        self.last_query: dict[str, Any] | None = None

    def find(
        self,
        query: dict[str, Any],
        sort: list[tuple[str, Any]] | None = None,
        limit: int | None = None,
    ) -> list[_TaskResultDoc]:
        self.last_query = query
        return self.docs


def _doc(task_id: str, qid: str, end_at: datetime) -> _TaskResultDoc:
    return _TaskResultDoc(
        project_id="proj-1",
        username="alice",
        task_id=task_id,
        name="CheckRabi",
        upstream_id="",
        status="completed",
        message="",
        stack_trace="",
        input_parameters={},
        output_parameters={},
        output_parameter_names=[],
        run_parameters={},
        note={},
        figure_path=[],
        json_figure_path=[],
        raw_data_path=[],
        start_at=end_at - timedelta(minutes=1),
        end_at=end_at,
        elapsed_time=timedelta(minutes=1),
        task_type="qubit",
        system_info=SystemInfoModel(),
        qid=qid,
        execution_id=f"exec-{task_id}",
        tags=[],
        chip_id="chip-1",
        ai_triage=AiTriageReviewModel(),
    )


def _ai_triage_config(tasks: list[str] | None = None) -> CopilotConfig:
    return CopilotConfig(
        enabled=True,
        model=ModelConfig(provider="openai", name="gpt-4.1"),
        analysis_models=[ModelConfig(provider="openai", name="gpt-5.1")],
        analysis=AnalysisConfig(enabled=True, ai_triage_tasks=tasks or ["CheckRabi"]),
    )


def _service(repo: _TaskResultRepo) -> TaskResultService:
    return TaskResultService(
        chip_repository=cast("ChipRepository", _ChipRepo()),
        task_result_repository=cast("TaskResultHistoryRepository", repo),
    )


def test_request_bulk_ai_triage_enqueues_latest_result_per_qid_with_upsert() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    repo = _TaskResultRepo(
        [
            _doc("new-q0", "0", now),
            _doc("old-q0", "0", now - timedelta(hours=1)),
            _doc("new-q1", "1", now),
        ]
    )
    service = _service(repo)

    with (
        patch.object(service, "_load_ai_triage_config", return_value=_ai_triage_config()),
        patch.object(service, "_enqueue_ai_triage_for_document") as enqueue,
    ):
        response = service.request_bulk_ai_triage(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
            requested_by="bob",
        )

    assert response.requested_count == 2
    assert response.task_ids == ["new-q0", "new-q1"]
    assert repo.last_query == {
        "project_id": "proj-1",
        "chip_id": "chip-1",
        "name": "CheckRabi",
        "qid": {"$in": ["0", "1", "2"]},
        "status": {"$in": ["completed", "failed"]},
    }
    assert enqueue.call_count == 2
    assert enqueue.call_args_list[0].args[0].task_id == "new-q0"
    assert enqueue.call_args_list[0].args[1] is None
    assert repo.docs[0].ai_triage.status == "requested"
    assert repo.docs[0].ai_triage.requested_by == "bob"
    assert repo.docs[0].ai_triage.model_provider == "openai"
    assert repo.docs[0].ai_triage.model_name == "gpt-5.1"
    assert repo.docs[0].saved is True


def test_request_bulk_ai_triage_filters_to_terminal_results() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    repo = _TaskResultRepo([_doc("new-q0", "0", now)])
    service = _service(repo)

    with (
        patch.object(service, "_load_ai_triage_config", return_value=_ai_triage_config()),
        patch.object(service, "_enqueue_ai_triage_for_document"),
    ):
        service.request_bulk_ai_triage(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
        )

    assert repo.last_query is not None
    assert repo.last_query["status"] == {"$in": ["completed", "failed"]}


def test_request_bulk_ai_triage_limits_to_selected_task_ids() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    repo = _TaskResultRepo(
        [
            _doc("new-q0", "0", now),
            _doc("new-q1", "1", now),
        ]
    )
    service = _service(repo)

    with (
        patch.object(service, "_load_ai_triage_config", return_value=_ai_triage_config()),
        patch.object(service, "_enqueue_ai_triage_for_document") as enqueue,
    ):
        response = service.request_bulk_ai_triage(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
            task_ids=["new-q1"],
        )

    assert response.requested_count == 1
    assert response.task_ids == ["new-q1"]
    assert repo.last_query is not None
    assert repo.last_query["task_id"] == {"$in": ["new-q1"]}
    enqueue.assert_called_once()


def test_request_bulk_ai_triage_passes_model_override() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    repo = _TaskResultRepo([_doc("new-q0", "0", now)])
    service = _service(repo)
    model_override = ModelConfig(provider="anthropic", name="claude-sonnet-4.5")

    with (
        patch.object(service, "_load_ai_triage_config", return_value=_ai_triage_config()),
        patch.object(service, "_enqueue_ai_triage_for_document") as enqueue,
    ):
        service.request_bulk_ai_triage(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
            task_ids=["new-q0"],
            model_override=model_override,
        )

    assert enqueue.call_args.args[1] is model_override
    assert repo.docs[0].ai_triage.model_provider == "anthropic"
    assert repo.docs[0].ai_triage.model_name == "claude-sonnet-4.5"


def test_request_bulk_ai_triage_historical_date_filters_by_day() -> None:
    now = datetime(2026, 5, 5, 12, tzinfo=timezone.utc)
    repo = _TaskResultRepo([_doc("hist-q0", "0", now)])
    service = _service(repo)

    with (
        patch.object(service, "_load_ai_triage_config", return_value=_ai_triage_config()),
        patch.object(service, "_enqueue_ai_triage_for_document"),
    ):
        response = service.request_bulk_ai_triage(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
            date="20260505",
        )

    assert response.date == "20260505"
    assert repo.last_query is not None
    assert repo.last_query["qid"] == {"$in": ["0", "1"]}
    parsed_date = parse_date("20260505", "YYYYMMDD")
    assert repo.last_query["start_at"] == {
        "$gte": start_of_day(parsed_date),
        "$lt": end_of_day(parsed_date),
    }


def test_request_bulk_ai_triage_skips_task_not_configured() -> None:
    repo = _TaskResultRepo([])
    service = _service(repo)

    with patch.object(
        service,
        "_load_ai_triage_config",
        return_value=_ai_triage_config(tasks=["CheckT1"]),
    ):
        response = service.request_bulk_ai_triage(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
        )

    assert response.requested_count == 0
    assert response.task_ids == []
    assert response.skipped_reason == "task_not_configured"
    assert repo.last_query is None


def test_bulk_ai_triage_config_applies_local_vlm_defaults_only_to_triage() -> None:
    config = CopilotConfig(
        enabled=True,
        model=ModelConfig(provider="openai", name="gpt-4.1", max_output_tokens=4096),
        analysis_models=[ModelConfig(provider="ollama", name="gemma4:26b", max_output_tokens=4096)],
        analysis=AnalysisConfig(
            enabled=True,
            max_expected_images=2,
            ai_triage_max_expected_images=0,
            ai_triage_max_output_tokens=1024,
        ),
    )

    triage_config = TaskResultService._ai_triage_config(config)

    assert config.analysis.max_expected_images == 2
    assert config.analysis_models[0].max_output_tokens == 4096
    assert triage_config.analysis.max_expected_images == 0
    assert triage_config.analysis_model is not None
    assert triage_config.analysis_model.max_output_tokens == 1024


def test_bulk_ai_triage_forced_markdown_marks_missing_f01_as_no_signal() -> None:
    markdown = TaskResultService._forced_ai_triage_markdown("CheckQubitSpectroscopy", {})

    assert markdown is not None
    assert "- Decision: `FAIL`" in markdown
    assert "- Human label suggestion: `NO_SIGNAL`" in markdown


def test_persist_ai_triage_markdown_marks_empty_content_as_failed() -> None:
    with (
        patch.object(TaskResultService, "_set_ai_triage_status") as set_status,
        patch.object(TaskResultService, "_upsert_ai_triage_note") as upsert,
    ):
        TaskResultService._persist_ai_triage_markdown(
            project_id="proj-1",
            task_id="task-1",
            markdown="",
            selected_model=ModelConfig(provider="openai", name="gpt-5.1"),
        )

    set_status.assert_called_once_with(
        "proj-1",
        "task-1",
        "failed",
        error="AI triage returned empty content",
    )
    upsert.assert_not_called()


def test_create_figures_zip_includes_ai_triage_markdown(tmp_path) -> None:
    figure = tmp_path / "figure.json"
    figure.write_text('{"data":[]}', encoding="utf-8")

    with patch.object(
        TaskResultService,
        "_load_ai_triage_note_entries",
        return_value=[
            ("ai_triage/CheckRabi_0_task-1.md", "## AI triage\n\n- Decision: `REVIEW`\n")
        ],
    ):
        buffer, filename = TaskResultService.create_figures_zip(
            [str(figure)],
            "artifacts.zip",
            project_id="proj-1",
            ai_triage_task_ids=["task-1"],
        )

    assert filename == "artifacts.zip"
    with zipfile.ZipFile(buffer) as archive:
        assert sorted(archive.namelist()) == [
            "ai_triage/CheckRabi_0_task-1.md",
            "figure.json",
        ]
        assert archive.read("ai_triage/CheckRabi_0_task-1.md").decode() == (
            "## AI triage\n\n- Decision: `REVIEW`\n"
        )


def test_create_figures_zip_includes_ai_triage_replay_bundle(tmp_path) -> None:
    figure = tmp_path / "figure.json"
    figure.write_text('{"data":[]}', encoding="utf-8")

    with patch.object(
        TaskResultService,
        "_load_ai_triage_bundle_entries",
        return_value=[("ai_triage_bundle/CheckRabi_0_task-1.zip", b"bundle-bytes")],
    ):
        buffer, filename = TaskResultService.create_figures_zip(
            [str(figure)],
            "artifacts.zip",
            project_id="proj-1",
            ai_triage_bundle_task_ids=["task-1"],
        )

    assert filename == "artifacts.zip"
    with zipfile.ZipFile(buffer) as archive:
        assert sorted(archive.namelist()) == [
            "ai_triage_bundle/CheckRabi_0_task-1.zip",
            "figure.json",
        ]
        assert archive.read("ai_triage_bundle/CheckRabi_0_task-1.zip") == b"bundle-bytes"
