from __future__ import annotations

import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from qdash.api.services.task_result_service import TaskResultService
from qdash.datamodel.note import NoteModel
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
        user_note=NoteModel(),
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
    assert repo.last_latest_call is not None
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


def test_create_figures_zip_maps_container_calib_data_path(tmp_path, monkeypatch) -> None:
    local_base = tmp_path / "calib_data"
    figure = local_base / "proj-1" / "figure.json"
    figure.parent.mkdir(parents=True)
    figure.write_text('{"data":[]}', encoding="utf-8")
    monkeypatch.setenv("CALIB_DATA_PATH", str(local_base))

    archive_path, filename = TaskResultService.create_figures_zip(
        ["/app/calib_data/proj-1/figure.json"],
        "artifacts.zip",
    )

    assert filename == "artifacts.zip"
    try:
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.namelist() == ["figure.json"]
            assert archive.read("figure.json").decode() == '{"data":[]}'
    finally:
        archive_path.unlink(missing_ok=True)


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
