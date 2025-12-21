from typing import Any, cast

from qdash.datamodel.chip import ChipModel
from qdash.dbmodel.initialize import initialize
from qdash.workflow.engine.backend.qubex import QubexBackend
from qdash.workflow.worker.flows.push_props.formatter import format_number
from qdash.workflow.worker.flows.push_props.io import ChipPropertyYAMLHandler
from qdash.workflow.worker.flows.push_props.models import (
    ChipProperties,
    CouplingProperties,
    QubitProperties,
)
from qdash.workflow.worker.flows.push_props.processor import _process_data
from ruamel.yaml.comments import CommentedMap

qubit_field_map = {
    "qubit_frequency": "qubit_frequency",
    # "resonator_frequency": "resonator_frequency",
    "t1": "t1",
    "t2_echo": "t2_echo",
    "t2_star": "t2_star",
    "average_readout_fidelity": "average_readout_fidelity",
    "x90_gate_fidelity": "x90_gate_fidelity",
    "x180_gate_fidelity": "x180_gate_fidelity",
}

coupling_field_map = {
    "static_zz_interaction": "static_zz_interaction",
    "qubit_qubit_coupling_strength": "qubit_qubit_coupling_strength",
    "zx90_gate_fidelity": "zx90_gate_fidelity",
    "bell_state_fidelity": "bell_state_fidelity",
}


def merge_properties(
    base_props: CommentedMap, chip_props: ChipProperties, chip_id: str = "64Qv1"
) -> CommentedMap:
    """Merge chip properties into the base properties map."""

    def update_if_different(section: str, key: str, value: float | str | None) -> None:
        if value is None:
            return
        if chip_id not in base_props:
            base_props[chip_id] = CommentedMap()

        if section not in base_props[chip_id]:
            base_props[chip_id][section] = CommentedMap()

        section_map = base_props[chip_id].get(section)
        if section_map is None:
            section_map = CommentedMap()
            base_props[chip_id][section] = section_map
        old_value = section_map.get(key)
        if old_value != value:
            section_map[key] = format_number(value)

    for qid, qubit in chip_props.qubits.items():
        for field, value in qubit.model_dump(exclude_none=True).items():
            if (
                field == "x90_gate_fidelity"
                and value > 1.0
                or field == "x180_gate_fidelity"
                and value > 1.0
            ):
                update_if_different(field, qid, None)
            # elif field == "qubit_frequency":
            #     continue
            else:
                update_if_different(field, qid, value)
    for cid, coupling in chip_props.couplings.items():
        for field, value in coupling.model_dump(exclude_none=True).items():
            if field == "zx90_gate_fidelity" and (value > 1.0):
                update_if_different(field, cid, None)
            else:
                update_if_different(field, cid, value)
    return base_props


def get_chip_properties(
    chip: ChipModel, backend: QubexBackend, within_24hrs: bool = False, cutoff_hours: int = 24
) -> tuple[ChipProperties, dict[str, Any]]:
    """Extract chip properties from chip data.

    Returns:
        Tuple of (ChipProperties, stats_dict) where stats_dict contains data availability info
    """
    props = ChipProperties()
    stats = {
        "total_qubits": 0,
        "qubits_with_recent_data": 0,
        "total_couplings": 0,
        "couplings_with_recent_data": 0,
        "cutoff_hours": cutoff_hours,
    }
    import re

    match = re.search(r"\d+", backend.config["chip_id"])
    if not match:
        raise ValueError(f"No digits found in chip_id: {backend.config['chip_id']}")
    n = int(match.group())
    exp = backend.get_instance()
    if exp is None:
        raise RuntimeError("Backend experiment instance is not initialized")
    for i in range(n):
        props.qubits[exp.get_qubit_label(i)] = QubitProperties()

    for qid, q in chip.qubits.items():
        stats["total_qubits"] += 1
        qubit_props = _process_data(
            q.data, qubit_field_map, QubitProperties, within_24hrs, cutoff_hours
        )
        props.qubits[exp.get_qubit_label(int(qid))] = qubit_props

        # Check if qubit has any recent data
        if within_24hrs and any(
            getattr(qubit_props, field, None) is not None for field in qubit_field_map.values()
        ):
            stats["qubits_with_recent_data"] += 1

    for cid, c in chip.couplings.items():
        source, target = cid.split("-")
        cid_str = f"{exp.get_qubit_label(int(source))}-{exp.get_qubit_label(int(target))}"
        stats["total_couplings"] += 1
        coupling_props = _process_data(
            c.data, coupling_field_map, CouplingProperties, within_24hrs, cutoff_hours
        )
        props.couplings[cid_str] = coupling_props

        # Check if coupling has any recent data
        if within_24hrs and any(
            getattr(coupling_props, field, None) is not None
            for field in coupling_field_map.values()
        ):
            stats["couplings_with_recent_data"] += 1

    return props, stats


def create_chip_properties(
    username: str, source_path: str, target_path: str, chip_id: str = "64Qv1"
) -> None:
    """Create and write chip properties to a YAML file."""
    initialize()
    from qdash.repository import MongoChipRepository

    chip_repo = MongoChipRepository()
    chip = chip_repo.get_current_chip(username=username)
    if chip is None:
        raise ValueError(f"Chip not found for user {username}")
    from qdash.workflow.engine.backend.factory import create_backend

    backend = create_backend(
        backend="qubex",
        config={
            "task_type": "",
            "username": "admin",
            "qids": "",
            "note_path": "",
            "chip_id": chip_id,
        },
    )
    props, _ = get_chip_properties(chip, within_24hrs=False, backend=cast(QubexBackend, backend))

    handler = ChipPropertyYAMLHandler(source_path)
    base = handler.read()

    merged = merge_properties(base, props, chip_id=chip_id)
    handler.write(merged, target_path)


if __name__ == "__main__":
    create_chip_properties(
        "orangekame3",
        source_path="/app/config/qubex/64Qv1/properties/chip_properties.yaml",
        target_path="/app/config/qubex/64Qv1/properties/chip_properties.yaml",
    )
