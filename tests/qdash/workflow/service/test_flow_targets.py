"""Per-run target overrides preserve code defaults unless explicitly requested."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from qdash.datamodel.flow_targets import TARGET_CONTEXT_KEY, FlowTargetOverride
from qdash.workflow import TaskCall
from qdash.workflow.service._internal.session import CalibSession
from qdash.workflow.service._internal.settings import SessionSettings
from qdash.workflow.service.flow_targets import (
    override_pipeline,
    override_target,
    read_target_override,
)
from qdash.workflow.service.steps import (
    CustomOneQubit,
    CustomTwoQubit,
    GenerateCRSchedule,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import AllMuxTargets, CouplingTargets, MuxTargets, QubitTargets

SELECTED = FlowTargetOverride(coupling_pairs=[["63", "85"], ["85", "63"], ["64", "42"]])


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"mux_ids": []},
        {"mux_ids": [-1]},
        {"mux_ids": [True]},
        {"qids": ["a"]},
        {"qids": ["1", "1"]},
        {"qids": ["1"], "mux_ids": [0]},
        {"qids": ["1"], "exclude_qids": ["2"]},
        {"coupling_pairs": []},
        {"coupling_pairs": [["63"]]},
        {"coupling_pairs": [["63", "85", "1"]]},
        {"coupling_pairs": [["63", "63"]]},
        {"coupling_pairs": [["63", "x"]]},
        {"coupling_pairs": [["63", 85]]},
        {"coupling_pairs": [["63", "85"], ["63", "85"]]},
        {"coupling_pairs": [["63", "85"]], "qids": ["1"]},
        {"coupling_pairs": [["63", "85"]], "exclude_qids": ["2"]},
    ],
)
def test_invalid_overrides(value):
    with pytest.raises(ValidationError):
        FlowTargetOverride.model_validate(value)


def test_unchanged_targets_preserve_identity():
    target = MuxTargets([1], ["4"])
    assert override_target(target, None) is target


def test_mode_switch_replaces_original_exclusions():
    assert override_target(MuxTargets([1], ["4"]), FlowTargetOverride(qids=["9"])) == QubitTargets(
        ["9"]
    )


def test_no_flow_context_leaves_defaults():
    assert read_target_override() is None


def test_context_override_replaces_the_pipeline_targets(monkeypatch):
    from qdash.workflow.service._internal import runs

    override = FlowTargetOverride(qids=["9"])
    context = SimpleNamespace(
        flow_run=SimpleNamespace(context={TARGET_CONTEXT_KEY: override.model_dump()})
    )
    run_pipeline = MagicMock(return_value={})
    monkeypatch.setattr(CalibSession, "run_pipeline", run_pipeline)
    settings = SessionSettings(
        username="user", chip_id="chip", project_id="project", backend_name="fake"
    )
    with patch.dict(
        sys.modules,
        {"prefect.context": SimpleNamespace(FlowRunContext=SimpleNamespace(get=lambda: context))},
    ):
        runs.run_calibration(settings, MuxTargets([0]), [])

    run_pipeline.assert_called_once_with(QubitTargets(["9"]), [])


def test_workers_never_read_the_override():
    """Workers keep their scheduled subset: borrowing never consults the run context."""
    import inspect

    from qdash.workflow.service._internal import session

    assert "read_target_override" not in inspect.getsource(session)


def test_directed_pairs_are_preserved_in_order():
    assert SELECTED.pairs() == [("63", "85"), ("85", "63"), ("64", "42")]
    assert SELECTED.mode == "coupling_pairs"


@pytest.mark.parametrize("target", [MuxTargets([0]), QubitTargets(["0"]), AllMuxTargets()])
def test_coupling_override_requires_coupling_targets(target):
    with pytest.raises(ValueError, match="CouplingTargets"):
        override_target(target, SELECTED)


def test_qubit_override_rejects_coupling_targets():
    with pytest.raises(ValueError, match="MuxTargets or QubitTargets"):
        override_target(CouplingTargets([("0", "1")]), FlowTargetOverride(qids=["1"]))


def test_coupling_override_replaces_only_the_targets():
    """The selected pairs replace the targets; the steps are passed on unchanged."""
    generate = GenerateCRSchedule(max_parallel_ops=4)
    calibration = TwoQubitCalibration()

    target, steps = override_pipeline(
        CouplingTargets([("0", "1"), ("4", "5"), ("2", "3")]),
        [generate, calibration],
        SELECTED,
    )

    assert target == CouplingTargets([("63", "85"), ("85", "63"), ("64", "42")])
    assert steps[0] is generate
    assert steps[1] is calibration


def test_missing_override_preserves_targets_and_steps():
    target = CouplingTargets([("0", "1")])
    steps = [TwoQubitCalibration()]

    new_target, new_steps = override_pipeline(target, steps, None)

    assert new_target is target
    assert all(new is old for new, old in zip(new_steps, steps, strict=True))


class _CustomPairStep(CustomTwoQubit):
    """A subclass may run pairs other than the targets."""


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        ([GenerateCRSchedule()], "CustomTwoQubit or TwoQubitCalibration"),
        ([CustomOneQubit()], "CustomTwoQubit or TwoQubitCalibration"),
        ([_CustomPairStep(tasks=[TaskCall(name="CheckCrossResonance")])], "_CustomPairStep"),
        ([TwoQubitCalibration(), MagicMock()], "built-in steps only"),
    ],
)
def test_coupling_override_rejects_pipelines_that_could_change_pairs(steps, message):
    with pytest.raises(ValueError, match=message):
        override_pipeline(CouplingTargets([("0", "1")]), steps, SELECTED)


def test_coupling_override_rejects_manual_steps():
    manual = TwoQubitCalibration(execution_mode="manual", rounds=[[("0", "1")]])

    with pytest.raises(ValueError, match="two_qubit_calibration"):
        override_pipeline(CouplingTargets([("0", "1")]), [manual], SELECTED)


def test_invalid_overrides_stop_the_run_before_a_session_exists(monkeypatch):
    from qdash.workflow.service._internal import runs

    context = SimpleNamespace(
        flow_run=SimpleNamespace(context={TARGET_CONTEXT_KEY: SELECTED.model_dump()})
    )
    created = MagicMock()
    monkeypatch.setattr(runs, "CalibSession", created)
    settings = SessionSettings(
        username="user", chip_id="chip", project_id="project", backend_name="fake"
    )
    with (
        patch.dict(
            sys.modules,
            {
                "prefect.context": SimpleNamespace(
                    FlowRunContext=SimpleNamespace(get=lambda: context)
                )
            },
        ),
        pytest.raises(ValueError, match="CouplingTargets"),
    ):
        runs.run_calibration(settings, QubitTargets(["0", "1"]), [TwoQubitCalibration()])

    created.assert_not_called()


def test_selected_pairs_reach_the_pipeline_as_targets(monkeypatch):
    from qdash.workflow.service._internal import runs

    context = SimpleNamespace(
        flow_run=SimpleNamespace(context={TARGET_CONTEXT_KEY: SELECTED.model_dump()})
    )
    run_pipeline = MagicMock(return_value={})
    monkeypatch.setattr(CalibSession, "run_pipeline", run_pipeline)
    settings = SessionSettings(
        username="user", chip_id="chip", project_id="project", backend_name="fake"
    )
    steps = [TwoQubitCalibration()]
    with patch.dict(
        sys.modules,
        {"prefect.context": SimpleNamespace(FlowRunContext=SimpleNamespace(get=lambda: context))},
    ):
        runs.run_calibration(settings, CouplingTargets([("0", "1")]), steps)

    run_pipeline.assert_called_once_with(
        CouplingTargets([("63", "85"), ("85", "63"), ("64", "42")]), steps
    )
