"""Chip service for QDash API.

This module provides business logic for chip operations,
abstracting away the repository layer from the routers.
"""

import logging
from datetime import datetime
from functools import lru_cache
from typing import Any

from starlette.exceptions import HTTPException

from qdash.api.schemas.chip import (
    ChipDeletionImpactResponse,
    ChipResponse,
    CouplingResponse,
    MetricHeatmapResponse,
    MetricsSummaryResponse,
    MuxDetailResponse,
    MuxTask,
    QubitResponse,
    UpdateChipRequest,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.chip.initializer import ChipInitializer
from qdash.common.config.metrics import load_metrics_config
from qdash.common.utils.datetime import now
from qdash.datamodel.note import NoteModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_note import ChipNoteDocument
from qdash.dbmodel.cooldown import CooldownDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.coupling_history import CouplingHistoryDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.qubit_history import QubitHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.protocols import (
    ChipRepository,
    ExecutionCounterRepository,
    TaskResultHistoryRepository,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_task_names_cached() -> tuple[str, ...]:
    """Get task names from task files (cached).

    Returns a tuple for cache compatibility.
    """
    from qdash.api.dependencies import get_task_file_service
    from qdash.common.config.backend import get_default_backend

    try:
        default_backend = get_default_backend()
    except Exception as e:
        logger.warning(f"Failed to load default backend: {e}")
        default_backend = "qubex"

    service = get_task_file_service()
    backend_path = service._base_path / default_backend
    if not backend_path.exists() or not backend_path.is_dir():
        logger.warning(f"Backend directory not found: {backend_path}")
        return ()
    tasks = service._collect_tasks_from_directory(backend_path, backend_path)
    return tuple(task.name for task in tasks)


def get_task_names() -> list[str]:
    """Get task names from task files.

    Uses cached results for performance optimization.

    Returns
    -------
    list[str]
        List of task names from task files.

    """
    return list(_get_task_names_cached())


class ChipService:
    """Service for chip-related operations.

    This class encapsulates the business logic for chip operations,
    using repository abstractions for data access.

    Parameters
    ----------
    chip_repository : ChipRepository
        Repository for chip data access
    execution_counter_repository : ExecutionCounterRepository
        Repository for execution counter operations
    task_result_repository : TaskResultHistoryRepository
        Repository for task result history access

    Example
    -------
        >>> service = ChipService(
        ...     chip_repository=MongoChipRepository(),
        ...     execution_counter_repository=MongoExecutionCounterRepository(),
        ...     task_result_repository=MongoTaskResultHistoryRepository(),
        ... )
        >>> summaries = service.list_chips_summary(project_id="proj-1")

    """

    def __init__(
        self,
        chip_repository: ChipRepository,
        execution_counter_repository: ExecutionCounterRepository,
        task_result_repository: TaskResultHistoryRepository,
    ) -> None:
        """Initialize the service with repositories."""
        self._chip_repo = chip_repository
        self._counter_repo = execution_counter_repository
        self._task_result_repo = task_result_repository

    def get_chip_dates(self, project_id: str, chip_id: str) -> list[str]:
        """Get available dates for a chip.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        list[str]
            List of available date strings

        """
        return self._counter_repo.get_dates_for_chip(project_id, chip_id)

    def get_chip_size(self, project_id: str, chip_id: str) -> int | None:
        """Get the size of a chip.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        int | None
            The chip size or None if not found

        """
        chip = self._chip_repo.find_by_id(project_id, chip_id)
        if chip is None:
            return None
        return chip.size

    def get_mux_detail(
        self,
        project_id: str,
        chip_id: str,
        mux_id: int,
    ) -> MuxDetailResponse:
        """Get multiplexer details for a chip.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        mux_id : int
            The multiplexer ID

        Returns
        -------
        MuxDetailResponse
            The multiplexer details

        """
        task_names = get_task_names()
        qids = [str(mux_id * 4 + i) for i in range(4)]

        # Fetch task results
        all_results = self._task_result_repo.find_latest_by_chip_and_qids(
            project_id=project_id,
            chip_id=chip_id,
            qids=qids,
            task_names=task_names,
        )

        # Organize results by qid and task name
        task_results: dict[str, dict[str, Any]] = {}
        for result in all_results:
            qid = result.qid if hasattr(result, "qid") else ""
            name = result.name if hasattr(result, "name") else ""
            if qid not in task_results:
                task_results[qid] = {}
            if name not in task_results[qid]:
                task_results[qid][name] = result

        return self._build_mux_detail(mux_id, task_names, task_results)

    def get_all_mux_details(
        self,
        project_id: str,
        chip_id: str,
        chip_size: int,
    ) -> dict[int, MuxDetailResponse]:
        """Get all multiplexer details for a chip.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        chip_size : int
            The size of the chip

        Returns
        -------
        dict[int, MuxDetailResponse]
            Dictionary of mux_id to MuxDetailResponse

        """
        task_names = get_task_names()
        mux_num = int(chip_size // 4)
        qids = [str(i) for i in range(chip_size)]

        # Fetch all task results in one query
        all_results = self._task_result_repo.find_latest_by_chip_and_qids(
            project_id=project_id,
            chip_id=chip_id,
            qids=qids,
            task_names=task_names,
        )

        # Organize results by qid and task name
        task_results: dict[str, dict[str, Any]] = {}
        for result in all_results:
            qid = result.qid if hasattr(result, "qid") else ""
            name = result.name if hasattr(result, "name") else ""
            if qid not in task_results:
                task_results[qid] = {}
            if name not in task_results[qid]:
                task_results[qid][name] = result

        # Build mux details
        muxes: dict[int, MuxDetailResponse] = {}
        for mux_id in range(mux_num):
            muxes[mux_id] = self._build_mux_detail(mux_id, task_names, task_results)

        return muxes

    def _build_mux_detail(
        self,
        mux_id: int,
        task_names: list[str],
        task_results: dict[str, dict[str, Any]],
    ) -> MuxDetailResponse:
        """Build MuxDetailResponse from task results."""
        qids = [str(mux_id * 4 + i) for i in range(4)]
        detail: dict[str, dict[str, MuxTask]] = {}

        for qid in qids:
            detail[qid] = {}
            qid_results = task_results.get(qid, {})

            for task_name in task_names:
                result = qid_results.get(task_name)
                if result is None:
                    task_result = MuxTask(name=task_name)
                else:
                    # Get status with proper default value
                    status = getattr(result, "status", None)
                    if status is None:
                        status = "pending"
                    elif hasattr(status, "value"):
                        # Handle enum-like status
                        status = str(status.value)
                    else:
                        status = str(status)

                    task_result = MuxTask(
                        task_id=getattr(result, "task_id", None),
                        name=getattr(result, "name", task_name),
                        status=status,
                        message=getattr(result, "message", None),
                        input_parameters=getattr(result, "input_parameters", None),
                        output_parameters=getattr(result, "output_parameters", None),
                        output_parameter_names=getattr(result, "output_parameter_names", None),
                        note=getattr(result, "note", None),
                        figure_path=getattr(result, "figure_path", None),
                        json_figure_path=getattr(result, "json_figure_path", None),
                        raw_data_path=getattr(result, "raw_data_path", None),
                        start_at=getattr(result, "start_at", None),
                        end_at=getattr(result, "end_at", None),
                        elapsed_time=getattr(result, "elapsed_time", None),
                        task_type=getattr(result, "task_type", None),
                    )
                detail[qid][task_name] = task_result

        return MuxDetailResponse(mux_id=mux_id, detail=detail)

    # =========================================================================
    # Optimized methods for scalability (256+ qubits)
    # =========================================================================

    def list_chips_summary(self, project_id: str) -> list[ChipResponse]:
        """List all chips with summary information.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        list[ChipResponse]
            List of chips

        """
        summaries = self._chip_repo.list_summary_by_project(project_id)
        return [
            ChipResponse.model_validate(
                {
                    "chip_id": s["chip_id"],
                    "size": s.get("size", 64),
                    "topology_id": s.get("topology_id"),
                    "qubit_count": s.get("qubit_count", 0),
                    "coupling_count": s.get("coupling_count", 0),
                    "installed_at": s.get("installed_at"),
                    "activity_status": s.get("activity_status", "active"),
                    "current_cooldown_id": s.get("current_cooldown_id"),
                    "note": s.get("note") or {},
                }
            )
            for s in summaries
        ]

    def get_chip_summary(self, project_id: str, chip_id: str) -> ChipResponse | None:
        """Get chip details.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        ChipResponse | None
            Chip details or None if not found

        """
        summary = self._chip_repo.find_summary_by_id(project_id, chip_id)
        if summary is None:
            return None
        return ChipResponse.model_validate(
            {
                "chip_id": summary["chip_id"],
                "size": summary.get("size", 64),
                "topology_id": summary.get("topology_id"),
                "qubit_count": summary.get("qubit_count", 0),
                "coupling_count": summary.get("coupling_count", 0),
                "installed_at": summary.get("installed_at"),
                "activity_status": summary.get("activity_status", "active"),
                "current_cooldown_id": summary.get("current_cooldown_id"),
                "note": summary.get("note") or {},
            }
        )

    # ---------- chip metadata edit ----------

    def update_chip(
        self,
        *,
        project_id: str,
        chip_id: str,
        body: UpdateChipRequest,
        username: str,
    ) -> ChipResponse:
        doc = ChipDocument.find_one(
            ChipDocument.project_id == project_id,
            ChipDocument.chip_id == chip_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Chip not found")
        if body.topology_id is not None:
            try:
                ChipInitializer.ensure_topology_documents(
                    project_id=project_id,
                    chip_id=chip_id,
                    topology_id=body.topology_id,
                    size=doc.size,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            doc.topology_id = body.topology_id
        if body.activity_status is not None:
            doc.activity_status = body.activity_status
        if body.note is not None:
            doc.note = NoteModel(content=body.note, updated_by=username, updated_at=now())
        doc.system_info.update_time()
        doc.save()
        result = self.get_chip_summary(project_id, chip_id)
        if result is None:  # pragma: no cover - we just saved it
            raise HTTPException(status_code=500, detail="Failed to reload chip")
        return result

    # ---------- chip note edit ----------

    @staticmethod
    def _get_chip_document(*, project_id: str, chip_id: str) -> ChipDocument:
        doc = ChipDocument.find_one(
            ChipDocument.project_id == project_id,
            ChipDocument.chip_id == chip_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Chip not found")
        return doc

    def get_chip_note(
        self,
        *,
        project_id: str,
        chip_id: str,
        cooldown_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> NoteModel:
        from qdash.api.services.note_service import NoteService

        doc = self._get_chip_document(project_id=project_id, chip_id=chip_id)
        scope = NoteService._resolve_metric_note_scope(
            project_id=project_id,
            chip_id=chip_id,
            cooldown_id=cooldown_id,
            start_at=start_at,
            end_at=end_at,
        )
        if scope.scope_type == "global":
            return doc.note

        scoped_doc = ChipNoteDocument.find_one(
            ChipNoteDocument.project_id == project_id,
            ChipNoteDocument.chip_id == chip_id,
            ChipNoteDocument.scope_key == scope.scope_key,
        ).run()
        if scoped_doc is None:
            return NoteModel()
        return scoped_doc.note

    def upsert_chip_note(
        self,
        *,
        project_id: str,
        chip_id: str,
        content: str,
        username: str,
        cooldown_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> NoteModel:
        from qdash.api.services.note_service import NoteService

        doc = self._get_chip_document(project_id=project_id, chip_id=chip_id)
        scope = NoteService._resolve_metric_note_scope(
            project_id=project_id,
            chip_id=chip_id,
            cooldown_id=cooldown_id,
            start_at=start_at,
            end_at=end_at,
        )
        note = NoteModel(content=content, updated_by=username, updated_at=now())
        if scope.scope_type == "global":
            doc.note = note
            doc.system_info.update_time()
            doc.save()
            return note

        scoped_doc = ChipNoteDocument.find_one(
            ChipNoteDocument.project_id == project_id,
            ChipNoteDocument.chip_id == chip_id,
            ChipNoteDocument.scope_key == scope.scope_key,
        ).run()
        if scoped_doc is None:
            scoped_doc = ChipNoteDocument(
                project_id=project_id,
                chip_id=chip_id,
                note=note,
                scope_type=scope.scope_type,
                scope_key=scope.scope_key,
                cooldown_id=scope.cooldown_id,
                scope_started_at=scope.started_at,
                scope_ended_at=scope.ended_at,
                scope_source=scope.source,
            )
            scoped_doc.insert()
        else:
            scoped_doc.note = note
            scoped_doc.scope_type = scope.scope_type
            scoped_doc.cooldown_id = scope.cooldown_id
            scoped_doc.scope_started_at = scope.started_at
            scoped_doc.scope_ended_at = scope.ended_at
            scoped_doc.scope_source = scope.source
            scoped_doc.system_info.update_time()
            scoped_doc.save()
        return note

    def delete_chip_note(
        self,
        *,
        project_id: str,
        chip_id: str,
        cooldown_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> SuccessResponse:
        from qdash.api.services.note_service import NoteService

        doc = self._get_chip_document(project_id=project_id, chip_id=chip_id)
        scope = NoteService._resolve_metric_note_scope(
            project_id=project_id,
            chip_id=chip_id,
            cooldown_id=cooldown_id,
            start_at=start_at,
            end_at=end_at,
        )
        if scope.scope_type == "global":
            doc.note = NoteModel()
            doc.system_info.update_time()
            doc.save()
            return SuccessResponse(message="Chip note cleared")

        scoped_doc = ChipNoteDocument.find_one(
            ChipNoteDocument.project_id == project_id,
            ChipNoteDocument.chip_id == chip_id,
            ChipNoteDocument.scope_key == scope.scope_key,
        ).run()
        if scoped_doc is not None:
            scoped_doc.delete()
        return SuccessResponse(message="Chip note cleared")

    # ---------- chip deletion ----------

    def get_deletion_impact(self, *, project_id: str, chip_id: str) -> ChipDeletionImpactResponse:
        doc = ChipDocument.find_one(
            ChipDocument.project_id == project_id,
            ChipDocument.chip_id == chip_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Chip not found")

        scope = {"project_id": project_id, "chip_id": chip_id}
        qubit_count = QubitDocument.find(scope).count()
        coupling_count = CouplingDocument.find(scope).count()
        task_result_count = TaskResultHistoryDocument.find(scope).count()
        qubit_history_count = QubitHistoryDocument.find(scope).count()
        coupling_history_count = CouplingHistoryDocument.find(scope).count()
        cooldowns_referencing = CooldownDocument.find(
            {"project_id": project_id, "chip_ids": chip_id}
        ).count()

        return ChipDeletionImpactResponse(
            chip_id=chip_id,
            qubits=qubit_count,
            couplings=coupling_count,
            task_results=task_result_count,
            qubit_history_snapshots=qubit_history_count,
            coupling_history_snapshots=coupling_history_count,
            cooldowns_referencing=cooldowns_referencing,
            can_delete_safely=(qubit_count == 0 and coupling_count == 0),
        )

    def delete_chip(self, *, project_id: str, chip_id: str, force: bool) -> SuccessResponse:
        doc = ChipDocument.find_one(
            ChipDocument.project_id == project_id,
            ChipDocument.chip_id == chip_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Chip not found")

        scope = {"project_id": project_id, "chip_id": chip_id}
        qubit_count = QubitDocument.find(scope).count()
        coupling_count = CouplingDocument.find(scope).count()

        if not force and (qubit_count > 0 or coupling_count > 0):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Chip has {qubit_count} qubit(s) and {coupling_count} coupling(s). "
                    "Pass force=true to cascade-delete them, or remove them first."
                ),
            )

        # Cascade: hard-delete qubit + coupling docs (history retained for audit)
        QubitDocument.get_motor_collection().delete_many(scope)
        CouplingDocument.get_motor_collection().delete_many(scope)

        # Detach this chip from any cool-downs that reference it
        CooldownDocument.get_motor_collection().update_many(
            {"project_id": project_id, "chip_ids": chip_id},
            {"$pull": {"chip_ids": chip_id}},
        )

        doc.delete()
        return SuccessResponse(message=f"Chip {chip_id} deleted")

    def list_qubits(
        self,
        project_id: str,
        chip_id: str,
        limit: int = 50,
        offset: int = 0,
        qids: list[str] | None = None,
    ) -> tuple[list[QubitResponse], int]:
        """List qubits with pagination.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        limit : int
            Maximum number of qubits to return
        offset : int
            Number of qubits to skip
        qids : list[str] | None
            Optional list of specific qubit IDs to fetch

        Returns
        -------
        tuple[list[QubitResponse], int]
            List of qubits and total count

        """
        qubits, total = self._chip_repo.list_qubits(
            project_id=project_id,
            chip_id=chip_id,
            limit=limit,
            offset=offset,
            qids=qids,
        )
        return (
            [
                QubitResponse.model_validate(
                    {
                        "qid": q["qid"],
                        "chip_id": q["chip_id"],
                        "status": q.get("status", "pending"),
                        "data": q.get("data", {}),
                        "note": q.get("note") or {},
                        "metric_notes": q.get("metric_notes") or {},
                    }
                )
                for q in qubits
            ],
            total,
        )

    def get_qubit(self, project_id: str, chip_id: str, qid: str) -> QubitResponse | None:
        """Get a single qubit by ID.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        qid : str
            The qubit identifier

        Returns
        -------
        QubitResponse | None
            Qubit data or None if not found

        """
        qubit = self._chip_repo.find_qubit(project_id, chip_id, qid)
        if qubit is None:
            return None
        return QubitResponse.model_validate(
            {
                "qid": qubit["qid"],
                "chip_id": qubit["chip_id"],
                "status": qubit.get("status", "pending"),
                "data": qubit.get("data", {}),
                "note": qubit.get("note") or {},
                "metric_notes": qubit.get("metric_notes") or {},
            }
        )

    def list_couplings(
        self,
        project_id: str,
        chip_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[CouplingResponse], int]:
        """List couplings with pagination.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        limit : int
            Maximum number of couplings to return
        offset : int
            Number of couplings to skip

        Returns
        -------
        tuple[list[CouplingResponse], int]
            List of couplings and total count

        """
        couplings, total = self._chip_repo.list_couplings(
            project_id=project_id,
            chip_id=chip_id,
            limit=limit,
            offset=offset,
        )
        return (
            [
                CouplingResponse.model_validate(
                    {
                        "qid": c["qid"],
                        "chip_id": c["chip_id"],
                        "status": c.get("status", "pending"),
                        "data": c.get("data", {}),
                        "note": c.get("note") or {},
                        "metric_notes": c.get("metric_notes") or {},
                    }
                )
                for c in couplings
            ],
            total,
        )

    def get_coupling(
        self, project_id: str, chip_id: str, coupling_id: str
    ) -> CouplingResponse | None:
        """Get a single coupling by ID.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        coupling_id : str
            The coupling identifier

        Returns
        -------
        CouplingResponse | None
            Coupling data or None if not found

        """
        coupling = self._chip_repo.find_coupling(project_id, chip_id, coupling_id)
        if coupling is None:
            return None
        return CouplingResponse.model_validate(
            {
                "qid": coupling["qid"],
                "chip_id": coupling["chip_id"],
                "status": coupling.get("status", "pending"),
                "data": coupling.get("data", {}),
                "note": coupling.get("note") or {},
                "metric_notes": coupling.get("metric_notes") or {},
            }
        )

    def get_metrics_summary(self, project_id: str, chip_id: str) -> MetricsSummaryResponse | None:
        """Get aggregated metrics summary.

        Uses MongoDB aggregation pipeline for efficient DB-side computation.
        Metric keys are loaded dynamically from metrics.yaml config.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        MetricsSummaryResponse | None
            Aggregated metrics or None if chip not found

        """
        # Get metric keys from config (cached)
        metrics_config = load_metrics_config()
        metric_keys = list(metrics_config.qubit_metrics.keys())

        summary = self._chip_repo.aggregate_metrics_summary(project_id, chip_id, metric_keys)
        if summary is None:
            return None
        return MetricsSummaryResponse(
            chip_id=chip_id,
            qubit_count=summary.get("qubit_count", 0),
            averages=summary.get("averages", {}),
        )

    def get_metric_heatmap(
        self, project_id: str, chip_id: str, metric: str
    ) -> MetricHeatmapResponse | None:
        """Get heatmap data for a single metric.

        Uses MongoDB aggregation pipeline to extract only the needed metric values.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        metric : str
            The metric name

        Returns
        -------
        MetricHeatmapResponse | None
            Metric values keyed by qubit/coupling ID

        """
        # Determine if this is a qubit or coupling metric
        coupling_metrics = {"zx90_gate_fidelity", "bell_state_fidelity", "static_zz_interaction"}
        is_coupling = metric in coupling_metrics

        result = self._chip_repo.aggregate_metric_heatmap(
            project_id=project_id,
            chip_id=chip_id,
            metric=metric,
            is_coupling=is_coupling,
        )
        if result is None:
            return None

        return MetricHeatmapResponse(
            chip_id=chip_id,
            metric=metric,
            values=result.get("values", {}),
            unit=result.get("unit"),
        )
