"""Chip service for QDash API.

This module provides business logic for chip operations,
abstracting away the repository layer from the routers.
"""

import logging
from typing import Any

from qdash.api.schemas.chip import (
    ChipResponse,
    CouplingResponse,
    MetricHeatmapResponse,
    MetricsSummaryResponse,
    MuxDetailResponse,
    MuxTask,
    QubitResponse,
)
from qdash.repository.protocols import (
    ChipRepository,
    ExecutionCounterRepository,
    TaskResultHistoryRepository,
)

logger = logging.getLogger(__name__)


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
        task_names: list[str],
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
        task_names : list[str]
            List of task names to include

        Returns
        -------
        MuxDetailResponse
            The multiplexer details

        """
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
        task_names: list[str],
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
        task_names : list[str]
            List of task names to include

        Returns
        -------
        dict[int, MuxDetailResponse]
            Dictionary of mux_id to MuxDetailResponse

        """
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
            ChipResponse(
                chip_id=s["chip_id"],
                size=s.get("size", 64),
                topology_id=s.get("topology_id"),
                qubit_count=s.get("qubit_count", 0),
                coupling_count=s.get("coupling_count", 0),
                installed_at=s.get("installed_at"),
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
        return ChipResponse(
            chip_id=summary["chip_id"],
            size=summary.get("size", 64),
            topology_id=summary.get("topology_id"),
            qubit_count=summary.get("qubit_count", 0),
            coupling_count=summary.get("coupling_count", 0),
            installed_at=summary.get("installed_at"),
        )

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
                QubitResponse(
                    qid=q["qid"],
                    chip_id=q["chip_id"],
                    status=q.get("status", "pending"),
                    data=q.get("data", {}),
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
        return QubitResponse(
            qid=qubit["qid"],
            chip_id=qubit["chip_id"],
            status=qubit.get("status", "pending"),
            data=qubit.get("data", {}),
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
                CouplingResponse(
                    qid=c["qid"],
                    chip_id=c["chip_id"],
                    status=c.get("status", "pending"),
                    data=c.get("data", {}),
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
        return CouplingResponse(
            qid=coupling["qid"],
            chip_id=coupling["chip_id"],
            status=coupling.get("status", "pending"),
            data=coupling.get("data", {}),
        )

    def get_metrics_summary(self, project_id: str, chip_id: str) -> MetricsSummaryResponse | None:
        """Get aggregated metrics summary.

        Uses MongoDB aggregation pipeline for efficient DB-side computation.

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
        summary = self._chip_repo.aggregate_metrics_summary(project_id, chip_id)
        if summary is None:
            return None
        return MetricsSummaryResponse(
            chip_id=chip_id,
            qubit_count=summary.get("qubit_count", 0),
            calibrated_count=summary.get("calibrated_count", 0),
            avg_t1=summary.get("avg_t1"),
            avg_t2_echo=summary.get("avg_t2_echo"),
            avg_t2_star=summary.get("avg_t2_star"),
            avg_qubit_frequency=summary.get("avg_qubit_frequency"),
            avg_readout_fidelity=summary.get("avg_readout_fidelity"),
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
