"""Launch metadata read from a saved flow's source, and the new authoring syntax in previews."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from qdash.api.services.flow_service.execution_plan import resolve_execution_plan
from qdash.api.services.flow_service.flow_metadata import (
    declared_session_name,
    is_flow_decorator,
)
from qdash.api.services.flow_service.plan_preview import build_execution_plan
from qdash.api.services.flow_service.target_defaults import (
    resolve_target_defaults,
    supported_target_modes,
)
from qdash.api.services.flow_service.validation import validate_flow_code
from qdash.api.services.manual_round_checks import ChipRoundModel

HEADER = """
from qdash.calibration import (
    CouplingTargets, CustomOneQubit, MuxTargets, QubitTargets, TaskCall, TwoQubitCalibration,
)
from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context
"""


def _flow(decorator: str, body: str, name: str = "my_flow") -> str:
    indented = "\n".join(f"    {line}" if line else "" for line in body.strip().splitlines())
    return (
        HEADER
        + f"\n\n{decorator}\ndef {name}(username, chip_id, mux_ids=None, project_id=None,"
        + " flow_name=None):\n"
        + indented
        + "\n"
    )


RUN = """
context = resolve_calib_context(username, chip_id, project_id=project_id)
session = CalibrationSession.from_context(context)
return session.run(
    targets=MuxTargets([0, 1]),
    steps=[CustomOneQubit(step_name="rabi", tasks=[TaskCall(name="CheckRabi")])],
    name=flow_name,
)
"""


@pytest.mark.parametrize(
    ("decorator", "expected"),
    [
        ('@calibration_flow(session_name="Coherence Check")', "Coherence Check"),
        ('@calibration_flow(session_name="  padded  ", retries=1)', "padded"),
        ('@qdash.workflow.calibration_flow(session_name="Dotted")', "Dotted"),
        ("@calibration_flow", None),
        ("@calibration_flow()", None),
        ("@calibration_flow(session_name=NAME)", None),
        ('@calibration_flow(session_name="a" + "b")', None),
        ('@calibration_flow(session_name="")', None),
        (f'@calibration_flow(session_name="{"x" * 501}")', None),
        ('@flow(name="x")', None),
    ],
)
def test_only_a_literal_session_name_is_read(decorator: str, expected: str | None) -> None:
    assert declared_session_name(_flow(decorator, RUN), "my_flow") == expected


def test_the_name_belongs_to_the_entrypoint_and_nothing_is_evaluated() -> None:
    code = _flow('@calibration_flow(session_name="Other")', RUN, name="helper") + _flow(
        "@calibration_flow", RUN
    )
    assert declared_session_name(code, "my_flow") is None
    assert declared_session_name(code, "helper") == "Other"
    # A source that would fail if imported is only parsed.
    exploding = "raise SystemExit(1)\n" + _flow('@calibration_flow(session_name="Safe")', RUN)
    assert declared_session_name(exploding, "my_flow") == "Safe"
    assert declared_session_name("def broken(:\n", "my_flow") is None


def test_calibration_flow_counts_as_a_flow_decorator() -> None:
    validate_flow_code(_flow('@calibration_flow(session_name="X")', RUN), "my_flow")
    validate_flow_code(_flow("@calibration_flow", RUN), "my_flow")
    with pytest.raises(HTTPException, match="calibration_flow"):
        validate_flow_code(HEADER + "\ndef my_flow():\n    pass\n", "my_flow")
    import ast

    decorators = ast.parse("@prefect.flow\n@calibration_flow()\ndef f(): pass").body[0]
    assert isinstance(decorators, ast.FunctionDef)
    assert all(is_flow_decorator(node) for node in decorators.decorator_list)


def test_the_preview_reads_calibration_session_runs() -> None:
    plan = resolve_execution_plan(_flow('@calibration_flow(session_name="X")', RUN), "my_flow", {})
    [run] = plan.runs
    assert [(step.type, step.name, step.execution_mode) for step in run.steps] == [
        ("CustomOneQubit", "rabi", "parallel_by_round")
    ]
    assert run.target_type == "MuxTargets"
    inline = RUN.replace(
        "session = CalibrationSession.from_context(context)\nreturn session.run(",
        "return CalibrationSession.from_context(context).run(",
    )
    [inline_run] = resolve_execution_plan(_flow("@calibration_flow", inline), "my_flow", {}).runs
    assert [step.name for step in inline_run.steps] == ["rabi"]


def test_two_runs_of_one_session_are_both_previewed() -> None:
    body = RUN.replace("return session.run(", "session.run(") + RUN.split("\n", 3)[3]
    plan = resolve_execution_plan(_flow("@calibration_flow", body), "my_flow", {})
    assert len(plan.runs) == 2


def test_target_defaults_and_pair_overrides_follow_the_new_syntax() -> None:
    code = _flow("@calibration_flow", RUN)
    defaults = resolve_target_defaults(code, "my_flow", {})
    assert defaults is not None and defaults.mux_ids == [0, 1]
    pairs = _flow(
        "@calibration_flow",
        """
context = resolve_calib_context(username, chip_id, project_id=project_id)
session = CalibrationSession.from_context(context)
targets = CouplingTargets([("0", "1")])
return session.run(targets=targets, steps=[TwoQubitCalibration()], name=flow_name)
""",
    )
    assert supported_target_modes(pairs, "my_flow") == ["coupling_pairs"]
    manual = pairs.replace(
        "TwoQubitCalibration()",
        'TwoQubitCalibration(execution_mode="manual", rounds=[[("0", "1")]])',
    )
    assert supported_target_modes(manual, "my_flow") == []
    response = build_execution_plan(
        flow_name="my_flow",
        chip_id="chip-1",
        updated_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        code=manual,
        function_name="my_flow",
        parameters={},
        chip_model=lambda: ChipRoundModel(
            wiring=[
                {"mux": 0, "ctrl": ["Q0A-2"], "read_out": "Q0A-1", "read_in": "Q0A-0"},
            ],
            coupling_ids=frozenset({"0-1"}),
        ),
    )
    assert response.status == "resolved", response.reason
    assert response.has_manual_rounds and not response.target_override_allowed


@pytest.mark.parametrize(
    "value",
    ['""', '"   "', repr("x" * 501), "42", "True", "NAME", '"a" + "b"', 'f"{NAME}"'],
)
def test_invalid_session_names_are_rejected_before_saving(value: str) -> None:
    code = _flow(f"@calibration_flow(session_name={value})", RUN)
    with pytest.raises(HTTPException) as caught:
        validate_flow_code(code, "my_flow")
    assert caught.value.status_code == 400
    assert "session_name" in caught.value.detail
    assert "500" in caught.value.detail


@pytest.mark.parametrize("value", ["None", repr("x" * 500), repr("  padded  ")])
def test_valid_session_names_can_be_saved(value: str) -> None:
    validate_flow_code(_flow(f"@calibration_flow(session_name={value})", RUN), "my_flow")


def test_invalid_helper_decorator_also_blocks_save_without_evaluating_source() -> None:
    code = (
        'raise AssertionError("must not execute")\n'
        + _flow('@qdash.workflow.calibration_flow(session_name=" ")', RUN, name="helper")
        + _flow("@flow", RUN)
    )
    with pytest.raises(HTTPException, match="helper: session_name"):
        validate_flow_code(code, "my_flow")
