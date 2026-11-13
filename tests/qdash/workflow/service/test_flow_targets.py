"""Per-run target overrides preserve code defaults unless explicitly requested."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from qdash.common.mux_mapping import MuxMapping
from qdash.datamodel.flow_targets import TARGET_CONTEXT_KEY, FlowTargetOverride
from qdash.workflow.service._internal.session import CalibSession
from qdash.workflow.service._internal.settings import SessionSettings
from qdash.workflow.service.flow_targets import (
    override_pipeline,
    override_target,
    read_target_override,
)
from qdash.workflow.service.steps import (
    GenerateCRSchedule,
    SetCRSchedule,
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


def test_coupling_override_replaces_pairs_and_source_schedule():
    """The selected pairs and their generated groups replace the source schedule."""
    source = SetCRSchedule(schedule=[[("0", "1"), ("4", "5")], [("2", "3")]])
    calibration = TwoQubitCalibration()
    scheduled: list[list[tuple[str, str]]] = []

    def schedule(pairs):
        scheduled.append(pairs)
        return [[("63", "85"), ("64", "42")], [("85", "63")]]

    target, steps = override_pipeline(
        CouplingTargets([("0", "1"), ("4", "5"), ("2", "3")]),
        [source, calibration],
        SELECTED,
        schedule,
    )

    assert scheduled == [[("63", "85"), ("85", "63"), ("64", "42")]]
    assert target == CouplingTargets([("63", "85"), ("85", "63"), ("64", "42")])
    assert steps[0] == SetCRSchedule(schedule=[[("63", "85"), ("64", "42")], [("85", "63")]])
    assert steps[1] is calibration
    assert source.schedule == [[("0", "1"), ("4", "5")], [("2", "3")]]


def test_missing_override_preserves_targets_and_steps():
    target = CouplingTargets([("0", "1")])
    steps = [SetCRSchedule(schedule=[[("0", "1")]]), TwoQubitCalibration()]

    def unexpected(pairs):
        raise AssertionError("no override must not schedule")

    new_target, new_steps = override_pipeline(target, steps, None, unexpected)

    assert new_target is target
    assert new_steps == steps
    assert all(new is old for new, old in zip(new_steps, steps, strict=True))


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        ([TwoQubitCalibration()], "SetCRSchedule"),
        (
            [SetCRSchedule(schedule=[[("0", "1")]]), GenerateCRSchedule(), TwoQubitCalibration()],
            "GenerateCRSchedule",
        ),
    ],
)
def test_coupling_override_rejects_pipelines_that_would_change_pairs(steps, message):
    def unexpected(pairs):
        raise AssertionError("invalid pipelines must fail before scheduling")

    with pytest.raises(ValueError, match=message):
        override_pipeline(CouplingTargets([("0", "1")]), steps, SELECTED, unexpected)


def test_scheduler_errors_stop_the_run_before_the_pipeline(monkeypatch):
    from qdash.workflow.service._internal import runs

    context = SimpleNamespace(
        flow_run=SimpleNamespace(context={TARGET_CONTEXT_KEY: SELECTED.model_dump()})
    )
    run_pipeline = MagicMock(return_value={})
    monkeypatch.setattr(CalibSession, "run_pipeline", run_pipeline)

    def reject(settings, pairs, *, mux_mapping=None):
        raise ValueError("Coupling pairs not found on chip chip: ['63-85']")

    monkeypatch.setattr(runs, "schedule_selected_pairs", reject)
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
        pytest.raises(ValueError, match="not found"),
    ):
        runs.run_calibration(
            settings, CouplingTargets([("0", "1")]), [SetCRSchedule(schedule=[[("0", "1")]])]
        )

    run_pipeline.assert_not_called()


def test_selected_pairs_use_the_chip_scheduler(monkeypatch):
    from qdash.workflow.service._internal import runs

    calls = {}

    class FakeScheduler:
        def __init__(self, username, chip_id, *, wiring_config_path, project_id, mux_mapping):
            calls["init"] = (username, chip_id, project_id, mux_mapping)

        def schedule_pairs(self, pairs):
            calls["pairs"] = pairs
            return SimpleNamespace(parallel_groups=[[("63", "85")]])

    monkeypatch.setattr("qdash.workflow.engine.CRScheduler", FakeScheduler)
    settings = SessionSettings(
        username="user", chip_id="chip", project_id="project", backend_name="fake"
    )
    pinned = MuxMapping.legacy()

    assert runs.schedule_selected_pairs(settings, [("63", "85")], mux_mapping=pinned) == [
        [("63", "85")]
    ]
    assert calls == {"init": ("user", "chip", "project", pinned), "pairs": [("63", "85")]}


def test_selected_pairs_are_grouped_with_the_running_session_mapping(monkeypatch):
    """The override schedule uses the MUX mapping the running session pinned, once."""
    from qdash.workflow.service._internal import runs

    context = SimpleNamespace(
        flow_run=SimpleNamespace(context={TARGET_CONTEXT_KEY: SELECTED.model_dump()})
    )
    pinned = MuxMapping.from_groups({21: ["85", "84", "86", "87"]}, topology_id="synthetic-pin")
    resolutions = []

    def resolve(project_id, chip_id):
        resolutions.append((project_id, chip_id))
        return pinned if len(resolutions) == 1 else MuxMapping.legacy()

    monkeypatch.setattr(
        "qdash.workflow.service._internal.session.resolve_chip_mux_mapping", resolve
    )
    scheduled = {}

    def schedule(settings, pairs, *, mux_mapping=None):
        scheduled["mapping"] = mux_mapping
        return [[tuple(pair)] for pair in pairs]

    sessions = []

    def run_pipeline(self, targets, steps):
        sessions.append(self)
        return {}

    monkeypatch.setattr(runs, "schedule_selected_pairs", schedule)
    monkeypatch.setattr(CalibSession, "run_pipeline", run_pipeline)
    settings = SessionSettings(
        username="user", chip_id="chip", project_id="project", backend_name="fake"
    )
    with patch.dict(
        sys.modules,
        {"prefect.context": SimpleNamespace(FlowRunContext=SimpleNamespace(get=lambda: context))},
    ):
        runs.run_calibration(
            settings, CouplingTargets([("0", "1")]), [SetCRSchedule(schedule=[[("0", "1")]])]
        )

    [session] = sessions
    assert scheduled["mapping"] is pinned
    assert session.mux_mapping is pinned
    assert resolutions == [("project", "chip")]
