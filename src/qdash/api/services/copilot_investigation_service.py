"""The opening message of a chat that investigates a failed execution or task.

The browser names the failure; this module loads its logs from the project the
user is working in, so the model sees what QDash recorded rather than what a
client sent. The message carries the identifiers, the error text and stack
trace (clipped when long), the source roots the model can read with
``qdash_search_source`` / ``qdash_read_source``, and what is known about the
revision of that source. It asks for an evidence-backed diagnosis and never for
a fix to be applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

if TYPE_CHECKING:
    from qdash.api.services.execution_service import ExecutionService
    from qdash.api.services.source_access_service import SourceAccessService, SourceRoot
    from qdash.api.services.task_service import TaskService
    from qdash.copilot.contracts import InvestigationTarget

MESSAGE_LIMIT = 4_000
STACK_TRACE_LIMIT = 12_000
MAX_LISTED_TASKS = 10


class InvestigationNotFoundError(Exception):
    """The execution to investigate does not exist in the user's project."""


@dataclass(frozen=True)
class InvestigationContext:
    """What the opening message was built from, for status lines and tests."""

    opening_message: str
    has_task_result: bool
    has_logs: bool


def clip(text: str, limit: int) -> tuple[str, bool]:
    """Keep the start and, mostly, the end of a long log; the end of a traceback names the error."""
    text = text.strip()
    if len(text) <= limit:
        return text, False
    head = limit // 4
    tail = limit - head
    omitted = len(text) - head - tail
    return f"{text[:head]}\n[... {omitted} characters omitted ...]\n{text[-tail:]}", True


def _fence(text: str) -> str:
    """A fenced block that the log's own backticks cannot close."""
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}text\n{text}\n{fence}"


def _field(value: Any) -> str:
    return str(value) if value not in (None, "") else "not recorded"


def _revision_line(root: SourceRoot) -> str:
    version = f" {root.version}" if root.version else ""
    if root.revision:
        dirty = " with uncommitted local changes" if root.dirty else ""
        revision = f"revision `{root.revision}` (from {root.revision_source}){dirty}"
    else:
        revision = "revision unknown"
    return f"- `{root.name}` ({root.kind}{version}): {revision}"


def _source_section(source: SourceAccessService) -> str:
    roots = source.roots
    lines = ["## Source you can read", ""]
    if roots:
        lines += [
            "Search with `qdash_search_source` (literal text, or `mode: path` for file "
            "names) and read with `qdash_read_source` (a path inside a root, or a path "
            "exactly as a traceback prints it). They are read-only. Available roots:",
            "",
            *(_revision_line(root) for root in roots),
        ]
    else:
        lines.append(
            "No source roots are available on this QDash server, so you cannot read "
            "code. Say so, and base the diagnosis on the logs alone."
        )
    missing = source.missing_dependencies()
    if missing:
        lines += [
            "",
            "Not available here: "
            + ", ".join(f"`{name}`" for name in missing)
            + ". Do not quote or cite their code; say which checks need it.",
        ]
    lines += [
        "",
        "QDash does not record which source revision an execution ran with. You cannot "
        "establish that the source above matches the code that produced this failure: "
        "say so when you cite it, and treat a mismatch between the traceback and the "
        "source (missing lines, different names) as a sign of a different revision.",
    ]
    return "\n".join(lines)


_INSTRUCTIONS = """\
## What to do

Diagnose why this failed. This is read-only: do not change parameters, re-run \
anything, or apply a fix.

Start with the frame that raised the error in the traceback and the source \
it points to. Stop reading once the logs and that code explain the error; do \
not scan the repository or list callers and alternatives that the evidence \
does not call for. Read further only when the evidence is ambiguous or \
contradictory, or when the user asks for more.

Keep the answer short: these three labeled items in a few sentences or \
bullets, with no other sections and no repeated caveats.

- **Likely cause**: one or two sentences. Mark it as a hypothesis, with your \
confidence, only when the evidence does not establish it.
- **Evidence**: a short quote of the decisive log line and one or a few \
`root:path:line` citations. Quote and cite only what you read.
- **Next step**: the single most useful check, or a proposed fix for the user \
to review; never apply it. Give two only when one is not enough.

Mention the source revision caveat in one short clause when you cite code. \
When the logs are missing or clipped, or the source you need is unavailable, \
say so in one sentence and what that prevents you from concluding. The user \
can ask a follow-up for more detail."""


