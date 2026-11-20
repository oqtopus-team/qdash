"""The qdash.sdk calibration and pipeline examples against the real calibration pipeline routes.

The SDK's QDashClient sends its requests through FastAPI's TestClient, so the spec it builds
is parsed by the server's CalibrationPipelineSpec and checked by the same preflight as any
other request. Prefect dispatch is patched; nothing runs.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from qdash.client import QDashClient, QDashConfig
from qdash.client.services.models import CustomTwoQubitStep, TwoQubitCalibrationStep
from qdash.datamodel import sweep as server_sweep
from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec as ServerSpec
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.sdk import QDash, QDashApiError, QDashValidationError
from qdash.sdk.calibration import MuxTargets, QubitTargets
from qdash.sdk.pipeline import CustomOneQubit, Pipeline, Qubits, TaskCall, sweep, to_spec
from tests.qdash.api.routers.test_calibration_pipeline import (  # noqa: F401 - pytest fixtures
    CHIP,
    chip,
    test_project,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

# Values CheckT1 and CheckT2Echo read from earlier Rabi and pulse calibration.
COHERENCE_INPUTS = (
    "control_amplitude",
    "hpi_amplitude",
    "hpi_duration",
    "pi_amplitude",
    "pi_duration",
    "maximum_rabi_frequency",
    "rabi_amplitude",
    "rabi_angle",
    "rabi_distance",
    "rabi_noise",
    "rabi_offset",
    "rabi_phase",
    "rabi_r2",
    "rabi_reference_phase",
)
READOUT_DURATION = 1024
TIME_RANGE = sweep.logspace(math.log10(300), math.log10(500_000), 51)
RUN_PARAMETERS = {"readout_duration": READOUT_DURATION, "interval": 262_144}


def coherence_steps() -> list[CustomOneQubit]:
    return [
        CustomOneQubit(
            step_name="coherence",
            tasks=[
                TaskCall(name="Configure"),
                TaskCall(name="CheckT1", run={"time_range": TIME_RANGE}),
                TaskCall(name="CheckT2Echo", run={"time_range": TIME_RANGE}),
            ],
        ),
    ]


def patched_dispatch() -> tuple[AsyncMock, Any]:
    """Patch the Prefect calls of execute; returns create_flow_run and the patch context."""
    create_flow_run = AsyncMock(return_value="flow-run-1")
    gateway = "qdash.api.services.flow_service.prefect_gateway.PrefectGateway"
    context = patch.multiple(
        gateway,
        read_deployment_id=AsyncMock(return_value="deployment-1"),
        create_flow_run=create_flow_run,
    )
    return create_flow_run, context


def coherence_pipeline() -> Pipeline:
    return Pipeline(
        name="coherence-t1-t2echo",
        targets=Qubits(["0", "1"]),
        steps=[
            CustomOneQubit(
                step_name="coherence",
                tasks=[
                    TaskCall(name="Configure"),
                    TaskCall(name="CheckT1", run={"time_range": TIME_RANGE}),
                    TaskCall(name="CheckT2Echo", run={"time_range": TIME_RANGE}),
                ],
            ),
        ],
        default_run_parameters={"readout_duration": READOUT_DURATION, "interval": 262_144},
    )


@pytest.fixture
def calibrated_chip(chip: None) -> None:  # noqa: F811
    """Give every qubit the Rabi and pulse values, measured at the example's readout duration."""
    now = datetime.now(UTC)
    for qubit in QubitDocument.find({"chip_id": CHIP}).run():
        rabi_task_id = f"rabi-{qubit.qid}"
        TaskResultHistoryDocument(
            project_id="test_project",
            username="test_user",
            task_id=rabi_task_id,
            name="CheckRabi",
            upstream_id="",
            status="completed",
            message="",
            input_parameters={},
            output_parameters={},
            output_parameter_names=[],
            run_parameters={"readout_duration": {"value": READOUT_DURATION}},
            note={},
            figure_path=[],
            json_figure_path=[],
            raw_data_path=[],
            start_at=now,
            end_at=now,
            elapsed_time=1.0,
            task_type="qubit",
            system_info=SystemInfoModel(),
            qid=qubit.qid,
            execution_id="exec-rabi",
            tags=[],
            chip_id=CHIP,
        ).insert()
        values = {name: {"value": 1.0, "task_id": rabi_task_id} for name in COHERENCE_INPUTS}
        qubit.data = {**qubit.data, **values}
        qubit.save()


@pytest.fixture
def qdash(test_client: Any, chip: None) -> Iterator[QDash]:  # noqa: F811
    config = QDashConfig(
        base_url=str(test_client.base_url),
        api_token="test_token",
        project_id="test_project",
    )
    client = QDashClient(config, http_client=test_client)
    with QDash(client) as session:
        yield session


def test_sdk_spec_is_accepted_by_the_server_model() -> None:
    spec = coherence_pipeline().to_spec()

    parsed = ServerSpec.model_validate(spec)

    assert [call.resolved_call_id for _, call in parsed.all_calls()] == [
        "Configure",
        "CheckT1",
        "CheckT2Echo",
    ]
    assert parsed.targets.qids == ["0", "1"]


