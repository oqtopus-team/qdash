"""Check the TaskCall flow-parameter contract of the templates against real Prefect.

The pytest process replaces ``prefect`` with a stub (``tests/conftest.py``), so
``test_task_call_flow_parameters.py`` runs this file in a separate interpreter.
It needs no Prefect server, database, or hardware: it uses the same functions a
deployment run goes through, in order:

1. ``ExecuteFlowRequest`` → JSON, as ``POST /flows/{name}/execute`` receives the
   parameters and the API forwards them to ``create_flow_run_from_deployment``;
2. ``parameter_schema`` and ``schema_tools.validate``, the Prefect server's
   parameter-schema check (QDash registers deployments with an empty schema,
   so this shows the payload would also pass if enforcement were on);
3. ``Flow.validate_parameters``, which the flow engine calls on the worker
   before running the flow function;
4. the flow function itself, with ``CalibService`` replaced by a recorder, to
   read the steps it builds.

It prints one JSON object: the calls it sent and a result per template module.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

from prefect import Flow
from prefect.exceptions import ParameterTypeError
from prefect.utilities.callables import parameter_schema
from prefect.utilities.schema_tools import validate

from qdash.api.schemas.flow import ExecuteFlowRequest
from qdash.datamodel.task_call import StepCalls
from qdash.workflow.service._internal.settings import WorkerSpec

CALLS: list[dict[str, Any]] = [
    {
        "name": "CheckRamsey",
        "call_id": "ramsey_coarse",
        "run": {"detuning": 0.001},
        "on_failure": "stop",
    },
    {
        "name": "CheckRamsey",
        "call_id": "ramsey_fine",
        "run": {"detuning": 0.0002},
        "input": {"qubit_frequency": {"value": 5.0}},
        "update_calibration_parameters": False,
        "on_failure": "continue",
    },
]
TEMPLATES: dict[str, tuple[str, dict[str, Any]]] = {
    "simple": ("simple_calibration", {"mux_ids": [0]}),
    "fake_backend": ("fake_calibration", {"qids": ["0"]}),
    "two_qubit": ("two_qubit", {"qids": ["0", "1"]}),
    "two_qubit_pairs": ("two_qubit_pairs", {"coupling_pairs": [["0", "1"]]}),
    "two_qubit_manual_rounds": ("two_qubit_manual_rounds", {}),
}


class _RecordingCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    @classmethod
    def from_context(cls, *args: Any, **kwargs: Any) -> _RecordingCalibService:
        return cls()

    def run(self, targets: Any, *, steps: list[Any]) -> list[Any]:
        return steps


def _wire(parameters: dict[str, Any]) -> dict[str, Any]:
    """The parameters as the API receives them and forwards them to Prefect."""
    body = ExecuteFlowRequest(parameters=parameters).model_dump_json()
    loaded: dict[str, Any] = json.loads(body)["parameters"]
    return loaded


def _rejected(flow: Flow[..., Any], parameters: dict[str, Any]) -> bool:
    try:
        flow.validate_parameters(parameters)
    except ParameterTypeError:
        return True
    return False


def _schema_rejects(schema: dict[str, Any], parameters: dict[str, Any]) -> bool:
    try:
        validate(parameters, schema, raise_on_error=True)
    except Exception:
        return True
    return False


def _call_step(steps: list[Any]) -> Any:
    return next(step for step in reversed(steps) if getattr(step, "tasks", None) is not None)


def check(module_name: str, function: str, required: dict[str, Any]) -> dict[str, Any]:
    module = importlib.import_module(f"qdash.workflow.templates.{module_name}")
    flow = getattr(module, function)
    assert isinstance(flow, Flow), f"{module_name}.{function} is not a Prefect flow"
    module.CalibService = _RecordingCalibService  # type: ignore[attr-defined]
    if hasattr(module, "resolve_calib_context"):
        module.resolve_calib_context = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    schema = parameter_schema(flow.fn).model_dump_for_openapi()
    base = {"username": "alice", "chip_id": "64Q", **required}

    parameters = _wire({**base, "tasks": CALLS})
    validate(parameters, schema, raise_on_error=True)
    validated = flow.validate_parameters(parameters)
    step = _call_step(flow.fn(**validated))

    defaults = flow.validate_parameters(_wire(base))
    default_step = _call_step(flow.fn(**defaults))

    duplicates = flow.validate_parameters(
        _wire({**base, "tasks": [{"name": "CheckRamsey"}, {"name": "CheckRamsey"}]})
    )
    try:
        flow.fn(**duplicates)
        duplicate_error = ""
    except ValueError as exc:
        duplicate_error = str(exc)

    names = _wire({**base, "tasks": ["CheckT1"]})
    unknown_field = _wire({**base, "tasks": [{"name": "CheckT1", "shots": 10}]})
    return {
        "tasks_schema": schema["properties"]["tasks"],
        "task_call_properties": sorted(schema["definitions"]["TaskCall"]["properties"]),
        "wire_tasks": parameters["tasks"],
        "validated_types": [type(call).__name__ for call in validated["tasks"]],
        "validated": [call.model_dump(exclude_none=True) for call in validated["tasks"]],
        "step_type": type(step).__name__,
        "step_calls": [call.model_dump(exclude_none=True) for call in step.tasks],
        "default_tasks_parameter": defaults.get("tasks"),
        "default_step_type": type(default_step).__name__,
        "default_call_count": len(default_step.tasks),
        "default_types": sorted({type(call).__name__ for call in default_step.tasks}),
        "duplicate_error": duplicate_error,
        "names_rejected_by_flow": _rejected(flow, names),
        "names_rejected_by_schema": _schema_rejects(schema, names),
        "unknown_field_rejected_by_flow": _rejected(flow, unknown_field),
    }


def worker_spec_contract() -> dict[str, Any]:
    """A WorkerSpec crosses the Prefect flow and Dask process boundaries unchanged."""
    import cloudpickle
    from prefect import flow
    from prefect.utilities.hashing import hash_objects

    from qdash.common.mux_mapping import MuxMapping, MuxMappingSnapshot
    from qdash.datamodel.task_call import TaskCall as Call
    from qdash.datamodel.task_call import normalize_calls
    from qdash.workflow.service._internal.settings import (
        ReservationScope,
        SessionSettings,
        SnapshotSource,
        WorkerLease,
    )

    spec = WorkerSpec(
        settings=SessionSettings(
            username="alice",
            chip_id="64Q",
            project_id="project-1",
            backend_name="fake",
            task_defaults={"CheckRabi": {"run": {"shots": 256}}},
            snapshot=SnapshotSource(
                execution_id="exec-src", task_id="task-src", exempt_tasks=frozenset({"Configure"})
            ),
            force_update_params=True,
        ).for_worker(),
        lease=WorkerLease(
            execution_id="exec-1",
            reservation=ReservationScope(chip_id="64Q", resources=("mux:0",)),
        ),
        # A synthetic explicit mapping with a standalone qubit, so the pinned
        # membership is part of what must cross the boundaries unchanged.
        mux_mapping=MuxMappingSnapshot.of(
            MuxMapping.from_groups(
                {0: ["0", "1", "2", "3"], 2: ["8", "10"]},
                topology_id="synthetic",
                known_qids=["0", "1", "2", "3", "8", "10", "20"],
            )
        ),
    )
    plan = StepCalls(step_id="step", calls=normalize_calls([Call(name="CheckRabi")]))

    # Annotated like the worker flows in scheduling_tasks: resolved from module globals.
    @flow
    def borrow(worker: WorkerSpec, plan: StepCalls) -> WorkerSpec:
        return worker

    validated = borrow.validate_parameters({"worker": spec, "plan": plan})
    from_json = borrow.validate_parameters(
        {"worker": spec.model_dump(mode="json"), "plan": plan.model_dump(mode="json")}
    )
    return {
        "validated_equal": validated["worker"] == spec,
        "json_validated_equal": from_json["worker"] == spec,
        "cloudpickle_equal": cloudpickle.loads(cloudpickle.dumps(spec)) == spec,
        "hashable": hash_objects(spec, plan) is not None,
    }


def main() -> None:
    results = {
        module: check(module, function, required)
        for module, (function, required) in TEMPLATES.items()
    }
    print(
        json.dumps(
            {"calls": CALLS, "templates": results, "worker_spec": worker_spec_contract()},
            default=str,
        )
    )


if __name__ == "__main__":
    main()
