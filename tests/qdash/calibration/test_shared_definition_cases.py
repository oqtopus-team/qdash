"""The shared calibration definition cases hold against the server's models.

``sdks/testdata/calibration_definitions.json`` is run by the Python SDK
(``sdks/python/tests/test_sdk_calibration_shared.py``) and the TypeScript SDK; here every
expected JSON is validated by the server's spec models, so a case both SDKs agree on is also
one the server accepts, and every local refusal is one the server would make too.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from qdash.datamodel import calibration_pipeline as server
from qdash.datamodel.task_call import TaskCall as WorkerTaskCall

CASES: dict[str, Any] = json.loads(
    (
        Path(__file__).resolve().parents[3] / "sdks" / "testdata" / "calibration_definitions.json"
    ).read_text(encoding="utf-8")
)
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


def wire(value: Any) -> Any:
    """Fixture values as JSON: sweeps in their wire form, task calls as their fields."""
    if isinstance(value, list):
        return [wire(entry) for entry in value]
    if isinstance(value, dict):
        if set(value) == {"$sweep"}:
            constructor, *arguments = value["$sweep"]
            value_type = {
                "values": "list",
                "linspace": "np.linspace",
                "logspace": "np.logspace",
                "arange": "np.arange",
                "range": "range",
            }[constructor]
            return {"value": list(arguments), "value_type": value_type}
        if set(value) == {"$task"}:
            return wire(value["$task"])
        return {key: wire(entry) for key, entry in value.items()}
    return value


def server_validate(kind: str, data: dict[str, Any], step_type: str | None = None) -> None:
    if kind == "task_call":
        WorkerTaskCall.model_validate(data)
    elif kind == "targets":
        server.PipelineTargets.model_validate(data)
    elif kind == "step":
        assert step_type is not None
        SERVER_STEPS[step_type].model_validate({**data, "type": step_type})
    else:
        server.CalibrationPipelineSpec.model_validate(data)


def ids(case: dict[str, Any]) -> str:
    name: str = case["name"]
    return name


@pytest.mark.parametrize("case", CASES["valid"], ids=ids)
def test_the_server_accepts_every_valid_case(case: dict[str, Any]) -> None:
    server_validate(case["kind"], case["expected"], case.get("type"))


@pytest.mark.parametrize("case", CASES["server_only"], ids=ids)
def test_server_only_rules_are_the_servers(case: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        server_validate(case["kind"], case["expected"], case.get("type"))


@pytest.mark.parametrize(
    "case", [case for case in CASES["invalid"] if case["server_rejects"] is not None], ids=ids
)
def test_local_refusals_are_server_refusals(case: dict[str, Any]) -> None:
    data = wire(case["fields"])
    if case["server_rejects"]:
        with pytest.raises(ValidationError):
            server_validate(case["kind"], data, case.get("type"))
    else:
        server_validate(case["kind"], data, case.get("type"))
