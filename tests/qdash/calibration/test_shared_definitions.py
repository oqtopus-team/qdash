"""``qdash.calibration`` means what the server's spec model and the worker mean.

The shared definitions are separate light classes; these tests hold them to the server's
``CalibrationPipelineSpec`` field for field and default for default, and check that the SDK's
JSON and the worker's conversion of the same definitions agree, for every bundled template.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter

import qdash.calibration as shared
from qdash.calibration import (
    STEP_TYPES,
    CalibrationStepDefinition,
    CouplingTargets,
    ExecutionStep,
    MuxTargets,
    QubitTargets,
    TaskCall,
    pipeline_spec,
)
from qdash.datamodel import calibration_pipeline as server
from qdash.datamodel import sweep as server_sweep
from qdash.datamodel.task_call import TaskCall as WorkerTaskCall
from qdash.workflow import sweep as workflow_sweep
from qdash.workflow.service.definitions import runtime_steps
from tests.qdash.workflow.calibration_session_fake import install_fake_session

SERVER_STEPS: dict[str, type[BaseModel]] = {
    "ConfigureAll": server.ConfigureAllStep,
    "BringUp": server.BringUpStep,
    "OneQubitCheck": server.OneQubitCheckStep,
    "OneQubitFineTune": server.OneQubitFineTuneStep,
    "CustomOneQubit": server.CustomOneQubitStep,
    "FilterByStatus": server.FilterByStatusStep,
    "FilterByMetric": server.FilterByMetricStep,
    "GenerateCRSchedule": server.GenerateCRScheduleStep,
    "TwoQubitCalibration": server.TwoQubitCalibrationStep,
    "CustomTwoQubit": server.CustomTwoQubitStep,
}


def test_every_server_step_type_has_a_definition() -> None:
    assert set(STEP_TYPES) == set(SERVER_STEPS) == set(server.STEP_CATALOG)


@pytest.mark.parametrize("step_type", sorted(SERVER_STEPS))
def test_definitions_have_the_server_fields_and_defaults(step_type: str) -> None:
    definition = STEP_TYPES[step_type].model_fields
    model = SERVER_STEPS[step_type].model_fields
    assert set(definition) == set(model) - {"type"}
    for name, info in definition.items():
        server_field = model[name]
        assert info.is_required() == server_field.is_required(), name
        if not info.is_required():
            assert info.get_default(call_default_factory=True) == server_field.get_default(
                call_default_factory=True
            ), name


def test_targets_and_task_calls_mirror_the_server_models() -> None:
    assert set(QubitTargets.model_fields) | set(MuxTargets.model_fields) | set(
        CouplingTargets.model_fields
    ) == set(server.PipelineTargets.model_fields)
    # The worker's call is the definition with its normalization: the same fields.
    assert issubclass(WorkerTaskCall, TaskCall)
    assert WorkerTaskCall.model_fields.keys() == TaskCall.model_fields.keys()
    for name, info in TaskCall.model_fields.items():
        assert WorkerTaskCall.model_fields[name].metadata == info.metadata, name


def test_sweeps_are_one_implementation() -> None:
    for name in ("values", "linspace", "logspace", "arange", "range"):
        assert getattr(workflow_sweep, name) is getattr(shared.sweep, name)
        assert getattr(server_sweep, name) is getattr(shared.sweep, name)
    assert workflow_sweep.Sweep is shared.sweep.Sweep
    declared = shared.sweep.logspace(2, 5, 4)
    assert declared == {"value": [2, 5, 4], "value_type": "np.logspace"}
    assert WorkerTaskCall(name="CheckT1", run={"time_range": declared}).run == {
        "time_range": {"value": (2, 5, 4), "value_type": "np.logspace"}
    }


EXAMPLES: list[ExecutionStep] = [
    shared.ConfigureAll(call=TaskCall(name="ConfigureAll", run={"configuration_mode": "ge-ef-cr"})),
    shared.BringUp(execution_mode="sequential"),
    shared.OneQubitCheck(),
    shared.OneQubitFineTune(execution_mode="manual", rounds=[["0"], ["1"]], step_id="fine"),
    shared.FilterByStatus(step="fine"),
    shared.CustomOneQubit(
        step_name="ramsey",
        tasks=[
            TaskCall(name="CheckRamsey", call_id="coarse", run={"detuning": 0.001}),
            TaskCall(name="CheckRamsey", call_id="fine", on_failure="continue"),
        ],
        continue_on_failure=True,
    ),
    shared.FilterByMetric(step="ramsey", call_id="fine", metric="t2_star", threshold=10.0),
    shared.GenerateCRSchedule(max_parallel_ops=4, inverse=True),
    shared.TwoQubitCalibration(),
    shared.CustomTwoQubit(
        execution_mode="manual",
        rounds=[[("0", "1")]],
        tasks=[TaskCall(name="CheckCrossResonance")],
    ),
]


def test_the_sdk_json_and_the_worker_conversion_agree() -> None:
    spec = pipeline_spec(QubitTargets(["0", "1"]), EXAMPLES, name="example", tags=["t"])
    parsed = server.CalibrationPipelineSpec.model_validate(spec)
    # Only what was set is sent; the server's defaults fill in the rest.
    assert spec["steps"][2] == {"type": "OneQubitCheck"}
    adapter: TypeAdapter[Any] = TypeAdapter(server.PipelineStep)
    worker = runtime_steps(EXAMPLES)
    from qdash.workflow.service.pipeline_flow import build_step

    for sent, server_step, built in zip(spec["steps"], parsed.steps, worker, strict=True):
        from_sdk = build_step(adapter.validate_python(sent))
        assert type(from_sdk) is type(built)
        assert from_sdk == built, server_step.type
        assert server_step.model_dump(mode="json") == adapter.validate_python(sent).model_dump(
            mode="json"
        )


TEMPLATES: dict[str, tuple[str, dict[str, Any]]] = {
    "box_setup": ("box_setup", {"mux_ids": [0]}),
    "bringup": ("bringup", {"mux_ids": [0]}),
    "characterization": ("characterization", {"mux_ids": [0]}),
    "check_waveform": ("check_waveform", {"mux_ids": [0]}),
    "coarse_one": ("coarse_one", {"mux_ids": [0]}),
    "coherence_check": ("coherence_check", {"mux_ids": [0]}),
    "coherence_limit": ("coherence_limit", {"mux_ids": [0]}),
    "ef_calibration": ("ef_calibration", {"mux_ids": [0]}),
    "fake_backend": ("fake_calibration", {"mux_ids": [0]}),
    "fast_full_calibration": ("fast_full_calibration", {"mux_ids": [0]}),
    "fine_one": ("fine_one", {"mux_ids": [0]}),
    "full_calibration": ("full_calibration", {"mux_ids": [0]}),
    "one_qubit": ("one_qubit", {"mux_ids": [0]}),
    "simple": ("simple_calibration", {"mux_ids": [0]}),
    "two_qubit": ("two_qubit", {"qids": ["0", "1"]}),
    "two_qubit_manual_rounds": ("two_qubit_manual_rounds", {}),
    "two_qubit_pairs": ("two_qubit_pairs", {"coupling_pairs": [["0", "1"]]}),
}


@pytest.mark.parametrize("module_name", sorted(TEMPLATES))
def test_every_template_writes_a_spec_the_server_accepts(
    monkeypatch: pytest.MonkeyPatch, module_name: str
) -> None:
    """A template's definitions are a valid pipeline spec, so the SDK could send them."""
    module = importlib.import_module(f"qdash.workflow.templates.{module_name}")
    fake = install_fake_session(monkeypatch, module)
    function, parameters = TEMPLATES[module_name]
    flow = getattr(module, function)
    result = getattr(flow, "fn", flow)(username="alice", chip_id="64Q", **parameters)

    definitions = result["definitions"]
    assert all(isinstance(step, ExecutionStep) for step in definitions)
    assert fake.last_definitions == definitions
    spec = pipeline_spec(result["definition_targets"], definitions)
    parsed = server.CalibrationPipelineSpec.model_validate(spec)
    assert [step.type for step in parsed.steps] == [type(step).type for step in definitions]
    assert getattr(flow, "qdash_session_name", None)


def test_every_step_is_an_execution_step_and_the_old_name_stays() -> None:
    """Measurement and transform definitions share one public base, which is pure to build."""
    steps: list[ExecutionStep] = [
        shared.OneQubitCheck(step_id="check"),
        shared.FilterByStatus(step="check"),
        shared.GenerateCRSchedule(max_parallel_ops=4),
    ]
    assert all(isinstance(step, ExecutionStep) for step in steps)
    assert all(issubclass(cls, ExecutionStep) for cls in STEP_TYPES.values())
    # The earlier name is the same class, so existing imports and isinstance checks hold.
    assert CalibrationStepDefinition is ExecutionStep
    assert shared.ExecutionStep is ExecutionStep
    assert [step.to_spec()["type"] for step in steps] == [
        "OneQubitCheck",
        "FilterByStatus",
        "GenerateCRSchedule",
    ]
