"""Inspecting executions after they ran: per-execution state, task results and artifacts.

A :class:`ExecutionResult` is one execution's detail as it was read; its :class:`TaskResult`
items wrap the task entries the execution lists. A :class:`TaskResult` read through
``QDash.task_result(task_id)`` wraps the full saved result instead. Figures and other
artifacts are :class:`Artifact` handles: building one sends no request, and only
:meth:`Artifact.read`, :meth:`Artifact.save` and :meth:`Figure.show` fetch their bytes, through
the session's authenticated connection.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from qdash.sdk._parameters import Parameters
from qdash.sdk._runs import TERMINAL_STATUSES

if TYPE_CHECKING:
    import datetime as dt
    import os

    from qdash.sdk._generated.types.execution_response_detail import ExecutionResponseDetail
    from qdash.sdk._generated.types.pipeline_step_progress import PipelineStepProgress
    from qdash.sdk._generated.types.task import Task
    from qdash.sdk._generated.types.task_invocation import TaskInvocation
    from qdash.sdk._generated.types.task_result_response import TaskResultResponse
    from qdash.sdk._runs import Executions

ArtifactKind = Literal["figure", "json_figure", "raw_data"]


def check_save_target(path: str | os.PathLike[str], *, overwrite: bool) -> Path:
    """``path`` as a file to save to: not a directory, and absent unless ``overwrite``."""
    target = Path(path)
    if target.is_dir():
        raise IsADirectoryError(f"{target} is a directory; pass a file name to save to")
    if not overwrite and target.exists():
        raise FileExistsError(f"{target} exists; pass overwrite=True to replace it")
    return target


def write_file(target: Path, content: bytes, *, overwrite: bool) -> Path:
    """Write ``content`` to ``target``; without ``overwrite`` an existing file is an error."""
    with target.open("wb" if overwrite else "xb") as file:
        file.write(content)
    return target


class Artifact:
    """A file a task saved on the server, such as a JSON figure or raw data.

    ``path`` is the server-side path the task result lists; it identifies the file in requests
    and is never written to locally. Creating or printing the handle sends no request.
    """

    def __init__(self, executions: Executions, path: str, kind: ArtifactKind) -> None:
        self._executions = executions
        self.path = path
        self.kind: ArtifactKind = kind

    @property
    def filename(self) -> str:
        """The last component of the server path, for display; ``save`` never uses it."""
        return PurePosixPath(self.path).name

    def __repr__(self) -> str:
        return f"{type(self).__name__}(kind={self.kind!r}, path={self.path!r})"

    def read(self) -> bytes:
        """The file's bytes, fetched from the server on every call.

        Raises ``QDashNotFoundError`` when the server no longer has the file.
        """
        return self._executions.artifact_bytes(self.path)

    def save(self, path: str | os.PathLike[str], *, overwrite: bool = False) -> Path:
        """Fetch the file and write it to ``path``, a file name the caller chooses.

        An existing file raises ``FileExistsError`` before anything is fetched unless
        ``overwrite`` is true. A directory raises ``IsADirectoryError``; missing parent
        directories are not created. Nothing is written when the fetch fails. Returns the path.
        """
        target = check_save_target(path, overwrite=overwrite)
        return write_file(target, self.read(), overwrite=overwrite)


class Figure(Artifact):
    """A PNG figure a task saved; :meth:`show` displays it in a notebook."""

    def __init__(self, executions: Executions, path: str) -> None:
        super().__init__(executions, path, "figure")

    def read(self) -> bytes:
        """The PNG bytes, fetched from the server on every call."""
        return self._executions.figure_bytes(self.path)

    def show(self) -> None:
        """Fetch the figure and display it in the running notebook (needs IPython)."""
        try:
            from IPython.display import Image, display
        except ImportError:
            raise ImportError(
                "Figure.show() needs IPython, which notebooks provide; install ipython, or use "
                "figure.read() or figure.save(path) instead"
            ) from None
        display(Image(data=self.read(), format="png"))


def _paths(value: list[str] | None) -> list[str]:
    return list(value) if value else []


class TaskResult:
    """One task run on one qubit or coupling, as an execution or the task result reported it.

    A result taken from :attr:`ExecutionResult.tasks` wraps the execution's task entry, in
    which optional fields may be missing; :meth:`get` reads the full saved result.
    Collections default to empty ones and scalars to None when the server left them out.
    ``input_parameters`` and ``output_parameters`` are :class:`~qdash.sdk.Parameters`: each
    :class:`~qdash.sdk.Parameter` has ``value``, ``unit`` and ``error`` and keeps every other
    reported field in ``metadata``; a bare value from an older result becomes its ``value``. Two results of the same task
    on the same target are told apart by ``task_id`` and ``invocation``, never by name.
    ``detail`` is the model as the API returned it. Reading the fields sends no request.
    """

    def __init__(
        self,
        executions: Executions,
        detail: Task | TaskResultResponse,
        *,
        execution_id: str | None = None,
    ) -> None:
        self._executions = executions
        self.detail = detail
        self._execution_id = execution_id
        self._figures = [Figure(executions, path) for path in _paths(detail.figure_path)]
        self._json_figures = [
            Artifact(executions, path, "json_figure") for path in _paths(detail.json_figure_path)
        ]
        self._raw_data = [
            Artifact(executions, path, "raw_data") for path in _paths(detail.raw_data_path)
        ]

    @property
    def task_id(self) -> str | None:
        return self.detail.task_id

    @property
    def name(self) -> str | None:
        """The task's name, such as ``CheckT1``."""
        task_name = getattr(self.detail, "task_name", None)
        return task_name if task_name is not None else getattr(self.detail, "name", None)

    @property
    def qid(self) -> str | None:
        return self.detail.qid

    @property
    def status(self) -> str | None:
        return self.detail.status

    @property
    def message(self) -> str | None:
        return self.detail.message

    @property
    def succeeded(self) -> bool:
        """Whether the task completed; any case of ``completed`` counts."""
        return (self.status or "").lower() == "completed"

    @property
    def execution_id(self) -> str | None:
        """The execution that ran the task."""
        own = getattr(self.detail, "execution_id", None)
        return own if own is not None else self._execution_id

    @property
    def chip_id(self) -> str | None:
        """The chip, when the full task result reported it."""
        return getattr(self.detail, "chip_id", None)

    @property
    def source_task_id(self) -> str | None:
        """The result this one re-executed, when the full task result reported one."""
        return getattr(self.detail, "source_task_id", None)

    @property
    def stack_trace(self) -> str | None:
        """The failure's stack trace, when the full task result reported one."""
        return getattr(self.detail, "stack_trace", None)

    @property
    def invocation(self) -> TaskInvocation | None:
        """The planned step and call this result executed; None for older results."""
        return self.detail.invocation

    @property
    def call_id(self) -> str | None:
        invocation = self.detail.invocation
        return invocation.call_id if invocation is not None else None

    @property
    def input_parameters(self) -> Parameters:
        """The task's input parameters by name, as :class:`~qdash.sdk.Parameter` values."""
        return Parameters.from_reported(self.detail.input_parameters)

    @property
    def output_parameters(self) -> Parameters:
        """The task's output parameters by name, as :class:`~qdash.sdk.Parameter` values."""
        return Parameters.from_reported(self.detail.output_parameters)

    @property
    def output_parameter_names(self) -> list[str]:
        return list(self.detail.output_parameter_names or [])

    @property
    def run_parameters(self) -> dict[str, Any]:
        return dict(self.detail.run_parameters or {})

    @property
    def note(self) -> dict[str, Any]:
        return dict(self.detail.note or {})

    @property
    def start_at(self) -> dt.datetime | None:
        return self.detail.start_at

    @property
    def end_at(self) -> dt.datetime | None:
        return self.detail.end_at

    @property
    def elapsed_time(self) -> str | None:
        return self.detail.elapsed_time

    @property
    def figures(self) -> list[Figure]:
        """PNG figures, in the order the task saved them."""
        return list(self._figures)

    @property
    def json_figures(self) -> list[Artifact]:
        """Interactive figure JSON files."""
        return list(self._json_figures)

    @property
    def raw_data(self) -> list[Artifact]:
        """Raw data files, such as NetCDF."""
        return list(self._raw_data)

    def get(self) -> TaskResult:
        """The full saved result of this task, read by ``task_id``; sends a request."""
        if not self.task_id:
            raise ValueError("this task result has no task_id to read the saved result by")
        return self._executions.task_result(self.task_id)

    def __repr__(self) -> str:
        return (
            f"TaskResult(name={self.name!r}, qid={self.qid!r}, status={self.status!r}, "
            f"task_id={self.task_id!r})"
        )


