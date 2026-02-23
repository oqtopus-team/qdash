"""Issue router for QDash API."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from qdash.api.dependencies import get_issue_service  # noqa: TCH002
from qdash.api.lib.ai_labels import STATUS_LABELS as _AI_STATUS_LABELS
from qdash.api.lib.ai_labels import TOOL_LABELS as _AI_TOOL_LABELS
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.lib.sse import SSETaskBridge, sse_event
from qdash.api.schemas.issue import (
    IssueAiReplyRequest,
    IssueCreate,
    IssueResponse,
    IssueUpdate,
    ListIssuesResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.issue_service import IssueService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

router = APIRouter()
public_router = APIRouter()

logger = logging.getLogger(__name__)


# =============================================================================
# Issue endpoints under /issues
# =============================================================================


@router.get(
    "/issues",
    summary="List all issues across tasks",
    operation_id="listIssues",
    response_model=ListIssuesResponse,
)
def list_issues(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueService, Depends(get_issue_service)],
    skip: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="Max items to return")] = 50,
    task_id: Annotated[str | None, Query(description="Filter by task ID")] = None,
    is_closed: Annotated[
        bool | None,
        Query(
            description=(
                "Filter by closed status. Default false (open only). "
                "Set to true for closed, or omit/null for all."
            )
        ),
    ] = False,
) -> ListIssuesResponse:
    """List all root issues across the project, with reply counts."""
    return service.list_issues(
        project_id=ctx.project_id,
        skip=skip,
        limit=limit,
        task_id=task_id,
        is_closed=is_closed,
    )


@router.get(
    "/issues/{issue_id}",
    summary="Get a single issue by ID",
    operation_id="getIssue",
    response_model=IssueResponse,
)
def get_issue(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueService, Depends(get_issue_service)],
) -> IssueResponse:
    """Get a single root issue by its ID, including reply count."""
    return service.get_issue(project_id=ctx.project_id, issue_id=issue_id)


@router.get(
    "/issues/{issue_id}/replies",
    summary="List replies for an issue",
    operation_id="getIssueReplies",
    response_model=list[IssueResponse],
)
def get_issue_replies(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueService, Depends(get_issue_service)],
) -> list[IssueResponse]:
    """List all replies to a specific issue, sorted by creation time ascending."""
    return service.get_issue_replies(project_id=ctx.project_id, issue_id=issue_id)


@router.delete(
    "/issues/{issue_id}",
    summary="Delete an issue",
    operation_id="deleteIssue",
    response_model=SuccessResponse,
)
def delete_issue(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueService, Depends(get_issue_service)],
) -> SuccessResponse:
    """Delete an issue. Only the author can delete their own issue."""
    return service.delete_issue(
        project_id=ctx.project_id,
        issue_id=issue_id,
        username=ctx.user.username,
    )


@router.patch(
    "/issues/{issue_id}",
    summary="Update an issue",
    operation_id="updateIssue",
    response_model=IssueResponse,
)
def update_issue(
    issue_id: str,
    body: IssueUpdate,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueService, Depends(get_issue_service)],
) -> IssueResponse:
    """Update an issue's content (and title for root issues). Only the author can edit."""
    return service.update_issue(
        project_id=ctx.project_id,
        issue_id=issue_id,
        username=ctx.user.username,
        title=body.title,
        content=body.content,
    )


@router.patch(
    "/issues/{issue_id}/close",
    summary="Close an issue",
    operation_id="closeIssue",
    response_model=SuccessResponse,
)
def close_issue(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueService, Depends(get_issue_service)],
) -> SuccessResponse:
    """Close an issue thread. Only the author or project owner can close."""
    return service.close_issue(
        project_id=ctx.project_id,
        issue_id=issue_id,
        username=ctx.user.username,
        role=ctx.role,
    )


@router.patch(
    "/issues/{issue_id}/reopen",
    summary="Reopen an issue",
    operation_id="reopenIssue",
    response_model=SuccessResponse,
)
def reopen_issue(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueService, Depends(get_issue_service)],
) -> SuccessResponse:
    """Reopen a closed issue thread. Only the author or project owner can reopen."""
    return service.reopen_issue(
        project_id=ctx.project_id,
        issue_id=issue_id,
        username=ctx.user.username,
        role=ctx.role,
    )


# =============================================================================
# Issue endpoints under /task-results/{task_id}/issues
# =============================================================================


@router.get(
    "/task-results/{task_id}/issues",
    summary="List issues for a task result",
    operation_id="getTaskResultIssues",
    response_model=list[IssueResponse],
)
def get_task_result_issues(
    task_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueService, Depends(get_issue_service)],
) -> list[IssueResponse]:
    """List all issues for a task result, sorted by creation time ascending."""
    return service.get_task_result_issues(project_id=ctx.project_id, task_id=task_id)


@router.post(
    "/task-results/{task_id}/issues",
    summary="Create an issue on a task result",
    operation_id="createIssue",
    response_model=IssueResponse,
    status_code=201,
)
def create_issue(
    task_id: str,
    body: IssueCreate,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueService, Depends(get_issue_service)],
) -> IssueResponse:
    """Create a new issue on a task result."""
    return service.create_issue(
        project_id=ctx.project_id,
        task_id=task_id,
        username=ctx.user.username,
        title=body.title,
        content=body.content,
        parent_id=body.parent_id,
    )


