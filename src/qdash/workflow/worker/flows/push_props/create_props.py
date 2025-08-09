from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize
from qdash.workflow.core.session.qubex import QubexSession
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


def merge_properties(base_props: CommentedMap, chip_props: ChipProperties, chip_id: str = "64Qv1") -> CommentedMap:
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
            if field == "x90_gate_fidelity" and value > 1.0 or field == "x180_gate_fidelity" and value > 1.0:
                update_if_different(field, qid, None)
            elif field == "qubit_frequency":
                continue
            else:
                update_if_different(field, qid, value)
    for cid, coupling in chip_props.couplings.items():
        for field, value in coupling.model_dump(exclude_none=True).items():
            if field == "zx90_gate_fidelity" and (value > 1.0):
                update_if_different(field, cid, None)
            else:
                update_if_different(field, cid, value)
    return base_props


def get_chip_properties(chip: ChipDocument, session: QubexSession, within_24hrs: bool = False) -> ChipProperties:
    """Extract chip properties from the ChipDocument."""
    props = ChipProperties()
    import re

    match = re.search(r"\d+", session.config["chip_id"])
    if not match:
        raise ValueError(f"No digits found in chip_id: {session.config['chip_id']}")
    n = int(match.group())
    exp = session.get_session()
    for i in range(n):
        props.qubits[exp.get_qubit_label(i)] = QubitProperties()

    for qid, q in chip.qubits.items():
        props.qubits[exp.get_qubit_label(int(qid))] = _process_data(
            q.data, qubit_field_map, QubitProperties, within_24hrs
        )

    for cid, c in chip.couplings.items():
        source, target = cid.split("-")
        cid_str = f"{exp.get_qubit_label(int(source))}-{exp.get_qubit_label(int(target))}"
        props.couplings[cid_str] = _process_data(c.data, coupling_field_map, CouplingProperties, within_24hrs)

    return props


def create_chip_properties(username: str, source_path: str, target_path: str, chip_id: str = "64Qv1") -> None:
    """Create and write chip properties to a YAML file."""
    initialize()
    chip = ChipDocument.get_current_chip(username=username)
    from qdash.workflow.core.session.factory import create_session

    session = create_session(
        backend="qubex",
        config={
            "task_type": "",
            "username": "admin",
            "qids": "",
            "note_path": "",
            "chip_id": chip_id,
        },
    )
    props = get_chip_properties(chip, within_24hrs=False, session=session)

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