class ExecutionResult:
    """One execution as it was read: its own status and its task results.

    ``status`` is this execution's own ``detail.status``, not the status of the pipeline run
    it may belong to (see :class:`~qdash.sdk.RunResult` for that). ``step`` is the pipeline
    step the execution ran, when it was read through :meth:`Run.executions`. ``detail`` is
    the execution detail as the API returned it.
    """

    def __init__(
        self,
        executions: Executions,
        execution_id: str,
        detail: ExecutionResponseDetail,
        *,
        step: PipelineStepProgress | None = None,
    ) -> None:
        self.execution_id = execution_id
        self.detail = detail
        self.step = step
        self._tasks = [
            TaskResult(executions, task, execution_id=execution_id) for task in detail.task
        ]

    @property
    def name(self) -> str:
        return self.detail.name

    @property
    def status(self) -> str:
        return self.detail.status

    @property
    def message(self) -> str | None:
        return self.detail.message

    @property
    def chip_id(self) -> str | None:
        return self.detail.chip_id

    @property
    def succeeded(self) -> bool:
        """Whether this execution completed; any case of ``completed`` counts."""
        return self.status.lower() == "completed"

    @property
    def done(self) -> bool:
        """Whether this execution ended: completed, failed, cancelled, canceled or crashed."""
        return self.status.lower() in TERMINAL_STATUSES

    @property
    def tasks(self) -> list[TaskResult]:
        """The execution's task results, in the order the execution lists them."""
        return list(self._tasks)

    def task(self, task_id: str) -> TaskResult:
        """The task result with ``task_id``; raises ``KeyError`` when the execution has none."""
        for task in self._tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(f"execution {self.execution_id!r} has no task {task_id!r}")

    def __repr__(self) -> str:
        return (
            f"ExecutionResult(execution_id={self.execution_id!r}, name={self.name!r}, "
            f"status={self.status!r}, tasks={len(self._tasks)})"
        )


