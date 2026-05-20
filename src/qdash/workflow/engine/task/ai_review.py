"""Automatic AI review for calibration task results."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import TYPE_CHECKING, cast

from qdash.copilot.review import (
    apply_ai_review_config as _shared_ai_review_config,
)
from qdash.copilot.review import (
    build_ai_review_context as _shared_build_ai_review_context,
)
from qdash.copilot.review import (
    forced_ai_review_markdown as _shared_forced_ai_review_markdown,
)
from qdash.copilot.review import (
    is_non_representative_mux_result as _shared_is_non_representative_mux_result,
)
from qdash.copilot.review import (
    render_ai_review_markdown as _shared_render_ai_review_markdown,
)
from qdash.copilot.review import (
    select_analysis_model as _shared_select_analysis_model,
)

if TYPE_CHECKING:
    from qdash.copilot.config import CopilotConfig, ModelConfig
    from qdash.datamodel.execution import ExecutionModel
    from qdash.datamodel.task import BaseTaskResultModel

logger = logging.getLogger(__name__)

AI_REVIEW_ACTOR = "qdash-ai"
AI_REVIEW_HEADER = "## AI review"
AI_REVIEW_SEPARATOR = "\n\n---\n\n"
AI_REVIEW_SECTION_RE = re.compile(r"^## AI review\n\n.*?(?:\n\n---\n\n|$)", re.DOTALL)
MAX_AI_REVIEW_NOTE_CHARS = 4500
AI_REVIEW_WORKERS = 2
AI_REVIEW_ELIGIBLE_STATUSES = frozenset({"completed", "failed"})

_EXECUTOR = ThreadPoolExecutor(max_workers=AI_REVIEW_WORKERS, thread_name_prefix="ai-review")
_IN_FLIGHT_TASK_IDS: set[str] = set()
_IN_FLIGHT_LOCK = Lock()


def enqueue_ai_review_note(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    *,
    overwrite_existing: bool = False,
) -> None:
    """Schedule AI review note attachment without blocking calibration progress."""
    try:
        from qdash.copilot.config import load_copilot_config

        config = load_copilot_config()
        if not config.enabled or not config.analysis.enabled:
            _log_info(
                "AI review enqueue skipped: task=%s task_id=%s copilot_enabled=%s "
                "analysis_enabled=%s",
                task.name,
                task.task_id,
                config.enabled,
                config.analysis.enabled,
            )
            return
        if task.name not in config.analysis.ai_review_tasks:
            _log_debug(
                "AI review enqueue skipped: task=%s task_id=%s not in ai_review_tasks=%s",
                task.name,
                task.task_id,
                config.analysis.ai_review_tasks,
            )
            return
        if not _is_terminal_ai_review_result(task):
            _log_info(
                "AI review enqueue skipped: task=%s task_id=%s status=%s non_terminal=true",
                task.name,
                task.task_id,
                _task_status_value(task),
            )
            return
        if _is_non_representative_mux_result(task):
            _log_info(
                "AI review enqueue skipped: task=%s task_id=%s qid=%s non_representative_mux=true",
                task.name,
                task.task_id,
                getattr(task, "qid", ""),
            )
            return

        with _IN_FLIGHT_LOCK:
            if task.task_id in _IN_FLIGHT_TASK_IDS:
                _log_debug(
                    "AI review enqueue skipped: task=%s task_id=%s already_in_flight=true",
                    task.name,
                    task.task_id,
                )
                return
            _IN_FLIGHT_TASK_IDS.add(task.task_id)

        task_snapshot = task.model_copy(deep=True)
        execution_snapshot = execution_model.model_copy(deep=True)
        try:
            _EXECUTOR.submit(
                _run_enqueued_ai_review,
                task_snapshot,
                execution_snapshot,
                overwrite_existing,
            )
        except Exception:
            with _IN_FLIGHT_LOCK:
                _IN_FLIGHT_TASK_IDS.discard(task.task_id)
            raise
        _log_info(
            "AI review enqueued: task=%s task_id=%s qid=%s execution_id=%s",
            task.name,
            task.task_id,
            getattr(task, "qid", ""),
            execution_model.execution_id,
        )
    except Exception as exc:
        _log_warning("AI review enqueue failed for task %s (%s): %s", task.name, task.task_id, exc)


def _run_enqueued_ai_review(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    overwrite_existing: bool,
) -> None:
    """Run queued AI review and clear the in-flight marker."""
    try:
        maybe_attach_ai_review_note(
            task,
            execution_model,
            overwrite_existing=overwrite_existing,
        )
    finally:
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_TASK_IDS.discard(task.task_id)


def maybe_attach_ai_review_note(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    *,
    overwrite_existing: bool = False,
) -> None:
    """Attach an AI-generated review section to a task-result note.

    This is a best-effort side effect. It must never fail calibration execution.
    """
    try:
        from qdash.copilot.config import load_copilot_config

        config = load_copilot_config()
        if not config.enabled or not config.analysis.enabled:
            _log_info(
                "AI review skipped: task=%s task_id=%s copilot_enabled=%s analysis_enabled=%s",
                task.name,
                task.task_id,
                config.enabled,
                config.analysis.enabled,
            )
            return
        if task.name not in config.analysis.ai_review_tasks:
            _log_debug(
                "AI review skipped: task=%s task_id=%s not in ai_review_tasks=%s",
                task.name,
                task.task_id,
                config.analysis.ai_review_tasks,
            )
            return
        if not _is_terminal_ai_review_result(task):
            _log_info(
                "AI review skipped: task=%s task_id=%s status=%s non_terminal=true",
                task.name,
                task.task_id,
                _task_status_value(task),
            )
            return
        if _is_non_representative_mux_result(task):
            _log_info(
                "AI review skipped: task=%s task_id=%s qid=%s non_representative_mux=true",
                task.name,
                task.task_id,
                getattr(task, "qid", ""),
            )
            return
        if not overwrite_existing and _has_ai_review_note(task, execution_model):
            _log_info(
                "AI review skipped: task=%s task_id=%s existing_note=true",
                task.name,
                task.task_id,
            )
            return

        selected_model = _select_analysis_model(config)
        _log_info(
            "AI review starting: task=%s task_id=%s qid=%s execution_id=%s model=%s/%s",
            task.name,
            task.task_id,
            getattr(task, "qid", ""),
            execution_model.execution_id,
            selected_model.provider,
            selected_model.name,
        )
        markdown = _run_ai_review(task, execution_model, config)
        if not markdown:
            _log_info(
                "AI review produced empty output: task=%s task_id=%s",
                task.name,
                task.task_id,
            )
            return
        _upsert_ai_review_note(task, execution_model, markdown, selected_model)
        _log_info("AI review note saved: task=%s task_id=%s", task.name, task.task_id)
    except Exception as exc:
        _set_ai_review_failure(task, execution_model, str(exc))
        _log_warning("AI review failed for task %s (%s): %s", task.name, task.task_id, exc)


def _prefect_logger() -> logging.Logger | None:
    """Return the current Prefect run logger when inside a flow/task run."""
    try:
        from prefect import get_run_logger

        return cast("logging.Logger", get_run_logger())
    except Exception:
        return None


def _log_debug(message: str, *args: object) -> None:
    """Log debug messages to both module and Prefect run loggers when available."""
    logger.debug(message, *args)
    run_logger = _prefect_logger()
    if run_logger is not None:
        run_logger.debug(message, *args)


def _log_info(message: str, *args: object) -> None:
    """Log info messages to both module and Prefect run loggers when available."""
    logger.info(message, *args)
    run_logger = _prefect_logger()
    if run_logger is not None:
        run_logger.info(message, *args)


def _log_warning(message: str, *args: object) -> None:
    """Log warning messages to both module and Prefect run loggers when available."""
    logger.warning(message, *args)
    run_logger = _prefect_logger()
    if run_logger is not None:
        run_logger.warning(message, *args)


def _select_analysis_model(config: CopilotConfig) -> ModelConfig:
    """Return the effective model used for task-result analysis."""
    return _shared_select_analysis_model(config)


def _ai_review_config(config: CopilotConfig) -> CopilotConfig:
    """Apply AI-review-only speed defaults without changing side-panel chat."""
    return _shared_ai_review_config(config)


def _forced_ai_review_markdown(task_name: str, output_params: dict[str, object]) -> str | None:
    """Apply deterministic safety guards before asking a local VLM."""
    return _shared_forced_ai_review_markdown(task_name, output_params)


def _is_non_representative_mux_result(task: BaseTaskResultModel) -> bool:
    """Return True for copied MUX task results that should not receive AI review notes."""
    return _shared_is_non_representative_mux_result(task.name, getattr(task, "qid", ""))


def _task_status_value(task: BaseTaskResultModel) -> str:
    """Return the task status as its persisted string value."""
    status = getattr(task, "status", "")
    return str(getattr(status, "value", status))


def _is_terminal_ai_review_result(task: BaseTaskResultModel) -> bool:
    """Return whether this task result is ready for AI review."""
    return _task_status_value(task) in AI_REVIEW_ELIGIBLE_STATUSES


def _run_ai_review(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    config: CopilotConfig,
) -> str | None:
    """Run Copilot analysis and return markdown content."""
    config = _ai_review_config(config)
    ctx = _shared_build_ai_review_context(
        task_name=task.name,
        chip_id=execution_model.chip_id,
        qid=getattr(task, "qid", ""),
        task_id=task.task_id,
        config=config,
    )
    selected_model = _select_analysis_model(config)
    _log_info(
        "AI review request: task=%s task_id=%s provider=%s model=%s image=%s expected_images=%d",
        task.name,
        task.task_id,
        selected_model.provider,
        selected_model.name,
        bool(ctx.image_base64),
        len(ctx.expected_images),
    )
    markdown = _shared_render_ai_review_markdown(
        task_name=task.name,
        config=config,
        context_bundle=ctx,
    )
    return markdown or None


def _has_ai_review_note(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
) -> bool:
    """Return whether this task result already has an AI review note section."""
    existing = _get_existing_ai_review_note_content(task, execution_model)
    if existing:
        return True
    legacy = _get_existing_task_note_content(task, execution_model)
    return bool(legacy and AI_REVIEW_SECTION_RE.search(legacy))


def _upsert_ai_review_note(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    markdown: str,
    model: ModelConfig,
) -> None:
    """Insert or replace the AI review section in the task-result note."""
    review_section = (
        f"{AI_REVIEW_HEADER}\n\n{_format_review_metadata(model)}\n\n{_truncate_markdown(markdown)}"
    )

    _set_ai_review_note_content(
        task, execution_model, review_section[:MAX_AI_REVIEW_NOTE_CHARS], model
    )


def _get_existing_task_note_content(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
) -> str:
    """Load the dashboard-facing task-result note content directly from history."""
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    doc = TaskResultHistoryDocument.find_one(
        {"project_id": execution_model.project_id, "task_id": task.task_id}
    ).run()
    if doc is None:
        return ""
    return doc.user_note.content or ""


def _get_existing_ai_review_note_content(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
) -> str:
    """Load the AI-generated review note content directly from history."""
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    doc = TaskResultHistoryDocument.find_one(
        {"project_id": execution_model.project_id, "task_id": task.task_id}
    ).run()
    if doc is None:
        return ""
    return doc.ai_review_note.content or ""


def _set_ai_review_note_content(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    content: str,
    model: ModelConfig,
) -> None:
    """Persist the AI-generated review note directly on history."""
    from qdash.common.utils.datetime import now
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    timestamp = now()
    doc = TaskResultHistoryDocument.find_one(
        {"project_id": execution_model.project_id, "task_id": task.task_id}
    ).run()
    if doc is None:
        raise ValueError(f"Task result not found: {task.task_id}")
    doc.ai_review_note.content = content
    doc.ai_review_note.updated_by = AI_REVIEW_ACTOR
    doc.ai_review_note.updated_at = timestamp
    doc.ai_review.status = "completed"
    doc.ai_review.model_provider = model.provider
    doc.ai_review.model_name = model.name
    doc.ai_review.completed_at = timestamp
    doc.ai_review.error = ""
    doc.save()


def _set_ai_review_failure(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    error: str,
) -> None:
    """Persist AI review failure metadata for workflow-triggered reviews."""
    from qdash.common.utils.datetime import now
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    doc = TaskResultHistoryDocument.find_one(
        {"project_id": execution_model.project_id, "task_id": task.task_id}
    ).run()
    if doc is None:
        return
    doc.ai_review.status = "failed"
    doc.ai_review.completed_at = now()
    doc.ai_review.error = error[:500]
    doc.save()


def _truncate_markdown(markdown: str) -> str:
    """Keep note content bounded while preserving a useful tail marker."""
    budget = MAX_AI_REVIEW_NOTE_CHARS - 200
    if len(markdown) <= budget:
        return markdown
    return markdown[:budget].rstrip() + "\n\n[truncated]"


def _format_review_metadata(model: ModelConfig) -> str:
    """Return a compact metadata line for the model that produced the review."""
    from qdash.common.utils.datetime import now

    return f"*Reviewed by: {model.provider}/{model.name} at {now().isoformat()}*"
