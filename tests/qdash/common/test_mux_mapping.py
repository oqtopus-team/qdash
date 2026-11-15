"""Explicit topology MUX membership is the single source for MUX lookups."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from qdash.common.config.loader import ConfigLoader
from qdash.common.config.topology import TopologyDefinition, list_topologies, load_topology
from qdash.common.mux_mapping import (
    MuxMapping,
    MuxMappingError,
    resolve_chip_mux_mapping,
    resolve_topology_mux_mapping,
)


def _topology(**overrides: Any) -> dict[str, Any]:
    """2x4 layout: MUX 7 = left 2x2 block (permuted slots), MUX 2 = right block."""
    data: dict[str, Any] = {
        "id": "sparse",
        "name": "Sparse",
        "grid_size": 4,
        "num_qubits": 8,
        "muxes": {7: [11, 4, 9, 0], 2: [1, 5, 3, 8]},
        "qubits": {
            11: {"row": 0, "col": 0},
            4: {"row": 0, "col": 1},
            9: {"row": 1, "col": 0},
            0: {"row": 1, "col": 1},
            1: {"row": 0, "col": 2},
            5: {"row": 0, "col": 3},
            3: {"row": 1, "col": 2},
            8: {"row": 1, "col": 3},
        },
        "couplings": [],
    }
    data.update(overrides)
    return data


def _legacy(mux: Any, **overrides: Any) -> dict[str, Any]:
    """The same layout declared with the old ``mux:`` block instead of ``muxes``."""
    data = _topology(**overrides)
    del data["muxes"]
    data["mux"] = mux
    return data


@pytest.fixture
def bundled_topologies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", ConfigLoader.LOCAL_CONFIG_DIR)
    load_topology.cache_clear()
    yield
    load_topology.cache_clear()


# --------------------------------------------------------------------- schema


def test_muxes_keep_sparse_ids_and_member_slot_order() -> None:
    topology = TopologyDefinition(**_topology())
    mapping = MuxMapping.from_topology(topology)

    assert topology.muxes_source == "muxes"
    assert mapping.is_explicit
    assert mapping.mux_ids == [2, 7]
    # The array index is the local slot: members are never sorted.
    assert topology.muxes[7] == [11, 4, 9, 0]
    assert mapping.qids_of(7) == ("11", "4", "9", "0")
    assert mapping.mux_of("0") == 7
    assert mapping.slot_of("0") == 3
    assert mapping.slot_of("Q11") == 0
    assert mapping.slots_of(2) == {0: "1", 1: "5", 2: "3", 3: "8"}
    assert mapping.qids_for_muxes([2, 7], exclude_qids=["5"]) == [
        "1",
        "3",
        "8",
        "11",
        "4",
        "9",
        "0",
    ]
    assert mapping.mux_ids_for_qids(["0", "8"]) == [2, 7]
    assert mapping.standalone_qids == []


def test_mux_declaration_order_has_no_meaning() -> None:
    forward = MuxMapping.from_topology(
        TopologyDefinition(**_topology(muxes={7: [11, 4, 9, 0], 2: [1, 5, 3, 8]}))
    )
    backward = MuxMapping.from_topology(
        TopologyDefinition(**_topology(muxes={2: [1, 5, 3, 8], 7: [11, 4, 9, 0]}))
    )

    assert forward == backward
    assert forward.mux_ids == backward.mux_ids == [2, 7]
    assert forward.slots_of(7) == backward.slots_of(7) == {0: "11", 1: "4", 2: "9", 3: "0"}


def test_muxes_have_no_arithmetic_fallback() -> None:
    mapping = MuxMapping.from_topology(TopologyDefinition(**_topology()))

    # qid 2 would be MUX 0 by qid // 4, but this topology does not define it.
    assert mapping.find_mux("2") is None
    assert not mapping.is_known("2")
    with pytest.raises(MuxMappingError, match="not defined"):
        mapping.mux_of("2")
    with pytest.raises(MuxMappingError):
        mapping.qids_of(0)
    with pytest.raises(MuxMappingError):
        mapping.qids_for_muxes([1])


def test_partial_variable_size_muxes_leave_known_qubits_standalone() -> None:
    topology = TopologyDefinition(**_topology(muxes={7: [4], 2: [8, 1, 5]}))
    mapping = MuxMapping.from_topology(topology)

    assert topology.standalone_qubits() == [0, 3, 9, 11]
    assert mapping.standalone_qids == ["0", "3", "9", "11"]
    assert mapping.all_qids == ["0", "1", "3", "4", "5", "8", "9", "11"]
    assert mapping.qids_of(2) == ("8", "1", "5")
    assert mapping.slot_of("5") == 2
    # Standalone is a known qubit, unlike a qubit the topology does not define.
    assert mapping.is_known("9") and mapping.is_standalone("9")
    assert not mapping.is_known("2") and not mapping.is_standalone("2")
    assert mapping.find_mux("9") is None
    with pytest.raises(MuxMappingError, match="standalone"):
        mapping.mux_of("9")
    with pytest.raises(MuxMappingError, match="standalone"):
        mapping.slot_of("9")
    with pytest.raises(MuxMappingError, match="standalone"):
        mapping.mux_ids_for_qids(["4", "9"])
    assert mapping.partition_qids(["9", "4", "1", "0"]) == ([2, 7], ["0", "9"])
    with pytest.raises(MuxMappingError, match="not defined"):
        mapping.partition_qids(["4", "2"])


def test_empty_muxes_declare_every_qubit_standalone() -> None:
    topology = TopologyDefinition(**_topology(muxes={}))
    mapping = MuxMapping.from_topology(topology)

    assert topology.muxes == {}
    assert mapping.mux_ids == []
    assert mapping.standalone_qids == ["0", "1", "3", "4", "5", "8", "9", "11"]
    assert mapping.groups_for_qubit_count(8) == {}
    assert mapping.partition_qids(["11", "0"]) == ([], ["0", "11"])


@pytest.mark.parametrize(
    ("muxes", "message"),
    [
        ({0: [11, 4, 9, 0], 1: [0, 1, 5, 3, 8]}, "MUX 1 lists qubit 0 in MUX 0 too"),
        ({0: [11, 11, 4]}, "MUX 0 lists qubit 11 twice"),
        ({-1: [11, 4]}, "MUX IDs must be non-negative"),
        ({0: [11, -4]}, "negative qubit ID"),
        ({0: []}, "MUX 0 has no qubits"),
        ({0: [11, 99]}, r"not in qubits: \[99\]"),
        ({0: ["11"]}, "valid integer"),
        ({0: [True]}, "valid integer"),
        ({0: {"qids": [11]}}, "valid list"),
        ({"a": [11]}, "valid integer"),
        (None, "must be a mapping"),
        ([[11, 4]], "must be a mapping"),
    ],
)
def test_malformed_muxes_are_rejected(muxes: Any, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        TopologyDefinition(**_topology(muxes=muxes))


def test_negative_qubit_ids_are_rejected() -> None:
    qubits = {**_topology()["qubits"], -1: {"row": 0, "col": 0}}
    with pytest.raises(ValidationError, match="non-negative"):
        TopologyDefinition(**_topology(qubits=qubits))


def test_missing_muxes_is_an_error_not_an_empty_declaration() -> None:
    data = _topology()
    del data["muxes"]

    with pytest.raises(ValidationError, match="does not declare 'muxes'"):
        TopologyDefinition(**data)


def test_template_with_both_mux_and_muxes_is_ambiguous() -> None:
    data = _topology()
    data["mux"] = {"enabled": True, "size": 2}

    with pytest.raises(ValidationError, match="both 'mux'"):
        TopologyDefinition(**data)


def test_muxes_source_is_derived_not_authored() -> None:
    with pytest.raises(ValidationError, match="derived"):
        TopologyDefinition(**_topology(muxes_source="legacy_groups"))


def test_qubit_positions_must_fit_the_grid() -> None:
    # The synthetic 2x4 layout uses columns up to 3, which grid_size 2 cannot hold.
    with pytest.raises(ValidationError, match="outside grid_size 2"):
        TopologyDefinition(**_topology(grid_size=2))


def test_known_qids_must_cover_mux_members() -> None:
    with pytest.raises(MuxMappingError, match="not known"):
        MuxMapping.from_groups({0: ["1", "2"]}, known_qids=["1"])
    mapping = MuxMapping.from_groups({0: ["1"]}, known_qids=["1", "2"])
    assert mapping.standalone_qids == ["2"]


# --------------------------------------------------------------- legacy policy


def test_legacy_mux_groups_are_normalized_into_muxes() -> None:
    topology = TopologyDefinition(
        **_legacy({"enabled": True, "size": 2, "groups": {7: {"qids": [11, 4, 9, 0]}}})
    )
    mapping = MuxMapping.from_topology(topology)

    assert topology.muxes_source == "legacy_groups"
    assert topology.muxes == {7: [11, 4, 9, 0]}
    assert mapping.is_explicit
    assert mapping.slot_of("0") == 3
    # Qubits outside the legacy groups are standalone, like in the new format.
    assert mapping.standalone_qids == ["1", "3", "5", "8"]


def test_legacy_template_without_groups_uses_qid_div_4_for_its_qubits() -> None:
    topology = TopologyDefinition(**_legacy({"enabled": True, "size": 2}))
    mapping = MuxMapping.from_topology(topology)

    assert topology.muxes_source == "legacy_qid_div_4"
    assert mapping.source == "legacy_topology"
    assert topology.muxes == {0: [0, 1, 3], 1: [4, 5], 2: [8, 9, 11]}
    # Legacy slots stay qid % 4 even when a MUX has holes.
    assert mapping.slot_of("3") == 3
    assert mapping.find_mux("2") is None
    assert mapping.standalone_qids == []


def test_legacy_disabled_mux_means_no_mux_not_qid_div_4() -> None:
    topology = TopologyDefinition(**_legacy({"enabled": False}))
    mapping = MuxMapping.from_topology(topology)

    assert topology.muxes_source == "legacy_disabled"
    assert topology.muxes == {}
    assert mapping.find_mux("9") is None
    assert mapping.is_standalone("9")
    assert len(mapping.standalone_qids) == 8


@pytest.mark.parametrize(
    ("mux", "message"),
    [
        ({"enabled": False, "groups": {0: {"qids": [11]}}}, "requires mux.enabled"),
        ({"enabled": True, "groups": {0: {"qids": [11], "slot": 1}}}, "Extra inputs"),
        ({"enabled": True, "groups": {0: {"qids": [11, 11]}}}, "twice"),
        ({"enabled": True, "groups": {0: {"qids": []}}}, "has no qubits"),
        ({"enabled": "yes"}, "valid boolean"),
        ({"enabled": True, "shape": 2}, "Extra inputs"),
    ],
)
def test_malformed_legacy_mux_is_rejected(mux: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        TopologyDefinition(**_legacy(mux))


def test_chip_without_topology_keeps_unbounded_legacy_mapping() -> None:
    mapping = resolve_topology_mux_mapping(None)

    assert mapping.unbounded
    assert mapping.qids_of(5) == ("20", "21", "22", "23")
    assert mapping.mux_of("Q07") == 1
    assert mapping.slot_of("23") == 3
    assert mapping.groups_for_qubit_count(6) == {0: ("0", "1", "2", "3"), 1: ("4", "5")}


def test_configured_topology_that_cannot_load_raises(bundled_topologies) -> None:
    with pytest.raises(MuxMappingError, match="not found"):
        resolve_topology_mux_mapping("does-not-exist")


def test_invalid_configured_topology_raises(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    topologies = tmp_path / "domain" / "topologies"
    topologies.mkdir(parents=True)
    (topologies / "broken.yaml").write_text(
        "id: broken\nname: Broken\ngrid_size: 1\nnum_qubits: 2\n"
        "muxes: {0: [0, 7]}\n"
        "qubits: {0: {row: 0, col: 0}, 1: {row: 0, col: 1}}\ncouplings: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    load_topology.cache_clear()
    try:
        with pytest.raises(MuxMappingError, match="invalid"):
            resolve_topology_mux_mapping("broken")
    finally:
        load_topology.cache_clear()


class _Query:
    def __init__(self, result: Any) -> None:
        self._result = result

    def run(self) -> Any:
        return self._result


def _patch_chip(monkeypatch: pytest.MonkeyPatch, chip: Any) -> list[dict[str, Any]]:
    from qdash.dbmodel.chip import ChipDocument

    queries: list[dict[str, Any]] = []

    def find_one(query: dict[str, Any]) -> _Query:
        queries.append(query)
        return _Query(chip)

    monkeypatch.setattr(ChipDocument, "find_one", staticmethod(find_one))
    return queries


def test_chip_resolution_is_project_scoped(monkeypatch, bundled_topologies) -> None:
    class Chip:
        topology_id = "square-lattice-mux-16"

    queries = _patch_chip(monkeypatch, Chip())

    mapping = resolve_chip_mux_mapping("project-1", "chip-16")

    assert queries == [{"project_id": "project-1", "chip_id": "chip-16"}]
    assert mapping.is_explicit
    assert mapping.mux_ids == list(range(4))


def test_chip_with_missing_configured_topology_raises(monkeypatch, bundled_topologies) -> None:
    class Chip:
        topology_id = "deleted-template"

    _patch_chip(monkeypatch, Chip())

    with pytest.raises(MuxMappingError):
        resolve_chip_mux_mapping("project-1", "chip-1")


def test_unknown_chip_or_missing_project_keeps_legacy(monkeypatch) -> None:
    _patch_chip(monkeypatch, None)

    assert resolve_chip_mux_mapping("project-1", "chip-1").unbounded
    assert resolve_chip_mux_mapping(None, "chip-1").unbounded


def test_chip_lookup_failure_raises(monkeypatch) -> None:
    from qdash.dbmodel.chip import ChipDocument

    def find_one(_query: dict[str, Any]) -> Any:
        raise RuntimeError("database down")

    monkeypatch.setattr(ChipDocument, "find_one", staticmethod(find_one))

    with pytest.raises(MuxMappingError, match="database down"):
        resolve_chip_mux_mapping("project-1", "chip-1")


# ---------------------------------------------------------------------- wiring


def test_wiring_needs_a_control_port_for_every_member_slot() -> None:
    mapping = MuxMapping.from_topology(TopologyDefinition(**_topology()))

    assert mapping.wiring_errors([{"mux": 7, "ctrl": ["a", "b", "c", "d"]}]) == []
    errors = mapping.wiring_errors([{"mux": 7, "ctrl": ["a", "b"]}, {"mux": 99, "ctrl": []}])
    assert errors == [
        "MUX 7 qubit 9 uses slot 2 but wiring lists 2 control port(s)",
        "MUX 7 qubit 0 uses slot 3 but wiring lists 2 control port(s)",
    ]
    with pytest.raises(MuxMappingError):
        mapping.check_wiring([{"mux": 7, "ctrl": ["a"]}])
    # The legacy mapping never second-guesses existing wiring.
    assert MuxMapping.legacy().wiring_errors([{"mux": 0, "ctrl": ["a"]}]) == []


# ------------------------------------------------------------ bundled templates


def test_bundled_templates_use_canonical_muxes(bundled_topologies) -> None:
    for summary in list_topologies():
        topology = load_topology(summary["id"])
        assert topology.muxes_source == "muxes", summary["id"]
        mapping = MuxMapping.from_topology(topology)
        if not topology.muxes:
            # Layouts without MUX (linear, heavy hex) declare every qubit standalone.
            assert mapping.standalone_qids == sorted(map(str, topology.qubits), key=int)
            continue
        assert mapping.standalone_qids == [], summary["id"]
        for qid in topology.qubits:
            assert mapping.mux_of(qid) == qid // 4, (summary["id"], qid)
            assert mapping.slot_of(qid) == qid % 4, (summary["id"], qid)


def test_bundled_template_list_is_the_public_set(bundled_topologies) -> None:
    assert [summary["id"] for summary in list_topologies()] == [
        "heavy-hex-27",
        "linear-16",
        "square-lattice-mux-1024",
        "square-lattice-mux-144",
        "square-lattice-mux-16",
        "square-lattice-mux-256",
        "square-lattice-mux-64",
    ]


# Synthetic, clipped, nonrectangular 7-qubit layout on a 4x4 grid (not modeled
# on any real chip). Couplings are listed in an arbitrary order and directions
# that do not follow lattice parity.
_SYNTHETIC_CLIPPED_YAML = """\
id: synthetic-clipped
name: Synthetic clipped layout
grid_size: 4
num_qubits: 7
direction_convention: checkerboard_cr
muxes:
  5: [10, 3]
  2: [6, 1, 8]
