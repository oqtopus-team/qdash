import itertools
from collections import defaultdict
from pathlib import Path

import yaml


def build_mux_readout_sharing_by_module(yaml_mux_list: list[dict]) -> dict[int, set[int]]:
    """Build mux readout sharing map using read_out module (e.g., U15A)."""
    module_to_muxes = defaultdict(set)

    for mux_entry in yaml_mux_list:
        mux_id = mux_entry["mux"]
        read_out = mux_entry.get("read_out")
        if read_out:
            module = read_out.split("-")[0]  # U15A-13 → U15A
            module_to_muxes[module].add(mux_id)

    mux_sharing = defaultdict(set)
    for muxes in module_to_muxes.values():
        for a, b in itertools.combinations(muxes, 2):
            mux_sharing[a].add(b)
            mux_sharing[b].add(a)

    return dict(mux_sharing)


def build_mux_control_conflicts_by_module(yaml_mux_list: list[dict]) -> dict[int, set[int]]:
    """Build mux control sharing map using ctrl module (e.g., U10B)."""
    module_to_muxes = defaultdict(set)

    for mux_entry in yaml_mux_list:
        mux_id = mux_entry["mux"]
        for ctrl in mux_entry.get("ctrl", []):
            module = ctrl.split("-")[0]  # e.g., U10B-5 → U10B
            module_to_muxes[module].add(mux_id)

    mux_conflict = defaultdict(set)
    for muxes in module_to_muxes.values():
        for a, b in itertools.combinations(muxes, 2):
            mux_conflict[a].add(b)
            mux_conflict[b].add(a)

    return dict(mux_conflict)


def merge_mux_conflicts(*conflict_maps: dict[int, set[int]]) -> dict[int, set[int]]:
    """Merge multiple mux conflict maps into one."""
    merged = defaultdict(set)
    for cmap in conflict_maps:
        for k, v in cmap.items():
            merged[k].update(v)
    return dict(merged)


if __name__ == "__main__":
    yaml_path = Path("/workspace/qdash/config/wiring.yaml")
    data = yaml.safe_load(yaml_path.read_text())

    mux_readout_conflicts = build_mux_readout_sharing_by_module(data["64Qv1"])
    mux_ctrl_conflicts = build_mux_control_conflicts_by_module(data["64Qv1"])
    mux_conflict_map = merge_mux_conflicts(mux_readout_conflicts, mux_ctrl_conflicts)

    print("📡 Mux Conflict Map (Readout + Control):")
    for mux, shared_muxes in sorted(mux_conflict_map.items()):
        print(f"  Mux {mux:2d}: {sorted(shared_muxes)}")
