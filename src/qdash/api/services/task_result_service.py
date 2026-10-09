"""Task result service for QDash API.

This module provides business logic for task result queries,
abstracting away the repository layer from the routers.
"""

from __future__ import annotations

import logging
import re
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bunnet import SortDirection

from qdash.api.schemas.task_result import (
    LatestTaskResultResponse,
    TaskHistoryResponse,
    TaskResult,
    TaskResultListItem,
    TaskResultListResponse,
    TimeSeriesData,
    TimeSeriesProjection,
)
from qdash.common.config.path_resolver import resolve_calib_data_path
from qdash.common.utils.datetime import (
    end_of_day,
    now,
    parse_date,
    parse_elapsed_time,
    start_of_day,
)
from qdash.datamodel.task import ParameterModel

if TYPE_CHECKING:
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
    from qdash.repository.protocols import ChipRepository, TaskResultHistoryRepository

logger = logging.getLogger(__name__)


def _document_to_task_result(doc: TaskResultHistoryDocument) -> TaskResult:
    """Convert a TaskResultHistoryDocument to a TaskResult schema."""
    return TaskResult(
        task_id=doc.task_id,
        execution_id=doc.execution_id,
        name=doc.name,
        status=doc.status,
        message=doc.message,
        input_parameters=doc.input_parameters,
        output_parameters=doc.output_parameters,
        output_parameter_names=doc.output_parameter_names,
        run_parameters=doc.run_parameters,
        note=doc.note,
        figure_path=doc.figure_path,
        json_figure_path=doc.json_figure_path,
        raw_data_path=doc.raw_data_path,
        start_at=doc.start_at,
        end_at=doc.end_at,
        elapsed_time=parse_elapsed_time(doc.elapsed_time),
        task_type=doc.task_type,
    )


