"""Calibration definition cases shared with the TypeScript SDK.

``sdks/testdata/calibration_definitions.json`` holds the cases; the TypeScript SDK runs the same
file against ``@oqtopus-team/qdash-sdk/calibration`` and ``tests/qdash/calibration`` checks the
expected JSON against the server's models.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qdash.calibration import (
    STEP_TYPES,
    CouplingTargets,
    MuxTargets,
    QubitTargets,
    TaskCall,
    pipeline_spec,
    sweep,
)

CASES: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[2] / "testdata" / "calibration_definitions.json").read_text(
        encoding="utf-8"
    )
)
TARGETS: dict[str, Any] = {
    "QubitTargets": QubitTargets,
    "MuxTargets": MuxTargets,
    "CouplingTargets": CouplingTargets,
}


def materialize(value: Any) -> Any:
    """Fixture values with ``$sweep`` and ``$task`` markers built by the Python definitions."""
    if isinstance(value, list):
        return [materialize(entry) for entry in value]
    if isinstance(value, dict):
        if set(value) == {"$sweep"}:
            constructor, *arguments = value["$sweep"]
            return getattr(sweep, constructor)(*arguments)
        if set(value) == {"$task"}:
            return TaskCall(**materialize(value["$task"]))
        return {key: materialize(entry) for key, entry in value.items()}
    return value


def build(case: dict[str, Any]) -> Any:
    """The JSON the Python definitions write for one case."""
    kind = case["kind"]
    if kind == "task_call":
        return TaskCall(**materialize(case["fields"])).to_spec()
    if kind == "targets":
        return TARGETS[case["type"]](**materialize(case["fields"])).to_spec()
    if kind == "step":
        return STEP_TYPES[case["type"]](**materialize(case["fields"])).to_spec()
    assert kind == "spec", kind
    targets = TARGETS[case["targets"]["type"]](**materialize(case["targets"]["fields"]))
    steps = [STEP_TYPES[step["type"]](**materialize(step["fields"])) for step in case["steps"]]
    return pipeline_spec(targets, steps, **materialize(case["options"]))


def ids(case: dict[str, Any]) -> str:
    name: str = case["name"]
    return name


@pytest.mark.parametrize("case", CASES["valid"] + CASES["server_only"], ids=ids)
def test_valid_cases_serialize_as_expected(case: dict[str, Any]) -> None:
    built = build(case)
    # Through JSON, as the SDK sends it.
    assert json.loads(json.dumps(built)) == case["expected"]


@pytest.mark.parametrize("case", CASES["invalid"], ids=ids)
def test_invalid_cases_are_refused_locally(case: dict[str, Any]) -> None:
    with pytest.raises((ValueError, TypeError)):
        build(case)


def test_the_fixture_lists_every_definition_field() -> None:
    assert CASES["task_call_fields"] == list(TaskCall.model_fields)
    assert {name: list(cls.model_fields) for name, cls in STEP_TYPES.items()} == CASES[
        "step_fields"
    ]


def test_every_step_type_has_a_valid_and_an_invalid_case() -> None:
    def covered(section: str) -> set[str]:
        types: set[str] = set()
        for case in CASES[section]:
            if case["kind"] == "step":
                types.add(case["type"])
            elif case["kind"] == "spec":
                types.update(step["type"] for step in case["steps"])
        return types

    assert covered("valid") == set(STEP_TYPES)
    assert {case["type"] for case in CASES["invalid"] if case["kind"] == "step"} == set(STEP_TYPES)
