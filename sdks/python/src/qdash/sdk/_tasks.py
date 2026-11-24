"""The task catalog and single-task runs, as the Task Workbench uses them.

``QDash.tasks.list()`` and ``QDash.tasks.get(name)`` read the task definitions of a backend,
with their input, run and output parameters. ``QDash.tasks.run(TaskCall(...), chip_id=...,
qid=...)`` dispatches one task on one qubit or coupling through the Workbench's own route,
``POST /tasks/{name}/execute``, with the current task definition and calibration state.
``QDash.tasks.load_parameters(name, chip_id=..., qid=...)`` reads the values a run would
start from, to inspect and edit before :meth:`TaskParameters.to_call` turns them into a call.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from qdash.calibration import TaskCall
from qdash.sdk._generated import _authoring as models
from qdash.sdk._http import api_errors, given, read_options
from qdash.sdk._runs import Run
from qdash.sdk._workflows import check_recorded_launch
from qdash.sdk.errors import QDashConfigError, QDashNotFoundError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.types.execute_flow_response import ExecuteFlowResponse
    from qdash.sdk._generated.types.task_info import TaskInfo
    from qdash.sdk._results import TaskResult
    from qdash.sdk._runs import Executions


def _identifier(label: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _optional_identifier(label: str, value: object) -> str | None:
    return None if value is None else _identifier(label, value)


def _flag(label: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be True or False, got {value!r}")
    return value


# How the backend resolves each input (``InputParameterSpec.resolution``). A definition that
# names none is a legacy declaration, which the worker resolves from the database.
_RESOLUTIONS = frozenset(
    {"database_required", "database_optional", "database_or_default", "default_only"}
)
_ROLES = frozenset({"self", "control", "target", "coupling"})
# Run parameters declared with a sweep constructor; the worker expands them.
_SWEEP_VALUE_TYPES = frozenset({"np.linspace", "np.logspace", "np.arange", "range"})


def _coupling_qids(qid: str) -> tuple[str, str]:
    parts = qid.split("-")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise ValueError(f"a coupling qid must be 'control-target', e.g. '0-1', got {qid!r}")
    return parts[0], parts[1]


def _names(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ValueError(f"the task definition's {label} must be a list of names, got {value!r}")
    return tuple(str(name) for name in value)


_MISSING = object()


def _stored_value(stored: object) -> Any:
    """A calibration entry's value: ``{"value": ...}`` as stored, or a bare value."""
    if isinstance(stored, dict):
        return stored.get("value", _MISSING)
    return _MISSING if stored is None else stored


def _lookup(
    sources: Sequence[Mapping[str, Any]], primary: Sequence[str], fallback: Sequence[str]
) -> Any:
    """The worker's database lookup: the first key present wins, even when its value is null.

    Primary names (``parameter_name`` and its aliases) are searched in every source before any
    fallback name, and each source in order, as ``QubexTask._populate_parameters`` does.
    """
    for names in (primary, fallback):
        for source in sources:
            for name in names:
                if name in source:
                    return _stored_value(source[name])
    return _MISSING


