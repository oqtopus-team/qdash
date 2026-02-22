"""Copilot API router for AI assistant configuration and analysis.

This router provides endpoints for copilot configuration
and LLM-powered calibration result analysis.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from qdash.api.dependencies import get_copilot_data_service  # noqa: TCH002
from qdash.api.lib.ai_labels import STATUS_LABELS, TOOL_LABELS
from qdash.api.lib.copilot_analysis import (
    AnalysisResponse,
    AnalyzeRequest,
    ChatRequest,
    TaskAnalysisContext,
)
from qdash.api.lib.copilot_config import load_copilot_config
from qdash.api.lib.sse import sse_event
from qdash.api.services.copilot_data_service import CopilotDataService  # noqa: TCH002
from qdash.datamodel.task_knowledge import get_task_knowledge

router = APIRouter()
public_router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/config",
    summary="Get Copilot configuration",
    operation_id="getCopilotConfig",
)
async def get_copilot_config() -> dict[str, Any]:
    """Get Copilot configuration for the metrics assistant.

    Retrieves the Copilot configuration from YAML, including:
    - enabled: Whether Copilot is enabled
    - evaluation_metrics: Which metrics to use for multi-metric evaluation
    - scoring: Thresholds for good/excellent ratings per metric
    - system_prompt: The AI assistant's system prompt
    - initial_message: The initial greeting message

    Returns
    -------
    dict[str, Any]
        Copilot configuration dictionary

    """
    config = load_copilot_config()
    return dict(config.model_dump())


@public_router.get("/expected-image", include_in_schema=False)
def get_expected_image(task_name: str, index: int) -> Response:
    """Serve a reference/expected image from TaskKnowledge by index."""
    knowledge = get_task_knowledge(task_name)
    if not knowledge or not knowledge.images or index < 0 or index >= len(knowledge.images):
        raise HTTPException(status_code=404, detail="Image not found")
    img = knowledge.images[index]
    if not img.base64_data:
        raise HTTPException(status_code=404, detail="Image has no data")
    return Response(content=base64.b64decode(img.base64_data), media_type="image/png")


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    summary="Analyze calibration result with AI",
    operation_id="analyzeCopilot",
)
async def analyze_task_result(
    request: AnalyzeRequest,
    copilot_data_service: Annotated[CopilotDataService, Depends(get_copilot_data_service)],
) -> dict[str, Any]:
    """Analyze a calibration task result using LLM.

    Constructs a rich context from task knowledge, qubit parameters,
    and experimental data, then sends it to the configured LLM for analysis.

    Parameters
    ----------
    request : AnalyzeRequest
        The analysis request containing task info, IDs, and user message.

    Returns
    -------
    AnalysisResponse
        Structured analysis from the LLM.

    """
    config = load_copilot_config()
    if not config.enabled:
        raise HTTPException(status_code=503, detail="Copilot is not enabled")

    # Resolve task knowledge
    knowledge = get_task_knowledge(request.task_name)
    knowledge_prompt = knowledge.to_prompt() if knowledge else f"Task: {request.task_name}"

    # Load qubit parameters
    qubit_params = copilot_data_service.load_qubit_params(request.chip_id, request.qid)

    # Load task result parameters
    task_result = copilot_data_service.load_task_result(request.task_id)
    input_params = task_result.get("input_parameters", {}) if task_result else {}
    output_params = task_result.get("output_parameters", {}) if task_result else {}
    run_params = task_result.get("run_parameters", {}) if task_result else {}

    # Load dynamic context from TaskKnowledge.related_context
    history_results: list[dict[str, Any]] = []
    neighbor_qubit_params: dict[str, dict[str, Any]] = {}
    coupling_params: dict[str, dict[str, Any]] = {}
    if knowledge and knowledge.related_context:
        for rc in knowledge.related_context:
            if rc.type == "history":
                history_results = copilot_data_service.load_task_history(
                    request.task_name, request.chip_id, request.qid, rc.last_n
                )
            elif rc.type == "neighbor_qubits":
                neighbor_qubit_params = copilot_data_service.load_neighbor_qubit_params(
                    request.chip_id, request.qid, rc.params
                )
            elif rc.type == "coupling":
                coupling_params = copilot_data_service.load_coupling_params(
                    request.chip_id, request.qid, rc.params
                )

    # Auto-load experiment figure if not provided and multimodal is enabled
    image_base64 = request.image_base64
    expected_images: list[tuple[str, str]] = []
    figure_paths: list[str] = task_result.get("figure_path", []) if task_result else []
    if config.analysis.multimodal:
        if not image_base64 and task_result:
            image_base64 = copilot_data_service.load_figure_as_base64(figure_paths)
        expected_images = copilot_data_service.collect_expected_images(knowledge)

    # Build analysis context
    context = TaskAnalysisContext(
        task_knowledge_prompt=knowledge_prompt,
        chip_id=request.chip_id,
        qid=request.qid,
        qubit_params=qubit_params,
        input_parameters=input_params,
        output_parameters=output_params,
        run_parameters=run_params,
        history_results=history_results,
        neighbor_qubit_params=neighbor_qubit_params,
        coupling_params=coupling_params,
    )

    # Build tool executors for function calling
    tool_executors = copilot_data_service.build_tool_executors()

    # Run the analysis agent
    try:
        from qdash.api.lib.copilot_agent import run_analysis

        result = await run_analysis(
            context=context,
            user_message=request.message,
            config=config,
            image_base64=image_base64,
            expected_images=expected_images,
            conversation_history=request.conversation_history,
            tool_executors=tool_executors,
        )
        result["images_sent"] = {
            "experiment_figure": bool(image_base64),
            "experiment_figure_paths": figure_paths if image_base64 else [],
            "expected_images": [
                {"alt_text": alt, "index": i} for i, (_, alt) in enumerate(expected_images)
            ],
            "task_name": request.task_name,
        }
        return result
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="openai is not installed. Install with: pip install openai",
        )
    except Exception as e:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.post("/analyze/stream", include_in_schema=False)
async def analyze_task_result_stream(
    request: AnalyzeRequest,
    copilot_data_service: Annotated[CopilotDataService, Depends(get_copilot_data_service)],
) -> StreamingResponse:
    """SSE streaming version of analyze_task_result.

    Sends status events as each step progresses, then a final result or error event.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        config = load_copilot_config()
        if not config.enabled:
            yield sse_event("error", {"step": "init", "detail": "Copilot is not enabled"})
            return

        # Step 1: Resolve task knowledge
        yield sse_event(
            "status", {"step": "resolve_knowledge", "message": "タスク知識を読み込み中..."}
        )
        await asyncio.sleep(0)
        knowledge = get_task_knowledge(request.task_name)
        knowledge_prompt = knowledge.to_prompt() if knowledge else f"Task: {request.task_name}"

        # Step 2: Load qubit parameters
        yield sse_event(
            "status", {"step": "load_qubit_params", "message": "キュービットパラメータを取得中..."}
        )
        await asyncio.sleep(0)
        qubit_params = copilot_data_service.load_qubit_params(request.chip_id, request.qid)

        # Step 3: Load task result
        yield sse_event("status", {"step": "load_task_result", "message": "タスク結果を取得中..."})
        await asyncio.sleep(0)
        task_result = copilot_data_service.load_task_result(request.task_id)
        input_params = task_result.get("input_parameters", {}) if task_result else {}
        output_params = task_result.get("output_parameters", {}) if task_result else {}
        run_params = task_result.get("run_parameters", {}) if task_result else {}

        # Load dynamic context from related_context
        history_results: list[dict[str, Any]] = []
        neighbor_qubit_params: dict[str, dict[str, Any]] = {}
        coupling_params: dict[str, dict[str, Any]] = {}
        if knowledge and knowledge.related_context:
            for rc in knowledge.related_context:
                if rc.type == "history":
                    history_results = copilot_data_service.load_task_history(
                        request.task_name, request.chip_id, request.qid, rc.last_n
                    )
                elif rc.type == "neighbor_qubits":
                    neighbor_qubit_params = copilot_data_service.load_neighbor_qubit_params(
                        request.chip_id, request.qid, rc.params
                    )
                elif rc.type == "coupling":
                    coupling_params = copilot_data_service.load_coupling_params(
                        request.chip_id, request.qid, rc.params
                    )

        # Auto-load experiment figure if not provided and multimodal is enabled
        image_base64 = request.image_base64
        expected_images: list[tuple[str, str]] = []
        figure_paths: list[str] = task_result.get("figure_path", []) if task_result else []
        if config.analysis.multimodal:
            if not image_base64 and task_result:
                image_base64 = copilot_data_service.load_figure_as_base64(figure_paths)
            expected_images = copilot_data_service.collect_expected_images(knowledge)

        # Emit image loading status
        has_experiment = bool(image_base64)
        num_expected = len(expected_images)
        if has_experiment and num_expected > 0:
            img_msg = f"実験結果画像と参照画像{num_expected}枚をAIに送信中..."
        elif has_experiment:
            img_msg = "実験結果画像をAIに送信中..."
        elif num_expected > 0:
            img_msg = f"参照画像{num_expected}枚をAIに送信中..."
        else:
            img_msg = None
        if img_msg:
            yield sse_event("status", {"step": "load_images", "message": img_msg})
            await asyncio.sleep(0)

        # Step 4: Build context
        yield sse_event(
            "status", {"step": "build_context", "message": "分析コンテキストを構築中..."}
        )
        await asyncio.sleep(0)
        context = TaskAnalysisContext(
            task_knowledge_prompt=knowledge_prompt,
            chip_id=request.chip_id,
            qid=request.qid,
            qubit_params=qubit_params,
            input_parameters=input_params,
            output_parameters=output_params,
            run_parameters=run_params,
            history_results=history_results,
            neighbor_qubit_params=neighbor_qubit_params,
            coupling_params=coupling_params,
        )

        # Step 5: Run analysis with tool progress streaming
        yield sse_event("status", {"step": "run_analysis", "message": "AIが分析中..."})
        tool_executors = copilot_data_service.build_tool_executors()

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def on_tool_call(name: str, args: dict[str, Any]) -> None:
            label = TOOL_LABELS.get(name, name)
            await queue.put({"step": "tool_call", "tool": name, "message": f"{label}..."})

        async def on_status(status: str) -> None:
            label = STATUS_LABELS.get(status, status)
            await queue.put({"step": status, "message": label})

        try:
            from qdash.api.lib.copilot_agent import run_analysis

            analysis_task = asyncio.create_task(
                run_analysis(
                    context=context,
                    user_message=request.message,
                    config=config,
                    image_base64=image_base64,
                    expected_images=expected_images,
                    conversation_history=request.conversation_history,
                    tool_executors=tool_executors,
                    on_tool_call=on_tool_call,
                    on_status=on_status,
                )
            )

            while not analysis_task.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.3)
                    yield sse_event("status", event)
                except asyncio.TimeoutError:  # noqa: PERF203
                    # Send SSE comment as heartbeat to keep connection alive
                    yield ":\n\n"

            result = analysis_task.result()
        except ImportError:
            yield sse_event(
                "error",
                {
                    "step": "run_analysis",
                    "detail": "openai is not installed. Install with: pip install openai",
                },
            )
            return
        except Exception as e:
            logger.exception("Analysis failed")
            yield sse_event("error", {"step": "run_analysis", "detail": f"Analysis failed: {e}"})
            return

        # Drain any remaining events in the queue
        while not queue.empty():
            event = queue.get_nowait()
            yield sse_event("status", event)

        # Inject images_sent metadata
        result["images_sent"] = {
            "experiment_figure": has_experiment,
            "experiment_figure_paths": figure_paths if has_experiment else [],
            "expected_images": [
                {"alt_text": alt, "index": i} for i, (_, alt) in enumerate(expected_images)
            ],
            "task_name": request.task_name,
        }

        # Step 6: Complete
        yield sse_event("status", {"step": "complete", "message": "分析完了"})
        yield sse_event("result", result)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/stream", include_in_schema=False)