class Execution:
    """One execution, by ID; ``QDash.execution(id)`` creates it without a request.

    Unlike :class:`~qdash.sdk.Run`, which follows a whole pipeline run from its first
    execution, this reads only the named execution.
    """

    def __init__(self, executions: Executions, execution_id: str) -> None:
        self._executions = executions
        self._execution_id = execution_id

    @property
    def execution_id(self) -> str:
        return self._execution_id

    def __repr__(self) -> str:
        return f"Execution(execution_id={self.execution_id!r})"

    def get(self) -> ExecutionResult:
        """The execution's current state; raises ``QDashNotFoundError`` before it exists."""
        return ExecutionResult(
            self._executions, self.execution_id, self._executions.get(self.execution_id)
        )


def collect_executions(executions: Executions, execution_id: str) -> list[ExecutionResult]:
    """Every started execution of the run ``execution_id`` starts, in step order.

    Reads the root execution once, then each pipeline step's own execution. Steps that have
    not started or run no execution (transforms) are skipped, and an execution listed by
    several steps is read once. A run without pipeline progress returns its root execution.
    """
    root = executions.get(execution_id)
    pipeline = root.pipeline
    step_ids: list[tuple[str, PipelineStepProgress]] = []
    if pipeline is not None:
        seen: set[str] = set()
        for step in sorted(pipeline.steps, key=lambda item: item.index):
            step_execution = step.execution_id
            if not step_execution or step_execution in seen:
                continue
            seen.add(step_execution)
            step_ids.append((step_execution, step))
    if not step_ids:
        return [ExecutionResult(executions, execution_id, root)]
    results: list[ExecutionResult] = []
    if execution_id not in {step_execution for step_execution, _ in step_ids}:
        # Keep the execution the run was followed by, even when no step names it.
        results.append(ExecutionResult(executions, execution_id, root))
    for step_execution, step in step_ids:
        detail = root if step_execution == execution_id else executions.get(step_execution)
        results.append(ExecutionResult(executions, step_execution, detail, step=step))
    return results