MANUAL = {"execution_mode": "manual", "rounds": [[["0", "1"]]]}
TWO_QUBIT_STEPS = {
    "CustomTwoQubit": lambda **fields: CustomTwoQubitStep(
        type="CustomTwoQubit", tasks=[TaskCall(name="CheckCrossResonance")], **fields
    ),
    "TwoQubitCalibration": lambda **fields: TwoQubitCalibrationStep(
        type="TwoQubitCalibration", **fields
    ),
}


def after_check(step: Any) -> Pipeline:
    return Pipeline(targets=Qubits(["0", "1"]), steps=[{"type": "OneQubitCheck"}, step])


@pytest.mark.parametrize("step_type", TWO_QUBIT_STEPS)
def test_generated_manual_two_qubit_steps_are_accepted_however_serialized(step_type: str) -> None:
    step = TWO_QUBIT_STEPS[step_type](**MANUAL)

    # to_spec writes only the set fields. A plain dump writes every field: the unset cap as
    # null and the empty collections at their defaults. A mapping is sent unchanged.
    for spec in (
        after_check(step).to_spec(),
        after_check(step).model_dump(mode="json"),
        after_check(step.model_dump(mode="json")).to_spec(),
        to_spec(after_check(step).model_dump(mode="json")),
    ):
        parsed = ServerSpec.model_validate(spec)
        assert parsed.steps[1].execution_mode == "manual"  # type: ignore[union-attr]


@pytest.mark.parametrize("step_type", TWO_QUBIT_STEPS)
def test_generated_two_qubit_caps_keep_the_server_rules(step_type: str) -> None:
    manual = after_check(TWO_QUBIT_STEPS[step_type](**MANUAL, max_parallel_ops=4))
    automatic = after_check(TWO_QUBIT_STEPS[step_type](max_parallel_ops=4))

    for spec in (manual.to_spec(), manual.model_dump(mode="json")):
        with pytest.raises(ValueError, match="max_parallel_ops only caps automatic"):
            ServerSpec.model_validate(spec)
    for spec in (automatic.to_spec(), automatic.model_dump(mode="json")):
        parsed = ServerSpec.model_validate(spec)
        assert parsed.steps[1].max_parallel_ops == 4  # type: ignore[union-attr]


def test_sdk_sweeps_match_the_server_sweeps() -> None:
    pairs = [
        (sweep.logspace(2.5, 5.7, 51), server_sweep.logspace(2.5, 5.7, 51)),
        (sweep.linspace(-0.05, 0.05, 41), server_sweep.linspace(-0.05, 0.05, 41)),
        (sweep.arange(0, 10_001, 100), server_sweep.arange(0, 10_001, 100)),
        (sweep.range(0, 10, 2), server_sweep.range(0, 10, 2)),
        (sweep.values(1, 2.5), server_sweep.values(1, 2.5)),
    ]
    for ours, theirs in pairs:
        expected = theirs.as_run_parameter()
        assert ours == {**expected, "value": list(expected["value"])}  # type: ignore[call-overload]


@pytest.mark.usefixtures("calibrated_chip")
def test_validate_resolves_the_example_without_dispatching(qdash: QDash) -> None:
    create_flow_run = AsyncMock(return_value="flow-run-1")
    with patch(
        "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
        new=create_flow_run,
    ):
        result = qdash.pipelines.validate(coherence_pipeline(), chip_id=CHIP)

    assert result.valid is True, result.problems
    assert result.steps is not None
    assert result.steps[0].tasks == ["Configure", "CheckT1", "CheckT2Echo"]
    assert result.task_run_count == 3
    create_flow_run.assert_not_called()


def test_validate_reports_missing_calibration_data(qdash: QDash) -> None:
    # Locally the spec is well formed; only the server knows the qubits lack Rabi data.
    result = qdash.pipelines.validate(coherence_pipeline(), chip_id=CHIP)

    assert result.valid is False
    assert result.problems is not None
    assert {problem.path for problem in result.problems} == {
        "steps[0].tasks[1]",
        "steps[0].tasks[2]",
    }


def test_validate_reports_server_problems_as_data(qdash: QDash) -> None:
    pipeline = coherence_pipeline()
    pipeline.targets = Qubits(["99"])

    result = qdash.pipelines.validate(pipeline, chip_id=CHIP)

    assert result.valid is False
    assert result.problems is not None
    assert result.problems[0].path == "targets.qids[0]"


@pytest.mark.usefixtures("calibrated_chip")
def test_execute_dispatches_the_validated_spec(qdash: QDash) -> None:
    read_deployment = AsyncMock(return_value="deployment-1")
    create_flow_run = AsyncMock(return_value="flow-run-1")
    with (
        patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.read_deployment_id",
            new=read_deployment,
        ),
        patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
            new=create_flow_run,
        ),
    ):
        run = qdash.pipelines.execute(coherence_pipeline(), chip_id=CHIP)

    assert run.response.flow_run_id == "flow-run-1"
    create_flow_run.assert_awaited_once()
    parameters = create_flow_run.call_args.kwargs["parameters"]
    assert parameters["project_id"] == "test_project"
    tasks = parameters["spec"]["steps"][0]["tasks"]
    assert [task["name"] for task in tasks] == ["Configure", "CheckT1", "CheckT2Echo"]
    assert tasks[1]["run"]["time_range"]["value_type"] == "np.logspace"


