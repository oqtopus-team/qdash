"""Service for task-related operations."""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException
from qdash.common.config_loader import ConfigLoader
from qdash.api.schemas.task import (
    ExpectedResultResponse,
    InputParameterModel,
    KnowledgeCaseResponse,
    KnowledgeImageResponse,
    ListTaskKnowledgeResponse,
    ListTaskResponse,
    ReExecutionEntry,
    TaskKnowledgeResponse,
    TaskKnowledgeSummaryResponse,
    TaskResponse,
    TaskResultResponse,
)
from qdash.datamodel.task_knowledge import (
    CATEGORY_DISPLAY_NAMES,
    get_task_knowledge as _lookup_knowledge,
    list_all_task_knowledge as _list_all_knowledge,
)
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
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

        # Look up execution to get flow_name
        flow_name = ""
        exec_doc = ExecutionHistoryDocument.find_one(
            {"project_id": project_id, "execution_id": task_result.execution_id}
        ).run()
        if exec_doc:
            flow_name = exec_doc.name

        # Cross-reference: find child task results re-executed from this one
        children = TaskResultHistoryDocument.find(
            {"project_id": project_id, "source_task_id": task_id}
        ).run()
        re_executions = [
            ReExecutionEntry(
                task_id=child.task_id,
                task_name=child.name,
                qid=child.qid,
                status=child.status,
                start_at=child.start_at,
            )
            for child in children
        ]

        return TaskResultResponse(
            task_id=task_result.task_id,
            task_name=task_result.name,
            qid=task_result.qid,
            status=task_result.status,
            execution_id=task_result.execution_id,
            flow_name=flow_name,
            figure_path=task_result.figure_path,
            json_figure_path=task_result.json_figure_path,
            input_parameters=task_result.input_parameters,
            output_parameters=task_result.output_parameters,
            run_parameters=task_result.run_parameters,
            tags=task_result.tags,
            source_task_id=task_result.source_task_id,
            re_executions=re_executions,
            start_at=task_result.start_at,
            end_at=task_result.end_at,
            elapsed_time=task_result.elapsed_time,
        )

    def get_task_knowledge_markdown(self, task_name: str) -> str:
        """Get raw markdown for a task knowledge entry.

        Reads the index.md file and replaces relative image references
        with inline base64 data URIs for self-contained rendering.
        """
        knowledge = _lookup_knowledge(task_name)
        if knowledge is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_name}' does not have knowledge defined",
            )

        # Locate the markdown file via category
        knowledge_dir = ConfigLoader.get_config_dir() / "task-knowledge"
        md_path = knowledge_dir / knowledge.category / task_name / "index.md"

        if not md_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"Markdown file not found for '{task_name}'",
            )

        content = md_path.read_text(encoding="utf-8")

        # Build a lookup of relative_path -> base64_data from the registry
        img_map: dict[str, str] = {}
        for img in knowledge.images:
            if img.base64_data:
                img_map[img.relative_path] = img.base64_data

        # Replace ![alt](relative_path) with ![alt](data:image/png;base64,...)
        def _replace_img(m: re.Match[str]) -> str:
            alt = m.group(1)
            rel_path = m.group(2)
            b64 = img_map.get(rel_path)
            if b64:
                return f"![{alt}](data:image/png;base64,{b64})"
            # Try reading the file directly as fallback
            img_path = md_path.parent / rel_path
            if img_path.is_file():
                try:
                    data = img_path.read_bytes()
                    encoded = base64.b64encode(data).decode("ascii")
                    return f"![{alt}](data:image/png;base64,{encoded})"
                except OSError:
                    pass
            return m.group(0)

        content = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _replace_img, content)
        return content

    def list_task_knowledge(self) -> ListTaskKnowledgeResponse:
        """List all available task knowledge entries with summary info."""
        all_knowledge = _list_all_knowledge()
        items = [
            TaskKnowledgeSummaryResponse(
                name=k.name,
                category=k.category,
                summary=k.summary,
                failure_mode_count=len(k.failure_modes),
                case_count=len(k.cases),
                image_count=len(k.images),
                has_analysis_guide=len(k.analysis_guide) > 0,
            )
            for k in all_knowledge
        ]
        return ListTaskKnowledgeResponse(
            items=items,
            categories=CATEGORY_DISPLAY_NAMES,
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
            category=knowledge.category,
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
            images=[
                KnowledgeImageResponse(**img.model_dump())
                for img in knowledge.images
            ],
            cases=[
                KnowledgeCaseResponse(**case.model_dump())
                for case in knowledge.cases
            ],
            prompt_text=knowledge.to_prompt(),
        )
