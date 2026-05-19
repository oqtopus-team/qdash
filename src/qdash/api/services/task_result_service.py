"""Task result service for QDash API.

This module provides business logic for task result queries,
abstracting away the repository layer from the routers.
"""

from __future__ import annotations

import io
import logging
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from bunnet import SortDirection
from pymongo import ReturnDocument

from qdash.api.schemas.task_result import (
    BulkAiReviewResponse,
    LatestTaskResultResponse,
    TaskHistoryResponse,
    TaskResult,
    TimeSeriesData,
    TimeSeriesProjection,
)
from qdash.common.utils.datetime import (
    end_of_day,
    now,
    parse_date,
    parse_elapsed_time,
    start_of_day,
)
from qdash.copilot.review import (
    apply_ai_review_config as _shared_ai_review_config,
)
from qdash.copilot.review import (
    build_ai_review_context as _shared_build_ai_review_context,
)
from qdash.copilot.review import (
    forced_ai_review_markdown as _shared_forced_ai_review_markdown,
)
from qdash.copilot.review import (
    is_non_representative_mux_result as _shared_is_non_representative_mux_result,
)
from qdash.copilot.review import (
    render_ai_review_markdown as _shared_render_ai_review_markdown,
)
from qdash.copilot.review import (
    select_analysis_model as _shared_select_analysis_model,
)
from qdash.datamodel.task import ParameterModel

if TYPE_CHECKING:
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
    from qdash.repository.protocols import ChipRepository, TaskResultHistoryRepository

logger = logging.getLogger(__name__)

AI_REVIEW_ACTOR = "qdash-ai"
AI_REVIEW_HEADER = "## AI review"
AI_REVIEW_SEPARATOR = "\n\n---\n\n"
MAX_AI_REVIEW_NOTE_CHARS = 4500
AI_REVIEW_WORKERS = 2
AI_REVIEW_IN_FLIGHT_STATUSES = ("requested", "running")

_AI_REVIEW_EXECUTOR = ThreadPoolExecutor(
    max_workers=AI_REVIEW_WORKERS,
    thread_name_prefix="api-ai-review",
)


@dataclass(frozen=True)
class _BulkAiReviewSelection:
    """Resolved target entities and repository filter for a bulk AI review request."""

    qids: list[str]
    query_filter: dict[str, Any]
    response_date: str | None
    requested_task_ids: set[str]


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
        ai_review=doc.ai_review,
    )


