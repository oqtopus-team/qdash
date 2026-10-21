"""Bulk calibration evaluation runs: selection, execution, records, verdicts.

A run evaluates the latest result of one task for every qubit or coupling of
a chip through the Pi Agent Runtime's planner-less `/evaluate` route, and
stores one evaluation record per task result. The API process executes the
run in the background with bounded concurrency; the records are the product,
so a run interrupted by an API restart simply keeps its unfinished items as
pending and can be requested again.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bunnet import SortDirection
from fastapi import HTTPException, status

from qdash.api.schemas.evaluation import (
    EvaluationItem,
    EvaluationRunDetailResponse,
    EvaluationRunSummary,
)
from qdash.api.services.pi_chat_service import thinking_level
from qdash.api.services.pi_evaluation_service import (
    EvaluationRuntimeError,
    evaluate_task_result,
)
from qdash.common.utils.datetime import end_of_day, now, parse_date, start_of_day
from qdash.copilot.config import load_copilot_config
from qdash.datamodel.evaluation import (
    EvaluationCallModel,
    EvaluationExampleModel,
    EvaluationFigureModel,
    EvaluationInputModel,
    EvaluationOutputModel,
    EvaluationPlannerModel,
    EvaluationVerdictModel,
    EvaluatorModel,
)
from qdash.dbmodel.evaluation import EvaluationDocument
from qdash.dbmodel.evaluation_run import EvaluationRunDocument

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from qdash.api.services.knowledge_draft_service import KnowledgeDraft
    from qdash.api.services.pi_chat_service import QDashAuth
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
    from qdash.repository.chip import MongoChipRepository
    from qdash.repository.task_result_history import MongoTaskResultHistoryRepository

logger = logging.getLogger(__name__)

# Evaluations sent to the runtime at once per run. The calibration VLM serves
# several requests concurrently; two keeps a 64-qubit run under twenty minutes
# without starving the chat.
DEFAULT_CONCURRENCY = int(os.environ.get("EVALUATION_CONCURRENCY", "2"))
# A task result is evaluable once the calibration has stopped touching it.
TERMINAL_STATUSES = frozenset({"completed", "failed"})
TRIGGERS = frozenset({"bulk", "single", "chat"})
MODES = frozenset({"direct", "planner"})


def planner_model_config() -> tuple[dict[str, str], str | None]:
    """The chat planner the UI would use, as the runtime wants it, with its thinking level."""
    config = load_copilot_config()
    model = config.chat_models[0] if config.chat_models else config.model
    return (
        {"provider": model.provider, "name": model.name},
        thinking_level(config.model_copy(update={"model": model})),
    )


@dataclass
class RunSelection:
    """A created run, its queued evaluations, and why entities were left out."""

    run: EvaluationRunDocument
    evaluations: list[EvaluationDocument]
    skipped: dict[str, str] = field(default_factory=dict)


def _natural_key(qid: str) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", qid))


def _success(doc: EvaluationDocument) -> bool:
    diagnosis = doc.output.diagnosis if doc.output else None
    return isinstance(diagnosis, dict) and diagnosis.get("success") is True


def _to_item(
    doc: EvaluationDocument, figures: dict[str, tuple[list[str], list[str]]] | None = None
) -> EvaluationItem:
    figure_path, json_figure_path = (figures or {}).get(doc.task_id, ([], []))
    return EvaluationItem(
        evaluation_id=doc.evaluation_id,
        run_id=doc.run_id,
        task_id=doc.task_id,
        task_name=doc.task_name,
        qid=doc.qid,
        execution_id=doc.execution_id,
        figure_path=figure_path,
        json_figure_path=json_figure_path,
        status=doc.status,
        requested_at=doc.requested_at,
        started_at=doc.started_at,
        completed_at=doc.completed_at,
        error=doc.error,
        input=doc.input,
        output=doc.output,
        evaluator=doc.evaluator,
        planner=doc.planner,
        verdict=doc.verdict,
    )


def _summary(
    run: EvaluationRunDocument, evaluations: list[EvaluationDocument]
) -> EvaluationRunSummary:
    completed = [doc for doc in evaluations if doc.status == "completed"]
    return EvaluationRunSummary(
        run_id=run.run_id,
        chip_id=run.chip_id,
        task_name=run.task_name,
        entity_type=run.entity_type,
        date=run.date,
        question=run.question,
        knowledge_draft_id=run.knowledge_draft_id,
        knowledge_draft_name=run.knowledge_draft_name,
        trigger=run.trigger,
        mode=run.mode,
        with_examples=run.with_examples,
        planner_model=run.planner_model,
        requested_by=run.requested_by,
        requested_at=run.requested_at,
        completed_at=run.completed_at,
        status=run.status,
        total=run.total,
        completed_count=run.completed_count,
        failed_count=run.failed_count,
        pending_count=sum(1 for doc in evaluations if doc.status in {"pending", "running"}),
        parsed_count=sum(1 for doc in completed if doc.output and doc.output.parsed),
        complete_count=sum(1 for doc in completed if doc.output and doc.output.complete),
        elapsed_ms=(
            int((run.completed_at - run.requested_at).total_seconds() * 1000)
            if run.completed_at
            else None
        ),
        duration_ms_total=sum(doc.output.duration_ms for doc in completed if doc.output),
        success_count=sum(1 for doc in completed if _success(doc)),
        agree_count=sum(1 for doc in evaluations if doc.verdict and doc.verdict.agree is True),
        disagree_count=sum(1 for doc in evaluations if doc.verdict and doc.verdict.agree is False),
        model=run.model,
        evaluator=run.evaluator,
    )


def _input_from_record(record: dict[str, Any], question: str | None) -> EvaluationInputModel:
    knowledge = record.get("knowledge") or {}
    evaluation = record.get("evaluation") or {}
    return EvaluationInputModel(
        context=str(record.get("context") or ""),
        prompt=evaluation.get("prompt"),
        system_prompt=evaluation.get("system_prompt"),
        question=question,
        knowledge_chars=knowledge.get("chars"),
        knowledge_sha256=knowledge.get("sha256"),
        figures=_figures_from(record.get("figures")),
        examples=[
            EvaluationExampleModel(
                id=str(example.get("id") or ""),
                title=str(example.get("title") or ""),
                outcome=str(example.get("outcome") or ""),
                status=str(example.get("status") or ""),
                figures=_figures_from(example.get("figures")),
            )
            for example in record.get("examples") or []
            if isinstance(example, dict)
        ],
    )


def _figures_from(value: Any) -> list[EvaluationFigureModel]:
    return [
        EvaluationFigureModel(
            sha256=str(figure.get("sha256", "")),
            mime_type=str(figure.get("mime_type", "")),
            bytes=int(figure.get("bytes", 0)),
            path=figure.get("path") or None,
        )
        for figure in value or []
        if isinstance(figure, dict)
    ]


def _context_window(model: Any) -> int | None:
    """The configured context window (`num_ctx`) of the `provider/name` that judged."""
    if not isinstance(model, str) or not model:
        return None
    try:
        config = load_copilot_config()
    except Exception:
        logger.warning("copilot config unavailable; context window of %s unknown", model)
        return None
    for candidate in [*config.evaluation_models, *config.chat_models, config.model]:
        if f"{candidate.provider}/{candidate.name}" == model:
            return candidate.num_ctx
    return None


def _output_from_record(record: dict[str, Any]) -> EvaluationOutputModel:
    evaluation = record.get("evaluation") or {}
    diagnosis = evaluation.get("diagnosis")
    parsed = isinstance(diagnosis, dict)
    return EvaluationOutputModel(
        model=evaluation.get("model"),
        fallback=evaluation.get("fallback") is True,
        diagnosis=diagnosis if parsed else None,
        raw=evaluation.get("raw"),
        answers=_answers_from(evaluation.get("answers")),
        questions=[key for key in evaluation.get("questions") or [] if isinstance(key, str)],
        parsed=parsed,
        attempts=evaluation.get("attempts")
        if isinstance(evaluation.get("attempts"), int)
        else None,
        structured=evaluation.get("structured")
        if isinstance(evaluation.get("structured"), bool)
        else None,
        stop_reason=evaluation.get("stop_reason")
        if isinstance(evaluation.get("stop_reason"), str)
        else None,
        calls=_calls_from(evaluation.get("calls")),
        duration_ms=int(evaluation.get("duration_ms") or 0),
        usage=evaluation.get("usage") if isinstance(evaluation.get("usage"), dict) else None,
        # Kept with the record: a later change to the config does not rewrite it.
        context_window=_context_window(evaluation.get("model")),
    )


def _answers_from(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    answers = {
        str(key): text for key, text in value.items() if isinstance(text, str) and text.strip()
    }
    return answers or None


def _calls_from(value: Any) -> list[EvaluationCallModel]:
    calls: list[EvaluationCallModel] = []
    for call in value if isinstance(value, list) else []:
        if not isinstance(call, dict) or not isinstance(call.get("stop_reason"), str):
            continue
        calls.append(
            EvaluationCallModel(
                question=call.get("question") if isinstance(call.get("question"), str) else None,
                duration_ms=int(call.get("duration_ms") or 0),
                stop_reason=call["stop_reason"],
                structured=call.get("structured") is True,
                input_tokens=(
                    call.get("input_tokens") if isinstance(call.get("input_tokens"), int) else None
                ),
                output_tokens=(
                    call.get("output_tokens")
                    if isinstance(call.get("output_tokens"), int)
                    else None
                ),
                missing_keys=[
                    key for key in call.get("missing_keys") or [] if isinstance(key, str)
                ],
            )
        )
    return calls


def _planner_from_record(record: dict[str, Any]) -> EvaluationPlannerModel | None:
    planner = record.get("planner")
    if not isinstance(planner, dict) or not planner.get("model"):
        return None
    return EvaluationPlannerModel(
        model=str(planner["model"]),
        answer=str(planner.get("answer") or ""),
        tool_calls=[str(name) for name in planner.get("tool_calls") or []],
        duration_ms=int(planner.get("duration_ms") or 0),
    )


def _evaluator_from_record(record: dict[str, Any]) -> EvaluatorModel | None:
    evaluator = record.get("evaluator")
    if not isinstance(evaluator, dict) or not evaluator.get("name"):
        return None
    return EvaluatorModel(
        name=str(evaluator["name"]),
        version=str(evaluator.get("version") or "unknown"),
        source=str(evaluator.get("source") or "package"),
        commit=evaluator.get("commit"),
    )


class EvaluationService:
    """Create, execute and read bulk evaluation runs."""

    def __init__(
        self,
        chip_repository: MongoChipRepository,
        task_result_repository: MongoTaskResultHistoryRepository,
        *,
        concurrency: int = DEFAULT_CONCURRENCY,
        evaluate: Callable[..., Awaitable[dict[str, Any]]] = evaluate_task_result,
    ) -> None:
        self._chip_repo = chip_repository
        self._task_result_repo = task_result_repository
        self._concurrency = max(1, concurrency)
        self._evaluate = evaluate
        # Background runs, referenced so the event loop does not drop them.
        self._background: set[asyncio.Task[None]] = set()

    # --- selection -----------------------------------------------------------------------

    def request_run(
        self,
        *,
        project_id: str,
        chip_id: str,
        task: str,
        entity_type: str,
        date: str | None = None,
        task_ids: list[str] | None = None,
        qids: list[str] | None = None,
        knowledge_draft: KnowledgeDraft | None = None,
        trigger: str = "bulk",
        mode: str = "direct",
        with_examples: bool = False,
        requested_by: str,
    ) -> RunSelection:
        """Create a run over the latest evaluable result of `task` per entity.

        `task_ids` or `qids` narrow the run to named results or entities; the
        rest are out of scope rather than skipped. A `knowledge_draft` replaces
        the shared knowledge of `task` for this run only.
        """
        if entity_type not in {"qubit", "coupling"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="entity_type must be 'qubit' or 'coupling'",
            )
        if trigger not in TRIGGERS or mode not in MODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="trigger must be 'bulk', 'single' or 'chat' and mode 'direct' or 'planner'",
            )
        if knowledge_draft is not None:
            if knowledge_draft.task_name != task:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"the knowledge draft describes {knowledge_draft.task_name}, not {task}",
                )
            if mode != "direct":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="a knowledge draft can only be evaluated in direct mode",
                )
        planner_model: str | None = None
        if mode == "planner":
            model, _ = planner_model_config()
            planner_model = f"{model['provider']}/{model['name']}"
        # Taken before `qids` is rebound to the chip's entity ids below.
        chosen = set(qids or [])
        is_latest = date is None or date == "latest"
        effective_date = None if is_latest else date
        try:
            qids = (
                self._entity_ids(project_id, chip_id, entity_type)
                if is_latest
                else self._historical_entity_ids(project_id, chip_id, entity_type, date or "")
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        latest = self._latest_results(
            project_id=project_id, chip_id=chip_id, task=task, qids=qids, date=effective_date
        )
        requested = set(task_ids or [])
        run = EvaluationRunDocument(
            run_id=f"evr_{uuid.uuid4().hex}",
            project_id=project_id,
            chip_id=chip_id,
            task_name=task,
            entity_type=entity_type,
            date=effective_date,
            knowledge_draft_id=knowledge_draft.draft_id if knowledge_draft else None,
            knowledge_draft_name=knowledge_draft.filename if knowledge_draft else None,
            trigger=trigger,
            mode=mode,
            with_examples=with_examples,
            planner_model=planner_model,
            requested_by=requested_by,
        )
        evaluations: list[EvaluationDocument] = []
        skipped: dict[str, str] = {}
        for qid in sorted(qids, key=_natural_key):
            if chosen and qid not in chosen:
                continue
            doc = latest.get(qid)
            if doc is None:
                # Out of scope, not skipped, when the caller named the task results.
                if not requested:
                    skipped[qid] = "no result"
                continue
            if requested and doc.task_id not in requested:
                continue
            if doc.status not in TERMINAL_STATUSES:
                skipped[qid] = f"status {doc.status}"
                continue
            if not doc.figure_path:
                skipped[qid] = "no figure"
                continue
            evaluations.append(
                EvaluationDocument(
                    evaluation_id=f"ev_{uuid.uuid4().hex}",
                    run_id=run.run_id,
                    project_id=project_id,
                    chip_id=chip_id,
                    task_id=doc.task_id,
                    task_name=doc.name,
                    qid=qid,
                    execution_id=doc.execution_id or "",
                    requested_at=run.requested_at,
                )
            )
        if not evaluations:
            reasons = ", ".join(f"{qid}: {reason}" for qid, reason in list(skipped.items())[:8])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"no evaluable result of {task} on {chip_id}"
                + (f" ({reasons})" if reasons else ""),
            )
        run.total = len(evaluations)
        run.insert()
        EvaluationDocument.insert_many(evaluations)
        return RunSelection(run=run, evaluations=evaluations, skipped=skipped)

    def _entity_ids(self, project_id: str, chip_id: str, entity_type: str) -> list[str]:
        qids = (
            self._chip_repo.get_qubit_ids(project_id, chip_id)
            if entity_type == "qubit"
            else self._chip_repo.get_coupling_ids(project_id, chip_id)
        )
        if not qids:
            raise ValueError(
                f"Chip {chip_id} not found or has no {entity_type}s in project {project_id}"
            )
        return qids

    def _historical_entity_ids(
        self, project_id: str, chip_id: str, entity_type: str, date: str
    ) -> list[str]:
        qids = (
            self._chip_repo.get_historical_qubit_ids(project_id, chip_id, date)
            if entity_type == "qubit"
            else self._chip_repo.get_historical_coupling_ids(project_id, chip_id, date)
        )
        if not qids:
            raise ValueError(f"Chip {chip_id} not found or has no {entity_type}s for date {date}")
        return qids

    def _latest_results(
        self,
        *,
        project_id: str,
        chip_id: str,
        task: str,
        qids: list[str],
        date: str | None,
    ) -> dict[str, TaskResultHistoryDocument]:
        """The newest result of `task` per entity, for the latest state or one day."""
        if date is None:
            docs = self._task_result_repo.find_latest_by_chip_and_qids(
                project_id=project_id, chip_id=chip_id, qids=qids, task_names=[task]
            )
        else:
            parsed = parse_date(date, "YYYYMMDD")
            docs = self._task_result_repo.find(
                {
                    "project_id": project_id,
                    "chip_id": chip_id,
                    "name": task,
                    "qid": {"$in": qids},
                    "start_at": {"$gte": start_of_day(parsed), "$lt": end_of_day(parsed)},
                },
                sort=[("end_at", SortDirection.DESCENDING)],
            )
        latest: dict[str, TaskResultHistoryDocument] = {}
        for doc in docs:
            if doc.qid and doc.qid not in latest:
                latest[doc.qid] = doc
        return latest

    # --- execution -----------------------------------------------------------------------

    def launch(self, run_id: str, auth: QDashAuth) -> None:
        """Execute a run in the background of the current event loop."""
        task = asyncio.get_running_loop().create_task(self.execute_run(run_id, auth))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def execute_run(self, run_id: str, auth: QDashAuth) -> None:
        """Evaluate every pending item of a run, a few at a time, then close the run."""
        run = EvaluationRunDocument.find_one(EvaluationRunDocument.run_id == run_id).run()
        if run is None:
            return
        pending = EvaluationDocument.find(
            EvaluationDocument.run_id == run_id, EvaluationDocument.status == "pending"
        ).to_list()
        semaphore = asyncio.Semaphore(self._concurrency)
        model: dict[str, str] | None = None
        thinking: str | None = None
        if run.mode == "planner":
            model, thinking = planner_model_config()

        async def one(doc: EvaluationDocument) -> None:
            async with semaphore:
                await self._evaluate_one(doc, run, auth, model=model, thinking=thinking)
                self._refresh_run(run_id)

        try:
            await asyncio.gather(*(one(doc) for doc in pending))
        finally:
            self._refresh_run(run_id)

    async def _evaluate_one(
        self,
        doc: EvaluationDocument,
        run: EvaluationRunDocument,
        auth: QDashAuth,
        *,
        model: dict[str, str] | None = None,
        thinking: str | None = None,
    ) -> None:
        doc.status = "running"
        doc.started_at = now()
        doc.save()
        try:
            record = await self._evaluate(
                doc.task_id,
                auth=auth,
                question=run.question,
                knowledge_draft_id=run.knowledge_draft_id,
                mode=run.mode,
                with_examples=run.with_examples,
                model=model,
                thinking_level=thinking,
            )
        except EvaluationRuntimeError as exc:
            self._fail(doc, str(exc))
            return
        except Exception as exc:
            logger.exception("evaluation %s of %s failed", doc.evaluation_id, doc.task_id)
            self._fail(doc, f"runtime: {exc}")
            return
        doc.input = _input_from_record(record, run.question)
        doc.output = _output_from_record(record)
        doc.evaluator = _evaluator_from_record(record)
        doc.planner = _planner_from_record(record)
        doc.status = "completed"
        doc.completed_at = now()
        doc.error = None
        doc.save()

    @staticmethod
    def _fail(doc: EvaluationDocument, error: str) -> None:
        doc.status = "failed"
        doc.error = error[:2000]
        doc.completed_at = now()
        doc.save()

    def _refresh_run(self, run_id: str) -> None:
        """Recompute a run's progress from its evaluations."""
        run = EvaluationRunDocument.find_one(EvaluationRunDocument.run_id == run_id).run()
        if run is None:
            return
        evaluations = EvaluationDocument.find(EvaluationDocument.run_id == run_id).to_list()
        run.total = len(evaluations)
        run.completed_count = sum(1 for doc in evaluations if doc.status == "completed")
        run.failed_count = sum(1 for doc in evaluations if doc.status == "failed")
        first = next((doc for doc in evaluations if doc.status == "completed"), None)
        if first is not None:
            run.model = run.model or (first.output.model if first.output else None)
            run.evaluator = run.evaluator or first.evaluator
        unfinished = any(doc.status in {"pending", "running"} for doc in evaluations)
        if not unfinished and run.status != "completed":
            run.status = "completed"
            run.completed_at = now()
        run.save()

    # --- chat ------------------------------------------------------------------------------

    def chat_recorder(
        self,
        *,
        project_id: str,
        username: str,
        session_id: str | None,
        planner_model: str,
        task_id: str | None = None,
    ) -> ChatEvaluationRecorder:
        """A recorder for the evaluations one chat turn's planner makes.

        `task_id` is the task result a task chat is about: the figures it opens
        with are that result's, so a judgement of them without a tool-fetched
        provenance is filed under it.
        """
        return ChatEvaluationRecorder(
            self,
            project_id=project_id,
            username=username,
            session_id=session_id,
            planner_model=planner_model,
            task_id=task_id,
        )

    def record_chat_evaluation(
        self,
        *,
        project_id: str,
        username: str,
        planner_model: str,
        record: dict[str, Any],
    ) -> tuple[str, str] | None:
        """Store one `qcal_evaluate` call the chat planner made, as a run of one.

        The figures a chat judges come from a tool that fetched them for a task
        result; its id rides on the record. A judgement of a figure with no
        known task result (a user attachment) is not recorded.
        """
        task_id = record.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            return None
        docs = self._task_result_repo.find({"project_id": project_id, "task_id": task_id}, limit=1)
        if not docs:
            return None
        doc = docs[0]
        output = _output_from_record(record)
        evaluator = _evaluator_from_record(record)
        requested = now()
        run = EvaluationRunDocument(
            run_id=f"evr_{uuid.uuid4().hex}",
            project_id=project_id,
            chip_id=doc.chip_id,
            task_name=doc.name,
            entity_type="coupling" if "-" in (doc.qid or "") else "qubit",
            trigger="chat",
            mode="planner",
            planner_model=planner_model,
            requested_by=username,
            requested_at=requested,
            completed_at=requested,
            status="completed",
            total=1,
            completed_count=1,
            model=output.model,
            evaluator=evaluator,
        )
        evaluation = EvaluationDocument(
            evaluation_id=f"ev_{uuid.uuid4().hex}",
            run_id=run.run_id,
            project_id=project_id,
            chip_id=doc.chip_id,
            task_id=task_id,
            task_name=doc.name,
            qid=doc.qid or "",
            execution_id=doc.execution_id or "",
            status="completed",
            requested_at=requested,
            started_at=requested,
            completed_at=requested,
            input=_input_from_record(record, None),
            output=output,
            evaluator=evaluator,
            planner=EvaluationPlannerModel(model=planner_model),
        )
        run.insert()
        evaluation.insert()
        return run.run_id, evaluation.evaluation_id

    def attach_chat_answer(self, evaluation_ids: list[str], answer: str) -> None:
        """Keep the planner's final answer with the evaluations it made in the turn."""
        if not evaluation_ids or not answer:
            return
        for doc in EvaluationDocument.find({"evaluation_id": {"$in": evaluation_ids}}).to_list():
            if doc.planner is None:
                continue
            doc.planner = doc.planner.model_copy(update={"answer": answer})
            doc.save()

    # --- reads ---------------------------------------------------------------------------

    def summarize(self, run: EvaluationRunDocument) -> EvaluationRunSummary:
        """The run with counts derived from its evaluations."""
        evaluations = EvaluationDocument.find(EvaluationDocument.run_id == run.run_id).to_list()
        return _summary(run, evaluations)

    def list_runs(
        self,
        *,
        project_id: str,
        chip_id: str | None = None,
        task: str | None = None,
        limit: int = 20,
    ) -> list[EvaluationRunSummary]:
        """Runs of a project, newest first, optionally for one chip or task."""
        query: dict[str, Any] = {"project_id": project_id}
        if chip_id:
            query["chip_id"] = chip_id
        if task:
            query["task_name"] = task
        runs = (
            EvaluationRunDocument.find(query)
            .sort([("requested_at", SortDirection.DESCENDING)])
            .limit(max(1, min(limit, 200)))
            .to_list()
        )
        if not runs:
            return []
        by_run: dict[str, list[EvaluationDocument]] = {run.run_id: [] for run in runs}
        for doc in EvaluationDocument.find({"run_id": {"$in": list(by_run)}}).to_list():
            by_run.setdefault(doc.run_id, []).append(doc)
        return [_summary(run, by_run[run.run_id]) for run in runs]

    def get_run(self, *, project_id: str, run_id: str) -> EvaluationRunDetailResponse:
        """One run with its evaluations in entity order."""
        run = self._require_run(project_id, run_id)
        evaluations = EvaluationDocument.find(EvaluationDocument.run_id == run_id).to_list()
        evaluations.sort(key=lambda doc: _natural_key(doc.qid))
        figures = self._figures_of(project_id, [doc.task_id for doc in evaluations])
        return EvaluationRunDetailResponse(
            run=_summary(run, evaluations),
            evaluations=[_to_item(doc, figures) for doc in evaluations],
        )

    def _figures_of(
        self, project_id: str, task_ids: list[str]
    ) -> dict[str, tuple[list[str], list[str]]]:
        """Figure paths of the task results, in one query, for display next to the records."""
        if not task_ids:
            return {}
        docs = self._task_result_repo.find(
            {"project_id": project_id, "task_id": {"$in": list(set(task_ids))}}
        )
        return {
            doc.task_id: (list(doc.figure_path or []), list(doc.json_figure_path or []))
            for doc in docs
        }

    def list_for_task(self, *, project_id: str, task_id: str) -> list[EvaluationItem]:
        """Every evaluation of one task result, newest first."""
        docs = (
            EvaluationDocument.find(
                EvaluationDocument.project_id == project_id, EvaluationDocument.task_id == task_id
            )
            .sort([("requested_at", SortDirection.DESCENDING)])
            .to_list()
        )
        figures = self._figures_of(project_id, [task_id])
        return [_to_item(doc, figures) for doc in docs]

    def set_verdict(
        self,
        *,
        project_id: str,
        evaluation_id: str,
        agree: bool | None,
        note: str | None,
        username: str,
    ) -> EvaluationItem:
        """Record a person's judgement; `agree=None` with no note clears it."""
        doc = EvaluationDocument.find_one(
            EvaluationDocument.project_id == project_id,
            EvaluationDocument.evaluation_id == evaluation_id,
        ).run()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"evaluation {evaluation_id} not found",
            )
        note = (note or "").strip() or None
        doc.verdict = (
            None
            if agree is None and note is None
            else EvaluationVerdictModel(agree=agree, note=note, username=username, updated_at=now())
        )
        doc.save()
        return _to_item(doc)

    def _require_run(self, project_id: str, run_id: str) -> EvaluationRunDocument:
        run = EvaluationRunDocument.find_one(
            EvaluationRunDocument.project_id == project_id, EvaluationRunDocument.run_id == run_id
        ).run()
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"evaluation run {run_id} not found"
            )
        return run


