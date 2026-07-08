from __future__ import annotations

import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import patch

from qdash.api.routers.dashboard import _load_reviewed_task_results
from qdash.api.services.task_result_service import TaskResultService
from qdash.common.utils.datetime import end_of_day, parse_date, start_of_day
from qdash.copilot.config import AnalysisConfig, CopilotConfig, ModelConfig
from qdash.datamodel.note import AiReviewModel, NoteModel
from qdash.datamodel.system_info import SystemInfoModel

if TYPE_CHECKING:
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
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
        self.last_latest_call: dict[str, Any] | None = None

    def find(
        self,
        query: dict[str, Any],
        sort: list[tuple[str, Any]] | None = None,
        limit: int | None = None,
    ) -> list[_TaskResultDoc]:
        self.last_query = query
        return self.docs

    def find_with_projection(
        self,
        query: dict[str, Any],
        projection_model: Any,
        sort: list[tuple[str, Any]] | None = None,
        limit: int | None = None,
    ) -> list[_TaskResultDoc]:
        self.last_query = query
        return self.docs

    def find_latest_by_chip_and_qids(
        self,
        *,
        project_id: str,
        chip_id: str,
        qids: list[str],
        task_names: list[str],
    ) -> list[_TaskResultDoc]:
        self.last_latest_call = {
            "project_id": project_id,
            "chip_id": chip_id,
            "qids": qids,
            "task_names": task_names,
        }
        return self.docs


def _doc(task_id: str, qid: str, end_at: datetime) -> _TaskResultDoc:
    return _TaskResultDoc(
        project_id="proj-1",
        user_id="user-1",
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
        source_task_id=None,
        ai_review=AiReviewModel(),
        user_note=NoteModel(),
        ai_review_note=NoteModel(),
    )


def _ai_review_config(tasks: list[str] | None = None) -> CopilotConfig:
    return CopilotConfig(
        enabled=True,
        model=ModelConfig(provider="openai", name="gpt-4.1"),
        analysis_models=[ModelConfig(provider="openai", name="gpt-5.1")],
        analysis=AnalysisConfig(enabled=True, ai_review_tasks=tasks or ["CheckRabi"]),
    )


def _service(repo: _TaskResultRepo) -> TaskResultService:
    return TaskResultService(
        chip_repository=cast("ChipRepository", _ChipRepo()),
        task_result_repository=cast("TaskResultHistoryRepository", repo),
    )


def test_get_latest_results_keeps_latest_per_qid_and_fills_missing() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    # qid "0" has two rows (newest first, as the repo returns latest-per-group);
    # qid "1" has one; qid "2" (from _ChipRepo.get_qubit_ids) has none.
    docs = [
        _doc("q0-new", "0", now),
        _doc("q0-old", "0", now - timedelta(days=1)),
        _doc("q1", "1", now),
    ]
    repo = _TaskResultRepo(docs)

    resp = _service(repo).get_latest_results("proj-1", "chip-1", "CheckRabi", "qubit")

    assert resp.task_name == "CheckRabi"
    # latest kept per qid
    assert resp.result["0"].task_id == "q0-new"
    assert resp.result["1"].task_id == "q1"
    # missing qid gets a default (qubit view) placeholder, not an error
    assert resp.result["2"].task_id is None
    assert resp.result["2"].name == "CheckRabi"
    # uses the optimized DB-side path scoped to the single requested task
    assert repo.last_latest_call is not None
    assert repo.last_latest_call["task_names"] == ["CheckRabi"]
    assert repo.last_latest_call["qids"] == ["0", "1", "2"]


def test_get_latest_results_coupling_uses_coupling_ids() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    doc = _doc("c01", "0-1", now)
    doc.task_type = "coupling"
    repo = _TaskResultRepo([doc])

    resp = _service(repo).get_latest_results("proj-1", "chip-1", "CheckCrossResonance", "coupling")

    assert resp.result["0-1"].task_id == "c01"
    # coupling ids come from the chip repo, single task name is forwarded
    assert repo.last_latest_call["qids"] == ["0-1"]
    assert repo.last_latest_call["task_names"] == ["CheckCrossResonance"]


