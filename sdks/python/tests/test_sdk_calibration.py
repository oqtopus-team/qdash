"""The calibration front door: QDash.chip, validate_calibration, calibrate and the result."""

from __future__ import annotations

import json
import math
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from test_sdk_session import CHIP, Server, detail, execute_body, validate_body

from qdash.sdk import (
    Chip,
    QDash,
    QDashConfigError,
    QDashValidationError,
    RunResult,
    calibration,
    pipeline,
)
from qdash.sdk.calibration import CustomOneQubit, MuxTargets, QubitTargets, TaskCall, sweep
from qdash.sdk.pipeline import Pipeline
from qdash.sdk.types import ExecutionResponseDetail

TIME_RANGE = sweep.logspace(math.log10(300), math.log10(500_000), 51)
RUN_PARAMETERS = {"readout_duration": 1024, "interval": 262_144}


def coherence_steps() -> list[CustomOneQubit]:
    return [
        CustomOneQubit(
            step_name="coherence",
            tasks=[
                TaskCall(name="Configure"),
                TaskCall(name="CheckT1", run={"time_range": TIME_RANGE}),
                TaskCall(name="CheckT2Echo", run={"time_range": TIME_RANGE}),
            ],
        )
    ]


def expected_spec() -> dict[str, Any]:
    return Pipeline(
        name="coherence-t1-t2echo",
        targets=QubitTargets(["0", "1"]),
        steps=coherence_steps(),
        default_run_parameters=RUN_PARAMETERS,
        tags=["sdk"],
    ).to_spec()


def calibrate(chip: Chip) -> Any:
    return chip.calibrate(
        QubitTargets(["0", "1"]),
        coherence_steps(),
        name="coherence-t1-t2echo",
        default_run_parameters=RUN_PARAMETERS,
        tags=["sdk"],
    )


def test_calibration_reexports_the_shared_definitions() -> None:
    import qdash.calibration as shared

    for name in ("CustomOneQubit", "MuxTargets", "QubitTargets", "TaskCall", "sweep"):
        assert getattr(calibration, name) is getattr(shared, name)
    # qdash.sdk.sweep is the shared module's helpers, so both write the same JSON.
    assert pipeline.sweep.linspace is shared.sweep.linspace


def test_targets_serialize_like_the_workflow_targets() -> None:
    assert QubitTargets(["0", "1"]).model_dump(exclude_unset=True) == {"qids": ["0", "1"]}
    assert QubitTargets(qids=("4",)).model_dump(exclude_unset=True) == {"qids": ["4"]}
    assert MuxTargets([0, 1]).model_dump(exclude_unset=True) == {"mux_ids": [0, 1]}
    assert MuxTargets([2], exclude_qids=["9"]).model_dump(exclude_unset=True) == {
        "mux_ids": [2],
        "exclude_qids": ["9"],
    }
    with pytest.raises(TypeError):
        QubitTargets("01")
    with pytest.raises(TypeError):
        MuxTargets([0], exclude_qids="5")
    with pytest.raises(ValidationError):
        MuxTargets(["a"])  # type: ignore[list-item]


def test_chip_binds_the_session_without_requests() -> None:
    server = Server()
    qdash = server.session()
    chip = qdash.chip(CHIP)
    coherence_steps()

    assert chip.chip_id == CHIP
    assert repr(chip) == f"Chip({CHIP!r})"
    assert server.requests == []
    with pytest.raises(ValueError, match="chip_id"):
        qdash.chip("")
    qdash.close()


def test_validate_calibration_posts_the_spec_and_dispatches_nothing() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/validate"): [
                httpx.Response(200, json=validate_body(valid=False))
            ]
        }
    )
    qdash = server.session()
    chip = qdash.chip(CHIP)

    check = chip.validate_calibration(
        QubitTargets(["0", "1"]),
        coherence_steps(),
        name="coherence-t1-t2echo",
        default_run_parameters=RUN_PARAMETERS,
        tags=["sdk"],
        backend_name="qubex",
    )

    assert check.valid is False
    assert server.paths() == [("POST", "/calibration-pipelines/validate")]
    assert json.loads(server.requests[0].content) == {
        "chip_id": CHIP,
        "spec": expected_spec(),
        "backend_name": "qubex",
    }
    assert server.requests[0].headers["X-Project-Id"] == "project-a"


def test_options_left_out_are_left_to_the_server() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=validate_body())]}
    )
    server.session().chip(CHIP).validate_calibration(MuxTargets([0]), coherence_steps())

    spec = json.loads(server.requests[0].content)["spec"]
    assert set(spec) == {"spec_version", "targets", "steps"}
    assert spec["targets"] == {"mux_ids": [0]}