qubits:
  10: {row: 0, col: 1}
  3: {row: 0, col: 2}
  6: {row: 1, col: 1}
  1: {row: 1, col: 2}
  8: {row: 1, col: 3}
  4: {row: 2, col: 2}
  7: {row: 3, col: 2}
couplings:
  - [3, 10]
  - [6, 10]
  - [1, 3]
  - [8, 1]
  - [6, 1]
  - [4, 1]
  - [7, 4]
"""


def test_synthetic_template_keeps_authored_couplings(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    topologies = tmp_path / "domain" / "topologies"
    topologies.mkdir(parents=True)
    (topologies / "synthetic-clipped.yaml").write_text(_SYNTHETIC_CLIPPED_YAML)
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    load_topology.cache_clear()
    try:
        topology = load_topology("synthetic-clipped")
    finally:
        load_topology.cache_clear()
    mapping = MuxMapping.from_topology(topology)

    assert topology.num_qubits == len(topology.qubits) == 7
    assert topology.muxes_source == "muxes"
    assert mapping.mux_ids == [2, 5]
    # Member order is the local slot order, never sorted.
    assert mapping.qids_of(2) == ("6", "1", "8")
    assert mapping.slot_of("10") == 0
    assert mapping.slot_of("3") == 1
    assert mapping.standalone_qids == ["4", "7"]
    occupied = {(p.row, p.col) for p in topology.qubits.values()}
    for empty in [(0, 0), (0, 3), (2, 0), (3, 3)]:
        assert empty not in occupied
    # Couplings are kept exactly as authored (order and direction): QDash does not
    # rewrite them from lattice parity.
    assert [tuple(edge) for edge in topology.couplings] == [
        (3, 10),
        (6, 10),
        (1, 3),
        (8, 1),
        (6, 1),
        (4, 1),
        (7, 4),
    ]


# ------------------------------------------------- aliases, MUX selection, snapshots


def test_exclusions_match_members_by_qubit_number() -> None:
    mapping = MuxMapping.from_groups({0: ["Q05", "12"]})

    assert mapping.qids_for_muxes([0], exclude_qids=["Q05"]) == ["12"]
    assert mapping.qids_for_muxes([0], exclude_qids=["012", "not-a-qubit"]) == ["5"]


def test_selected_mux_ids_must_be_defined() -> None:
    mapping = MuxMapping.from_groups({3: ["12"], 9: ["36"]})

    assert mapping.check_mux_ids([9, "3"]) == [9, 3]
    with pytest.raises(MuxMappingError, match=r"MUX IDs \[0, True, -1, 'x'\].*defined: 3, 9"):
        mapping.check_mux_ids([0, True, -1, "x", 3])
    # The unbounded legacy mapping knows every non-negative MUX, and nothing else.
    assert MuxMapping.legacy().check_mux_ids([0, 15]) == [0, 15]
    with pytest.raises(MuxMappingError):
        MuxMapping.legacy().check_mux_ids([-1])


@pytest.mark.parametrize(
    "mapping",
    [
        MuxMapping.from_groups(
            {15: ["61", "60"], 3: ["14", "12"]},
            topology_id="synthetic",
            slots={"61": 1, "60": 0, "14": 2, "12": 3},
            known_qids=["12", "14", "20", "60", "61"],
        ),
        MuxMapping.from_groups({}, known_qids=["0", "1"]),
        MuxMapping.legacy(),
    ],
    ids=["explicit-with-standalone", "standalone-only", "legacy"],
)
def test_snapshot_round_trips_through_json_and_pickle(mapping: MuxMapping) -> None:
    import pickle

    from qdash.common.mux_mapping import MuxMappingSnapshot

    snapshot = MuxMappingSnapshot.of(mapping)
    for restored_snapshot in (
        MuxMappingSnapshot.model_validate_json(snapshot.model_dump_json()),
        pickle.loads(pickle.dumps(snapshot)),  # noqa: S301 - round trip of our own object
    ):
        restored = restored_snapshot.to_mapping()
        assert restored == mapping
        assert restored.standalone_qids == mapping.standalone_qids
        for mux_id in mapping.mux_ids:
            assert restored.slots_of(mux_id) == mapping.slots_of(mux_id)
        assert restored.find_mux("61") == mapping.find_mux("61")
