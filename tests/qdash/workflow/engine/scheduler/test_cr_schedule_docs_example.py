"""Keep the CR schedule docs example in step with the scheduler.

``docs/demos/two_qubit_cr_schedule.py`` holds the fixture that the docs GIF and
``docs/diagrams/cr-schedule-conflict-graph.svg`` draw. These tests recompute its groups,
conflict edges and graph colors with the scheduler code.
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from qdash.common.mux_mapping import MuxMapping
from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler
from qdash.workflow.engine.scheduler.cr_utils import (
    build_mux_conflict_map,
    build_qubit_to_mux_map,
    group_cr_pairs_by_conflict,
    split_fast_slow_pairs,
)
from qdash.workflow.engine.scheduler.plugins import (
    IntraThenInterMuxScheduler,
    MuxConflictScheduler,
)
from qdash.workflow.engine.scheduler.plugins.base import ScheduleContext

if TYPE_CHECKING:
    from types import ModuleType

_DEMO = Path(__file__).resolve().parents[5] / "docs" / "demos" / "two_qubit_cr_schedule.py"


@pytest.fixture(scope="module")
def demo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("two_qubit_cr_schedule_demo", _DEMO)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def _ids(pairs: Any) -> list[str]:
    return [f"{control}-{target}" for control, target in pairs]


def _wiring(demo: ModuleType) -> list[dict[str, Any]]:
    return [dict(entry) for entry in demo.WIRING]


def test_docs_groups_match_schedule_pairs(demo: ModuleType, tmp_path: Path) -> None:
    scheduler = CRScheduler(
        username="docs",
        chip_id="docs_chip",
        wiring_config_path=str(tmp_path / "unused.yaml"),
        # The docs fixture is a chip without a topology: the legacy MUX layout.
        mux_mapping=MuxMapping.legacy(),
    )
    scheduler._coupling_ids = _ids(demo.PAIRS)
    scheduler._wiring_config = _wiring(demo)

    result = scheduler.schedule_pairs(list(demo.PAIRS), max_parallel_ops=demo.MAX_PARALLEL_OPS)

    assert result.parallel_groups == [list(group) for group in demo.GROUPS]
    assert result.metadata["fast_pairs"] == 7
    assert result.metadata["slow_pairs"] == 1
    # G1 fills the cap: every pair of graph color 1 runs at once.
    assert len(result.parallel_groups[0]) == demo.MAX_PARALLEL_OPS


def test_docs_cap_2_splits_color_1(demo: ModuleType, tmp_path: Path) -> None:
    """The docs text says a cap of 2 splits G1 in two; the other groups stay the same."""
    scheduler = CRScheduler(
        username="docs",
        chip_id="docs_chip",
        wiring_config_path=str(tmp_path / "unused.yaml"),
        # The docs fixture is a chip without a topology: the legacy MUX layout.
        mux_mapping=MuxMapping.legacy(),
    )
    scheduler._coupling_ids = _ids(demo.PAIRS)
    scheduler._wiring_config = _wiring(demo)

    result = scheduler.schedule_pairs(list(demo.PAIRS), max_parallel_ops=2)

    assert result.parallel_groups == [list(group) for group in demo.GROUPS_AT_CAP_2]
    assert [*demo.GROUPS_AT_CAP_2[0], *demo.GROUPS_AT_CAP_2[1]] == list(demo.GROUPS[0])
    assert demo.GROUPS_AT_CAP_2[2:] == demo.GROUPS[1:]


def test_docs_groups_match_plugin_pipeline(demo: ModuleType) -> None:
    wiring = _wiring(demo)
    context = ScheduleContext(
        qid_to_mux=build_qubit_to_mux_map(wiring),
        mux_conflict_map=build_mux_conflict_map(wiring),
    )
    strategy = IntraThenInterMuxScheduler(
        MuxConflictScheduler(max_parallel_ops=demo.MAX_PARALLEL_OPS)
    )

    groups = strategy.schedule(_ids(demo.PAIRS), context)

    assert groups == [_ids(group) for group in demo.GROUPS]


def test_docs_graph_colors(demo: ModuleType) -> None:
    wiring = _wiring(demo)
    qid_to_mux = build_qubit_to_mux_map(wiring)
    conflicts = build_mux_conflict_map(wiring)
    intra, inter = split_fast_slow_pairs(_ids(demo.PAIRS), qid_to_mux)

    colors = {
        f"intra {index + 1}": sorted(group)
        for index, group in enumerate(group_cr_pairs_by_conflict(intra, qid_to_mux, conflicts))
    } | {
        f"inter {index + 1}": sorted(group)
        for index, group in enumerate(group_cr_pairs_by_conflict(inter, qid_to_mux, conflicts))
    }

    expected: dict[str, list[str]] = {}
    for pair, color in demo.COLOR_CLASS.items():
        expected.setdefault(color, []).append(f"{pair[0]}-{pair[1]}")
    assert colors == {color: sorted(pairs) for color, pairs in expected.items()}


def test_docs_conflict_edges(demo: ModuleType) -> None:
    """Two pairs conflict exactly when the scheduler refuses to group them together."""
    wiring = _wiring(demo)
    qid_to_mux = build_qubit_to_mux_map(wiring)
    intra, _ = split_fast_slow_pairs(_ids(demo.PAIRS), qid_to_mux)

    def edges(conflicts: dict[int, set[int]]) -> set[frozenset[str]]:
        return {
            frozenset((a, b))
            for a, b in itertools.combinations(intra, 2)
            if len(group_cr_pairs_by_conflict([a, b], qid_to_mux, conflicts)) == 2
        }

    shared_qubit = {frozenset(("0-1", "3-1")), frozenset(("3-1", "3-2"))}
    same_mux = {frozenset(("0-1", "3-2"))}
    shared_module = {frozenset(("4-5", "8-9"))}
    assert edges(build_mux_conflict_map(wiring)) == shared_qubit | same_mux | shared_module

    # The 4-5 / 8-9 edge comes only from control module C1 shared by MUX1 and MUX2.
    unshared = _wiring(demo)
    unshared[2]["ctrl"] = ["C2:0", "C2:1"]
    assert edges(build_mux_conflict_map(unshared)) == shared_qubit | same_mux


def test_docs_group_colors(demo: ModuleType) -> None:
    """Each execution group has its own color, and the SVG uses the GIF's light colors."""
    assert len(demo.GROUP_COLOR) == len(demo.GROUPS)
    assert len(set(demo.GROUP_COLOR)) == len(demo.GROUP_COLOR)

    svg = (_DEMO.parents[1] / "diagrams" / "cr-schedule-conflict-graph.svg").read_text()
    for index, (red, green, blue) in enumerate(demo.GROUP_COLOR, start=1):
        rule = f".qd-crs-g{index} {{ fill: rgba({red}, {green}, {blue}, 0.14);"
        assert rule in svg, rule