def test_calibrate_dispatches_once_and_reports_the_whole_run_status() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute_body())],
            ("GET", "/executions/exec-1"): [
                # The first step's execution completes; the run goes on and then fails.
                httpx.Response(200, json=detail("completed", "running")),
                httpx.Response(200, json=detail("completed", "failed")),
            ],
        }
    )
    qdash = server.session()
    chip = qdash.chip(CHIP)

    run = calibrate(chip)
    assert server.paths() == [("POST", "/calibration-pipelines/execute")]
    assert json.loads(server.requests[0].content) == {"chip_id": CHIP, "spec": expected_spec()}
    assert run.execution_id == "exec-1"
    assert run.response.flow_run_id == "run-1"
    assert repr(run) == "CalibrationRun(execution_id='exec-1')"

    result = run.wait(timeout_seconds=60, poll_interval_seconds=2)

    assert isinstance(result, RunResult)
    assert result.status == "failed"
    assert result.detail.status == "completed"
    assert result.execution_id == "exec-1"
    assert server.sleeps == [2]
    assert ("POST", "/calibration-pipelines/validate") not in server.paths()


def test_get_reads_the_current_state_without_waiting() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute_body())],
            ("GET", "/executions/exec-1"): [
                httpx.Response(200, json=detail("completed", "running"))
            ],
        }
    )
    run = calibrate(server.session().chip(CHIP))

    assert run.get().status == "running"
    assert server.sleeps == []


def test_status_falls_back_to_the_execution_without_pipeline_progress() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute_body())],
            ("GET", "/executions/exec-1"): [
                httpx.Response(404, json={"detail": "not found"}),
                httpx.Response(200, json=detail("cancelled", None)),
            ],
        }
    )
    result = calibrate(server.session().chip(CHIP)).wait(poll_interval_seconds=1)

    assert result.status == "cancelled"
    assert result.detail.pipeline is None


def test_wait_times_out_without_cancelling() -> None:
    server = Server(
        {
            ("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute_body())],
            ("GET", "/executions/exec-1"): [httpx.Response(200, json=detail("running", "running"))],
        }
    )
    run = calibrate(server.session().chip(CHIP))

    with pytest.raises(TimeoutError):
        run.wait(timeout_seconds=0)
    assert {path for _, path in server.paths()} == {
        "/calibration-pipelines/execute",
        "/executions/exec-1",
    }


def test_calibrate_rejection_raises_with_the_problems() -> None:
    rejected = {"detail": {"message": "calibration pipeline spec is not valid", "problems": []}}
    server = Server(
        {("POST", "/calibration-pipelines/execute"): [httpx.Response(422, json=rejected)]}
    )
    with pytest.raises(QDashValidationError) as raised:
        calibrate(server.session().chip(CHIP))

    assert raised.value.payload == rejected
    assert len(server.requests) == 1


def test_calibrate_needs_a_project_but_validate_does_not() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=validate_body())]}
    )
    chip = server.session(project_id=None).chip(CHIP)

    with pytest.raises(QDashConfigError):
        calibrate(chip)
    assert server.requests == []
    chip.validate_calibration(QubitTargets(["0"]), coherence_steps())
    assert "X-Project-Id" not in server.requests[0].headers


def test_chips_share_the_session_client_and_project() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=validate_body())]}
    )
    owner = server.session(project_id="project-a")
    qdash = owner.with_project("project-b")

    for chip_id in ("64Qv3", "144Qv1"):
        qdash.chip(chip_id).validate_calibration(QubitTargets(["0"]), coherence_steps())
    qdash.close()
    owner.api.calibration_pipeline.validate_calibration_pipeline(chip_id=CHIP, spec=expected_spec())

    assert [request.headers["X-Project-Id"] for request in server.requests] == [
        "project-b",
        "project-b",
        "project-a",
    ]
    assert [json.loads(r.content)["chip_id"] for r in server.requests[:2]] == ["64Qv3", "144Qv1"]


def test_a_closed_owned_session_does_not_reopen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_BASE_URL", "http://qdash.local")
    monkeypatch.setenv("QDASH_API_TOKEN", "api-token")
    monkeypatch.setenv("QDASH_PROJECT_ID", "project-a")

    qdash = QDash.from_env()
    chip = qdash.chip(CHIP)
    http_client = qdash._http_client
    assert chip._pipelines is qdash.pipelines
    qdash.close()

    assert http_client.is_closed