def test_list_task_results_filters_failed_rows_and_paginates(monkeypatch: Any) -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    docs = [
        _doc("failed-q0", "0", now),
        _doc("failed-q1", "1", now - timedelta(minutes=5)),
        _doc("completed-q2", "2", now - timedelta(minutes=10)),
    ]
    docs[0].status = "failed"
    docs[0].message = "RuntimeError: bad calibration"
    docs[0].stack_trace = "Traceback..."
    docs[1].status = "failed"
    docs[1].message = "Timeout waiting for backend"

    class _Finder:
        def __init__(self, rows: list[_TaskResultDoc]) -> None:
            self.rows = rows
            self.offset = 0
            self.page_limit: int | None = None

        def count(self) -> int:
            return len(self.rows)

        def sort(self, sort: list[tuple[str, Any]]) -> _Finder:
            self.rows = sorted(
                self.rows,
                key=lambda doc: (doc.start_at or datetime.min, doc.task_id),
                reverse=True,
            )
            return self

        def skip(self, skip: int) -> _Finder:
            self.offset = skip
            return self

        def limit(self, limit: int) -> _Finder:
            self.page_limit = limit
            return self

        def run(self) -> list[_TaskResultDoc]:
            end = None if self.page_limit is None else self.offset + self.page_limit
            return self.rows[self.offset : end]

    class _Aggregate:
        def run(self) -> list[dict[str, Any]]:
            return [{"_id": "completed", "count": 1}, {"_id": "failed", "count": 2}]

    class _Document:
        @staticmethod
        def find(query: dict[str, Any]) -> _Finder:
            filtered = [
                doc
                for doc in docs
                if doc.project_id == query["project_id"]
                and (not query.get("status") or doc.status == query["status"])
                and (not query.get("chip_id") or doc.chip_id == query["chip_id"])
                and (not query.get("message") or "calibration" in doc.message)
            ]
            return _Finder(filtered)

        @staticmethod
        def aggregate(pipeline: list[dict[str, Any]]) -> _Aggregate:
            return _Aggregate()

    import qdash.dbmodel.task_result_history as task_result_history

    monkeypatch.setattr(task_result_history, "TaskResultHistoryDocument", _Document)

    response = _service(_TaskResultRepo([])).list_task_results(
        project_id="proj-1",
        status="failed",
        chip_id="chip-1",
        message_contains="calibration",
        skip=0,
        limit=10,
    )

    assert response.total == 1
    assert response.status_counts == {"completed": 1, "failed": 2}
    assert response.items[0].task_id == "failed-q0"
    assert response.items[0].status == "failed"
    assert response.items[0].message == "RuntimeError: bad calibration"
    assert response.items[0].has_stack_trace is True


def _claim_ai_review_document(
    doc: _TaskResultDoc,
    requested_by: str,
    selected_model: ModelConfig,
    review_run_id: str,
) -> _TaskResultDoc | None:
    if doc.ai_review.status in {"requested", "running"}:
        return None
    TaskResultService._mark_ai_review_requested(
        cast("TaskResultHistoryDocument", doc),
        requested_by,
        selected_model,
        review_run_id,
    )
    return doc


def test_request_bulk_ai_review_enqueues_latest_result_per_qid_with_upsert() -> None:
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
        patch.object(service, "_load_ai_review_config", return_value=_ai_review_config()),
        patch.object(service, "_claim_ai_review_document", side_effect=_claim_ai_review_document),
        patch.object(service, "_submit_ai_review_document") as enqueue,
    ):
        response = service.request_bulk_ai_review(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
            requested_by="bob",
        )

    assert response.requested_count == 2
    assert response.review_run_id.startswith("airv_")
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
    assert enqueue.call_args_list[0].args[0].ai_review.review_run_id == response.review_run_id
    assert enqueue.call_args_list[0].args[1] is None
    assert repo.docs[0].ai_review.status == "requested"
    assert repo.docs[0].ai_review.requested_by == "bob"
    assert repo.docs[0].ai_review.model_provider == "openai"
    assert repo.docs[0].ai_review.model_name == "gpt-5.1"
    assert repo.docs[0].saved is True