def _same(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, list | tuple) and isinstance(right, list | tuple):
        return len(left) == len(right) and all(map(_same, left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    return left == right


class TaskParameters:
    """The parameters a task run on one qubit or coupling would start from, to edit and run.

    Returned by :meth:`Tasks.load_parameters`; a snapshot that sends nothing. ``input`` maps
    every input parameter of the definition to the value loaded for it: the current
    calibration value, else the definition's default, else None. ``run`` maps each run
    parameter that declares a default to that default, in the form a
    :class:`~qdash.sdk.calibration.TaskCall` carries it (a sweep as ``{"value": [...],
    "value_type": ...}``, not expanded). Both are plain dictionaries to read and edit;
    :meth:`to_call` turns them into the call :meth:`Tasks.run` sends.

    ``name``, ``chip_id``, ``qid`` and ``backend_name`` identify what was loaded, and
    ``definition`` is a copy of the task definition read. ``forbidden`` names the inputs the
    definition does not let a run override; they stay in ``input`` for inspection only.
    """

    def __init__(
        self,
        definition: TaskInfo,
        *,
        chip_id: str,
        qid: str,
        backend_name: str,
        input: dict[str, Any],
        run: dict[str, Any],
        unresolved: Sequence[str] = (),
    ) -> None:
        self._definition = definition.model_copy(deep=True)
        self.name = definition.name
        self.chip_id = chip_id
        self.qid = qid
        self.backend_name = backend_name
        self.input = input
        self.run = run
        self._loaded_input = deepcopy(input)
        self._unresolved = tuple(unresolved)

    @property
    def definition(self) -> TaskInfo:
        """A copy of the task definition the parameters were loaded from."""
        return self._definition.model_copy(deep=True)

    def _inputs(self) -> dict[str, dict[str, Any]]:
        return self._definition.input_parameters or {}

    @property
    def forbidden(self) -> list[str]:
        """Inputs whose definition sets ``user_override="forbidden"``; to_call omits them."""
        return [
            name
            for name, spec in self._inputs().items()
            if spec.get("user_override") == "forbidden"
        ]

    @property
    def unresolved(self) -> list[str]:
        """Inputs the SDK left None because their resolution or ``qid_role`` is unknown to it.

        The worker resolves them when the task runs; set a value in ``input`` to override.
        """
        return list(self._unresolved)

    @property
    def missing(self) -> list[str]:
        """Inputs that need a value and have none in ``input`` now.

        An input needs a value unless its resolution is ``database_optional``, which the task
        accepts as None, or the SDK left it unresolved. Recomputed on every read, so setting
        ``input[name]`` removes the name. A forbidden input counts with its loaded value,
        which a run cannot change.
        """
        forbidden = set(self.forbidden)
        return [
            name
            for name, spec in self._inputs().items()
            if spec.get("resolution") != "database_optional"
            and name not in self._unresolved
            and (self._loaded_input if name in forbidden else self.input).get(name) is None
        ]

    def to_call(self, *, update_calibration_parameters: bool | None = False) -> TaskCall:
        """The :class:`~qdash.sdk.calibration.TaskCall` of the current ``input`` and ``run``.

        Every input with a value is sent as an input override, except the ``forbidden`` ones,
        which are left for the server to resolve; an input set to None is not sent, so the
        server resolves it when the task runs. Every run parameter with a value is sent as it
        is. ``update_calibration_parameters`` is False by default, so a run only records its
        results, as in the Workbench; pass True, or None for the server's default in a
        pipeline step. The input values belong to ``qid``: to call the task on other qubits
        in a pipeline, leave ``input`` out of that call.

        Raises ``ValueError``, sending nothing, for a name the definition does not declare,
        an edited forbidden input, or an input still in ``missing``. The values themselves,
        their types and bounds, are checked by the server when the call runs.
        """
        if update_calibration_parameters is not None:
            _flag("update_calibration_parameters", update_calibration_parameters)
        inputs = self._inputs()
        runs = self._definition.run_parameters or {}
        problems: list[str] = []
        for kind, values, declared in (("input", self.input, inputs), ("run", self.run, runs)):
            unknown = sorted(set(values) - set(declared))
            if unknown:
                problems.append(f"unknown {kind} parameters: {', '.join(unknown)}")
        forbidden = set(self.forbidden)
        edited = sorted(
            name
            for name in forbidden
            if name in self.input and not _same(self.input[name], self._loaded_input.get(name))
        )
        if edited:
            problems.append(
                f"input parameters that do not allow overrides were changed: {', '.join(edited)}"
            )
        missing = self.missing
        if missing:
            fixable = [name for name in missing if name not in forbidden]
            locked = [name for name in missing if name in forbidden]
            if fixable:
                problems.append(
                    f"input parameters without a value: {', '.join(fixable)}; set them in input"
                )
            if locked:
                problems.append(
                    "input parameters without a calibration value that cannot be overridden: "
                    f"{', '.join(locked)}; calibrate them first"
                )
        if problems:
            raise ValueError(f"cannot build a call for {self.name}: " + "; ".join(problems))
        options: dict[str, Any] = {
            "name": self.name,
            "input": {
                name: deepcopy(value)
                for name, value in self.input.items()
                if value is not None and name not in forbidden
            },
            "run": {name: deepcopy(value) for name, value in self.run.items() if value is not None},
        }
        if update_calibration_parameters is not None:
            options["update_calibration_parameters"] = update_calibration_parameters
        return TaskCall(**options)

    def __repr__(self) -> str:
        return (
            f"TaskParameters(name={self.name!r}, chip_id={self.chip_id!r}, qid={self.qid!r}, "
            f"missing={self.missing!r})"
        )


class TaskRun(Run):
    """A dispatched single-task run, returned by :meth:`Tasks.run`.

    ``call`` is the :class:`~qdash.sdk.calibration.TaskCall` that was sent, and ``response``
    the dispatch response as the API returned it, including ``flow_run_id``. The run belongs
    to ``calibration_session_id`` and ``calibration_run_id``. :meth:`get` and :meth:`wait`
    follow the run as for a workflow; :meth:`results` reads the task's results.
    """

    def __init__(
        self,
        executions: Executions,
        call: TaskCall,
        *,
        chip_id: str,
        qid: str,
        response: ExecuteFlowResponse,
    ) -> None:
        super().__init__(executions, response.execution_id)
        self._call = call.model_copy(deep=True)
        self.chip_id = chip_id
        self.qid = qid
        self.response = response

    @property
    def call(self) -> TaskCall:
        """A copy of the task definition captured at launch."""
        return self._call.model_copy(deep=True)

    @property
    def name(self) -> str:
        """The task's name."""
        return self._call.name

    @property
    def calibration_session_id(self) -> str | None:
        """The run's calibration session: the one named, an automatic one, or None."""
        return self.response.calibration_session_id

    @property
    def calibration_run_id(self) -> str | None:
        """The run's record in that session."""
        return self.response.calibration_run_id

    def results(self) -> list[TaskResult]:
        """The results of this task on ``qid`` in the run's executions, as they are now.

        Reads the executions (see :meth:`executions`) and keeps every result whose name and
        target match the call, in execution order; other tasks the run reports, such as a
        reconfiguration, are left out. A run that has not reported the task yet returns an
        empty list, so call :meth:`wait` first.
        """
        return [
            task
            for execution in self.executions()
            for task in execution.tasks
            if task.name == self.name and task.qid == self.qid
        ]

    def __repr__(self) -> str:
        return f"TaskRun(name={self.name!r}, qid={self.qid!r}, execution_id={self.execution_id!r})"


class Tasks:
    """The task catalog and single-task runs, reached as ``QDash.tasks``."""

    def __init__(
        self, api: QDashApi, config: QDashConfig, executions: Executions, project_id: str | None
    ) -> None:
        self._api = api
        self._config = config
        self._executions = executions
        self._project_id = project_id

    def list(
        self, *, backend_name: str | None = None, enabled_only: bool = False
    ) -> list[TaskInfo]:
        """The task definitions of ``backend_name``, as the Task Workbench lists them.

        Each :class:`~qdash.sdk.types.TaskInfo` carries the task's ``input_parameters``,
        ``run_parameters``, ``output_parameters`` and whether it is ``enabled``; only enabled
        tasks can run. Without ``backend_name`` the project's configured default backend is
        used, which is read first.
        """
        backend = self._backend(backend_name)
        with api_errors():
            response = self._api.task_file.list_task_info(
                backend=backend,
                **given(enabled_only=_flag("enabled_only", enabled_only) or None),
                request_options=read_options(self._config),
            )
        return list(response.tasks)

    def get(self, name: str, *, backend_name: str | None = None) -> TaskInfo:
        """The definition of the task ``name`` in ``backend_name``'s catalog.

        Raises ``QDashNotFoundError`` when the catalog has no such task, and ``ValueError``
        when it lists more than one definition with the name.
        """
        checked = _identifier("name", name)
        matches = [task for task in self.list(backend_name=backend_name) if task.name == checked]
        if not matches:
            raise QDashNotFoundError(f"no task named {checked!r} in the task catalog")
        if len(matches) > 1:
            files = ", ".join(task.file_path for task in matches)
            raise ValueError(f"the task catalog defines {checked!r} more than once: {files}")
        return matches[0]

    def load_parameters(
        self,
        task_name: str,
        *,
        chip_id: str,
        qid: str,
        backend_name: str | None = None,
    ) -> TaskParameters:
        """The parameters a run of ``task_name`` on ``qid`` would start from, to edit and run.

        Reads the task definition (as :meth:`get`) and the current calibration data of
        ``qid`` on ``chip_id``, as the Task Workbench's reload of current inputs does, and
        returns them as :class:`TaskParameters`. Nothing is dispatched or written; call
        :meth:`TaskParameters.to_call` and :meth:`run` to run.

        Each input is looked up by its ``parameter_name`` (else its own name), then its
        ``parameter_aliases``, then its ``fallback_parameter_names``. For a qubit ``qid`` the
        source is the qubit's data. For a coupling ``qid`` (``"control-target"``) a
        ``control`` or ``target`` input reads that qubit's data, then the coupling's; a
        ``self`` or ``coupling`` input reads the coupling's. A stored ``{"value": ...}`` or
        bare value is used as it is; when none is found, or for ``resolution="default_only"``,
        the definition's ``default_value`` is used, else None. An explicit stored
        ``{"value": None}`` stays None rather than taking that default. An input whose resolution or
        ``qid_role`` the SDK does not know is left None and listed in
        :attr:`TaskParameters.unresolved`.

        The values are what the database holds now; the worker resolves the inputs again
        when the task runs, applies the overrides the call carries and validates them.

        Raises ``ValueError`` for a malformed coupling ``qid``, ``QDashNotFoundError`` when
        the task, qubit or coupling does not exist, and the other SDK errors for failed reads.
        """
        name = _identifier("task_name", task_name)
        chip = _identifier("chip_id", chip_id)
        target = _identifier("qid", qid)
        if "-" in target:
            _coupling_qids(target)
        backend = self._backend(backend_name)
        definition = self.get(name, backend_name=backend)
        coupling = "-" in target or definition.task_type == "coupling"
        options = read_options(self._config)
        role_sources: dict[str, list[dict[str, Any]]]
        with api_errors():
            if coupling:
                control_qid, target_qid = _coupling_qids(target)
                control = self._api.chip.get_chip_qubit(chip, control_qid, request_options=options)
                target_ = self._api.chip.get_chip_qubit(chip, target_qid, request_options=options)
                pair = self._api.chip.get_chip_coupling(chip, target, request_options=options)
                pair_data = pair.data or {}
                role_sources = {
                    "self": [pair_data],
                    "coupling": [pair_data],
                    "control": [control.data or {}, pair_data],
                    "target": [target_.data or {}, pair_data],
                }
            else:
                qubit = self._api.chip.get_chip_qubit(chip, target, request_options=options)
                data = qubit.data or {}
                role_sources = {role: [data] for role in _ROLES}
        inputs: dict[str, Any] = {}
        unresolved: list[str] = []
        for input_name, spec in (definition.input_parameters or {}).items():
            resolution = spec.get("resolution")
            role = spec.get("qid_role") or "self"
            if (resolution is not None and resolution not in _RESOLUTIONS) or role not in _ROLES:
                inputs[input_name] = None
                unresolved.append(input_name)
                continue
            value = _MISSING
            if resolution != "default_only":
                primary = (
                    str(spec.get("parameter_name") or input_name),
                    *_names(spec.get("parameter_aliases"), "parameter_aliases"),
                )
                fallback = _names(spec.get("fallback_parameter_names"), "fallback_parameter_names")
                value = _lookup(role_sources[role], primary, fallback)
            if value is _MISSING:
                value = spec.get("default_value")
                if value is None and resolution is None:
                    # Legacy declarations carry their fallback as the parameter's own value.
                    value = spec.get("value")
            inputs[input_name] = deepcopy(value)
        runs: dict[str, Any] = {}
        for run_name, spec in (definition.run_parameters or {}).items():
            default = spec.get("value")
            if default is None:
                continue
            value_type = spec.get("value_type")
            runs[run_name] = (
                {"value": deepcopy(default), "value_type": value_type}
                if value_type in _SWEEP_VALUE_TYPES
                else deepcopy(default)
            )
        return TaskParameters(
            definition,
            chip_id=chip,
            qid=target,
            backend_name=backend,
            input=inputs,
            run=runs,
            unresolved=unresolved,
        )

    def run(
        self,
        task: TaskCall | models.TaskCall | str,
        *,
        chip_id: str,
        qid: str,
        backend_name: str | None = None,
        input_parameters: Mapping[str, Any] | None = None,
        run_parameters: Mapping[str, Any] | None = None,
        update_calibration_parameters: bool | None = None,
        reconfigure: bool = False,
        update_params: bool = False,
        source_task_id: str | None = None,
        calibration_session_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> TaskRun:
        """Run one task on one qubit or coupling, as the Task Workbench does.

        ``task`` is a :class:`~qdash.sdk.calibration.TaskCall`, the same call a calibration
        step lists: ``TaskCall(name="CheckT1", run={...}, input={...})``. Its ``run`` and
        ``input`` are sent as the run's run and input parameter overrides as they are,
        including :mod:`~qdash.sdk.sweep` declarations, over the task's current definition
        and the chip's current calibration values. Its ``update_calibration_parameters``
        decides whether validated outputs replace the current calibration values; None leaves
        them unchanged, as in the Workbench, and the run still saves its history, figures and
        raw data. ``call_id`` and ``on_failure`` order calls within a pipeline step and have
        no meaning for a single task; a call that sets either is rejected before any request.

        A task name alone is short for ``TaskCall(name=...)``; only with a name may
        ``input_parameters``, ``run_parameters`` and ``update_calibration_parameters`` be
        passed here, so a call's own settings are never overridden or merged.

        ``reconfigure`` and ``update_params`` are sent as given, false by default as in the
        Workbench. ``source_task_id`` records the result this run repeats, for provenance
        only. The server rejects an unknown or disabled task, unknown parameters and values
        of the wrong type with ``QDashValidationError`` or a 400 ``QDashApiError``.

        Requires a configured project. The request is sent once: a transport error or an
        error status is raised, never retried. The run joins ``calibration_session_id`` when
        given, otherwise an automatic session; a retry with the same ``idempotency_key``
        returns the recorded run. With a session or key, a response that does not echo the
        recorded run raises ``RuntimeError``: reconcile the run instead of retrying. Returns
        once the run is dispatched; call :meth:`TaskRun.wait` to follow it.
        """
        call = self._call(task, input_parameters, run_parameters, update_calibration_parameters)
        chip = _identifier("chip_id", chip_id)
        target = _identifier("qid", qid)
        backend = _optional_identifier("backend_name", backend_name)
        source = _optional_identifier("source_task_id", source_task_id)
        session = _optional_identifier("calibration_session_id", calibration_session_id)
        key = _optional_identifier("idempotency_key", idempotency_key)
        reconfigure = _flag("reconfigure", reconfigure)
        update_params = _flag("update_params", update_params)
        if not self._project_id:
            raise QDashConfigError(
                "running a task needs a project: set QDASH_PROJECT_ID, "
                "project_id in the profile, or QDash(..., project_id=...)"
            )
        # The JSON form of the call: run and input go out exactly as a pipeline spec has them.
        spec = call.model_dump(mode="json")
        with api_errors():
            response = self._api.task.quick_run_task(
                call.name,
                chip_id=chip,
                qid=target,
                input_parameter_overrides=dict(spec.get("input") or {}),
                run_parameter_overrides=dict(spec.get("run") or {}),
                update_calibration_parameters=bool(call.update_calibration_parameters),
                reconfigure=reconfigure,
                update_params=update_params,
                **given(
                    backend_name=backend,
                    source_task_id=source,
                    calibration_session_id=session,
                    idempotency_key=key,
                ),
            )
        if session is not None or key is not None:
            check_recorded_launch(response, session, what="Task")
        return TaskRun(self._executions, call, chip_id=chip, qid=target, response=response)

    @staticmethod
    def _call(
        task: TaskCall | models.TaskCall | str,
        input_parameters: Mapping[str, Any] | None,
        run_parameters: Mapping[str, Any] | None,
        update_calibration_parameters: bool | None,
    ) -> TaskCall:
        if isinstance(task, str):
            options: dict[str, Any] = {"name": task}
            if input_parameters is not None:
                options["input"] = dict(input_parameters)
            if run_parameters is not None:
                options["run"] = dict(run_parameters)
            if update_calibration_parameters is not None:
                options["update_calibration_parameters"] = update_calibration_parameters
            return TaskCall(**options)
        if not isinstance(task, TaskCall | models.TaskCall):
            raise TypeError(f"task must be a TaskCall or a task name, got {type(task).__name__}")
        duplicated = [
            label
            for label, value in (
                ("input_parameters", input_parameters),
                ("run_parameters", run_parameters),
                ("update_calibration_parameters", update_calibration_parameters),
            )
            if value is not None
        ]
        if duplicated:
            raise TypeError(
                f"the TaskCall already carries its settings; set {', '.join(duplicated)} on "
                "the TaskCall (input, run, update_calibration_parameters) instead"
            )
        pipeline_only = [
            label
            for label, value in (("call_id", task.call_id), ("on_failure", task.on_failure))
            if value is not None
        ]
        if pipeline_only:
            raise ValueError(
                f"{' and '.join(pipeline_only)} only apply to calls within a calibration "
                "pipeline step; a single task run cannot carry them. Remove them, or run the "
                "call in a step with CalibrationSession.run(...)"
            )
        if isinstance(task, TaskCall):
            return task.model_copy(deep=True)
        return TaskCall.model_validate(task.model_dump(exclude_unset=True))

    def _backend(self, backend_name: str | None) -> str:
        if backend_name is not None:
            return _identifier("backend_name", backend_name)
        with api_errors():
            settings = self._api.task_file.get_task_file_settings(
                request_options=read_options(self._config)
            )
        if not settings.default_backend:
            raise QDashConfigError(
                "the server reports no default task backend; pass backend_name=..."
            )
        return settings.default_backend