def whole_pipeline() -> Pipeline:
    """A pipeline with every option set, including fields the targets form cannot set."""
    return calibration.Pipeline(
        name="coherence-t1-t2echo",
        targets=QubitTargets(["0", "1"]),
        steps=[
            CustomOneQubit(
                step_name="coherence",
                execution_mode="parallel_by_mux",
                tasks=[
                    TaskCall(
                        name="CheckT1",
                        call_id="t1",
                        run={"time_range": TIME_RANGE},
                        update_calibration_parameters=False,
                        on_failure="continue",
                    )
                ],
            )
        ],
        default_run_parameters=RUN_PARAMETERS,
        tags=["sdk", "notebook"],
    )


def test_calibration_exports_pipeline() -> None:
    from qdash.sdk.calibration import Pipeline as CalibrationPipeline

    assert CalibrationPipeline is Pipeline
    assert "Pipeline" in calibration.__all__


def test_validate_calibration_sends_a_whole_pipeline_unchanged() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=validate_body())]}
    )
    spec = whole_pipeline()

    server.session().chip(CHIP).validate_calibration(spec, backend_name="qubex")

    assert server.paths() == [("POST", "/calibration-pipelines/validate")]
    assert json.loads(server.requests[0].content) == {
        "chip_id": CHIP,
        "spec": spec.to_spec(),
        "backend_name": "qubex",
    }
    sent = json.loads(server.requests[0].content)["spec"]
    assert sent["tags"] == ["sdk", "notebook"]
    assert sent["default_run_parameters"] == RUN_PARAMETERS
    assert sent["steps"][0]["execution_mode"] == "parallel_by_mux"
    assert sent["steps"][0]["tasks"][0]["on_failure"] == "continue"


def test_calibrate_dispatches_a_whole_pipeline_once() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/execute"): [httpx.Response(200, json=execute_body())]}
    )
    spec = whole_pipeline()

    run = server.session().chip(CHIP).calibrate(spec)

    assert run.execution_id == "exec-1"
    assert server.paths() == [("POST", "/calibration-pipelines/execute")]
    assert json.loads(server.requests[0].content) == {"chip_id": CHIP, "spec": spec.to_spec()}
    assert server.requests[0].headers["X-Project-Id"] == "project-a"


def test_targets_and_steps_still_work_by_keyword() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/validate"): [httpx.Response(200, json=validate_body())]}
    )
    server.session().chip(CHIP).validate_calibration(
        targets=QubitTargets(["0", "1"]),
        steps=coherence_steps(),
        name="coherence-t1-t2echo",
        default_run_parameters=RUN_PARAMETERS,
        tags=["sdk"],
    )

    assert json.loads(server.requests[0].content)["spec"] == expected_spec()


@pytest.mark.parametrize(
    "extra",
    [
        {"steps": []},
        {"name": "other"},
        {"default_run_parameters": {}},
        {"tags": []},
    ],
)
def test_a_pipeline_with_fields_beside_it_is_rejected_locally(extra: dict[str, Any]) -> None:
    server = Server()
    chip = server.session().chip(CHIP)

    with pytest.raises(TypeError, match="already defines"):
        chip.validate_calibration(whole_pipeline(), **extra)
    with pytest.raises(TypeError, match="already defines"):
        chip.calibrate(whole_pipeline(), **extra)
    assert server.requests == []


def test_targets_without_steps_are_rejected_locally() -> None:
    server = Server()
    chip = server.session().chip(CHIP)

    with pytest.raises(TypeError, match="steps is required"):
        chip.validate_calibration(QubitTargets(["0"]))
    with pytest.raises(TypeError, match="steps is required"):
        chip.calibrate(QubitTargets(["0"]))
    assert server.requests == []


@pytest.mark.parametrize(
    ("status", "pipeline_status", "succeeded", "done"),
    [
        # The whole pipeline's status wins over the first step's completed execution.
        ("completed", "running", False, False),
        ("completed", "failed", False, True),
        ("running", "completed", True, True),
        ("completed", "COMPLETED", True, True),
        ("completed", "cancelled", False, True),
        ("completed", "Canceled", False, True),
        ("completed", "crashed", False, True),
        ("completed", "scheduled", False, False),
        ("completed", "mystery", False, False),
        # Without pipeline progress, the execution's own status applies.
        ("completed", None, True, True),
        ("Running", None, False, False),
        ("FAILED", None, False, True),
    ],
)
def test_run_result_flags_follow_the_whole_run_status(
    status: str, pipeline_status: str | None, succeeded: bool, done: bool
) -> None:
    payload = detail(status, pipeline_status)
    result = RunResult("exec-1", ExecutionResponseDetail.model_validate(payload))

    assert (result.succeeded, result.done) == (succeeded, done)
    assert result.status == (pipeline_status if pipeline_status is not None else status)
    assert result.detail.status == status
