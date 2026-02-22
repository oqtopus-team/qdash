"""Issue router for QDash API."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.issue import (
    IssueAiReplyRequest,
    IssueCreate,
    IssueResponse,
    IssueUpdate,
    ListIssuesResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.common.paths import CALIB_DATA_BASE
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.issue import IssueDocument
from starlette.exceptions import HTTPException

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

router = APIRouter()
public_router = APIRouter()

ISSUES_IMAGE_DIR = CALIB_DATA_BASE / "issues"
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
CONTENT_TYPE_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
FILENAME_PATTERN = re.compile(r"^[0-9a-f\-]{36}\.(png|jpg|gif|webp)$")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    skip: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="Max items to return")] = 50,
    task_id: Annotated[str | None, Query(description="Filter by task ID")] = None,
    is_closed: Annotated[
        bool | None,
        Query(
            description="Filter by closed status. Default false (open only). Set to true for closed, or omit/null for all."
        ),
    ] = False,
) -> ListIssuesResponse:
    """List all root issues across the project, with reply counts."""
    query: dict[str, object] = {
        "project_id": ctx.project_id,
        "parent_id": None,
    }
    if task_id:
        query["task_id"] = task_id
    if is_closed is not None:
        query["is_closed"] = is_closed

    total = IssueDocument.find(query).count()

    docs = (
        IssueDocument.find(query).sort("-system_info.created_at").skip(skip).limit(limit).to_list()
    )

    # Collect root issue IDs to get reply counts
    root_ids = [str(doc.id) for doc in docs]

    # Aggregate reply counts for these root issues
    reply_counts: dict[str, int] = {}
    if root_ids:
        pipeline = [
            {
                "$match": {
                    "project_id": ctx.project_id,
                    "parent_id": {"$in": root_ids},
                }
            },
            {"$group": {"_id": "$parent_id", "count": {"$sum": 1}}},
        ]
        results = IssueDocument.aggregate(pipeline).to_list()
        for item in results:
            reply_counts[item["_id"]] = item["count"]

    issues = [
        IssueResponse(
            id=str(doc.id),
            task_id=doc.task_id,
            username=doc.username,
            title=doc.title,
            content=doc.content,
            created_at=doc.system_info.created_at,
            updated_at=doc.system_info.updated_at,
            parent_id=doc.parent_id,
            reply_count=reply_counts.get(str(doc.id), 0),
            is_closed=doc.is_closed,
            is_ai_reply=doc.is_ai_reply,
        )
        for doc in docs
    ]

    return ListIssuesResponse(
        issues=issues,
        total=total,
        skip=skip,
        limit=limit,
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
) -> IssueResponse:
    """Get a single root issue by its ID, including reply count."""
    from bson import ObjectId

    doc = IssueDocument.find_one(
        {
            "_id": ObjectId(issue_id),
            "project_id": ctx.project_id,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Count replies if this is a root issue
    reply_count = 0
    if doc.parent_id is None:
        reply_count = IssueDocument.find(
            {
                "project_id": ctx.project_id,
                "parent_id": issue_id,
            },
        ).count()

    return IssueResponse(
        id=str(doc.id),
        task_id=doc.task_id,
        username=doc.username,
        title=doc.title,
        content=doc.content,
        created_at=doc.system_info.created_at,
        updated_at=doc.system_info.updated_at,
        parent_id=doc.parent_id,
        reply_count=reply_count,
        is_closed=doc.is_closed,
        is_ai_reply=doc.is_ai_reply,
    )


@router.get(
    "/issues/{issue_id}/replies",
    summary="List replies for an issue",
    operation_id="getIssueReplies",
    response_model=list[IssueResponse],
)
def get_issue_replies(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> list[IssueResponse]:
    """List all replies to a specific issue, sorted by creation time ascending."""
    docs = (
        IssueDocument.find(
            {
                "project_id": ctx.project_id,
                "parent_id": issue_id,
            },
        )
        .sort("system_info.created_at")
        .to_list()
    )

    return [
        IssueResponse(
            id=str(doc.id),
            task_id=doc.task_id,
            username=doc.username,
            title=doc.title,
            content=doc.content,
            created_at=doc.system_info.created_at,
            updated_at=doc.system_info.updated_at,
            parent_id=doc.parent_id,
            is_closed=doc.is_closed,
            is_ai_reply=doc.is_ai_reply,
        )
        for doc in docs
    ]


@router.delete(
    "/issues/{issue_id}",
    summary="Delete an issue",
    operation_id="deleteIssue",
    response_model=SuccessResponse,
)
def delete_issue(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> SuccessResponse:
    """Delete an issue. Only the author can delete their own issue."""
    from bson import ObjectId

    doc = IssueDocument.find_one(
        {
            "_id": ObjectId(issue_id),
            "project_id": ctx.project_id,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    if doc.username != ctx.user.username:
        raise HTTPException(status_code=403, detail="You can only delete your own issues")

    doc.delete()

    return SuccessResponse(message="Issue deleted")


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
) -> IssueResponse:
    """Update an issue's content (and title for root issues). Only the author can edit."""
    from bson import ObjectId

    doc = IssueDocument.find_one(
        {
            "_id": ObjectId(issue_id),
            "project_id": ctx.project_id,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    if doc.username != ctx.user.username:
        raise HTTPException(status_code=403, detail="You can only edit your own issues")

    # Only update title for root issues
    if doc.parent_id is None and body.title is not None:
        doc.title = body.title

    doc.content = body.content
    doc.system_info.update_time()
    doc.save()

    return IssueResponse(
        id=str(doc.id),
        task_id=doc.task_id,
        username=doc.username,
        title=doc.title,
        content=doc.content,
        created_at=doc.system_info.created_at,
        updated_at=doc.system_info.updated_at,
        parent_id=doc.parent_id,
        is_closed=doc.is_closed,
        is_ai_reply=doc.is_ai_reply,
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
) -> SuccessResponse:
    """Close an issue thread. Only the author or project owner can close."""
    from bson import ObjectId

    doc = IssueDocument.find_one(
        {
            "_id": ObjectId(issue_id),
            "project_id": ctx.project_id,
            "parent_id": None,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    if doc.username != ctx.user.username and ctx.role != ProjectRole.OWNER:
        raise HTTPException(
            status_code=403, detail="Only the author or project owner can close this issue"
        )

    doc.is_closed = True
    doc.save()

    return SuccessResponse(message="Issue closed")


@router.patch(
    "/issues/{issue_id}/reopen",
    summary="Reopen an issue",
    operation_id="reopenIssue",
    response_model=SuccessResponse,
)
def reopen_issue(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> SuccessResponse:
    """Reopen a closed issue thread. Only the author or project owner can reopen."""
    from bson import ObjectId

    doc = IssueDocument.find_one(
        {
            "_id": ObjectId(issue_id),
            "project_id": ctx.project_id,
            "parent_id": None,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    if doc.username != ctx.user.username and ctx.role != ProjectRole.OWNER:
        raise HTTPException(
            status_code=403, detail="Only the author or project owner can reopen this issue"
        )

    doc.is_closed = False
    doc.save()

    return SuccessResponse(message="Issue reopened")


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
) -> list[IssueResponse]:
    """List all issues for a task result, sorted by creation time ascending."""
    docs = (
        IssueDocument.find(
            {
                "project_id": ctx.project_id,
                "task_id": task_id,
            },
        )
        .sort("system_info.created_at")
        .to_list()
    )

    return [
        IssueResponse(
            id=str(doc.id),
            task_id=doc.task_id,
            username=doc.username,
            title=doc.title,
            content=doc.content,
            created_at=doc.system_info.created_at,
            updated_at=doc.system_info.updated_at,
            parent_id=doc.parent_id,
            is_closed=doc.is_closed,
            is_ai_reply=doc.is_ai_reply,
        )
        for doc in docs
    ]


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
) -> IssueResponse:
    """Create a new issue on a task result."""
    # Validate: root issues must have a title
    if body.parent_id is None and not body.title:
        raise HTTPException(status_code=422, detail="Title is required for root issues")

    doc = IssueDocument(
        project_id=ctx.project_id,
        task_id=task_id,
        username=ctx.user.username,
        title=body.title if body.parent_id is None else None,
        content=body.content,
        parent_id=body.parent_id,
    )
    doc.insert()

    return IssueResponse(
        id=str(doc.id),
        task_id=doc.task_id,
        username=doc.username,
        title=doc.title,
        content=doc.content,
        created_at=doc.system_info.created_at,
        updated_at=doc.system_info.updated_at,
        parent_id=doc.parent_id,
        is_closed=doc.is_closed,
        is_ai_reply=doc.is_ai_reply,
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
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {file.content_type}. Allowed: png, jpeg, gif, webp",
        )

    data = await file.read()
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image exceeds 5MB size limit")

    ext = CONTENT_TYPE_TO_EXT[file.content_type]
    filename = f"{uuid4()}{ext}"
    dest = ISSUES_IMAGE_DIR / filename

    ISSUES_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    return {"url": f"/api/issues/images/{filename}"}


@public_router.get(
    "/issues/images/{filename}",
    summary="Serve an issue image",
    include_in_schema=False,
)
def get_issue_image(filename: str) -> FileResponse:
    """Serve an uploaded issue image."""
    if not FILENAME_PATTERN.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = ISSUES_IMAGE_DIR / filename
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    ext = Path(filename).suffix.lstrip(".")
    media_types = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(filepath, media_type=media_type)


# =============================================================================
# AI reply endpoint
# =============================================================================

_AI_TOOL_LABELS: dict[str, str] = {
    "get_qubit_params": "キュービットパラメータを取得中",
    "get_latest_task_result": "最新タスク結果を取得中",
    "get_task_history": "タスク履歴を取得中",
    "get_parameter_timeseries": "パラメータ時系列を取得中",
    "execute_python_analysis": "Python分析コードを実行中",
    "get_chip_summary": "チップサマリーを取得中",
    "get_coupling_params": "カップリングパラメータを取得中",
    "get_execution_history": "実行履歴を取得中",
    "compare_qubits": "キュービット比較データを取得中",
    "get_chip_topology": "チップトポロジーを取得中",
    "search_task_results": "タスク結果を検索中",
    "get_calibration_notes": "キャリブレーションノートを取得中",
    "get_parameter_lineage": "パラメータ履歴を取得中",
    "get_provenance_lineage_graph": "プロベナンス系譜グラフを取得中",
}

_AI_STATUS_LABELS: dict[str, str] = {
    "thinking": "AIが考え中...",
}


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/issues/{issue_id}/ai-reply/stream", include_in_schema=False)
async def issue_ai_reply_stream(
    issue_id: str,
    body: IssueAiReplyRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
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
        from bson import ObjectId
        from qdash.api.lib.copilot_config import load_copilot_config

        config = load_copilot_config()
        if not config.enabled:
            yield _sse_event("error", {"step": "init", "detail": "Copilot is not enabled"})
            return

        # Load root issue
        yield _sse_event("status", {"step": "load_issue", "message": "Issueを読み込み中..."})
        await asyncio.sleep(0)

        root_doc = IssueDocument.find_one(
            {"_id": ObjectId(issue_id), "project_id": ctx.project_id}
        ).run()
        if root_doc is None:
            yield _sse_event("error", {"step": "load_issue", "detail": "Issue not found"})
            return

        # Build conversation history from thread
        yield _sse_event("status", {"step": "build_history", "message": "スレッド履歴を構築中..."})
        await asyncio.sleep(0)

        # Get the root issue's parent_id to determine if this IS the root
        actual_root_id = issue_id if root_doc.parent_id is None else root_doc.parent_id

        reply_docs = (
            IssueDocument.find({"project_id": ctx.project_id, "parent_id": actual_root_id})
            .sort("system_info.created_at")
            .to_list()
        )

        conversation_history: list[dict[str, str]] = []
        # Add root issue content
        if root_doc.parent_id is None:
            conversation_history.append({"role": "user", "content": root_doc.content})
        # Add replies — but exclude the latest user reply that matches
        # body.user_message to avoid duplication (run_chat adds it as the
        # final user turn automatically).
        for reply_doc in reply_docs:
            role = "assistant" if reply_doc.is_ai_reply else "user"
            conversation_history.append({"role": role, "content": reply_doc.content})

        # Pop the last entry if it is the same user message we'll pass to run_chat
        if (
            conversation_history
            and conversation_history[-1]["role"] == "user"
            and conversation_history[-1]["content"] == body.user_message
        ):
            conversation_history.pop()

        # Strip @qdash mentions from conversation history so the LLM
        # doesn't see the UI-only trigger text in prior turns either.
        for entry in conversation_history:
            if entry["role"] == "user":
                entry["content"] = re.sub(r"@qdash\b\s*", "", entry["content"]).strip()

        # Resolve chip_id / qid from task result
        yield _sse_event(
            "status", {"step": "load_context", "message": "タスクコンテキストを取得中..."}
        )
        await asyncio.sleep(0)

        chip_id: str | None = None
        qid: str | None = None
        task_id = root_doc.task_id

        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        task_doc = TaskResultHistoryDocument.find_one({"task_id": task_id}).run()
        if task_doc:
            chip_id = task_doc.chip_id
            qid = task_doc.qid

        # Resolve default chip_id if not available from task result
        if not chip_id:
            from qdash.dbmodel.chip import ChipDocument

            chip_doc = ChipDocument.find_one({}, sort=[("installed_at", -1)]).run()
            if chip_doc:
                chip_id = str(chip_doc.chip_id)

        # Optionally load qubit params
        qubit_params: dict[str, Any] = {}
        if chip_id and qid:
            from qdash.dbmodel.qubit import QubitDocument

            qubit_doc = QubitDocument.find_one({"chip_id": chip_id, "qid": qid}).run()
            if qubit_doc:
                import math

                def _sanitize(obj: Any) -> Any:
                    if isinstance(obj, float):
                        return None if not math.isfinite(obj) else obj
                    if isinstance(obj, dict):
                        return {k: _sanitize(v) for k, v in obj.items()}
                    if isinstance(obj, list):
                        return [_sanitize(v) for v in obj]
                    return obj

                qubit_params = _sanitize(dict(qubit_doc.data))

        # Build tool executors
        from qdash.api.routers.copilot import _build_tool_executors

        tool_executors = _build_tool_executors()

        # Run AI chat
        # Strip @qdash mention from user message before sending to LLM.
        # The mention is a UI trigger, not an instruction for the model.
        clean_message = re.sub(r"@qdash\b\s*", "", body.user_message).strip()
        if not clean_message:
            clean_message = "この Issue について教えてください"
        logger.info("AI reply: original=%r, clean=%r", body.user_message, clean_message)

        yield _sse_event("status", {"step": "run_chat", "message": "AIが応答中..."})
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def on_tool_call(name: str, args: dict[str, Any]) -> None:
            label = _AI_TOOL_LABELS.get(name, name)
            await queue.put({"step": "tool_call", "tool": name, "message": f"{label}..."})

        async def on_status(status: str) -> None:
            label = _AI_STATUS_LABELS.get(status, status)
            await queue.put({"step": status, "message": label})

        try:
            from qdash.api.lib.copilot_agent import blocks_to_markdown, run_chat

            chat_task = asyncio.create_task(
                run_chat(
                    user_message=clean_message,
                    config=config,
                    chip_id=chip_id,
                    qid=qid,
                    qubit_params=qubit_params if qubit_params else None,
                    conversation_history=conversation_history,
                    tool_executors=tool_executors,
                    on_tool_call=on_tool_call,
                    on_status=on_status,
                )
            )

            while not chat_task.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.3)
                    yield _sse_event("status", event)
                except asyncio.TimeoutError:  # noqa: PERF203
                    yield ":\n\n"

            result = chat_task.result()
        except ImportError:
            yield _sse_event(
                "error",
                {
                    "step": "run_chat",
                    "detail": "openai is not installed. Install with: pip install openai",
                },
            )
            return
        except Exception as e:
            logger.exception("AI reply failed")
            yield _sse_event("error", {"step": "run_chat", "detail": f"AI reply failed: {e}"})
            return

        # Drain remaining queue events
        while not queue.empty():
            event = queue.get_nowait()
            yield _sse_event("status", event)

        # Convert blocks to markdown and save as issue reply
        yield _sse_event("status", {"step": "save_reply", "message": "返信を保存中..."})
        await asyncio.sleep(0)

        logger.info(
            "AI reply raw result: blocks=%d, keys=%s",
            len(result.get("blocks", [])),
            list(result.keys()),
        )
        markdown_content = blocks_to_markdown(result)
        if not markdown_content:
            logger.warning("blocks_to_markdown returned empty, full result=%s", result)
            # Last-resort fallback: dump the raw result as JSON so the
            # frontend MarkdownContent can still render it.
            try:
                raw_json = json.dumps(result, indent=2, ensure_ascii=False)
                markdown_content = f"```json\n{raw_json}\n```"
            except Exception:
                yield _sse_event(
                    "error",
                    {"step": "save_reply", "detail": "AIが空の応答を返しました"},
                )
                return

        ai_doc = IssueDocument(
            project_id=ctx.project_id,
            task_id=root_doc.task_id,
            username="qdash-ai",
            title=None,
            content=markdown_content,
            parent_id=actual_root_id,
            is_ai_reply=True,
        )
        ai_doc.insert()

        saved_response = IssueResponse(
            id=str(ai_doc.id),
            task_id=ai_doc.task_id,
            username=ai_doc.username,
            title=ai_doc.title,
            content=ai_doc.content,
            created_at=ai_doc.system_info.created_at,
            updated_at=ai_doc.system_info.updated_at,
            parent_id=ai_doc.parent_id,
            is_closed=ai_doc.is_closed,
            is_ai_reply=ai_doc.is_ai_reply,
        )

        yield _sse_event("status", {"step": "complete", "message": "完了"})
        yield _sse_event("result", saved_response.model_dump(mode="json"))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
