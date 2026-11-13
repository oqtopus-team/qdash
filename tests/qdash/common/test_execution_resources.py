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


@pytest.mark.parametrize("shared_resource", ["read_out", "ctrl"])
def test_colon_modules_preserve_parallelism_and_shared_conflicts(
    wiring_file: Path, shared_resource: str
) -> None:
    from qdash.workflow.engine.scheduler.cr_utils import (
        build_mux_conflict_map,
        build_qubit_to_mux_map,
        group_cr_pairs_by_conflict,
    )

    entries = [
        {"mux": 0, "ctrl": ["control-box-a:0"], "read_out": "readout-box-a:0"},
        {"mux": 1, "ctrl": ["control-box-b:0"], "read_out": "readout-box-b:0"},
        {
            "mux": 2,
            "ctrl": ["control-box-a:1" if shared_resource == "ctrl" else "control-box-c:0"],
            "read_out": "readout-box-a:1" if shared_resource == "read_out" else "readout-box-c:0",
        },
    ]
    wiring_file.write_text(yaml.safe_dump({"chip-1": entries}))
    conflicts = build_mux_conflict_map(entries)
    assert conflicts == {0: {2}, 2: {0}}

    groups = group_cr_pairs_by_conflict(
        ["0-1", "4-5", "8-9"], build_qubit_to_mux_map(entries), conflicts, max_parallel_ops=10
    )
    assert len(groups) == 2
    assert sorted(len(group) for group in groups) == [1, 2]
    assert not any("0-1" in group and "8-9" in group for group in groups)

    scopes = [resolve_execution_resource_scope("chip-1", {"mux_ids": [i]}) for i in range(3)]
    assert all(not scope.exclusive for scope in scopes)
    assert not scopes_conflict(scopes[0], scopes[1])
    assert scopes_conflict(scopes[0], scopes[2])
    assert not scopes_conflict(scopes[1], scopes[2])


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


# --------------------------------------------------------------------------
# MUX membership comes from the chip topology, not qid // 4.


def _explicit_mapping():
    from qdash.common.mux_mapping import MuxMapping

    # MUX 9 owns noncontiguous qubits; qid 0 is NOT on MUX 0 here.
    return MuxMapping.from_groups({9: ["0", "17", "5", "2"], 3: ["4", "1"]})


def _write_two_mux_wiring(wiring_file: Path) -> None:
    wiring_file.write_text(
        yaml.safe_dump(
            {
                "chip-1": [
                    {"mux": 9, "ctrl": ["C9-0", "C9-1", "C9-2", "C9-3"], "read_out": "R9-0"},
                    {"mux": 3, "ctrl": ["C3-0", "C3-1"], "read_out": "R3-0"},
                    {"mux": 0, "ctrl": ["C0-0"], "read_out": "R0-0"},
                ]
            }
        )
    )


def test_explicit_mapping_locks_the_owning_mux(wiring_file: Path) -> None:
    _write_two_mux_wiring(wiring_file)
    mapping = _explicit_mapping()

    scope = resolve_execution_resource_scope("chip-1", {"qid": "17"}, mux_mapping=mapping)
    coupling = resolve_execution_resource_scope("chip-1", {"qid": "0-1"}, mux_mapping=mapping)

    assert {r for r in scope.resources if r.startswith("mux:")} == {"mux:9"}
    assert "channel:R9-0" in scope.resources
    assert {r for r in coupling.resources if r.startswith("mux:")} == {"mux:3", "mux:9"}
    assert not scope.exclusive


def test_explicit_mapping_is_conservative_for_unknown_targets(wiring_file: Path) -> None:
    _write_two_mux_wiring(wiring_file)
    mapping = _explicit_mapping()

    # qid 8 is in no MUX; MUX 0 is wired but not in the topology.
    assert resolve_execution_resource_scope("chip-1", {"qid": "8"}, mux_mapping=mapping).exclusive
    assert resolve_execution_resource_scope(
        "chip-1", {"mux_ids": [0]}, mux_mapping=mapping
    ).exclusive


def test_slot_without_control_port_claims_the_chip(wiring_file: Path) -> None:
    from qdash.common.mux_mapping import MuxMapping

    _write_two_mux_wiring(wiring_file)
    mapping = MuxMapping.from_groups({3: ["4", "1", "6"]})

    assert resolve_execution_resource_scope("chip-1", {"qid": "4"}, mux_mapping=mapping).exclusive


def test_project_scoped_lookup_failure_claims_the_chip(
    wiring_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qdash.common.mux_mapping import MuxMappingError

    _write_two_mux_wiring(wiring_file)

    def unresolved(_project_id: str, _chip_id: str):
        raise MuxMappingError("Topology 'gone' not found")

    monkeypatch.setattr(execution_resources, "resolve_chip_mux_mapping", unresolved)

    scope = resolve_execution_resource_scope("chip-1", {"qid": "0"}, project_id="project-1")

    assert scope.exclusive


def test_project_scoped_lookup_uses_the_chip_topology(
    wiring_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_two_mux_wiring(wiring_file)
    calls: list[tuple[str, str]] = []

    def resolved(project_id: str, chip_id: str):
        calls.append((project_id, chip_id))
        return _explicit_mapping()

    monkeypatch.setattr(execution_resources, "resolve_chip_mux_mapping", resolved)

    scope = resolve_execution_resource_scope("chip-1", {"qid": "2"}, project_id="project-1")

    assert calls == [("project-1", "chip-1")]
    assert {r for r in scope.resources if r.startswith("mux:")} == {"mux:9"}


def test_standalone_targets_reserve_the_whole_chip(wiring_file: Path) -> None:
    """Wiring maps only MUXes, so a standalone qubit's hardware sharing is unknown."""
    from qdash.common.mux_mapping import MuxMapping

    _write_two_mux_wiring(wiring_file)
    mapping = MuxMapping.from_groups(
        {9: ["0", "17", "5", "2"], 3: ["4", "1"]}, known_qids=["0", "1", "2", "4", "5", "8", "17"]
    )

    standalone = resolve_execution_resource_scope("chip-1", {"qid": "8"}, mux_mapping=mapping)
    mixed = resolve_execution_resource_scope("chip-1", {"qids": ["17", "8"]}, mux_mapping=mapping)
    coupling = resolve_execution_resource_scope("chip-1", {"qid": "8-17"}, mux_mapping=mapping)
    muxed = resolve_execution_resource_scope("chip-1", {"qids": ["17", "4"]}, mux_mapping=mapping)

    assert standalone.exclusive and mixed.exclusive and coupling.exclusive
    # A standalone run conflicts with any MUX work on the chip, and vice versa.
    assert scopes_conflict(standalone, muxed)
    assert not muxed.exclusive
