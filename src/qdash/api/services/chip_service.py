"""Chip service for QDash API.

This module provides business logic for chip operations,
abstracting away the repository layer from the routers.
"""

import logging
from typing import Any

from qdash.api.schemas.chip import ChipResponse, MuxDetailResponse, MuxTask
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
        >>> chips = service.list_chips(project_id="proj-1")

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

    def list_chips(self, project_id: str) -> list[ChipResponse]:
        """List all chips in a project.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        list[ChipResponse]
            List of chip responses

        """
        chips = self._chip_repo.list_by_project(project_id)
        return [
            ChipResponse(
                chip_id=chip.chip_id,
                size=chip.size,
                topology_id=chip.topology_id,
                qubits=chip.qubits,
                couplings=chip.couplings,
                installed_at=chip.installed_at,
            )
            for chip in chips
        ]

    def get_chip(self, project_id: str, chip_id: str) -> ChipResponse | None:
        """Get a chip by ID.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        ChipResponse | None
            The chip response or None if not found

        """
        chip = self._chip_repo.find_by_id(project_id, chip_id)
        if chip is None:
            return None
        return ChipResponse(
            chip_id=chip.chip_id,
            size=chip.size,
            topology_id=chip.topology_id,
            qubits=chip.qubits,
            couplings=chip.couplings,
            installed_at=chip.installed_at,
        )

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