def test_request_bulk_ai_review_filters_to_terminal_results() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    repo = _TaskResultRepo([_doc("new-q0", "0", now)])
    service = _service(repo)

    with (
        patch.object(service, "_load_ai_review_config", return_value=_ai_review_config()),
        patch.object(service, "_claim_ai_review_document", side_effect=_claim_ai_review_document),
        patch.object(service, "_submit_ai_review_document"),
    ):
        service.request_bulk_ai_review(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
        )

    assert repo.last_query is not None
    assert repo.last_query["status"] == {"$in": ["completed", "failed"]}


def test_request_bulk_ai_review_limits_to_selected_task_ids() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    repo = _TaskResultRepo(
        [
            _doc("new-q0", "0", now),
            _doc("new-q1", "1", now),
        ]
    )
    service = _service(repo)

    with (
        patch.object(service, "_load_ai_review_config", return_value=_ai_review_config()),
        patch.object(service, "_claim_ai_review_document", side_effect=_claim_ai_review_document),
        patch.object(service, "_submit_ai_review_document") as enqueue,
    ):
        response = service.request_bulk_ai_review(
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


def test_request_bulk_ai_review_skips_non_representative_mux_results() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    repo = _TaskResultRepo(
        [
            _doc("mux-q0", "0", now),
            _doc("mux-q1", "1", now),
        ]
    )
    repo.docs[0].name = "CheckResonatorSpectroscopy"
    repo.docs[1].name = "CheckResonatorSpectroscopy"
    service = _service(repo)

    with (
        patch.object(
            service,
            "_load_ai_review_config",
            return_value=_ai_review_config(tasks=["CheckResonatorSpectroscopy"]),
        ),
        patch.object(service, "_claim_ai_review_document", side_effect=_claim_ai_review_document),
        patch.object(service, "_submit_ai_review_document") as submit,
    ):
        response = service.request_bulk_ai_review(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckResonatorSpectroscopy",
            entity_type="qubit",
        )

    assert response.requested_count == 1
    assert response.task_ids == ["mux-q0"]
    submit.assert_called_once()


def test_request_bulk_ai_review_does_not_rewrite_already_claimed_runs() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    repo = _TaskResultRepo([_doc("new-q0", "0", now)])
    repo.docs[0].ai_review = AiReviewModel(
        status="running",
        requested_by="alice",
        model_provider="openai",
        model_name="gpt-5.1",
    )
    service = _service(repo)

    with (
        patch.object(service, "_load_ai_review_config", return_value=_ai_review_config()),
        patch.object(service, "_claim_ai_review_document", side_effect=_claim_ai_review_document),
    ):
        response = service.request_bulk_ai_review(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
            requested_by="bob",
        )

    assert response.requested_count == 0
    assert response.task_ids == []
    assert repo.docs[0].ai_review.requested_by == "alice"
    assert repo.docs[0].ai_review.status == "running"
    assert repo.docs[0].saved is False


def test_request_bulk_ai_review_passes_model_override() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    repo = _TaskResultRepo([_doc("new-q0", "0", now)])
    service = _service(repo)
    model_override = ModelConfig(provider="anthropic", name="claude-sonnet-4.5")

    with (
        patch.object(service, "_load_ai_review_config", return_value=_ai_review_config()),
        patch.object(service, "_claim_ai_review_document", side_effect=_claim_ai_review_document),
        patch.object(service, "_submit_ai_review_document") as enqueue,
    ):
        service.request_bulk_ai_review(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
            task_ids=["new-q0"],
            model_override=model_override,
        )

    assert enqueue.call_args.args[1] is model_override
    assert repo.docs[0].ai_review.model_provider == "anthropic"
    assert repo.docs[0].ai_review.model_name == "claude-sonnet-4.5"


def test_request_bulk_ai_review_historical_date_filters_by_day() -> None:
    now = datetime(2026, 5, 5, 12, tzinfo=timezone.utc)
    repo = _TaskResultRepo([_doc("hist-q0", "0", now)])
    service = _service(repo)

    with (
        patch.object(service, "_load_ai_review_config", return_value=_ai_review_config()),
        patch.object(service, "_claim_ai_review_document", side_effect=_claim_ai_review_document),
        patch.object(service, "_submit_ai_review_document"),
    ):
        response = service.request_bulk_ai_review(
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


def test_request_bulk_ai_review_skips_task_not_configured() -> None:
    repo = _TaskResultRepo([])
    service = _service(repo)

    with patch.object(
        service,
        "_load_ai_review_config",
        return_value=_ai_review_config(tasks=["CheckT1"]),
    ):
        response = service.request_bulk_ai_review(
            project_id="proj-1",
            chip_id="chip-1",
            task="CheckRabi",
            entity_type="qubit",
        )

    assert response.requested_count == 0
    assert response.task_ids == []
    assert response.skipped_reason == "task_not_configured"
    assert repo.last_query is None


def test_bulk_ai_review_config_applies_local_vlm_defaults_only_to_review() -> None:
    config = CopilotConfig(
        enabled=True,
        model=ModelConfig(provider="openai", name="gpt-4.1", max_output_tokens=4096),
        analysis_models=[ModelConfig(provider="ollama", name="gemma4:26b", max_output_tokens=4096)],
        analysis=AnalysisConfig(
            enabled=True,
            max_expected_images=2,
            ai_review_max_expected_images=0,
            ai_review_max_output_tokens=1024,
        ),
    )

    review_config = TaskResultService._ai_review_config(config)

    assert config.analysis.max_expected_images == 2
    assert config.analysis_models[0].max_output_tokens == 4096
    assert review_config.analysis.max_expected_images == 0
    assert review_config.analysis_model is not None
    assert review_config.analysis_model.max_output_tokens == 1024


def test_bulk_ai_review_forced_markdown_marks_missing_f01_as_no_signal() -> None:
    markdown = TaskResultService._forced_ai_review_markdown("CheckQubitSpectroscopy", {})

    assert markdown is not None
    assert "- Decision: `FAIL`" in markdown
    assert "- Human label suggestion: `NO_SIGNAL`" in markdown


def test_persist_ai_review_markdown_marks_empty_content_as_failed() -> None:
    with (
        patch.object(TaskResultService, "_set_ai_review_status") as set_status,
        patch.object(TaskResultService, "_upsert_ai_review_note") as upsert,
    ):
        TaskResultService._persist_ai_review_markdown(
            project_id="proj-1",
            task_id="task-1",
            markdown="",
            selected_model=ModelConfig(provider="openai", name="gpt-5.1"),
        )

    set_status.assert_called_once_with(
        "proj-1",
        "task-1",
        "failed",
        error="AI review returned empty content",
    )
    upsert.assert_not_called()


def test_create_figures_zip_includes_ai_review_markdown(tmp_path) -> None:
    figure = tmp_path / "figure.json"
    figure.write_text('{"data":[]}', encoding="utf-8")

    with patch.object(
        TaskResultService,
        "_load_ai_review_note_entries",
        return_value=[
            ("ai_review/CheckRabi_0_task-1.md", "## AI review\n\n- Decision: `REVIEW`\n")
        ],
    ):
        buffer, filename = TaskResultService.create_figures_zip(
            [str(figure)],
            "artifacts.zip",
            project_id="proj-1",
            ai_review_task_ids=["task-1"],
        )

    assert filename == "artifacts.zip"
    with zipfile.ZipFile(buffer) as archive:
        assert sorted(archive.namelist()) == [
            "ai_review/CheckRabi_0_task-1.md",
            "figure.json",
        ]
        assert archive.read("ai_review/CheckRabi_0_task-1.md").decode() == (
            "## AI review\n\n- Decision: `REVIEW`\n"
        )


def test_create_figures_zip_maps_container_calib_data_path(tmp_path, monkeypatch) -> None:
    local_base = tmp_path / "calib_data"
    figure = local_base / "proj-1" / "figure.json"
    figure.parent.mkdir(parents=True)
    figure.write_text('{"data":[]}', encoding="utf-8")
    monkeypatch.setenv("CALIB_DATA_PATH", str(local_base))

    buffer, filename = TaskResultService.create_figures_zip(
        ["/app/calib_data/proj-1/figure.json"],
        "artifacts.zip",
    )

    assert filename == "artifacts.zip"
    with zipfile.ZipFile(buffer) as archive:
        assert archive.namelist() == ["figure.json"]
        assert archive.read("figure.json").decode() == '{"data":[]}'


def test_create_figures_zip_includes_ai_review_replay_bundle(tmp_path) -> None:
    figure = tmp_path / "figure.json"
    figure.write_text('{"data":[]}', encoding="utf-8")

    with patch.object(
        TaskResultService,
        "_load_ai_review_bundle_entries",
        return_value=[("ai_review_bundle/CheckRabi_0_task-1.zip", b"bundle-bytes")],
    ):
        buffer, filename = TaskResultService.create_figures_zip(
            [str(figure)],
            "artifacts.zip",
            project_id="proj-1",
            ai_review_bundle_task_ids=["task-1"],
        )

    assert filename == "artifacts.zip"
    with zipfile.ZipFile(buffer) as archive:
        assert sorted(archive.namelist()) == [
            "ai_review_bundle/CheckRabi_0_task-1.zip",
            "figure.json",
        ]
        assert archive.read("ai_review_bundle/CheckRabi_0_task-1.zip") == b"bundle-bytes"


def test_load_reviewed_task_results_prefers_latest_completed_review_over_newer_pending() -> None:
    completed_doc = _doc("done-q0", "0", datetime(2026, 5, 5, 10, tzinfo=timezone.utc))
    completed_doc.ai_review_note = NoteModel(content="## AI review\n\n- Decision: `PASS`\n")
    completed_doc.ai_review = AiReviewModel(status="completed")

    pending_doc = _doc("pending-q0", "0", datetime(2026, 5, 5, 11, tzinfo=timezone.utc))
    pending_doc.ai_review = AiReviewModel(status="running")

    class _Finder:
        def __init__(self, docs):
            self._docs = docs

        def run(self):
            return self._docs

    with patch(
        "qdash.api.routers.dashboard.TaskResultHistoryDocument.find",
        return_value=_Finder([pending_doc, completed_doc]),
    ):
        docs = _load_reviewed_task_results(
            project_id="proj-1",
            chip_id="chip-1",
            task_name="CheckRabi",
            latest_only=True,
        )

    assert [doc.task_id for doc in docs] == ["done-q0"]


def test_list_ai_reviews_extracts_decision_and_paginates() -> None:
    first_doc = _doc("task-1", "0", datetime(2026, 5, 5, 11, tzinfo=timezone.utc))
    first_doc.name = "CheckQubitSpectroscopy"
    first_doc.figure_path = ["/tmp/task-1.png"]
    first_doc.json_figure_path = ["/tmp/task-1.json"]
    first_doc.ai_review_note = NoteModel(
        content=(
            "## AI review\n\n"
            "- Decision: `REVIEW`\n"
            "- Human label suggestion: `SUSPICIOUS`\n"
            "- Primary reason: signal is weak\n"
            "- Recommended action: inspect the trace\n"
        ),
        updated_at=datetime(2026, 5, 5, 11, 5, tzinfo=timezone.utc),
    )
    first_doc.ai_review = AiReviewModel(
        status="completed",
        review_run_id="airv_test",
        model_provider="ollama",
        model_name="gemma4:26b",
        completed_at=datetime(2026, 5, 5, 11, 4, tzinfo=timezone.utc),
    )

    second_doc = _doc("task-2", "1", datetime(2026, 5, 5, 10, tzinfo=timezone.utc))
    second_doc.ai_review_note = NoteModel(content="## AI review\n\n- Decision: `PASS`\n")
    second_doc.ai_review = AiReviewModel(status="completed")

    class _Finder:
        def __init__(self, docs):
            self._docs = docs

        def run(self):
            return self._docs

    service = _service(_TaskResultRepo([]))
    with patch(
        "qdash.dbmodel.task_result_history.TaskResultHistoryDocument.find",
        return_value=_Finder([second_doc, first_doc]),
    ):
        response = service.list_ai_reviews(
            project_id="proj-1",
            decision="REVIEW",
            skip=0,
            limit=10,
        )

    assert response.total == 1
    assert response.decision_counts == {"REVIEW": 1}
    item = response.items[0]
    assert item.task_id == "task-1"
    assert item.task_name == "CheckQubitSpectroscopy"
    assert item.target == "Q0"
    assert item.human_label == "SUSPICIOUS"
    assert item.primary_reason == "signal is weak"
    assert item.recommended_action == "inspect the trace"
    assert item.model == "ollama/gemma4:26b"
    assert item.figure_path == ["/tmp/task-1.png"]
    assert item.json_figure_path == ["/tmp/task-1.json"]


def test_get_ai_review_run_groups_reviews_by_run_id() -> None:
    first_doc = _doc("task-1", "0", datetime(2026, 5, 5, 11, tzinfo=timezone.utc))
    first_doc.ai_review_note = NoteModel(content="## AI review\n\n- Decision: `REVIEW`\n")
    first_doc.ai_review = AiReviewModel(
        status="completed",
        requested_by="bob",
        review_run_id="airv_group",
        model_provider="ollama",
        model_name="gemma4:26b",
        requested_at=datetime(2026, 5, 5, 11, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 5, 11, 5, tzinfo=timezone.utc),
    )

    second_doc = _doc("task-2", "1", datetime(2026, 5, 5, 11, tzinfo=timezone.utc))
    second_doc.ai_review_note = NoteModel(content="## AI review\n\n- Decision: `PASS`\n")
    second_doc.ai_review = AiReviewModel(
        status="running",
        requested_by="bob",
        review_run_id="airv_group",
        model_provider="ollama",
        model_name="gemma4:26b",
        requested_at=datetime(2026, 5, 5, 11, tzinfo=timezone.utc),
    )

    class _Finder:
        def __init__(self, docs):
            self._docs = docs

        def run(self):
            return self._docs

    service = _service(_TaskResultRepo([]))
    with patch(
        "qdash.dbmodel.task_result_history.TaskResultHistoryDocument.find",
        return_value=_Finder([second_doc, first_doc]),
    ):
        response = service.get_ai_review_run(
            project_id="proj-1",
            review_run_id="airv_group",
        )

    assert response.run.review_run_id == "airv_group"
    assert response.run.trigger_type == "manual_chip_bulk"
    assert response.run.execution_ids == ["exec-task-1", "exec-task-2"]
    assert response.run.total == 2
    assert response.run.completed_count == 1
    assert response.run.running_count == 1
    assert response.run.decision_counts == {"PASS": 1, "REVIEW": 1}
    assert [item.task_id for item in response.items] == ["task-1", "task-2"]


def test_get_timeseries_filters_by_tag() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    repo = _TaskResultRepo([])

    _service(repo).get_timeseries(
        chip_id="chip-1",
        tag="t1",
        parameter="t1",
        project_id="proj-1",
        start_at=(now - timedelta(days=1)).isoformat(),
        end_at=now.isoformat(),
    )

    assert repo.last_query is not None
    assert repo.last_query["tags"] == "t1"
    assert repo.last_query["project_id"] == "proj-1"
    assert repo.last_query["chip_id"] == "chip-1"
    assert repo.last_query["output_parameter_names"] == "t1"
