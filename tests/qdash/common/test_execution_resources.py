"""Execution admission must respect scheduler hardware conflicts."""

from pathlib import Path

import pytest
import yaml

from qdash.common import execution_resources
from qdash.common.execution_resources import (
    ExecutionResourceScope,
    resolve_execution_resource_scope,
    scopes_conflict,
)


@pytest.fixture
def wiring_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "chip-1" / "config" / "wiring.yaml"
    path.parent.mkdir(parents=True)
    monkeypatch.setattr(execution_resources, "resolve_config_base_path", lambda: tmp_path)
    return path


def test_resolves_qubit_and_coupling_targets_to_muxes(wiring_file: Path) -> None:
    wiring_file.write_text(
        yaml.safe_dump(
            {
                "chip-1": [
                    {"mux": mux, "ctrl": [f"C{mux}-0"], "read_out": f"R{mux}-0"} for mux in range(4)
                ]
            }
        )
    )
    qubit = resolve_execution_resource_scope("chip-1", {"qid": "Q07"})
    coupling = resolve_execution_resource_scope("chip-1", {"qid": "3-12"})

    assert {r for r in qubit.resources if r.startswith("mux:")} == {"mux:1"}
    assert {r for r in coupling.resources if r.startswith("mux:")} == {"mux:0", "mux:3"}
    assert qubit.exclusive is False


def test_resolves_shared_wiring_channels(monkeypatch, tmp_path: Path) -> None:
    wiring = tmp_path / "chip-1" / "config"
    wiring.mkdir(parents=True)
    (wiring / "wiring.yaml").write_text(
        "chip-1:\n"
        "  - mux: 0\n    ctrl: [BOX-0]\n    read_out: SHARED-1\n"
        "  - mux: 1\n    ctrl: [BOX-1]\n    read_out: SHARED-1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(execution_resources, "resolve_config_base_path", lambda: tmp_path)

    first = resolve_execution_resource_scope("chip-1", {"mux_ids": [0]})
    second = resolve_execution_resource_scope("chip-1", {"mux_ids": [1]})

    assert "channel:SHARED-1" in first.resources
    assert scopes_conflict(first, second)


def test_different_resources_and_chips_do_not_conflict() -> None:
    first = ExecutionResourceScope("chip-1", ("mux:0",))
    other_mux = ExecutionResourceScope("chip-1", ("mux:2",))
    other_chip = ExecutionResourceScope("chip-2", ("mux:0",), exclusive=True)

    assert not scopes_conflict(first, other_mux)
    assert not scopes_conflict(first, other_chip)


def test_unknown_targets_claim_the_whole_chip() -> None:
    scope = resolve_execution_resource_scope("chip-1", {})

    assert scope.exclusive is True
    assert scopes_conflict(scope, ExecutionResourceScope("chip-1", ("mux:9",)))


@pytest.mark.parametrize("grouped", [False, True])
def test_module_conflicts_match_cr_scheduler(wiring_file: Path, grouped: bool) -> None:
    from qdash.workflow.engine.scheduler.cr_utils import build_mux_conflict_map

    entries = [
        {"mux": 0, "ctrl": ["R21B-5"], "read_out": "Q73A-1"},
        {"mux": 4, "ctrl": ["R21B-7"], "read_out": "Q2A-8"},
        {"mux": 1, "ctrl": ["Q73A-2"], "read_out": "Q73A-8"},
        {"mux": 2, "ctrl": ["S159A-2"], "read_out": "S159A-1"},
    ]
    raw = {"A": entries[:2], "B": entries[2:]} if grouped else {"chip-1": entries}
    wiring_file.write_text(yaml.safe_dump(raw))
    conflicts = build_mux_conflict_map(entries)
    scopes = {}
    for entry in entries:
        mux_id = entry["mux"]
        assert isinstance(mux_id, int)
        scopes[mux_id] = resolve_execution_resource_scope("chip-1", {"mux_ids": [mux_id]})
    assert all(not scope.exclusive for scope in scopes.values())
    for left, left_scope in scopes.items():
        for right, right_scope in scopes.items():
            assert scopes_conflict(left_scope, right_scope) == (
                left == right or right in conflicts.get(left, set())
            )


def test_shared_box_b_module_is_locked_across_one_qubit_groups(wiring_file: Path) -> None:
    from qdash.workflow.engine.scheduler.one_qubit_scheduler import OneQubitScheduler

    entries = [
        {"mux": 0, "ctrl": ["R21B-5"], "read_out": "Q73A-1"},
        {"mux": 4, "ctrl": ["R21B-7"], "read_out": "Q2A-8"},
    ]
    wiring_file.write_text(yaml.safe_dump({"chip-1": entries}))
    scheduler = OneQubitScheduler("chip-1", wiring_config_path=wiring_file)
    schedule = scheduler.generate(qids=["0", "16"])
    assert [stage.qids for stage in schedule.stages] == [["0"], ["16"]]
    assert scopes_conflict(
        resolve_execution_resource_scope("chip-1", {"qid": "0"}),
        resolve_execution_resource_scope("chip-1", {"qid": "16"}),
    )


@pytest.mark.parametrize(
    "contents",
    [
        None,
        "invalid: [",
        "[]",
        "chip-1: null",
        "chip-1: [null]",
        "chip-1: [{mux: 0}]",
        "chip-1: [{mux: 0, ctrl: [null], read_out: R-0}]",
        "chip-1: [{mux: 0, ctrl: [C-0], read_out: R-0}]",
    ],
)
def test_unresolved_wiring_claims_whole_chip(wiring_file: Path, contents: str | None) -> None:
    if contents is not None:
        wiring_file.write_text(contents)
    scope = resolve_execution_resource_scope("chip-1", {"mux_ids": [0, 4]})
    assert scope.exclusive is True
    assert scopes_conflict(scope, ExecutionResourceScope("chip-1", ("mux:9",)))
