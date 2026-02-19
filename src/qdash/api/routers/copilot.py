"""Copilot API router for AI assistant configuration and analysis.

This router provides endpoints for copilot configuration
and LLM-powered calibration result analysis.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bunnet import SortDirection
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
from qdash.api.lib.copilot_analysis import (
    AnalysisResponse,
    AnalyzeRequest,
    ChatRequest,
    TaskAnalysisContext,
)
from qdash.api.lib.copilot_config import load_copilot_config
from qdash.datamodel.task_knowledge import get_task_knowledge

router = APIRouter()
public_router = APIRouter()
logger = logging.getLogger(__name__)

TOOL_LABELS: dict[str, str] = {
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
}

STATUS_LABELS: dict[str, str] = {
    "thinking": "AIが考え中...",
}


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
async def analyze_task_result(request: AnalyzeRequest) -> dict[str, Any]:
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
    qubit_params = _load_qubit_params(request.chip_id, request.qid)

    # Load task result parameters
    task_result = _load_task_result(request.task_id)
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
                history_results = _load_task_history(
                    request.task_name, request.chip_id, request.qid, rc.last_n
                )
            elif rc.type == "neighbor_qubits":
                neighbor_qubit_params = _load_neighbor_qubit_params(
                    request.chip_id, request.qid, rc.params
                )
            elif rc.type == "coupling":
                coupling_params = _load_coupling_params(request.chip_id, request.qid, rc.params)

    # Auto-load experiment figure if not provided and multimodal is enabled
    image_base64 = request.image_base64
    expected_images: list[tuple[str, str]] = []
    figure_paths: list[str] = task_result.get("figure_path", []) if task_result else []
    if config.analysis.multimodal:
        if not image_base64 and task_result:
            image_base64 = _load_figure_as_base64(figure_paths)
        expected_images = _collect_expected_images(knowledge)

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
    tool_executors = _build_tool_executors()

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


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/analyze/stream", include_in_schema=False)
async def analyze_task_result_stream(request: AnalyzeRequest) -> StreamingResponse:
    """SSE streaming version of analyze_task_result.

    Sends status events as each step progresses, then a final result or error event.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        config = load_copilot_config()
        if not config.enabled:
            yield _sse_event("error", {"step": "init", "detail": "Copilot is not enabled"})
            return

        # Step 1: Resolve task knowledge
        yield _sse_event(
            "status", {"step": "resolve_knowledge", "message": "タスク知識を読み込み中..."}
        )
        await asyncio.sleep(0)
        knowledge = get_task_knowledge(request.task_name)
        knowledge_prompt = knowledge.to_prompt() if knowledge else f"Task: {request.task_name}"

        # Step 2: Load qubit parameters
        yield _sse_event(
            "status", {"step": "load_qubit_params", "message": "キュービットパラメータを取得中..."}
        )
        await asyncio.sleep(0)
        qubit_params = _load_qubit_params(request.chip_id, request.qid)

        # Step 3: Load task result
        yield _sse_event("status", {"step": "load_task_result", "message": "タスク結果を取得中..."})
        await asyncio.sleep(0)
        task_result = _load_task_result(request.task_id)
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
                    history_results = _load_task_history(
                        request.task_name, request.chip_id, request.qid, rc.last_n
                    )
                elif rc.type == "neighbor_qubits":
                    neighbor_qubit_params = _load_neighbor_qubit_params(
                        request.chip_id, request.qid, rc.params
                    )
                elif rc.type == "coupling":
                    coupling_params = _load_coupling_params(request.chip_id, request.qid, rc.params)

        # Auto-load experiment figure if not provided and multimodal is enabled
        image_base64 = request.image_base64
        expected_images: list[tuple[str, str]] = []
        figure_paths: list[str] = task_result.get("figure_path", []) if task_result else []
        if config.analysis.multimodal:
            if not image_base64 and task_result:
                image_base64 = _load_figure_as_base64(figure_paths)
            expected_images = _collect_expected_images(knowledge)

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
            yield _sse_event("status", {"step": "load_images", "message": img_msg})
            await asyncio.sleep(0)

        # Step 4: Build context
        yield _sse_event(
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
        yield _sse_event("status", {"step": "run_analysis", "message": "AIが分析中..."})
        tool_executors = _build_tool_executors()

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
                    yield _sse_event("status", event)
                except asyncio.TimeoutError:  # noqa: PERF203
                    # Send SSE comment as heartbeat to keep connection alive
                    yield ":\n\n"

            result = analysis_task.result()
        except ImportError:
            yield _sse_event(
                "error",
                {
                    "step": "run_analysis",
                    "detail": "openai is not installed. Install with: pip install openai",
                },
            )
            return
        except Exception as e:
            logger.exception("Analysis failed")
            yield _sse_event("error", {"step": "run_analysis", "detail": f"Analysis failed: {e}"})
            return

        # Drain any remaining events in the queue
        while not queue.empty():
            event = queue.get_nowait()
            yield _sse_event("status", event)

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
        yield _sse_event("status", {"step": "complete", "message": "分析完了"})
        yield _sse_event("result", result)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/stream", include_in_schema=False)
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """SSE streaming generic chat endpoint.

    Does not require task context. Optionally accepts chip_id/qid for scoped queries.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        config = load_copilot_config()
        if not config.enabled:
            yield _sse_event("error", {"step": "init", "detail": "Copilot is not enabled"})
            return

        # Step 1: Load config and resolve default chip_id
        yield _sse_event("status", {"step": "load_config", "message": "設定を読み込み中..."})
        await asyncio.sleep(0)

        chip_id = request.chip_id
        qid = request.qid

        # Resolve default chip_id if not provided
        if not chip_id:
            chip_id = _load_default_chip_id()

        # Step 2: Optionally load qubit params
        qubit_params: dict[str, Any] = {}
        if chip_id and qid:
            yield _sse_event(
                "status",
                {"step": "load_qubit_params", "message": "キュービットパラメータを取得中..."},
            )
            await asyncio.sleep(0)
            qubit_params = _load_qubit_params(chip_id, qid)

        # Step 3: Run chat with tool progress streaming
        yield _sse_event("status", {"step": "run_chat", "message": "AIが応答中..."})
        tool_executors = _build_tool_executors()

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
                    yield _sse_event("status", event)
                except asyncio.TimeoutError:  # noqa: PERF203
                    # Send SSE comment as heartbeat to keep connection alive
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
            logger.exception("Chat failed")
            yield _sse_event("error", {"step": "run_chat", "detail": f"Chat failed: {e}"})
            return

        # Drain any remaining events in the queue
        while not queue.empty():
            event = queue.get_nowait()
            yield _sse_event("status", event)

        # Step 4: Complete
        yield _sse_event("status", {"step": "complete", "message": "完了"})
        yield _sse_event("result", result)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _load_default_chip_id() -> str | None:
    """Load the most recently installed chip_id from DB."""
    from qdash.dbmodel.chip import ChipDocument

    doc = ChipDocument.find_one({}, sort=[("installed_at", -1)]).run()
    if doc is None:
        return None
    return str(doc.chip_id)


def _load_qubit_params(chip_id: str, qid: str) -> dict[str, Any]:
    """Load current qubit parameters from DB."""
    from qdash.dbmodel.qubit import QubitDocument

    doc = QubitDocument.find_one({"chip_id": chip_id, "qid": qid}).run()
    if doc is None:
        return {}
    result: dict[str, Any] = _sanitize_for_json(dict(doc.data))
    return result


def _load_task_result(task_id: str) -> dict[str, Any] | None:
    """Load task result from DB."""
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    doc = TaskResultHistoryDocument.find_one({"task_id": task_id}).run()
    if doc is None:
        return None
    return {
        "input_parameters": doc.input_parameters or {},
        "output_parameters": doc.output_parameters or {},
        "run_parameters": getattr(doc, "run_parameters", {}) or {},
        "figure_path": getattr(doc, "figure_path", []) or [],
    }


def _load_figure_as_base64(figure_paths: list[str]) -> str | None:
    """Read the first existing PNG file from figure_paths and return base64."""
    for fp in figure_paths:
        p = Path(fp)
        if p.is_file() and p.suffix.lower() == ".png":
            return base64.b64encode(p.read_bytes()).decode("ascii")
    return None


def _collect_expected_images(
    knowledge: Any,
) -> list[tuple[str, str]]:
    """Collect expected reference images from TaskKnowledge.

    Returns list of (base64_data, alt_text) for images with embedded data.
    """
    if knowledge is None or not knowledge.images:
        return []
    return [(img.base64_data, img.alt_text) for img in knowledge.images if img.base64_data]


def _load_task_history(
    task_name: str, chip_id: str, qid: str, last_n: int = 5
) -> list[dict[str, Any]]:
    """Load recent completed results for the same task+qubit."""
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    docs = (
        TaskResultHistoryDocument.find(
            {"chip_id": chip_id, "name": task_name, "qid": qid, "status": "completed"}
        )
        .sort([("start_at", SortDirection.DESCENDING)])
        .limit(last_n)
        .run()
    )
    results: list[dict[str, Any]] = []
    for doc in docs:
        results.append(
            {
                "output_parameters": doc.output_parameters or {},
                "start_at": doc.start_at.isoformat() if doc.start_at else None,
                "execution_id": doc.execution_id,
            }
        )
    return results


def _load_neighbor_qubit_params(
    chip_id: str, qid: str, param_names: list[str]
) -> dict[str, dict[str, Any]]:
    """Load specified parameters from neighboring qubits via topology."""
    from qdash.dbmodel.chip import ChipDocument
    from qdash.dbmodel.qubit import QubitDocument

    chip = ChipDocument.find_one({"chip_id": chip_id}).run()
    if chip is None or chip.topology_id is None:
        return {}

    from qdash.common.topology_config import load_topology

    topology = load_topology(chip.topology_id)

    # Find neighbor qubit IDs from coupling pairs
    try:
        qid_int = int(qid)
    except ValueError:
        return {}

    neighbors: set[int] = set()
    for q1, q2 in topology.couplings:
        if q1 == qid_int:
            neighbors.add(q2)
        elif q2 == qid_int:
            neighbors.add(q1)

    result: dict[str, dict[str, Any]] = {}
    for neighbor_id in sorted(neighbors):
        neighbor_qid = str(neighbor_id)
        doc = QubitDocument.find_one({"chip_id": chip_id, "qid": neighbor_qid}).run()
        if doc is None:
            continue
        params: dict[str, Any] = {}
        for name in param_names:
            if name in doc.data:
                params[name] = doc.data[name]
        if params:
            result[neighbor_qid] = params
    return result


def _load_coupling_params(
    chip_id: str, qid: str, param_names: list[str]
) -> dict[str, dict[str, Any]]:
    """Load specified parameters from couplings related to the target qubit."""
    from qdash.dbmodel.coupling import CouplingDocument

    # If qid contains "-", it's already a coupling ID
    if "-" in qid:
        coupling_ids = [qid]
    else:
        # Find related couplings via topology
        from qdash.dbmodel.chip import ChipDocument

        chip = ChipDocument.find_one({"chip_id": chip_id}).run()
        if chip is None or chip.topology_id is None:
            return {}

        from qdash.common.topology_config import load_topology

        topology = load_topology(chip.topology_id)

        try:
            qid_int = int(qid)
        except ValueError:
            return {}

        coupling_ids = []
        for q1, q2 in topology.couplings:
            if q1 == qid_int or q2 == qid_int:
                coupling_ids.append(f"{q1}-{q2}")

    result: dict[str, dict[str, Any]] = {}
    for coupling_id in coupling_ids:
        doc = CouplingDocument.find_one({"chip_id": chip_id, "qid": coupling_id}).run()
        if doc is None:
            continue
        params: dict[str, Any] = {}
        for name in param_names:
            if name in doc.data:
                params[name] = doc.data[name]
        if params:
            result[coupling_id] = params
    return result


def _load_latest_task_result(task_name: str, chip_id: str, qid: str) -> dict[str, Any]:
    """Load the latest completed result for a task+qubit."""
    results = _load_task_history(task_name, chip_id, qid, last_n=1)
    return results[0] if results else {"error": "No results found"}


def _load_parameter_timeseries(
    parameter_name: str, chip_id: str, qid: str, last_n: int = 10
) -> list[dict[str, Any]]:
    """Load time series data for a specific output parameter by name.

    Queries task_result_history by output_parameter_names field,
    which is indexed and allows parameter-name-based lookups
    regardless of task name.
    """
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    docs = (
        TaskResultHistoryDocument.find(
            {
                "chip_id": chip_id,
                "qid": qid,
                "status": "completed",
                "output_parameter_names": parameter_name,
            }
        )
        .sort([("start_at", SortDirection.DESCENDING)])
        .limit(last_n)
        .run()
    )

    results: list[dict[str, Any]] = []
    for doc in reversed(docs):  # chronological order (oldest first)
        param_data = (doc.output_parameters or {}).get(parameter_name)
        if param_data is None:
            continue
        entry: dict[str, Any] = {
            "start_at": doc.start_at.isoformat() if doc.start_at else None,
            "execution_id": doc.execution_id,
            "task_name": doc.name,
        }
        if isinstance(param_data, dict):
            entry["value"] = param_data.get("value")
            entry["unit"] = param_data.get("unit", "")
            entry["calibrated_at"] = param_data.get("calibrated_at")
        else:
            entry["value"] = param_data
            entry["unit"] = ""
        results.append(entry)

    if not results:
        return [{"error": f"No results found for parameter '{parameter_name}' on qid={qid}"}]
    return results


def _sanitize_for_json(obj: Any) -> Any:
    """Replace NaN/Infinity float values with None for JSON safety."""
    import math

    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _load_chip_summary(chip_id: str, param_names: list[str] | None = None) -> dict[str, Any]:
    """Load summary of all qubits on a chip with computed statistics."""
    import math
    import statistics as stats_mod

    from qdash.dbmodel.qubit import QubitDocument

    docs = QubitDocument.find({"chip_id": chip_id}).run()
    if not docs:
        return {"error": f"No qubits found for chip_id={chip_id}"}

    qubits: dict[str, dict[str, Any]] = {}
    numeric_values: dict[str, list[float]] = {}

    for doc in docs:
        data = dict(doc.data)
        if param_names:
            data = {k: v for k, v in data.items() if k in param_names}
        qubits[doc.qid] = _sanitize_for_json(data)
        for key, val in data.items():
            raw = val.get("value") if isinstance(val, dict) and "value" in val else val
            if isinstance(raw, (int, float)) and math.isfinite(raw):
                numeric_values.setdefault(key, []).append(float(raw))

    statistics: dict[str, dict[str, float]] = {}
    for key, values in numeric_values.items():
        if len(values) >= 2:
            statistics[key] = {
                "mean": stats_mod.mean(values),
                "median": stats_mod.median(values),
                "stdev": stats_mod.stdev(values),
                "min": min(values),
                "max": max(values),
                "count": len(values),
            }
        elif len(values) == 1:
            statistics[key] = {
                "mean": values[0],
                "median": values[0],
                "stdev": 0.0,
                "min": values[0],
                "max": values[0],
                "count": 1,
            }

    return {
        "chip_id": chip_id,
        "num_qubits": len(qubits),
        "qubits": qubits,
        "statistics": statistics,
    }


def _load_coupling_params_tool(
    chip_id: str,
    coupling_id: str | None = None,
    qubit_id: str | None = None,
    param_names: list[str] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Load coupling parameters by coupling_id or qubit_id."""
    from qdash.dbmodel.coupling import CouplingDocument

    if coupling_id:
        coupling_ids = [coupling_id]
    elif qubit_id:
        from qdash.dbmodel.chip import ChipDocument

        chip = ChipDocument.find_one({"chip_id": chip_id}).run()
        if chip is None or chip.topology_id is None:
            return {"error": f"Chip {chip_id} not found or has no topology"}

        from qdash.common.topology_config import load_topology

        topology = load_topology(chip.topology_id)
        try:
            qid_int = int(qubit_id)
        except ValueError:
            return {"error": f"Invalid qubit_id: {qubit_id}"}

        coupling_ids = []
        for q1, q2 in topology.couplings:
            if q1 == qid_int or q2 == qid_int:
                coupling_ids.append(f"{q1}-{q2}")
    else:
        return {"error": "Either coupling_id or qubit_id must be provided"}

    results: list[dict[str, Any]] = []
    for cid in coupling_ids:
        doc = CouplingDocument.find_one({"chip_id": chip_id, "qid": cid}).run()
        if doc is None:
            continue
        data = dict(doc.data)
        if param_names:
            data = {k: v for k, v in data.items() if k in param_names}
        results.append({"coupling_id": cid, "data": _sanitize_for_json(data)})

    if not results:
        return {"error": "No coupling data found"}
    return results


def _load_execution_history(
    chip_id: str,
    status: str | None = None,
    tags: list[str] | None = None,
    last_n: int = 10,
) -> list[dict[str, Any]]:
    """Load recent execution history for a chip."""
    from qdash.dbmodel.execution_history import ExecutionHistoryDocument

    query: dict[str, Any] = {"chip_id": chip_id}
    if status:
        query["status"] = status
    if tags:
        query["tags"] = {"$all": tags}

    docs = (
        ExecutionHistoryDocument.find(query)
        .sort([("start_at", SortDirection.DESCENDING)])
        .limit(last_n)
        .run()
    )

    results: list[dict[str, Any]] = []
    for doc in docs:
        results.append(
            {
                "execution_id": doc.execution_id,
                "name": doc.name,
                "status": doc.status,
                "chip_id": doc.chip_id,
                "tags": doc.tags,
                "start_at": doc.start_at.isoformat() if doc.start_at else None,
                "end_at": doc.end_at.isoformat() if doc.end_at else None,
                "elapsed_time": doc.elapsed_time,
                "message": doc.message,
            }
        )

    if not results:
        return [{"error": f"No executions found for chip_id={chip_id}"}]
    return results


def _load_compare_qubits(
    chip_id: str, qids: list[str], param_names: list[str] | None = None
) -> dict[str, Any]:
    """Load and compare parameters across multiple qubits."""
    from qdash.dbmodel.qubit import QubitDocument

    comparison: dict[str, dict[str, Any]] = {}
    for qid in qids:
        doc = QubitDocument.find_one({"chip_id": chip_id, "qid": qid}).run()
        if doc is None:
            comparison[qid] = {"error": f"Qubit {qid} not found"}
            continue
        data = dict(doc.data)
        if param_names:
            data = {k: v for k, v in data.items() if k in param_names}
        comparison[qid] = _sanitize_for_json(data)

    return {"chip_id": chip_id, "qubits": comparison}


def _load_chip_topology(chip_id: str) -> dict[str, Any]:
    """Load chip topology information."""
    from qdash.dbmodel.chip import ChipDocument

    chip = ChipDocument.find_one({"chip_id": chip_id}).run()
    if chip is None:
        return {"error": f"Chip {chip_id} not found"}
    if chip.topology_id is None:
        return {"error": f"Chip {chip_id} has no topology configured"}

    from qdash.common.topology_config import load_topology

    topology = load_topology(chip.topology_id)

    qubit_positions = {
        str(qid): {"row": pos.row, "col": pos.col} for qid, pos in topology.qubits.items()
    }
    couplings = [[q1, q2] for q1, q2 in topology.couplings]

    return {
        "chip_id": chip_id,
        "topology_id": chip.topology_id,
        "grid_size": topology.grid_size,
        "num_qubits": topology.num_qubits,
        "layout_type": topology.layout_type,
        "qubit_positions": qubit_positions,
        "couplings": couplings,
    }


def _load_search_task_results(
    chip_id: str,
    task_name: str | None = None,
    qid: str | None = None,
    status: str | None = None,
    execution_id: str | None = None,
    last_n: int = 10,
) -> list[dict[str, Any]]:
    """Search task result history with flexible filters."""
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    query: dict[str, Any] = {"chip_id": chip_id}
    if task_name:
        query["name"] = task_name
    if qid:
        query["qid"] = qid
    if status:
        query["status"] = status
    if execution_id:
        query["execution_id"] = execution_id

    docs = (
        TaskResultHistoryDocument.find(query)
        .sort([("start_at", SortDirection.DESCENDING)])
        .limit(last_n)
        .run()
    )

    results: list[dict[str, Any]] = []
    for doc in docs:
        results.append(
            {
                "task_id": doc.task_id,
                "task_name": doc.name,
                "qid": doc.qid,
                "status": doc.status,
                "execution_id": doc.execution_id,
                "start_at": doc.start_at.isoformat() if doc.start_at else None,
                "end_at": doc.end_at.isoformat() if doc.end_at else None,
                "elapsed_time": doc.elapsed_time,
                "output_parameters": doc.output_parameters or {},
                "message": doc.message,
            }
        )

    if not results:
        return [{"error": "No task results found matching the filters"}]
    return results


def _load_calibration_notes(
    chip_id: str,
    execution_id: str | None = None,
    task_id: str | None = None,
    last_n: int = 10,
) -> list[dict[str, Any]]:
    """Load calibration notes for a chip."""
    from qdash.dbmodel.calibration_note import CalibrationNoteDocument

    query: dict[str, Any] = {"chip_id": chip_id}
    if execution_id:
        query["execution_id"] = execution_id
    if task_id:
        query["task_id"] = task_id

    docs = (
        CalibrationNoteDocument.find(query)
        .sort([("timestamp", SortDirection.DESCENDING)])
        .limit(last_n)
        .run()
    )

    results: list[dict[str, Any]] = []
    for doc in docs:
        results.append(
            {
                "execution_id": doc.execution_id,
                "task_id": doc.task_id,
                "note": doc.note,
                "timestamp": doc.timestamp.isoformat() if doc.timestamp else None,
            }
        )

    if not results:
        return [{"error": f"No calibration notes found for chip_id={chip_id}"}]
    return results


def _load_parameter_lineage(
    parameter_name: str, qid: str, chip_id: str, last_n: int = 10
) -> list[dict[str, Any]]:
    """Load version history for a specific parameter."""
    from qdash.dbmodel.provenance import ParameterVersionDocument

    docs = (
        ParameterVersionDocument.find(
            {"parameter_name": parameter_name, "qid": qid, "chip_id": chip_id}
        )
        .sort([("version", SortDirection.DESCENDING)])
        .limit(last_n)
        .run()
    )

    results: list[dict[str, Any]] = []
    for doc in docs:
        results.append(
            {
                "version": doc.version,
                "value": doc.value,
                "unit": doc.unit,
                "error": doc.error,
                "execution_id": doc.execution_id,
                "task_id": doc.task_id,
                "task_name": doc.task_name,
                "valid_from": doc.valid_from.isoformat() if doc.valid_from else None,
                "valid_until": doc.valid_until.isoformat() if doc.valid_until else None,
            }
        )

    if not results:
        return [
            {
                "error": (
                    f"No version history found for parameter '{parameter_name}' "
                    f"on qid={qid}, chip_id={chip_id}"
                )
            }
        ]
    return results


def _build_tool_executors() -> dict[str, Any]:
    """Build the tool executor mapping for LLM function calling."""
    from qdash.api.lib.copilot_sandbox import execute_python_analysis

    return {
        "get_qubit_params": lambda args: _load_qubit_params(args["chip_id"], args["qid"]),
        "get_latest_task_result": lambda args: _load_latest_task_result(
            args["task_name"], args["chip_id"], args["qid"]
        ),
        "get_task_history": lambda args: _load_task_history(
            args["task_name"], args["chip_id"], args["qid"], args.get("last_n", 5)
        ),
        "get_parameter_timeseries": lambda args: _load_parameter_timeseries(
            args["parameter_name"], args["chip_id"], args["qid"], args.get("last_n", 10)
        ),
        "execute_python_analysis": lambda args: execute_python_analysis(
            args["code"], args.get("context_data")
        ),
        "get_chip_summary": lambda args: _load_chip_summary(
            args["chip_id"], args.get("param_names")
        ),
        "get_coupling_params": lambda args: _load_coupling_params_tool(
            args["chip_id"], args.get("coupling_id"), args.get("qubit_id"), args.get("param_names")
        ),
        "get_execution_history": lambda args: _load_execution_history(
            args["chip_id"], args.get("status"), args.get("tags"), args.get("last_n", 10)
        ),
        "compare_qubits": lambda args: _load_compare_qubits(
            args["chip_id"], args["qids"], args.get("param_names")
        ),
        "get_chip_topology": lambda args: _load_chip_topology(args["chip_id"]),
        "search_task_results": lambda args: _load_search_task_results(
            args["chip_id"],
            args.get("task_name"),
            args.get("qid"),
            args.get("status"),
            args.get("execution_id"),
            args.get("last_n", 10),
        ),
        "get_calibration_notes": lambda args: _load_calibration_notes(
            args["chip_id"], args.get("execution_id"), args.get("task_id"), args.get("last_n", 10)
        ),
        "get_parameter_lineage": lambda args: _load_parameter_lineage(
            args["parameter_name"], args["qid"], args["chip_id"], args.get("last_n", 10)
        ),
    }