class ChatEvaluationRecorder:
    """Records the evaluations the planner makes during one chat turn.

    `record` is called from the SSE translation on every `qcal_evaluate`
    result; `finish` once the turn's answer is known. Failures are logged and
    never interrupt the chat.
    """

    def __init__(
        self,
        service: EvaluationService,
        *,
        project_id: str,
        username: str,
        session_id: str | None,
        planner_model: str,
        task_id: str | None = None,
    ) -> None:
        self._service = service
        self._project_id = project_id
        self._username = username
        self._session_id = session_id
        self._planner_model = planner_model
        self._task_id = task_id
        self.evaluation_ids: list[str] = []

    def record(self, record: dict[str, Any]) -> dict[str, str] | None:
        """Store one evaluation; returns its run and evaluation ids, or None when not stored."""
        if not record.get("task_id") and self._task_id:
            # The opening figures of a task chat are the task's own.
            record = {**record, "task_id": self._task_id}
        try:
            ids = self._service.record_chat_evaluation(
                project_id=self._project_id,
                username=self._username,
                planner_model=self._planner_model,
                record=record,
            )
        except Exception:
            logger.exception("recording a chat evaluation failed (session %s)", self._session_id)
            return None
        if ids is None:
            return None
        run_id, evaluation_id = ids
        self.evaluation_ids.append(evaluation_id)
        return {"run_id": run_id, "evaluation_id": evaluation_id}

    def finish(self, answer: str) -> None:
        """Attach the planner's answer to the evaluations of this turn."""
        try:
            self._service.attach_chat_answer(self.evaluation_ids, answer)
        except Exception:
            logger.exception("attaching the chat answer failed (session %s)", self._session_id)