class TaskResultService:
    """Service for task result operations."""

    def __init__(
        self,
        chip_repository: ChipRepository,
        task_result_repository: TaskResultHistoryRepository,
    ) -> None:
        self._chip_repo = chip_repository
        self._task_result_repo = task_result_repository

    def list_task_results(
        self,
        *,
        project_id: str,
        status: str | None = None,
        chip_id: str | None = None,
        task_name: str | None = None,
        qid: str | None = None,
        execution_id: str | None = None,
        username: str | None = None,
        start_from: datetime | None = None,
        start_to: datetime | None = None,
        message_contains: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> TaskResultListResponse:
        """List task results for cross-task investigation."""
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        query: dict[str, Any] = {"project_id": project_id}
        if status:
            query["status"] = status
        if chip_id:
            query["chip_id"] = chip_id
        if task_name:
            query["name"] = task_name
        if qid:
            query["qid"] = qid
        if execution_id:
            query["execution_id"] = execution_id
        if username:
            query["username"] = username
        start_bounds: dict[str, datetime] = {}
        if start_from:
            start_bounds["$gte"] = start_from
        if start_to:
            start_bounds["$lte"] = start_to
        if start_bounds:
            query["start_at"] = start_bounds
        if message_contains:
            query["message"] = {"$regex": re.escape(message_contains), "$options": "i"}

        total = TaskResultHistoryDocument.find(query).count()
        docs = list(
            TaskResultHistoryDocument.find(query)
            .sort([("start_at", SortDirection.DESCENDING), ("task_id", SortDirection.ASCENDING)])
            .skip(skip)
            .limit(limit)
            .run()
        )

        count_query = {key: value for key, value in query.items() if key != "status"}
        status_docs = TaskResultHistoryDocument.aggregate(
            [
                {"$match": count_query},
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            ]
        ).run()
        status_counts = {
            str(row.get("_id") or "unknown"): int(row.get("count") or 0) for row in status_docs
        }

        return TaskResultListResponse(
            items=[self._document_to_list_item(doc) for doc in docs],
            total=total,
            skip=skip,
            limit=limit,
            status_counts=dict(sorted(status_counts.items())),
        )

    @staticmethod
    def _document_to_list_item(doc: TaskResultHistoryDocument) -> TaskResultListItem:
        return TaskResultListItem(
            task_id=doc.task_id,
            task_name=doc.name,
            qid=doc.qid,
            chip_id=doc.chip_id,
            status=doc.status,
            execution_id=doc.execution_id,
            user_id=doc.user_id,
            username=doc.username,
            message=doc.message,
            has_stack_trace=bool(doc.stack_trace),
            source_task_id=doc.source_task_id,
            start_at=doc.start_at,
            end_at=doc.end_at,
            elapsed_time=parse_elapsed_time(doc.elapsed_time),
        )

    def get_latest_results(
        self,
        project_id: str,
        chip_id: str,
        task: str,
        entity_type: str,
    ) -> LatestTaskResultResponse:
        """Get the latest task results for all entities on a chip.

        Parameters
        ----------
        project_id : str
            Project ID for scoping
        chip_id : str
            Chip ID
        task : str
            Task name
        entity_type : str
            "qubit" or "coupling"

        Returns
        -------
        LatestTaskResultResponse

        """
        qids = self._get_entity_ids(project_id, chip_id, entity_type)
        default_view = entity_type == "qubit"

        # Collapse to the latest result per qid in the DB rather than fetching
        # every historical row for (chip, task) and deduping in Python — the
        # latter grows linearly with history depth.
        all_results = self._task_result_repo.find_latest_by_chip_and_qids(
            project_id=project_id,
            chip_id=chip_id,
            qids=qids,
            task_names=[task],
        )

        task_results = self._organize_by_qid(all_results)

        results = {}
        for qid in qids:
            doc = task_results.get(qid)
            if doc is not None:
                results[qid] = _document_to_task_result(doc)
            else:
                results[qid] = (
                    TaskResult(name=task)
                    if default_view
                    else TaskResult(name=task, default_view=False)
                )

        return LatestTaskResultResponse(task_name=task, result=results)

    def get_historical_results(
        self,
        project_id: str,
        chip_id: str,
        task: str,
        entity_type: str,
        date: str,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> LatestTaskResultResponse:
        """Get historical task results for a specific date.

        Parameters
        ----------
        project_id : str
            Project ID for scoping
        chip_id : str
            Chip ID
        task : str
            Task name
        entity_type : str
            "qubit" or "coupling"
        date : str
            Date in YYYYMMDD format

        Returns
        -------
        LatestTaskResultResponse

        """
        parsed_date = parse_date(date, "YYYYMMDD")
        start_time = start_at or start_of_day(parsed_date)
        end_time = end_at or end_of_day(parsed_date)
        default_view = entity_type == "qubit"

        if start_at is not None or end_at is not None:
            # A range request may end on a day that has no chip-history snapshot.
            # The range itself is the source of truth for task-result selection;
            # use current entity IDs for the grid skeleton and avoid failing before
            # querying task_result_history.
            qids = self._get_entity_ids(project_id, chip_id, entity_type)
        else:
            qids = self._get_historical_entity_ids(project_id, chip_id, entity_type, date)

        all_results = self._task_result_repo.find(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "name": task,
                "qid": {"$in": qids},
                "start_at": {"$gte": start_time, "$lt": end_time},
            },
            sort=[("end_at", SortDirection.DESCENDING)],
        )

        task_results = self._organize_by_qid(all_results)

        results = {}
        for qid in qids:
            doc = task_results.get(qid)
            if doc is not None:
                results[qid] = _document_to_task_result(doc)
            else:
                results[qid] = (
                    TaskResult(name=task)
                    if default_view
                    else TaskResult(name=task, default_view=False)
                )

        return LatestTaskResultResponse(task_name=task, result=results)

    def get_history(
        self,
        project_id: str,
        chip_id: str,
        task: str,
        entity_id: str,
    ) -> TaskHistoryResponse:
        """Get complete task history for a specific entity.

        Parameters
        ----------
        project_id : str
            Project ID for scoping
        chip_id : str
            Chip ID
        task : str
            Task name
        entity_id : str
            Qubit or coupling ID

        Returns
        -------
        TaskHistoryResponse

        """
        chip = self._chip_repo.find_one_document({"project_id": project_id, "chip_id": chip_id})
        if chip is None:
            raise ValueError(f"Chip {chip_id} not found in project {project_id}")

        all_results = self._task_result_repo.find(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "name": task,
                "qid": entity_id,
            },
            sort=[("end_at", SortDirection.DESCENDING)],
        )

        data = {}
        for result in all_results:
            data[result.task_id] = _document_to_task_result(result)

        return TaskHistoryResponse(name=task, data=data)

    def get_timeseries(
        self,
        chip_id: str,
        tag: str | None,
        parameter: str,
        project_id: str,
        target_qid: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> TimeSeriesData:
        """Fetch timeseries data for all qids or a specific qid.

        Parameters
        ----------
        chip_id : str
            Chip ID
        tag : str
            Tag to filter by
        parameter : str
            Parameter name
        project_id : str
            Project ID for scoping
        target_qid : str | None
            Optional specific qid filter
        start_at : str | None
            Start time in ISO format
        end_at : str | None
            End time in ISO format

        Returns
        -------
        TimeSeriesData

        """
        if start_at is None or end_at is None:
            end_at_dt = now()
            start_at_dt = now() - timedelta(days=7)
        else:
            start_at_dt = datetime.fromisoformat(start_at)
            end_at_dt = datetime.fromisoformat(end_at)

        query_filter: dict[str, Any] = {
            "project_id": project_id,
            "chip_id": chip_id,
            "output_parameter_names": parameter,
            "start_at": {"$gte": start_at_dt, "$lte": end_at_dt},
        }
        if tag is not None:
            query_filter["tags"] = tag

        task_results = self._task_result_repo.find_with_projection(
            query_filter,
            projection_model=TimeSeriesProjection,
            sort=[("start_at", SortDirection.ASCENDING)],
        )

        timeseries_by_qid: dict[str, list[ParameterModel]] = {}

        for task_result in task_results:
            qid = task_result.qid
            if target_qid is not None and qid != target_qid:
                continue
            if qid not in timeseries_by_qid:
                timeseries_by_qid[qid] = []
            if parameter not in task_result.output_parameters:
                logger.warning(
                    f"Parameter '{parameter}' not found in output_parameters for task_result "
                    f"(qid={qid}, start_at={task_result.start_at}), skipping"
                )
                continue
            param_data = task_result.output_parameters[parameter]
            if isinstance(param_data, dict):
                timeseries_by_qid[qid].append(ParameterModel(**param_data))
            else:
                timeseries_by_qid[qid].append(param_data)

        return TimeSeriesData(data=timeseries_by_qid)

    def _get_entity_ids(self, project_id: str, chip_id: str, entity_type: str) -> list[str]:
        """Get entity IDs for a chip."""
        if entity_type == "qubit":
            qids = self._chip_repo.get_qubit_ids(project_id, chip_id)
            if not qids:
                raise ValueError(
                    f"Chip {chip_id} not found or has no qubits in project {project_id}"
                )
        else:
            qids = self._chip_repo.get_coupling_ids(project_id, chip_id)
            if not qids:
                raise ValueError(
                    f"Chip {chip_id} not found or has no couplings in project {project_id}"
                )
        return qids

    def _get_historical_entity_ids(
        self, project_id: str, chip_id: str, entity_type: str, date: str
    ) -> list[str]:
        """Get historical entity IDs for a chip."""
        if entity_type == "qubit":
            qids = self._chip_repo.get_historical_qubit_ids(project_id, chip_id, date)
            if not qids:
                raise ValueError(f"Chip {chip_id} not found or has no qubits for date {date}")
        else:
            qids = self._chip_repo.get_historical_coupling_ids(project_id, chip_id, date)
            if not qids:
                raise ValueError(f"Chip {chip_id} not found or has no couplings for date {date}")
        return qids

    @staticmethod
    def _organize_by_qid(
        results: list[TaskResultHistoryDocument],
    ) -> dict[str, TaskResultHistoryDocument]:
        """Organize results by qid, keeping only the first (most recent) per qid."""
        task_results: dict[str, TaskResultHistoryDocument] = {}
        for result in results:
            if result.qid is not None and result.qid not in task_results:
                task_results[result.qid] = result
        return task_results

    @staticmethod
    def create_figures_zip(paths: list[str], filename: str) -> tuple[Path, str]:
        """Create a ZIP archive from the given file paths.

        Parameters
        ----------
        paths : list[str]
            Absolute paths to include in the archive.
        filename : str
            Desired archive filename (will be sanitised).

        Returns
        -------
        tuple[pathlib.Path, str]
            (temporary archive path, safe filename)

        Raises
        ------
        HTTPException
            If no paths are given or any path does not exist.

        """
        from starlette.exceptions import HTTPException

        if not paths:
            raise HTTPException(status_code=400, detail="No files provided")

        resolved_paths = [(p, resolve_calib_data_path(p)) for p in paths]
        missing = [p for p, resolved in resolved_paths if not resolved.exists()]
        if missing:
            detail = f"Files not found: {', '.join(missing[:5])}"
            if len(missing) > 5:
                detail += "..."
            raise HTTPException(status_code=400, detail=detail)

        safe_filename = (
            "".join(c for c in filename if c.isalnum() or c in "._-").strip() or "figures.zip"
        )
        if not safe_filename.endswith(".zip"):
            safe_filename += ".zip"

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temporary_file:
            archive_path = Path(temporary_file.name)
        try:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for _, path in resolved_paths:
                    zf.write(path, path.name)
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise

        return archive_path, safe_filename
