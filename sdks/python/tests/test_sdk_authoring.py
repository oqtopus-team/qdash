"""Strict authoring models: local validation and the JSON the helpers send."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from test_sdk_session import CHIP, Server, execute_body

from qdash.sdk._generated import _authoring
from qdash.sdk.dashboard import Dashboard, Script
from qdash.sdk.pipeline import (
    CalibrationPipelineSpec,
    CustomOneQubit,
    OneQubitCheckStep,
    Pipeline,
    QubitTargets,
    TaskCall,
)


def test_unknown_fields_are_rejected_at_every_level() -> None:
    with pytest.raises(ValidationError, match="extra"):
        TaskCall(name="CheckT1", updte_calibration_parameters=False)  # type: ignore[call-arg]
    with pytest.raises(ValidationError, match="extra"):
        Pipeline(targets=QubitTargets(["0"]), steps=[{"type": "OneQubitCheck", "taks": []}])
    with pytest.raises(ValidationError, match="extra"):
        Pipeline(targets={"qids": ["0"], "qubits": ["1"]}, steps=[{"type": "OneQubitCheck"}])
    with pytest.raises(ValidationError, match="extra"):
        CalibrationPipelineSpec.model_validate(
            {"spec_version": 2, "targets": {"qids": ["0"]}, "steps": [], "nmae": "x"}
        )


def test_patterns_constants_and_defaults_are_kept() -> None:
    with pytest.raises(ValidationError, match="pattern"):
        Pipeline(name="has space", targets=QubitTargets(["0"]), steps=[{"type": "BringUp"}])
    with pytest.raises(ValidationError, match="spec_version"):
        CalibrationPipelineSpec.model_validate(
            {"spec_version": 1, "targets": {"qids": ["0"]}, "steps": [{"type": "BringUp"}]}
        )
    pipeline = Pipeline(targets=QubitTargets(["0"]), steps=[{"type": "BringUp"}])

    assert pipeline.spec_version == 2
    assert pipeline.name == "pipeline"
    assert "name" not in pipeline.to_spec()
    assert CustomOneQubit(tasks=[TaskCall(name="CheckT1")]).step_name == "custom_one_qubit"


def test_explicit_null_is_sent_and_unset_is_omitted() -> None:
    call = TaskCall(name="CheckT1", update_calibration_parameters=None, on_failure="stop")
    spec = Pipeline(targets=QubitTargets(["0"]), steps=[CustomOneQubit(tasks=[call])]).to_spec()

    assert spec["steps"][0]["tasks"] == [
        {"name": "CheckT1", "update_calibration_parameters": None, "on_failure": "stop"}
    ]


def test_dict_steps_become_the_discriminated_union() -> None:
    pipeline = Pipeline(
        targets={"mux_ids": [0]},
        steps=[
            {"type": "OneQubitCheck", "execution_mode": "parallel_by_mux"},
            {"type": "CustomOneQubit", "tasks": [{"name": "CheckT1"}]},
            {"type": "FilterByStatus"},
        ],
    )

    assert [type(step).__name__ for step in pipeline.steps] == [
        "OneQubitCheckStep",
        "CustomOneQubitStep",
        "FilterByStatusStep",
    ]
    assert isinstance(pipeline.steps[0], OneQubitCheckStep)
    assert pipeline.to_spec()["steps"] == [
        {"type": "OneQubitCheck", "execution_mode": "parallel_by_mux"},
        {"type": "CustomOneQubit", "tasks": [{"name": "CheckT1"}]},
        {"type": "FilterByStatus"},
    ]


def test_authoring_models_are_independent_of_the_generated_responses() -> None:
    from qdash.sdk._generated.core.pydantic_utilities import UniversalBaseModel

    assert not issubclass(_authoring.CalibrationPipelineSpec, UniversalBaseModel)
    assert _authoring.TaskCall.model_config.get("extra") == "forbid"


def test_execute_sends_the_nested_spec_unchanged() -> None:
    server = Server(
        {("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute_body())]}
    )
    pipeline = Pipeline(
        name="nested",
        targets=QubitTargets(["0", "1"]),
        steps=[
            CustomOneQubit(
                step_name="t1",
                tasks=[TaskCall(name="CheckT1", call_id="t1_a", run={"shots": 128})],
            ),
            {"type": "FilterByStatus"},
        ],
        tags=["a"],
    )
    server.session().pipelines.execute(pipeline, chip_id=CHIP, backend_name=None)

    body = json.loads(server.requests[0].content)
    assert body == {"chip_id": CHIP, "spec": pipeline.to_spec()}
    assert body["spec"]["steps"][0] == {
        "type": "CustomOneQubit",
        "step_name": "t1",
        "tasks": [{"name": "CheckT1", "call_id": "t1_a", "run": {"shots": 128}}],
    }


def test_metric_script_and_dashboard_requests_follow_their_schemas() -> None:
    # Enums and closed objects (additionalProperties: false) are enforced as the schema says.
    with pytest.raises(ValidationError):
        Script(name="s", source="x", visibility="public").create_request()  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        _authoring.DashboardUpdateRequest.model_validate({"name": "d", "visibility": "public"})
    with pytest.raises(ValidationError, match="extra"):
        _authoring.MetricScriptPanelConfig.model_validate(
            {"script_id": "s", "script_revision": 1, "metric_id": "m", "unknown": 1}
        )
    request = Dashboard("d", chip_id="64Qv3").update_request(expected_version=3)

    assert request.model_dump(mode="json", exclude_unset=True) == {
        "name": "d",
        "panels": [],
        "chip_id": "64Qv3",
        "expected_version": 3,
    }


def test_dashboard_create_sends_nested_panels_as_json() -> None:
    created: dict[str, Any] = {
        "dashboard_id": "d-1",
        "project_id": "p",
        "name": "d",
        "description": "",
        "visibility": "private",
        "panels": [],
        "owner_username": "alice",
        "can_edit": True,
        "version": 1,
        "created_at": "2026-11-24T00:00:00Z",
        "updated_at": "2026-11-24T00:00:00Z",
    }
    server = Server({("POST", "/dashboards"): [httpx.Response(200, json=created)]})
    dashboard = Dashboard("d")
    dashboard.add_markdown("# Notes", title="Notes")
    server.session().dashboards.create(dashboard)

    assert json.loads(server.requests[0].content) == {
        "name": "d",
        "panels": [
            {
                "panel_id": "markdown",
                "type": "markdown",
                "title": "Notes",
                "layout": {"x": 0, "y": 0, "w": 12, "h": 2},
                "config": {"content": "# Notes"},
            }
        ],
    }
