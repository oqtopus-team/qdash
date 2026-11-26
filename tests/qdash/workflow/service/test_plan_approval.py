"""The worker refuses a plan run that differs from its approved plan, before any reservation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec
from qdash.datamodel.calibration_plan import (
    ApprovedPipelinePlan,
    materialize_default_tasks,
    review_content,
    review_digest,
    review_steps,
)
from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service import pipeline_flow
from qdash.workflow.service.pipeline_flow import build_steps, build_targets
from qdash.workflow.service.plan_approval import (
    ApprovedPlanCheck,
    PlanApprovalMismatch,
    check_dispatched_plan,
    observed_review_steps,
)
from qdash.workflow.service.steps import GenerateCRSchedule, OneQubitFineTune
from qdash.workflow.service.targets import QubitTargets
from tests.qdash.workflow.service.test_calib_session import (  # noqa: F401 - fixtures
    chips_without_topology,
    clear_session_state,
    mock_flow_session_deps,
    pipeline_execution_env,
)
from tests.qdash.workflow.service.test_pipeline_flow import EVERY_STEP
from tests.qdash.workflow.service.test_transform_step_executions import _owner

# Steps that run their catalog defaults until the plan writes them out.
DEFAULT_STEPS: list[dict[str, Any]] = [
    {"type": "ConfigureAll"},
    {"type": "BringUp", "step_id": "bringup_default"},
    {"type": "OneQubitCheck", "step_id": "check_default", "configure": True},
    {"type": "OneQubitFineTune", "step_id": "fine_default"},
    {"type": "GenerateCRSchedule"},
    {"type": "TwoQubitCalibration", "step_id": "two_default"},
    {
        "type": "CustomTwoQubit",
        "step_name": "manual_zx",
        "tasks": [{"name": "CreateZX90"}],
        "execution_mode": "manual",
        "rounds": [[["0", "1"]]],
    },
]


def _spec(steps: list[dict[str, Any]], **fields: Any) -> CalibrationPipelineSpec:
    return materialize_default_tasks(
        CalibrationPipelineSpec.model_validate(
            {"spec_version": 2, "targets": {"qids": ["0", "1"]}, "steps": steps, **fields}
        )
    )


def _approved(spec: CalibrationPipelineSpec, qids: list[str]) -> ApprovedPipelinePlan:
    review = review_content(chip_id="chip-1", backend_name="fake", spec=spec, target_qids=qids)
    return ApprovedPipelinePlan(plan_id="cpp-1", review_digest=review_digest(review), review=review)


def _check(approved: ApprovedPipelinePlan, spec: CalibrationPipelineSpec, **observed: Any) -> None:
    steps = observed.pop("steps", build_steps(spec))
    ApprovedPlanCheck(approved)(
        targets=observed.pop("targets", build_targets(spec)),
        qids=observed.pop("qids", ["0", "1"]),
        steps=steps,
        default_run_parameters=observed.pop("default_run_parameters", {}),
        task_parameters=observed.pop("task_parameters", {}),
    )


MANUAL_STEPS: list[dict[str, Any]] = [
    {
        "type": "CustomOneQubit",
        "step_name": "manual_t1",
        "tasks": [{"name": "CheckT1", "on_failure": "continue"}],
        "execution_mode": "manual",
        "rounds": [["0"], ["1"]],
    },
    {"type": "FilterByStatus", "step": "manual_t1"},
    {"type": "OneQubitCheck", "execution_mode": "sequential"},
]


@pytest.mark.parametrize("steps", [EVERY_STEP, DEFAULT_STEPS, MANUAL_STEPS])
def test_the_worker_rebuilds_the_review_of_every_step_type(steps: list[dict[str, Any]]) -> None:
    spec = _spec(steps)
    assert observed_review_steps(build_steps(spec)) == review_steps(spec)
    _check(_approved(spec, ["0", "1"]), spec)


def test_materialized_defaults_name_every_call() -> None:
    spec = _spec(DEFAULT_STEPS)
    assert all(
        getattr(step, "tasks", None)
        for step in spec.steps
        if step.type not in ("GenerateCRSchedule", "ConfigureAll")
    )
    # The implicit Configure call stays implicit, so the call ids do not change.
    check = review_steps(spec)[2]
    assert check["calls"][0]["call_id"] == "Configure"
    assert [call["name"] for call in check["calls"]].count("Configure") == 1


def test_a_worker_default_that_differs_is_refused() -> None:
    spec = _spec(DEFAULT_STEPS)
    steps = build_steps(spec)
    # A worker whose default fine-tune list differs from the one approved.
    steps[3] = OneQubitFineTune(tasks=[TaskCall(name="CheckRabi")], step_id="fine_default")
    with pytest.raises(PlanApprovalMismatch, match=r"steps \(first at step 4\)"):
        _check(_approved(spec, ["0", "1"]), spec, steps=steps)


def test_a_target_expansion_that_differs_is_refused() -> None:
    spec = _spec(EVERY_STEP)
    approved = _approved(spec, ["0", "1"])
    # The same qubits in another order and form are the same targets.
    _check(approved, spec, qids=["1", "0"])
    with pytest.raises(PlanApprovalMismatch, match="target_qids"):
        _check(approved, spec, qids=["0", "1", "2"])


def test_run_defaults_the_approval_did_not_show_are_refused() -> None:
    spec = _spec(EVERY_STEP, default_run_parameters={"shots": 1024})
    approved = _approved(spec, ["0", "1"])
    _check(approved, spec, default_run_parameters={"shots": {"value": 1024}})
    with pytest.raises(PlanApprovalMismatch, match="default_run_parameters"):
        _check(
            approved,
            spec,
            default_run_parameters={"shots": {"value": 1024}, "interval": {"value": 1}},
        )


def test_the_dispatched_spec_and_digest_must_be_the_approved_ones() -> None:
    spec = _spec(EVERY_STEP)
    approved = _approved(spec, ["0", "1"])
    dumped = spec.model_dump(mode="json", exclude_none=True)
    check_dispatched_plan(approved, chip_id="chip-1", backend_name="fake", spec=dumped)
    with pytest.raises(PlanApprovalMismatch, match="spec"):
        check_dispatched_plan(
            approved, chip_id="chip-1", backend_name="fake", spec={**dumped, "tags": ["x"]}
        )
    with pytest.raises(PlanApprovalMismatch, match="backend_name"):
        check_dispatched_plan(approved, chip_id="chip-1", backend_name="qubex", spec=dumped)
    tampered = approved.model_copy(update={"review": {**approved.review, "target_qids": ["9"]}})
    with pytest.raises(PlanApprovalMismatch, match="review digest"):
        check_dispatched_plan(tampered, chip_id="chip-1", backend_name="fake", spec=dumped)


def _run_flow(monkeypatch: pytest.MonkeyPatch, raw_spec: dict[str, Any], **kwargs: Any) -> Any:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(pipeline_flow, "get_run_logger", MagicMock)
    monkeypatch.setattr(
        pipeline_flow,
        "resolve_calib_context",
        MagicMock(return_value=SimpleNamespace(backend_name="fake", project_id="p")),
    )

    def settings(context: Any, **fields: Any) -> dict[str, Any]:
        captured.update(fields)
        return fields

    run = MagicMock()
    monkeypatch.setattr(pipeline_flow, "workflow_settings", settings)
    monkeypatch.setattr(pipeline_flow, "run_calibration", run)
    body = getattr(pipeline_flow.calibration_pipeline, "fn", pipeline_flow.calibration_pipeline)
    body(username="alice", chip_id="chip-1", spec=raw_spec, **kwargs)
    return captured, run


def test_the_flow_checks_an_approved_plan_and_uses_only_its_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _spec(EVERY_STEP, name="nightly")
    approved = _approved(spec, ["0", "1"])
    raw = spec.model_dump(mode="json", exclude_none=True)
    captured, run = _run_flow(monkeypatch, raw, approved_plan=approved.model_dump())
    assert captured["saved_flow_name"] is None
    assert captured["note"]["pipeline"]["plan"] == {
        "plan_id": "cpp-1",
        "review_digest": approved.review_digest,
    }
    check = run.call_args.kwargs["approved_plan"]
    assert isinstance(check, ApprovedPlanCheck)
    assert check.approved == approved

    # A spec run passes no check and keeps the saved flow's defaults.
    captured, run = _run_flow(monkeypatch, raw)
    assert "saved_flow_name" not in captured
    assert "approved_plan" not in run.call_args.kwargs


def test_the_flow_refuses_a_spec_that_is_not_the_approved_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _spec(EVERY_STEP)
    approved = _approved(spec, ["0", "1"])
    raw = {**spec.model_dump(mode="json", exclude_none=True), "tags": ["swapped"]}
    with pytest.raises(PlanApprovalMismatch):
        _run_flow(monkeypatch, raw, approved_plan=approved.model_dump())


@pytest.fixture
def cr_scheduler(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    scheduler = MagicMock()
    monkeypatch.setattr("qdash.workflow.engine.CRScheduler", lambda *a, **kw: scheduler)
    return scheduler


def _transform_plan(qids: list[str]) -> ApprovedPlanCheck:
    spec = CalibrationPipelineSpec.model_validate(
        {"spec_version": 2, "targets": {"qids": ["0"]}, "steps": [{"type": "GenerateCRSchedule"}]}
    )
    review = review_content(chip_id="chip-1", backend_name="fake", spec=spec, target_qids=qids)
    return ApprovedPlanCheck(
        ApprovedPipelinePlan(plan_id="cpp-1", review_digest=review_digest(review), review=review)
    )


def test_a_mismatch_stops_the_run_before_any_reservation_or_execution(
    pipeline_execution_env: Any,  # noqa: F811
    cr_scheduler: MagicMock,
) -> None:
    env = pipeline_execution_env
    session = _owner(env)
    with pytest.raises(PlanApprovalMismatch, match="target_qids"):
        session.run_pipeline(
            QubitTargets(["0"]), steps=[GenerateCRSchedule()], approved_plan=_transform_plan(["1"])
        )
    assert env.lock.try_lock_calls == []
    assert env.records == []
    cr_scheduler.generate.assert_not_called()


def test_a_matching_plan_runs(
    pipeline_execution_env: Any,  # noqa: F811
    cr_scheduler: MagicMock,
) -> None:
    env = pipeline_execution_env
    session = _owner(env)
    session.run_pipeline(
        QubitTargets(["0"]), steps=[GenerateCRSchedule()], approved_plan=_transform_plan(["0"])
    )
    assert env.lock.try_lock_calls == ["exec-reserved"]
    assert [record.status for record in env.records] == ["completed"]


def test_pipeline_flow_advertises_the_approved_plan_contract() -> None:
    """The ``approved_plan`` parameter's schema names the contract the API requires.

    Prefect builds a deployment's parameter schema from the signature with pydantic, so the
    key reaches the registered deployment (``FlowService.approved_plan_deployment``).
    """
    import typing

    from pydantic import create_model

    from qdash.api.services.flow_service.service import approved_plan_contract
    from qdash.datamodel.calibration_plan import APPROVED_PLAN_CONTRACT

    hints = typing.get_type_hints(pipeline_flow.calibration_pipeline, include_extras=True)
    fields: dict[str, Any] = {"approved_plan": (hints["approved_plan"], None)}
    model = create_model("Parameters", **fields)
    schema = model.model_json_schema()
    assert approved_plan_contract(schema) == APPROVED_PLAN_CONTRACT
    assert schema["properties"]["approved_plan"]["default"] is None