def test_execute_rejects_an_invalid_spec_before_dispatch(qdash: QDash) -> None:
    pipeline = coherence_pipeline()
    pipeline.targets = Qubits(["99"])
    create_flow_run = AsyncMock(return_value="flow-run-1")
    with (
        patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
            new=create_flow_run,
        ),
        pytest.raises(QDashValidationError) as raised,
    ):
        qdash.pipelines.execute(pipeline, chip_id=CHIP)

    assert raised.value.status_code == 422
    assert isinstance(raised.value.payload, dict)
    assert raised.value.payload["detail"]["problems"][0]["path"] == "targets.qids[0]"
    create_flow_run.assert_not_called()


def test_execute_without_editor_role_is_refused(qdash: QDash) -> None:
    membership = ProjectMembershipDocument.find_one({"username": "test_user"}).run()
    assert membership is not None
    membership.role = ProjectRole.VIEWER
    membership.save()

    with pytest.raises(QDashApiError) as raised:
        qdash.pipelines.execute(coherence_pipeline(), chip_id=CHIP)

    assert raised.value.status_code == 403


@pytest.mark.parametrize(
    ("targets", "expected"),
    [
        (QubitTargets(["0", "1"]), {"qids": ["0", "1"], "mux_ids": None, "exclude_qids": []}),
        (
            MuxTargets([0, 1], exclude_qids=["2"]),
            {"qids": None, "mux_ids": [0, 1], "exclude_qids": ["2"]},
        ),
    ],
)
def test_calibration_targets_parse_into_the_server_targets(
    targets: QubitTargets | MuxTargets, expected: dict[str, Any]
) -> None:
    spec = Pipeline(targets=targets, steps=coherence_steps()).to_spec()

    assert ServerSpec.model_validate(spec).targets.model_dump() == expected


@pytest.mark.usefixtures("calibrated_chip")
def test_validate_calibration_checks_the_example_without_dispatching(qdash: QDash) -> None:
    create_flow_run, dispatch = patched_dispatch()
    with dispatch:
        check = qdash.chip(CHIP).validate_calibration(
            QubitTargets(["0", "1"]), coherence_steps(), default_run_parameters=RUN_PARAMETERS
        )

    assert check.valid is True, check.problems
    assert check.steps is not None
    assert check.steps[0].tasks == ["Configure", "CheckT1", "CheckT2Echo"]
    create_flow_run.assert_not_called()


def test_validate_calibration_reports_missing_calibration_data(qdash: QDash) -> None:
    check = qdash.chip(CHIP).validate_calibration(
        QubitTargets(["0", "1"]), coherence_steps(), default_run_parameters=RUN_PARAMETERS
    )

    assert check.valid is False
    assert check.problems is not None
    assert {problem.path for problem in check.problems} == {
        "steps[0].tasks[1]",
        "steps[0].tasks[2]",
    }


@pytest.mark.usefixtures("calibrated_chip")
def test_calibrate_dispatches_the_same_spec_as_the_pipeline(qdash: QDash) -> None:
    create_flow_run, dispatch = patched_dispatch()
    with dispatch:
        run = qdash.chip(CHIP).calibrate(
            QubitTargets(["0", "1"]),
            coherence_steps(),
            name="coherence-t1-t2echo",
            default_run_parameters=RUN_PARAMETERS,
            tags=["sdk"],
        )

    assert run.response.flow_run_id == "flow-run-1"
    create_flow_run.assert_awaited_once()
    parameters = create_flow_run.call_args.kwargs["parameters"]
    assert parameters["project_id"] == "test_project"
    expected = ServerSpec.model_validate({**coherence_pipeline().to_spec(), "tags": ["sdk"]})
    assert ServerSpec.model_validate(parameters["spec"]) == expected


def test_calibrate_rejects_an_invalid_calibration_before_dispatch(qdash: QDash) -> None:
    create_flow_run, dispatch = patched_dispatch()
    with dispatch, pytest.raises(QDashValidationError) as raised:
        qdash.chip(CHIP).calibrate(QubitTargets(["99"]), coherence_steps())

    assert raised.value.status_code == 422
    assert isinstance(raised.value.payload, dict)
    assert raised.value.payload["detail"]["problems"][0]["path"] == "targets.qids[0]"
    create_flow_run.assert_not_called()


def test_calibrate_without_editor_role_is_refused(qdash: QDash) -> None:
    membership = ProjectMembershipDocument.find_one({"username": "test_user"}).run()
    assert membership is not None
    membership.role = ProjectRole.VIEWER
    membership.save()

    with pytest.raises(QDashApiError) as raised:
        qdash.chip(CHIP).calibrate(QubitTargets(["0", "1"]), coherence_steps())

    assert raised.value.status_code == 403