async def chat_stream(
    request: ChatRequest,
    copilot_data_service: Annotated[CopilotDataService, Depends(get_copilot_data_service)],
) -> StreamingResponse:
    """SSE streaming generic chat endpoint.

    Does not require task context. Optionally accepts chip_id/qid for scoped queries.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        config = load_copilot_config()
        if not config.enabled:
            yield sse_event("error", {"step": "init", "detail": "Copilot is not enabled"})
            return

        # Step 1: Load config and resolve default chip_id
        yield sse_event("status", {"step": "load_config", "message": "設定を読み込み中..."})
        await asyncio.sleep(0)

        chip_id = request.chip_id
        qid = request.qid

        # Resolve default chip_id if not provided
        if not chip_id:
            chip_id = copilot_data_service.load_default_chip_id()

        # Step 2: Optionally load qubit params
        qubit_params: dict[str, Any] = {}
        if chip_id and qid:
            yield sse_event(
                "status",
                {"step": "load_qubit_params", "message": "キュービットパラメータを取得中..."},
            )
            await asyncio.sleep(0)
            qubit_params = copilot_data_service.load_qubit_params(chip_id, qid)

        # Step 3: Run chat with tool progress streaming
        yield sse_event("status", {"step": "run_chat", "message": "AIが応答中..."})
        tool_executors = copilot_data_service.build_tool_executors()

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def on_tool_call(name: str, args: dict[str, Any]) -> None:
            label = TOOL_LABELS.get(name, name)
            await queue.put({"step": "tool_call", "tool": name, "message": f"{label}..."})

        async def on_status(status: str) -> None:
            label = STATUS_LABELS.get(status, status)
            await queue.put({"step": status, "message": label})

        try:
            from qdash.api.lib.copilot_agent import run_chat

            chat_task = asyncio.create_task(
                run_chat(
                    user_message=request.message,
                    config=config,
                    chip_id=chip_id,
                    qid=qid,
                    qubit_params=qubit_params if qubit_params else None,
                    image_base64=request.image_base64,
                    conversation_history=request.conversation_history,
                    tool_executors=tool_executors,
                    on_tool_call=on_tool_call,
                    on_status=on_status,
                )
            )

            while not chat_task.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.3)
                    yield sse_event("status", event)
                except asyncio.TimeoutError:  # noqa: PERF203
                    # Send SSE comment as heartbeat to keep connection alive
                    yield ":\n\n"

            result = chat_task.result()
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
            logger.exception("Chat failed")
            yield sse_event("error", {"step": "run_chat", "detail": f"Chat failed: {e}"})
            return

        # Drain any remaining events in the queue
        while not queue.empty():
            event = queue.get_nowait()
            yield sse_event("status", event)

        # Step 4: Complete
        yield sse_event("status", {"step": "complete", "message": "完了"})
        yield sse_event("result", result)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