def _truncate_ai_review_markdown(markdown: str) -> str:
    """Keep AI review note content bounded while preserving a tail marker."""
    budget = MAX_AI_REVIEW_NOTE_CHARS - 200
    if len(markdown) <= budget:
        return markdown
    return markdown[:budget].rstrip() + "\n\n[truncated]"


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

    def request_bulk_ai_review(
        self,
        *,
        project_id: str,
        chip_id: str,
        task: str,
        entity_type: str,
        date: str | None = None,
        task_ids: list[str] | None = None,
        model_override: Any | None = None,
        requested_by: str = "",
    ) -> BulkAiReviewResponse:
        """Enqueue AI review for the latest task results on a chip."""
        from starlette.exceptions import HTTPException

        if entity_type not in {"qubit", "coupling"}:
            raise HTTPException(status_code=400, detail="entity_type must be 'qubit' or 'coupling'")

        config = self._load_ai_review_config()
        skipped_reason = self._get_ai_review_skip_reason(config, task)
        if skipped_reason is not None:
            return BulkAiReviewResponse(
                chip_id=chip_id,
                task=task,
                entity_type=entity_type,
                date=None if date is None or date == "latest" else date,
                requested_count=0,
                task_ids=[],
                skipped_reason=skipped_reason,
            )
        review_config = config
        if model_override is not None:
            review_config = config.model_copy(update={"analysis_model": model_override})
        selected_model = self._select_analysis_model(review_config)
        selection = self._resolve_bulk_ai_review_selection(
            project_id=project_id,
            chip_id=chip_id,
            task=task,
            entity_type=entity_type,
            date=date,
            task_ids=task_ids,
        )
        enqueued_task_ids = self._enqueue_bulk_ai_review(
            selection=selection,
            requested_by=requested_by,
            selected_model=selected_model,
            model_override=model_override,
        )

        return BulkAiReviewResponse(
            chip_id=chip_id,
            task=task,
            entity_type=entity_type,
            date=selection.response_date,
            requested_count=len(enqueued_task_ids),
            task_ids=enqueued_task_ids,
        )

    def _resolve_bulk_ai_review_selection(
        self,
        *,
        project_id: str,
        chip_id: str,
        task: str,
        entity_type: str,
        date: str | None,
        task_ids: list[str] | None,
    ) -> _BulkAiReviewSelection:
        """Resolve the entity set and repository query for a bulk AI review request."""
        is_latest = date is None or date == "latest"
        qids = (
            self._get_entity_ids(project_id, chip_id, entity_type)
            if is_latest
            else self._get_historical_entity_ids(project_id, chip_id, entity_type, date or "")
        )

        query_filter = self._build_bulk_ai_review_query_filter(
            project_id=project_id,
            chip_id=chip_id,
            task=task,
            qids=qids,
            date=None if is_latest else (date or ""),
            task_ids=task_ids,
        )
        return _BulkAiReviewSelection(
            qids=qids,
            query_filter=query_filter,
            response_date=None if is_latest else date,
            requested_task_ids=set(task_ids or []),
        )

    @staticmethod
    def _build_bulk_ai_review_query_filter(
        *,
        project_id: str,
        chip_id: str,
        task: str,
        qids: list[str],
        date: str | None,
        task_ids: list[str] | None,
    ) -> dict[str, Any]:
        """Build the repository query for bulk AI review candidate results."""
        query_filter: dict[str, Any] = {
            "project_id": project_id,
            "chip_id": chip_id,
            "name": task,
            "qid": {"$in": qids},
            "status": {"$in": ["completed", "failed"]},
        }
        if date is not None:
            parsed_date = parse_date(date, "YYYYMMDD")
            query_filter["start_at"] = {
                "$gte": start_of_day(parsed_date),
                "$lt": end_of_day(parsed_date),
            }
        if task_ids:
            query_filter["task_id"] = {"$in": task_ids}
        return query_filter

    def _enqueue_bulk_ai_review(
        self,
        *,
        selection: _BulkAiReviewSelection,
        requested_by: str,
        selected_model: Any,
        model_override: Any | None,
    ) -> list[str]:
        """Mark and enqueue the latest review candidate for each requested entity."""
        all_results = self._task_result_repo.find(
            selection.query_filter,
            sort=[("end_at", SortDirection.DESCENDING)],
        )
        latest_results = self._organize_by_qid(all_results)

        enqueued_task_ids: list[str] = []
        for qid in selection.qids:
            doc = latest_results.get(qid)
            if doc is None:
                continue
            if selection.requested_task_ids and doc.task_id not in selection.requested_task_ids:
                continue
            if self._is_non_representative_mux_result(doc.name, doc.qid):
                continue
            claimed_doc = self._claim_ai_review_document(doc, requested_by, selected_model)
            if claimed_doc is None:
                continue
            try:
                self._submit_ai_review_document(claimed_doc, model_override)
            except Exception:
                self._set_ai_review_status(
                    doc.project_id,
                    doc.task_id,
                    "failed",
                    error="Failed to enqueue AI review",
                )
                raise
            enqueued_task_ids.append(doc.task_id)
        return enqueued_task_ids

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
    def _claim_ai_review_document(
        doc: TaskResultHistoryDocument,
        requested_by: str,
        selected_model: Any,
    ) -> TaskResultHistoryDocument | None:
        """Atomically mark a task result as requested unless another worker owns it."""
        from qdash.datamodel.note import AiReviewModel
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        ai_review = AiReviewModel(
            status="requested",
            requested_at=now(),
            requested_by=requested_by,
            model_provider=getattr(selected_model, "provider", ""),
            model_name=getattr(selected_model, "name", ""),
            completed_at=None,
            error="",
        )
        collection = TaskResultHistoryDocument.get_motor_collection()
        result = collection.find_one_and_update(
            {
                "project_id": doc.project_id,
                "task_id": doc.task_id,
                "$or": [
                    {"ai_review.status": {"$nin": list(AI_REVIEW_IN_FLIGHT_STATUSES)}},
                    {"ai_review.status": {"$exists": False}},
                ],
            },
            {"$set": {"ai_review": ai_review.model_dump()}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        return cast("TaskResultHistoryDocument", TaskResultHistoryDocument.model_validate(result))

    @staticmethod
    def _submit_ai_review_document(
        doc: TaskResultHistoryDocument,
        model_override: Any | None = None,
    ) -> None:
        """Submit API-side AI review for a previously claimed task result."""
        _AI_REVIEW_EXECUTOR.submit(
            TaskResultService._run_ai_review_for_task_result,
            doc.project_id,
            doc.chip_id,
            doc.qid,
            doc.name,
            doc.task_id,
            model_override,
        )

    @staticmethod
    def _mark_ai_review_requested(
        doc: TaskResultHistoryDocument,
        requested_by: str,
        selected_model: Any,
    ) -> None:
        """Persist that an AI review request was accepted for this task result."""
        from qdash.datamodel.note import AiReviewModel

        doc.ai_review = AiReviewModel(
            status="requested",
            requested_at=now(),
            requested_by=requested_by,
            model_provider=getattr(selected_model, "provider", ""),
            model_name=getattr(selected_model, "name", ""),
        )
        doc.save()

    @staticmethod
    def _load_ai_review_config() -> Any:
        """Load Copilot config lazily so tests can patch it."""
        from qdash.copilot.config import load_copilot_config

        return load_copilot_config()

    @staticmethod
    def _get_ai_review_skip_reason(config: Any, task: str) -> str | None:
        """Return why bulk AI review should be skipped for this task."""
        if not config.enabled:
            return "copilot_disabled"
        if not config.analysis.enabled:
            return "analysis_disabled"
        if task not in config.analysis.ai_review_tasks:
            return "task_not_configured"
        return None

    @staticmethod
    def _run_ai_review_for_task_result(
        project_id: str | None,
        chip_id: str,
        qid: str,
        task_name: str,
        task_id: str,
        model_override: Any | None = None,
    ) -> None:
        """Run AI review in the API process and upsert the dashboard note."""
        try:
            TaskResultService._set_ai_review_status(project_id, task_id, "running")
            config = TaskResultService._load_ai_review_runtime_config(model_override)
            selected_model = TaskResultService._select_analysis_model(config)
            context_bundle = TaskResultService._build_ai_review_context(
                task_name=task_name,
                chip_id=chip_id,
                qid=qid,
                task_id=task_id,
                config=config,
            )
            markdown = TaskResultService._render_ai_review_markdown(
                task_name=task_name,
                config=config,
                context_bundle=context_bundle,
            )
            TaskResultService._persist_ai_review_markdown(
                project_id=project_id,
                task_id=task_id,
                markdown=markdown,
                selected_model=selected_model,
            )
        except Exception as exc:
            logger.warning("AI review failed for task result %s: %s", task_id, exc)
            TaskResultService._set_ai_review_status(
                project_id,
                task_id,
                "failed",
                error=str(exc),
            )

    @staticmethod
    def _load_ai_review_runtime_config(model_override: Any | None) -> Any:
        """Load Copilot config and apply AI-review-specific defaults."""
        from qdash.copilot.config import load_copilot_config

        config = load_copilot_config()
        if model_override is not None:
            config = config.model_copy(update={"analysis_model": model_override})
        return TaskResultService._ai_review_config(config)

    @staticmethod
    def _build_ai_review_context(
        *,
        task_name: str,
        chip_id: str,
        qid: str,
        task_id: str,
        config: Any,
    ) -> Any:
        """Build the compact context passed to AI review analysis."""
        return _shared_build_ai_review_context(
            task_name=task_name,
            chip_id=chip_id,
            qid=qid,
            task_id=task_id,
            config=config,
        )

    @staticmethod
    def _render_ai_review_markdown(
        *,
        task_name: str,
        config: Any,
        context_bundle: Any,
    ) -> str:
        """Render markdown for a review run, using deterministic guards when possible."""
        return _shared_render_ai_review_markdown(
            task_name=task_name,
            config=config,
            context_bundle=context_bundle,
        )

    @staticmethod
    def _persist_ai_review_markdown(
        *,
        project_id: str | None,
        task_id: str,
        markdown: str,
        selected_model: Any,
    ) -> None:
        """Persist a successful review note or mark the run as failed."""
        if not markdown:
            TaskResultService._set_ai_review_status(
                project_id,
                task_id,
                "failed",
                error="AI review returned empty content",
            )
            return

        model_label = f"{selected_model.provider}/{selected_model.name}"
        TaskResultService._upsert_ai_review_note(
            project_id,
            task_id,
            markdown,
            model_label,
        )

    @staticmethod
    def _set_ai_review_status(
        project_id: str | None,
        task_id: str,
        status: str,
        *,
        error: str = "",
    ) -> None:
        """Persist AI review status without changing the requested model metadata."""
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        doc = TaskResultHistoryDocument.find_one(
            {"project_id": project_id, "task_id": task_id}
        ).run()
        if doc is None:
            logger.warning("AI review status skipped: task result not found %s", task_id)
            return

        doc.ai_review.status = status
        doc.ai_review.error = error[:500]
        if status in {"completed", "failed"}:
            doc.ai_review.completed_at = now()
        doc.save()

    @staticmethod
    def _upsert_ai_review_note(
        project_id: str | None,
        task_id: str,
        markdown: str,
        model_label: str,
    ) -> None:
        """Insert or replace the AI review section in the task-result note."""
        import re

        from qdash.common.utils.datetime import now
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        section_re = re.compile(r"^## AI review\n\n.*?(?:\n\n---\n\n|$)", re.DOTALL)
        doc = TaskResultHistoryDocument.find_one(
            {"project_id": project_id, "task_id": task_id}
        ).run()
        if doc is None:
            logger.warning("AI review note skipped: task result not found %s", task_id)
            return

        existing = doc.user_note.content or ""
        review_section = (
            f"{AI_REVIEW_HEADER}\n\n"
            f"*Reviewed by: {model_label} at {now().isoformat()}*\n\n"
            f"{_truncate_ai_review_markdown(markdown)}"
        )
        if section_re.search(existing):
            remainder = section_re.sub("", existing).strip()
            content = (
                f"{review_section}{AI_REVIEW_SEPARATOR}{remainder}" if remainder else review_section
            )
        elif existing.strip():
            content = f"{review_section}{AI_REVIEW_SEPARATOR}{existing.rstrip()}"
        else:
            content = review_section

        doc.user_note.content = content[:MAX_AI_REVIEW_NOTE_CHARS]
        doc.user_note.updated_by = AI_REVIEW_ACTOR
        doc.user_note.updated_at = now()
        doc.ai_review.status = "completed"
        doc.ai_review.completed_at = now()
        doc.ai_review.error = ""
        doc.save()

    @staticmethod
    def _select_analysis_model(config: Any) -> Any:
        """Return the effective model used for task-result analysis."""
        return _shared_select_analysis_model(config)

    @staticmethod
    def _ai_review_config(config: Any) -> Any:
        """Apply AI-review-only speed defaults without changing side-panel chat."""
        return _shared_ai_review_config(config)

    @staticmethod
    def _forced_ai_review_markdown(task_name: str, output_params: dict[str, Any]) -> str | None:
        """Apply deterministic safety guards before asking a local VLM."""
        return _shared_forced_ai_review_markdown(task_name, output_params)

    @staticmethod
    def _is_non_representative_mux_result(task_name: str, qid: str | None) -> bool:
        """Return True for copied MUX resonator results that should not be reviewed."""
        return _shared_is_non_representative_mux_result(task_name, qid)

    @staticmethod
    def create_figures_zip(
        paths: list[str],
        filename: str,
        *,
        project_id: str | None = None,
        ai_review_task_ids: list[str] | None = None,
        ai_review_bundle_task_ids: list[str] | None = None,
    ) -> tuple[io.BytesIO, str]:
        """Create a ZIP archive from the given file paths.

        Parameters
        ----------
        paths : list[str]
            Absolute paths to include in the archive.
        filename : str
            Desired archive filename (will be sanitised).

        Returns
        -------
        tuple[io.BytesIO, str]
            (zip_buffer, safe_filename)

        Raises
        ------
        HTTPException
            If no paths are given or any path does not exist.

        """
        from starlette.exceptions import HTTPException

        ai_review_entries = TaskResultService._load_ai_review_note_entries(
            project_id=project_id,
            task_ids=ai_review_task_ids or [],
        )
        ai_review_bundle_entries = TaskResultService._load_ai_review_bundle_entries(
            project_id=project_id,
            task_ids=ai_review_bundle_task_ids or [],
        )
        if not paths and not ai_review_entries and not ai_review_bundle_entries:
            raise HTTPException(status_code=400, detail="No files provided")

        missing = [p for p in paths if not Path(p).exists()]
        if missing:
            detail = f"Files not found: {', '.join(missing[:5])}"
            if len(missing) > 5:
                detail += "..."
            raise HTTPException(status_code=400, detail=detail)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in paths:
                path = Path(file_path)
                zf.write(path, path.name)
            for entry_name, note_content in ai_review_entries:
                zf.writestr(entry_name, note_content)
            for entry_name, bundle_content in ai_review_bundle_entries:
                zf.writestr(entry_name, bundle_content)
        zip_buffer.seek(0)

        safe_filename = (
            "".join(c for c in filename if c.isalnum() or c in "._-").strip() or "figures.zip"
        )
        if not safe_filename.endswith(".zip"):
            safe_filename += ".zip"

        return zip_buffer, safe_filename

    @staticmethod
    def _load_ai_review_note_entries(
        *,
        project_id: str | None,
        task_ids: list[str],
    ) -> list[tuple[str, str]]:
        """Return ZIP entries containing AI review markdown sections for task results."""
        if not task_ids:
            return []

        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        docs = TaskResultHistoryDocument.find(
            {"project_id": project_id, "task_id": {"$in": task_ids}}
        ).run()
        docs_by_task_id = {doc.task_id: doc for doc in docs}

        entries: list[tuple[str, str]] = []
        used_names: set[str] = set()
        for task_id in task_ids:
            doc = docs_by_task_id.get(task_id)
            if doc is None:
                continue
            content = TaskResultService._extract_ai_review_section(doc.user_note.content)
            if not content:
                continue
            qid = doc.qid or "unknown"
            base_name = TaskResultService._safe_zip_entry_name(
                f"ai_review/{doc.name}_{qid}_{doc.task_id}.md"
            )
            entry_name = base_name
            suffix = 2
            while entry_name in used_names:
                entry_name = base_name.replace(".md", f"_{suffix}.md")
                suffix += 1
            used_names.add(entry_name)
            entries.append((entry_name, content))
        return entries

    @staticmethod
    def _load_ai_review_bundle_entries(
        *,
        project_id: str | None,
        task_ids: list[str],
    ) -> list[tuple[str, bytes]]:
        """Return ZIP entries containing replay bundles for selected task results."""
        if not task_ids:
            return []

        from qdash.copilot.bundle.exporters.ai_review import export_ai_review_replay_bundle
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        docs = TaskResultHistoryDocument.find(
            {"project_id": project_id, "task_id": {"$in": task_ids}}
        ).run()
        docs_by_task_id = {doc.task_id: doc for doc in docs}

        entries: list[tuple[str, bytes]] = []
        used_names: set[str] = set()
        for task_id in task_ids:
            doc = docs_by_task_id.get(task_id)
            if doc is None:
                continue

            qid = doc.qid or "unknown"
            base_name = TaskResultService._safe_zip_entry_name(
                f"ai_review_bundle/{doc.name}_{qid}_{doc.task_id}.zip"
            )
            entry_name = base_name
            suffix = 2
            while entry_name in used_names:
                entry_name = base_name.replace(".zip", f"_{suffix}.zip")
                suffix += 1
            used_names.add(entry_name)

            with tempfile.TemporaryDirectory() as tmp_dir:
                bundle_path = Path(tmp_dir) / "bundle.zip"
                export_ai_review_replay_bundle(
                    task_name=doc.name,
                    chip_id=doc.chip_id,
                    qid=doc.qid or "",
                    task_id=doc.task_id,
                    trigger="chip_page",
                    output_path=bundle_path,
                    project_id=project_id,
                    execution_id=doc.execution_id,
                )
                entries.append((entry_name, bundle_path.read_bytes()))
        return entries

    @staticmethod
    def _extract_ai_review_section(content: str) -> str:
        """Extract only the AI review section from a task-result note."""
        import re

        if not content:
            return ""
        match = re.search(r"^## AI review\n\n.*?(?=\n\n---\n\n|$)", content, re.DOTALL)
        return match.group(0).strip() + "\n" if match else ""

    @staticmethod
    def _safe_zip_entry_name(name: str) -> str:
        """Sanitise an in-archive filename while preserving simple directories."""
        parts = []
        for part in name.split("/"):
            safe_part = "".join(c if c.isalnum() or c in "._-" else "_" for c in part).strip("_")
            parts.append(safe_part or "entry")
        return "/".join(parts)