class CopilotInvestigationService:
    """Build an investigation's opening message from project-scoped records."""

    def __init__(
        self,
        execution_service: ExecutionService,
        task_service: TaskService,
        source_service: SourceAccessService,
    ) -> None:
        self._executions = execution_service
        self._tasks = task_service
        self._source = source_service

    def _task_result(self, project_id: str, task_id: str) -> Any | None:
        try:
            return self._tasks.get_task_result(project_id, task_id)
        except HTTPException as exc:
            if exc.status_code == 404:
                return None
            raise

    @staticmethod
    def _execution_task(execution: Any, target: InvestigationTarget) -> Any | None:
        """The execution's own record of the task, for a task without a result."""
        for task in execution.task or []:
            if target.task_id and task.task_id == target.task_id:
                return task
        if target.task_name:
            for task in execution.task or []:
                if task.name == target.task_name and (not target.qid or task.qid == target.qid):
                    return task
        return None

    def build(
        self,
        *,
        project_id: str,
        target: InvestigationTarget,
        user_message: str,
        language_instruction: str,
    ) -> InvestigationContext:
        """The opening message; raises ``InvestigationNotFoundError`` for an unknown execution."""
        execution = self._executions.get_execution(project_id, target.execution_id)
        if execution is None:
            raise InvestigationNotFoundError(target.execution_id)

        has_logs = False
        sections: list[str] = [
            "# Investigate a failure",
            "",
            language_instruction,
            "",
            "## Execution",
            "",
            f"- Execution ID: `{target.execution_id}`",
            f"- Name: {_field(execution.name)}",
            f"- Flow: {_field(execution.flow_name)}",
            f"- Chip: {_field(execution.chip_id or target.chip_id)}",
            f"- Status: {_field(execution.status)}",
            f"- Started: {_field(execution.start_at)}; ended: {_field(execution.end_at)}",
            "",
        ]
        if execution.message and execution.message.strip():
            has_logs = True
            text, clipped = clip(execution.message, MESSAGE_LIMIT)
            sections += [
                "### Execution error message" + (" (clipped)" if clipped else ""),
                "",
                _fence(text),
                "",
            ]
        else:
            sections += ["The execution recorded no error message.", ""]

        failed = [t for t in execution.task or [] if t.status == "failed"]
        if failed:
            sections += ["### Failed tasks in this execution", ""]
            for task in failed[:MAX_LISTED_TASKS]:
                first_line = (str(task.message or "").strip().splitlines() or [""])[0][:200]
                sections.append(
                    f"- {_field(task.name)} on `{_field(task.qid)}` "
                    f"(task ID `{_field(task.task_id)}`): {first_line or 'no message'}"
                )
            if len(failed) > MAX_LISTED_TASKS:
                sections.append(f"- ... and {len(failed) - MAX_LISTED_TASKS} more")
            sections.append("")

        has_task_result = False
        if target.task_id or target.task_name:
            result = self._task_result(project_id, target.task_id) if target.task_id else None
            sections += ["## Task", ""]
            if result is not None:
                if result.execution_id != target.execution_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Task result does not belong to the requested execution",
                    )
                has_task_result = True
                sections += [
                    f"- Task: {_field(result.task_name)} on `{_field(result.qid)}`",
                    f"- Task ID: `{result.task_id}`",
                    f"- Status: {_field(result.status)}",
                    "",
                ]
                message, stack = result.message or "", result.stack_trace or ""
            else:
                entry = self._execution_task(execution, target)
                sections += [
                    f"- Task: {_field(target.task_name or (entry.name if entry else None))} "
                    f"on `{_field(target.qid or (entry.qid if entry else None))}`",
                    f"- Task ID: `{_field(target.task_id)}`",
                    "- No task result is recorded for it; the execution's own record is below.",
                    "",
                ]
                message, stack = (str(entry.message or "") if entry else ""), ""
            if message.strip():
                has_logs = True
                text, clipped = clip(message, MESSAGE_LIMIT)
                sections += [
                    "### Task error log" + (" (clipped)" if clipped else ""),
                    "",
                    _fence(text),
                    "",
                ]
            if stack.strip():
                has_logs = True
                text, clipped = clip(stack, STACK_TRACE_LIMIT)
                sections += [
                    "### Stack trace"
                    + (" (clipped: the start and the end are kept)" if clipped else ""),
                    "",
                    _fence(text),
                    "",
                ]
            if not message.strip() and not stack.strip():
                sections += ["The task recorded no error message or stack trace.", ""]

        if not has_logs:
            sections += [
                "No logs were recorded for this failure. Use `qdash_get_execution` for "
                "what else QDash holds about it before reading code.",
                "",
            ]

        sections += [
            _source_section(self._source),
            "",
            _INSTRUCTIONS,
            "",
            "## Request",
            "",
            user_message,
        ]
        return InvestigationContext(
            opening_message="\n".join(sections),
            has_task_result=has_task_result,
            has_logs=has_logs,
        )
