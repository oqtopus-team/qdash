"""Service for task-related operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException
from qdash.api.schemas.task import (
    ExpectedResultResponse,
    InputParameterModel,
    ListTaskResponse,
    TaskKnowledgeResponse,
    TaskResponse,
    TaskResultResponse,
)
from qdash.datamodel.task_knowledge import get_task_knowledge as _lookup_knowledge
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from qdash.repository.task_definition import MongoTaskDefinitionRepository

logger = logging.getLogger(__name__)


class TaskService:
    """Service for task definition and result operations."""

    def __init__(
        self,
        task_definition_repository: MongoTaskDefinitionRepository,
    ) -> None:
        """Initialize the service with repositories."""
        self._task_def_repo = task_definition_repository

    def list_tasks(self, project_id: str, backend: str | None = None) -> ListTaskResponse:
        """List all tasks for a project.

        Parameters
        ----------
        project_id : str
            The project ID to list tasks for.
        backend : str | None
            Optional backend name to filter tasks by.

        Returns
        -------
        ListTaskResponse
            The list of tasks.

        """
        tasks = self._task_def_repo.list_by_project(project_id, backend=backend)
        return ListTaskResponse(
            tasks=[
                TaskResponse(
                    name=task["name"],
                    description=task["description"],
                    task_type=task["task_type"],
                    backend=task["backend"],
                    input_parameters={
                        name: InputParameterModel(**param)
                        for name, param in task["input_parameters"].items()
                    },
                    output_parameters={
                        name: InputParameterModel(**param)
                        for name, param in task["output_parameters"].items()
                    },
                )
                for task in tasks
            ]
        )

    def get_task_result(self, project_id: str, task_id: str) -> TaskResultResponse:
        """Get task result by task_id.

        Parameters
        ----------
        project_id : str
            The project ID.
        task_id : str
            The task ID to search for.

        Returns
        -------
        TaskResultResponse
            The task result information.

        Raises
        ------
        HTTPException
            404 if task result not found.

        """
        task_result = TaskResultHistoryDocument.find_one(
            {"project_id": project_id, "task_id": task_id}
        ).run()

        if not task_result:
            raise HTTPException(
                status_code=404, detail=f"Task result with task_id {task_id} not found"
            )

        return TaskResultResponse(
            task_id=task_result.task_id,
            task_name=task_result.name,
            qid=task_result.qid,
            status=task_result.status,
            execution_id=task_result.execution_id,
            figure_path=task_result.figure_path,
            json_figure_path=task_result.json_figure_path,
            input_parameters=task_result.input_parameters,
            output_parameters=task_result.output_parameters,
            run_parameters=task_result.run_parameters,
            start_at=task_result.start_at,
            end_at=task_result.end_at,
            elapsed_time=task_result.elapsed_time,
        )

    def get_task_knowledge(self, task_name: str) -> TaskKnowledgeResponse:
        """Get structured domain knowledge for a calibration task.

        Parameters
        ----------
        task_name : str
            The task name (e.g. "CheckT1", "CheckRabi").

        Returns
        -------
        TaskKnowledgeResponse
            Structured task knowledge.

        Raises
        ------
        HTTPException
            404 if knowledge not defined for the given task name.

        """
        knowledge = _lookup_knowledge(task_name)
        if knowledge is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_name}' does not have knowledge defined",
            )

        return TaskKnowledgeResponse(
            name=knowledge.name,
            summary=knowledge.summary,
            what_it_measures=knowledge.what_it_measures,
            physical_principle=knowledge.physical_principle,
            expected_result=ExpectedResultResponse(**knowledge.expected_result.model_dump()),
            evaluation_criteria=knowledge.evaluation_criteria,
            check_questions=knowledge.check_questions,
            failure_modes=[fm.model_dump() for fm in knowledge.failure_modes],
            tips=knowledge.tips,
            output_parameters_info=[p.model_dump() for p in knowledge.output_parameters_info],
            analysis_guide=knowledge.analysis_guide,
            prerequisites=knowledge.prerequisites,
            prompt_text=knowledge.to_prompt(),
        )
