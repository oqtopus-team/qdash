from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize
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
    "bare_frequency": "qubit_frequency",
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

        section_map = base_props[chip_id][section]
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
            else:
                update_if_different(field, qid, value)

    for cid, coupling in chip_props.couplings.items():
        for field, value in coupling.model_dump(exclude_none=True).items():
            if field == "zx90_gate_fidelity" and (value > 1.0 or cid in {"Q40-Q37", "Q40-Q41"}):
                update_if_different(field, cid, None)
            else:
                update_if_different(field, cid, value)

    return base_props


def get_chip_properties(chip: ChipDocument, within_24hrs: bool = False) -> ChipProperties:
    """Extract chip properties from the ChipDocument."""
    props = ChipProperties()

    for i in range(64):
        props.qubits[f"Q{i:02d}"] = QubitProperties()

    for qid, q in chip.qubits.items():
        props.qubits[f"Q{int(qid):02d}"] = _process_data(
            q.data, qubit_field_map, QubitProperties, within_24hrs
        )

    for cid, c in chip.couplings.items():
        source, target = cid.split("-")
        cid_str = f"Q{int(source):02d}-Q{int(target):02d}"
        props.couplings[cid_str] = _process_data(
            c.data, coupling_field_map, CouplingProperties, within_24hrs
        )

    return props


def create_chip_properties(
    username: str, source_path: str, target_path: str, chip_id: str = "64Qv1"
) -> None:
    """Create and write chip properties to a YAML file."""
    initialize()
    chip = ChipDocument.get_current_chip(username=username)
    props = get_chip_properties(chip, within_24hrs=False)

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
