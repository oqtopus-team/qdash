"""Templates accept ``tasks`` as structured TaskCall JSON through the real Prefect path.

``POST /flows/{name}/execute`` (and the pi ``qdash_execute_flow`` tool, schedules, and
Prefect's own run form) send flow parameters as JSON. The pytest process stubs
``prefect``, so this runs ``task_call_flow_contract.py`` with real Prefect in a
separate interpreter and checks what it reports. No server, database, or hardware is used.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = Path(__file__).with_name("task_call_flow_contract.py")
# Every built-in template with a ``tasks: list[TaskCall] | None`` flow parameter.
TEMPLATES = [
    "fake_backend",
    "simple",
    "two_qubit",
    "two_qubit_manual_rounds",
    "two_qubit_pairs",
]


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    completed = subprocess.run(  # noqa: S603 - runs a file from this repository
        [sys.executable, str(CONTRACT)],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    result: dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
    assert sorted(result["templates"]) == TEMPLATES
    return result


@pytest.mark.parametrize("template", TEMPLATES)
def test_structured_calls_reach_the_step_unchanged(contract: dict[str, Any], template: str) -> None:
    result = contract["templates"][template]

    # JSON arrays of objects stay objects on the wire; nothing is coerced to strings.
    assert result["wire_tasks"] == contract["calls"]
    assert result["validated_types"] == ["TaskCall", "TaskCall"]
    expected = [
        {
            "name": "CheckRamsey",
            "call_id": "ramsey_coarse",
            "run": {"detuning": {"value": 0.001}},
            "on_failure": "stop",
        },
        {
            "name": "CheckRamsey",
            "call_id": "ramsey_fine",
            "run": {"detuning": {"value": 0.0002}},
            "input": {"qubit_frequency": 5.0},
            "update_calibration_parameters": False,
            "on_failure": "continue",
        },
    ]
    assert result["validated"] == expected
    # The same task twice in one step, each call with its own id and settings.
    assert result["step_type"] in {"CustomOneQubit", "CustomTwoQubit"}
    assert result["step_calls"] == expected


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_parameter_schema_describes_an_optional_task_call_list(
    contract: dict[str, Any], template: str
) -> None:
    result = contract["templates"][template]

    assert result["tasks_schema"]["anyOf"] == [
        {"items": {"$ref": "#/definitions/TaskCall"}, "type": "array"},
        {"type": "null"},
    ]
    assert result["tasks_schema"]["default"] is None
    assert result["task_call_properties"] == [
        "call_id",
        "input",
        "name",
        "on_failure",
        "run",
        "update_calibration_parameters",
    ]


@pytest.mark.parametrize("template", TEMPLATES)
def test_omitted_tasks_fall_back_to_the_template_calls(
    contract: dict[str, Any], template: str
) -> None:
    result = contract["templates"][template]

    assert result["default_tasks_parameter"] is None
    assert result["default_call_count"] > 0
    assert result["default_types"] == ["TaskCall"]


@pytest.mark.parametrize("template", TEMPLATES)
def test_task_names_unknown_fields_and_unnamed_repeats_are_rejected(
    contract: dict[str, Any], template: str
) -> None:
    result = contract["templates"][template]

    assert result["names_rejected_by_flow"] is True
    assert result["names_rejected_by_schema"] is True
    assert result["unknown_field_rejected_by_flow"] is True
    assert "give every occurrence its own call_id" in result["duplicate_error"]


def test_worker_specs_cross_prefect_and_process_boundaries(contract: dict[str, Any]) -> None:
    """Workers receive the owner's settings through real Prefect validation and pickling."""
    assert contract["worker_spec"] == {
        "validated_equal": True,
        "json_validated_equal": True,
        "cloudpickle_equal": True,
        "hashable": True,
    }
