"""Service for task-related operations."""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING

from fastapi import HTTPException

from qdash.api.schemas.task import (
    InputParameterModel,
    KnowledgeExampleResponse,
    KnowledgeFigureResponse,
    ListTaskKnowledgeResponse,
    ListTaskResponse,
    ReExecutionEntry,
    TaskKnowledgeResponse,
    TaskKnowledgeSummaryResponse,
    TaskReferenceResponse,
    TaskResponse,
    TaskResultResponse,
)
from qdash.datamodel.task_knowledge import (
    CATEGORY_DISPLAY_NAMES,
    KnowledgeFigure,
)
from qdash.datamodel.task_knowledge import (
    get_task_knowledge as _lookup_knowledge,
)
from qdash.datamodel.task_knowledge import (
    list_all_task_knowledge as _list_all_knowledge,
)
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from qdash.datamodel.task_knowledge import TaskKnowledge
    from qdash.repository.task_definition import MongoTaskDefinitionRepository

logger = logging.getLogger(__name__)


_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def knowledge_response(knowledge: TaskKnowledge) -> TaskKnowledgeResponse:
    """A task's knowledge as served to the UI and the runtime: figures inlined, prompt rendered."""

    def _figure(fig: KnowledgeFigure) -> KnowledgeFigureResponse:
        loaded = knowledge.load_figure_base64(fig.path)
        data, mime = loaded if loaded else ("", "")
        return KnowledgeFigureResponse(alt=fig.alt, path=fig.path, base64_data=data, mime_type=mime)

    return TaskKnowledgeResponse(
        name=knowledge.name,
        category=knowledge.category,
        background=knowledge.background,
        figures=[_figure(f) for f in knowledge.figures],
        examples=[
            KnowledgeExampleResponse(
                **example.model_dump(exclude={"figures"}),
                figures=[_figure(f) for f in example.figures],
                label=example.label(),
            )
            for example in knowledge.examples
        ],
        prompt_text=knowledge.to_prompt(),
        reference=TaskReferenceResponse(**knowledge.reference().model_dump()),
    )


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
            chip_id=task_result.chip_id,
            status=task_result.status,
            execution_id=task_result.execution_id,
            flow_name=flow_name,
            user_id=task_result.user_id,
            username=task_result.username,
            figure_path=task_result.figure_path,
            json_figure_path=task_result.json_figure_path,
            raw_data_path=task_result.raw_data_path,
            input_parameters=task_result.input_parameters,
            output_parameters=task_result.output_parameters,
            output_parameter_names=task_result.output_parameter_names,
            run_parameters=task_result.run_parameters,
            note=task_result.note,
            tags=task_result.tags,
            message=task_result.message,
            stack_trace=task_result.stack_trace,
            source_task_id=task_result.source_task_id,
            re_executions=re_executions,
            start_at=task_result.start_at,
            end_at=task_result.end_at,
            elapsed_time=(
                timedelta(seconds=task_result.elapsed_time)
                if task_result.elapsed_time is not None
                else None
            ),
        )

    def get_task_knowledge_markdown(self, task_name: str) -> str:
        """The task's ``index.md`` with its figures inlined as data URIs.

        Falls back to the rendered prompt when the markdown file is not on disk.
        """
        knowledge = _lookup_knowledge(task_name)
        if knowledge is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_name}' does not have knowledge defined",
            )
        task_dir = knowledge.task_dir()
        md_path = task_dir / "index.md" if task_dir else None
        content = (
            md_path.read_text(encoding="utf-8")
            if md_path and md_path.is_file()
            else knowledge.to_prompt()
        )

        def _inline(match: re.Match[str]) -> str:
            alt, rel_path = match.group(1), match.group(2)
            if rel_path.startswith(("http://", "https://", "data:")):
                return match.group(0)
            loaded = knowledge.load_figure_base64(rel_path)
            if loaded is None:
                return match.group(0)
            data, mime = loaded
            return f"![{alt}](data:{mime};base64,{data})"

        return _MARKDOWN_IMAGE_RE.sub(_inline, content)

    def list_task_knowledge(self) -> ListTaskKnowledgeResponse:
        """List all available task knowledge entries with summary info."""
        items = [
            TaskKnowledgeSummaryResponse(
                name=k.name,
                category=k.category,
                summary=k.summary,
                example_count=len(k.examples),
                figure_count=len(k.figures) + sum(len(e.figures) for e in k.examples),
            )
            for k in _list_all_knowledge()
        ]
        return ListTaskKnowledgeResponse(items=items, categories=CATEGORY_DISPLAY_NAMES)

    def get_task_knowledge(self, task_name: str) -> TaskKnowledgeResponse:
        """Structured knowledge of a task, figures inlined, plus the rendered prompt.

        Raises 404 when the task has no knowledge.
        """
        knowledge = _lookup_knowledge(task_name)
        if knowledge is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_name}' does not have knowledge defined",
            )

        return knowledge_response(knowledge)
