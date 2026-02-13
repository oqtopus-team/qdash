"""Copilot API router for AI assistant configuration and analysis.

This router provides endpoints for copilot configuration
and LLM-powered calibration result analysis.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
from qdash.api.lib.copilot_analysis import AnalysisResponse, AnalyzeRequest, TaskAnalysisContext
from qdash.api.lib.copilot_config import load_copilot_config
from qdash.datamodel.task_knowledge import get_task_knowledge

router = APIRouter()
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


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    summary="Analyze calibration result with AI",
    operation_id="analyzeCopilot",
)
async def analyze_task_result(request: AnalyzeRequest) -> AnalysisResponse:
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

        return await run_analysis(
            context=context,
            user_message=request.message,
            config=config,
            image_base64=request.image_base64,
            conversation_history=request.conversation_history,
            tool_executors=tool_executors,
        )
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

        # Step 5: Run analysis
        yield _sse_event("status", {"step": "run_analysis", "message": "AIが分析中..."})
        tool_executors = _build_tool_executors()
        try:
            from qdash.api.lib.copilot_agent import run_analysis

            result = await run_analysis(
                context=context,
                user_message=request.message,
                config=config,
                image_base64=request.image_base64,
                conversation_history=request.conversation_history,
                tool_executors=tool_executors,
            )
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

        # Step 6: Complete
        yield _sse_event("status", {"step": "complete", "message": "分析完了"})
        yield _sse_event("result", result.model_dump())

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _load_qubit_params(chip_id: str, qid: str) -> dict[str, Any]:
    """Load current qubit parameters from DB."""
    from qdash.dbmodel.qubit import QubitDocument

    doc = QubitDocument.find_one({"chip_id": chip_id, "qid": qid}).run()
    if doc is None:
        return {}
    return dict(doc.data)


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
    }


def _load_task_history(
    task_name: str, chip_id: str, qid: str, last_n: int = 5
) -> list[dict[str, Any]]:
    """Load recent completed results for the same task+qubit."""
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    docs = (
        TaskResultHistoryDocument.find(
            {"chip_id": chip_id, "name": task_name, "qid": qid, "status": "completed"}
        )
        .sort([("start_at", -1)])
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


def _build_tool_executors() -> dict[str, Any]:
    """Build the tool executor mapping for LLM function calling."""
    return {
        "get_qubit_params": lambda args: _load_qubit_params(args["chip_id"], args["qid"]),
        "get_latest_task_result": lambda args: _load_latest_task_result(
            args["task_name"], args["chip_id"], args["qid"]
        ),
        "get_task_history": lambda args: _load_task_history(
            args["task_name"], args["chip_id"], args["qid"], args.get("last_n", 5)
        ),
    }
