"""Task result service for QDash API.

This module provides business logic for task result queries,
abstracting away the repository layer from the routers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from bunnet import SortDirection
from qdash.api.schemas.task_result import (
    LatestTaskResultResponse,
    TaskHistoryResponse,
    TaskResult,
    TimeSeriesData,
    TimeSeriesProjection,
)
from qdash.common.datetime_utils import (
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

        all_results = self._task_result_repo.find(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "name": task,
                "qid": {"$in": qids},
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

    def get_historical_results(
        self,
        project_id: str,
        chip_id: str,
        task: str,
        entity_type: str,
        date: str,
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
        start_time = start_of_day(parsed_date)
        end_time = end_of_day(parsed_date)
        default_view = entity_type == "qubit"

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
        tag: str,
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

        task_results = self._task_result_repo.find_with_projection(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "tags": tag,
                "output_parameter_names": parameter,
                "start_at": {"$gte": start_at_dt, "$lte": end_at_dt},
            },
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