# =============================================================================
# Image upload / serving endpoints
# =============================================================================


@router.post(
    "/issues/upload-image",
    summary="Upload an image for an issue",
    operation_id="uploadIssueImage",
    include_in_schema=False,
)
async def upload_issue_image(
    file: UploadFile,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> dict[str, str]:
    """Upload an image to attach to an issue. Returns the image URL."""
    data = await file.read()
    url = IssueService.upload_image(data, file.content_type or "")
    return {"url": url}


@public_router.get(
    "/issues/images/{filename}",
    summary="Serve an issue image",
    include_in_schema=False,
)
def get_issue_image(filename: str) -> FileResponse:
    """Serve an uploaded issue image."""
    filepath, media_type = IssueService.get_image_path(filename)
    return FileResponse(filepath, media_type=media_type)


# =============================================================================
# AI reply endpoint
# =============================================================================


@router.post("/issues/{issue_id}/ai-reply/stream", include_in_schema=False)
async def issue_ai_reply_stream(
    issue_id: str,
    body: IssueAiReplyRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueService, Depends(get_issue_service)],
) -> StreamingResponse:
    """SSE endpoint that generates an AI reply in an issue thread.

    1. Loads copilot config, checks enabled
    2. Fetches root issue and thread replies as conversation history
    3. Resolves chip_id/qid from the task result
    4. Calls run_chat() with tool executors
    5. Saves AI reply as IssueDocument
    6. Streams status events and final result via SSE
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        from qdash.api.lib.copilot_config import load_copilot_config

        config = load_copilot_config()
        if not config.enabled:
            yield sse_event("error", {"step": "init", "detail": "Copilot is not enabled"})
            return

        # Load root issue and build context
        yield sse_event("status", {"step": "load_issue", "message": "Issueを読み込み中..."})
        await asyncio.sleep(0)

        ai_context = service.build_ai_reply_context(
            project_id=ctx.project_id,
            issue_id=issue_id,
        )

        if ai_context["root_doc"] is None:
            yield sse_event("error", {"step": "load_issue", "detail": "Issue not found"})
            return

        # Build conversation history from thread
        yield sse_event("status", {"step": "build_history", "message": "スレッド履歴を構築中..."})
        await asyncio.sleep(0)

        conversation_history: list[dict[str, str]] = ai_context["conversation_history"]
        actual_root_id: str = ai_context["actual_root_id"]
        chip_id: str | None = ai_context["chip_id"]
        qid: str | None = ai_context["qid"]
        qubit_params: dict[str, Any] = ai_context["qubit_params"]
        task_id: str = ai_context["task_id"]

        # Deduplicate last message if it matches user_message
        conversation_history = IssueService.deduplicate_last_message(
            conversation_history,
            body.user_message,
        )

        # Resolve chip_id / qid context
        yield sse_event(
            "status", {"step": "load_context", "message": "タスクコンテキストを取得中..."}
        )
        await asyncio.sleep(0)

        # Build tool executors
        from qdash.api.services.copilot_data_service import CopilotDataService

        copilot_data_svc = CopilotDataService()
        tool_executors = copilot_data_svc.build_tool_executors()

        # Strip @qdash mention from user message before sending to LLM
        clean_message = IssueService.strip_mention(body.user_message)
        if not clean_message:
            clean_message = "この Issue について教えてください"
        logger.info("AI reply: original=%r, clean=%r", body.user_message, clean_message)

        yield sse_event("status", {"step": "run_chat", "message": "AIが応答中..."})
        bridge = SSETaskBridge(
            tool_labels=_AI_TOOL_LABELS,
            status_labels=_AI_STATUS_LABELS,
        )

        try:
            from qdash.api.lib.copilot_agent import run_chat

            coro = partial(
                run_chat,
                user_message=clean_message,
                config=config,
                chip_id=chip_id,
                qid=qid,
                qubit_params=qubit_params if qubit_params else None,
                conversation_history=conversation_history,
                tool_executors=tool_executors,
            )

            result: dict[str, Any] = {}
            async for event in bridge.drain(coro):
                if isinstance(event, str):
                    yield event
                else:
                    result = event
        except ImportError:
            yield sse_event(
                "error",
                {
                    "step": "run_chat",
                    "detail": "openai is not installed. Install with: pip install openai",
                },
            )
            return
        except Exception as e:
            logger.exception("AI reply failed")
            yield sse_event("error", {"step": "run_chat", "detail": f"AI reply failed: {e}"})
            return

        # Convert blocks to markdown and save as issue reply
        yield sse_event("status", {"step": "save_reply", "message": "返信を保存中..."})
        await asyncio.sleep(0)

        logger.info(
            "AI reply raw result: blocks=%d, keys=%s",
            len(result.get("blocks", [])),
            list(result.keys()),
        )
        markdown_content = IssueService.format_ai_response_as_markdown(result)
        if not markdown_content:
            yield sse_event(
                "error",
                {"step": "save_reply", "detail": "AIが空の応答を返しました"},
            )
            return

        saved_response = service.save_ai_reply(
            project_id=ctx.project_id,
            task_id=task_id,
            parent_id=actual_root_id,
            content=markdown_content,
        )

        yield sse_event("status", {"step": "complete", "message": "完了"})
        yield sse_event("result", saved_response.model_dump(mode="json"))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
