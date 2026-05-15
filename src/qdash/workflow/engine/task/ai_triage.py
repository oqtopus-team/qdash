"""Automatic AI triage for calibration task results."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import TYPE_CHECKING, cast

from qdash.copilot.triage import (
    apply_ai_triage_config as _shared_ai_triage_config,
)
from qdash.copilot.triage import (
    build_ai_triage_context as _shared_build_ai_triage_context,
)
from qdash.copilot.triage import (
    forced_ai_triage_markdown as _shared_forced_ai_triage_markdown,
)
from qdash.copilot.triage import (
    is_non_representative_mux_result as _shared_is_non_representative_mux_result,
)
from qdash.copilot.triage import (
    render_ai_triage_markdown as _shared_render_ai_triage_markdown,
)
from qdash.copilot.triage import (
    select_analysis_model as _shared_select_analysis_model,
)

if TYPE_CHECKING:
    from qdash.copilot.config import CopilotConfig, ModelConfig
    from qdash.datamodel.execution import ExecutionModel
    from qdash.datamodel.task import BaseTaskResultModel

logger = logging.getLogger(__name__)

AI_TRIAGE_ACTOR = "qdash-ai"
AI_TRIAGE_HEADER = "## AI triage"
AI_TRIAGE_SEPARATOR = "\n\n---\n\n"
AI_TRIAGE_SECTION_RE = re.compile(r"^## AI triage\n\n.*?(?:\n\n---\n\n|$)", re.DOTALL)
MAX_AI_TRIAGE_NOTE_CHARS = 4500
AI_TRIAGE_WORKERS = 2
AI_TRIAGE_ELIGIBLE_STATUSES = frozenset({"completed", "failed"})

_EXECUTOR = ThreadPoolExecutor(max_workers=AI_TRIAGE_WORKERS, thread_name_prefix="ai-triage")
_IN_FLIGHT_TASK_IDS: set[str] = set()
_IN_FLIGHT_LOCK = Lock()


def enqueue_ai_triage_note(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    *,
    overwrite_existing: bool = False,
) -> None:
    """Schedule AI triage note attachment without blocking calibration progress."""
    try:
        from qdash.copilot.config import load_copilot_config

        config = load_copilot_config()
        if not config.enabled or not config.analysis.enabled:
            _log_info(
                "AI triage enqueue skipped: task=%s task_id=%s copilot_enabled=%s "
                "analysis_enabled=%s",
                task.name,
                task.task_id,
                config.enabled,
                config.analysis.enabled,
            )
            return
        if task.name not in config.analysis.ai_triage_tasks:
            _log_debug(
                "AI triage enqueue skipped: task=%s task_id=%s not in ai_triage_tasks=%s",
                task.name,
                task.task_id,
                config.analysis.ai_triage_tasks,
            )
            return
        if not _is_terminal_ai_triage_result(task):
            _log_info(
                "AI triage enqueue skipped: task=%s task_id=%s status=%s non_terminal=true",
                task.name,
                task.task_id,
                _task_status_value(task),
            )
            return
        if _is_non_representative_mux_result(task):
            _log_info(
                "AI triage enqueue skipped: task=%s task_id=%s qid=%s non_representative_mux=true",
                task.name,
                task.task_id,
                getattr(task, "qid", ""),
            )
            return

        with _IN_FLIGHT_LOCK:
            if task.task_id in _IN_FLIGHT_TASK_IDS:
                _log_debug(
                    "AI triage enqueue skipped: task=%s task_id=%s already_in_flight=true",
                    task.name,
                    task.task_id,
                )
                return
            _IN_FLIGHT_TASK_IDS.add(task.task_id)

        task_snapshot = task.model_copy(deep=True)
        execution_snapshot = execution_model.model_copy(deep=True)
        try:
            _EXECUTOR.submit(
                _run_enqueued_ai_triage,
                task_snapshot,
                execution_snapshot,
                overwrite_existing,
            )
        except Exception:
            with _IN_FLIGHT_LOCK:
                _IN_FLIGHT_TASK_IDS.discard(task.task_id)
            raise
        _log_info(
            "AI triage enqueued: task=%s task_id=%s qid=%s execution_id=%s",
            task.name,
            task.task_id,
            getattr(task, "qid", ""),
            execution_model.execution_id,
        )
    except Exception as exc:
        _log_warning("AI triage enqueue failed for task %s (%s): %s", task.name, task.task_id, exc)


def _run_enqueued_ai_triage(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    overwrite_existing: bool,
) -> None:
    """Run queued AI triage and clear the in-flight marker."""
    try:
        maybe_attach_ai_triage_note(
            task,
            execution_model,
            overwrite_existing=overwrite_existing,
        )
    finally:
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_TASK_IDS.discard(task.task_id)


def maybe_attach_ai_triage_note(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    *,
    overwrite_existing: bool = False,
) -> None:
    """Attach an AI-generated triage section to a task-result note.

    This is a best-effort side effect. It must never fail calibration execution.
    """
    try:
        from qdash.copilot.config import load_copilot_config

        config = load_copilot_config()
        if not config.enabled or not config.analysis.enabled:
            _log_info(
                "AI triage skipped: task=%s task_id=%s copilot_enabled=%s analysis_enabled=%s",
                task.name,
                task.task_id,
                config.enabled,
                config.analysis.enabled,
            )
            return
        if task.name not in config.analysis.ai_triage_tasks:
            _log_debug(
                "AI triage skipped: task=%s task_id=%s not in ai_triage_tasks=%s",
                task.name,
                task.task_id,
                config.analysis.ai_triage_tasks,
            )
            return
        if not _is_terminal_ai_triage_result(task):
            _log_info(
                "AI triage skipped: task=%s task_id=%s status=%s non_terminal=true",
                task.name,
                task.task_id,
                _task_status_value(task),
            )
            return
        if _is_non_representative_mux_result(task):
            _log_info(
                "AI triage skipped: task=%s task_id=%s qid=%s non_representative_mux=true",
                task.name,
                task.task_id,
                getattr(task, "qid", ""),
            )
            return
        if not overwrite_existing and _has_ai_triage_note(task, execution_model):
            _log_info(
                "AI triage skipped: task=%s task_id=%s existing_note=true",
                task.name,
                task.task_id,
            )
            return

        selected_model = _select_analysis_model(config)
        _log_info(
            "AI triage starting: task=%s task_id=%s qid=%s execution_id=%s model=%s/%s",
            task.name,
            task.task_id,
            getattr(task, "qid", ""),
            execution_model.execution_id,
            selected_model.provider,
            selected_model.name,
        )
        markdown = _run_ai_triage(task, execution_model, config)
        if not markdown:
            _log_info(
                "AI triage produced empty output: task=%s task_id=%s",
                task.name,
                task.task_id,
            )
            return
        _upsert_ai_triage_note(task, execution_model, markdown, selected_model)
        _log_info("AI triage note saved: task=%s task_id=%s", task.name, task.task_id)
    except Exception as exc:
        _set_ai_triage_failure(task, execution_model, str(exc))
        _log_warning("AI triage failed for task %s (%s): %s", task.name, task.task_id, exc)


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


def _ai_triage_config(config: CopilotConfig) -> CopilotConfig:
    """Apply AI-triage-only speed defaults without changing side-panel chat."""
    return _shared_ai_triage_config(config)


def _forced_ai_triage_markdown(task_name: str, output_params: dict[str, object]) -> str | None:
    """Apply deterministic safety guards before asking a local VLM."""
    return _shared_forced_ai_triage_markdown(task_name, output_params)


def _is_non_representative_mux_result(task: BaseTaskResultModel) -> bool:
    """Return True for copied MUX task results that should not receive AI notes."""
    return _shared_is_non_representative_mux_result(task.name, getattr(task, "qid", ""))


def _task_status_value(task: BaseTaskResultModel) -> str:
    """Return the task status as its persisted string value."""
    status = getattr(task, "status", "")
    return str(getattr(status, "value", status))


def _is_terminal_ai_triage_result(task: BaseTaskResultModel) -> bool:
    """Return whether this task result is ready for AI triage."""
    return _task_status_value(task) in AI_TRIAGE_ELIGIBLE_STATUSES


def _run_ai_triage(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    config: CopilotConfig,
) -> str | None:
    """Run Copilot analysis and return markdown content."""
    config = _ai_triage_config(config)
    ctx = _shared_build_ai_triage_context(
        task_name=task.name,
        chip_id=execution_model.chip_id,
        qid=getattr(task, "qid", ""),
        task_id=task.task_id,
        config=config,
    )
    selected_model = _select_analysis_model(config)
    _log_info(
        "AI triage request: task=%s task_id=%s provider=%s model=%s image=%s expected_images=%d",
        task.name,
        task.task_id,
        selected_model.provider,
        selected_model.name,
        bool(ctx.image_base64),
        len(ctx.expected_images),
    )
    markdown = _shared_render_ai_triage_markdown(
        task_name=task.name,
        config=config,
        context_bundle=ctx,
    )
    return markdown or None


def _has_ai_triage_note(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
) -> bool:
    """Return whether this task result already has an AI triage note section."""
    existing = _get_existing_task_note_content(task, execution_model)
    return bool(existing and AI_TRIAGE_SECTION_RE.search(existing))


def _upsert_ai_triage_note(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    markdown: str,
    model: ModelConfig,
) -> None:
    """Insert or replace the AI triage section in the task-result note."""
    existing = _get_existing_task_note_content(task, execution_model)

    triage_section = (
        f"{AI_TRIAGE_HEADER}\n\n{_format_review_metadata(model)}\n\n{_truncate_markdown(markdown)}"
    )
    if AI_TRIAGE_SECTION_RE.search(existing):
        remainder = AI_TRIAGE_SECTION_RE.sub("", existing).strip()
        content = (
            f"{triage_section}{AI_TRIAGE_SEPARATOR}{remainder}" if remainder else triage_section
        )
    elif existing.strip():
        content = f"{triage_section}{AI_TRIAGE_SEPARATOR}{existing.rstrip()}"
    else:
        content = triage_section

    _set_task_note_content(task, execution_model, content[:MAX_AI_TRIAGE_NOTE_CHARS], model)


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


def _set_task_note_content(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    content: str,
    model: ModelConfig,
) -> None:
    """Persist the dashboard-facing task-result note directly on history."""
    from qdash.common.utils.datetime import now
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    timestamp = now()
    doc = TaskResultHistoryDocument.find_one(
        {"project_id": execution_model.project_id, "task_id": task.task_id}
    ).run()
    if doc is None:
        raise ValueError(f"Task result not found: {task.task_id}")
    doc.user_note.content = content
    doc.user_note.updated_by = AI_TRIAGE_ACTOR
    doc.user_note.updated_at = timestamp
    doc.ai_triage.status = "completed"
    doc.ai_triage.model_provider = model.provider
    doc.ai_triage.model_name = model.name
    doc.ai_triage.completed_at = timestamp
    doc.ai_triage.error = ""
    doc.save()


def _set_ai_triage_failure(
    task: BaseTaskResultModel,
    execution_model: ExecutionModel,
    error: str,
) -> None:
    """Persist AI triage failure metadata for workflow-triggered reviews."""
    from qdash.common.utils.datetime import now
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    doc = TaskResultHistoryDocument.find_one(
        {"project_id": execution_model.project_id, "task_id": task.task_id}
    ).run()
    if doc is None:
        return
    doc.ai_triage.status = "failed"
    doc.ai_triage.completed_at = now()
    doc.ai_triage.error = error[:500]
    doc.save()


def _truncate_markdown(markdown: str) -> str:
    """Keep note content bounded while preserving a useful tail marker."""
    budget = MAX_AI_TRIAGE_NOTE_CHARS - 200
    if len(markdown) <= budget:
        return markdown
    return markdown[:budget].rstrip() + "\n\n[truncated]"


def _format_review_metadata(model: ModelConfig) -> str:
    """Return a compact metadata line for the model that produced the review."""
    from qdash.common.utils.datetime import now

    return f"*Reviewed by: {model.provider}/{model.name} at {now().isoformat()}*"
