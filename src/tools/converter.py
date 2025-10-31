import math
from typing import Any, Protocol, TypeAlias, cast

from pydantic import BaseModel, Field
from qdash.db.init import initialize
from qdash.dbmodel.chip import ChipDocument

# Import YAML module
from ruamel import yaml
from ruamel.yaml.comments import CommentedMap

# Create YAML instance for reading with round-trip mode
yaml_rt = yaml.YAML(typ="rt")
yaml_rt.preserve_quotes = True
yaml_rt.width = None
yaml_rt.indent(mapping=2, sequence=4, offset=2)

# Create YAML instance for writing
yaml_impl = yaml.YAML()
yaml_impl.width = None
yaml_impl.default_flow_style = False
yaml_impl.preserve_quotes = True
yaml_impl.indent(mapping=2, sequence=4, offset=2)
yaml_impl.allow_unicode = True
yaml_impl.explicit_start = True


# Custom representer for None values
def represent_none(self: Any, _: Any) -> Any:
    """Represent None as 'null' in YAML."""
    return self.represent_scalar("tag:yaml.org,2002:null", "null")


yaml_impl.representer.add_representer(type(None), represent_none)


# Custom representer for scientific notation
def represent_float(self: Any, data: float) -> Any:
    """Represent float values in scientific notation."""
    if abs(data) >= 1e3:  # Changed from 1e4 to 1e3
        # Convert to e+3 notation
        exp = math.floor(math.log10(abs(data)))
        exp3 = exp - (exp % 3)  # Round down to nearest multiple of 3
        mantissa = data / (10**exp3)
        return self.represent_scalar("tag:yaml.org,2002:float", f"{mantissa:.1f}e+3")
    return self.represent_scalar("tag:yaml.org,2002:float", str(data))


yaml_rt.representer.add_representer(float, represent_float)


# Type aliases
YAMLValue: TypeAlias = None | bool | int | float | str | list[Any] | dict[str, Any]
YAMLDict: TypeAlias = dict[str, dict[str, YAMLValue]]


class YAMLDumper(Protocol):
    """Protocol for YAML dumper."""

    def represent_scalar(self, tag: str, value: str) -> Any: ...


class QubitProperties(BaseModel):
    """Properties for a single qubit."""

    resonator_frequency: float | None = None
    qubit_frequency: float | None = None
    anharmonicity: float | None = None
    external_loss_rate: float | None = None
    internal_loss_rate: float | None = None
    t1: float | None = None  # in ns
    t2_echo: float | None = None  # in ns
    t2_star: float | None = None  # in ns
    average_readout_fidelity: float | None = None
    average_gate_fidelity: float | None = None
    x90_gate_fidelity: float | None = None
    x180_gate_fidelity: float | None = None


class CouplingProperties(BaseModel):
    """Properties for a coupling between qubits."""

    static_zz_interaction: float | None = None
    qubit_qubit_coupling_strength: float | None = None
    zx90_gate_fidelity: float | None = None


class ChipProperties(BaseModel):
    """Properties for the entire chip."""

    qubits: dict[str, QubitProperties] = Field(default_factory=dict)
    couplings: dict[str, CouplingProperties] = Field(default_factory=dict)


def _process_qubit_data(qubit_data: dict) -> QubitProperties:
    """Process a single qubit's data dict into QubitProperties."""
    qubit_props = QubitProperties()
    if not qubit_data:
        return qubit_props
    for key, value in qubit_data.items():
        v = value.get("value")
        if key == "qubit_frequency":
            qubit_props.qubit_frequency = v
        elif key == "t1":
            qubit_props.t1 = v * 1e3 if v is not None else None  # Convert to ns
        elif key == "t2_echo":
            qubit_props.t2_echo = v * 1e3 if v is not None else None  # Convert to ns
        elif key == "t2_star":
            qubit_props.t2_star = v * 1e3 if v is not None else None  # Convert to ns
        elif key == "average_readout_fidelity":
            qubit_props.average_readout_fidelity = v
        elif key == "x90_gate_fidelity":
            qubit_props.x90_gate_fidelity = v
        elif key == "x180_gate_fidelity":
            qubit_props.x180_gate_fidelity = v
    return qubit_props


def _process_coupling_data(coupling_data: dict) -> CouplingProperties:
    """Process a single coupling's data dict into CouplingProperties."""
    coupling_props = CouplingProperties()
    if not coupling_data:
        return coupling_props
    for key, value in coupling_data.items():
        v = value.get("value")
        if key == "zx90_gate_fidelity":
            coupling_props.zx90_gate_fidelity = v
        elif key == "static_zz_interaction":
            coupling_props.static_zz_interaction = v
        elif key == "qubit_qubit_coupling_strength":
            coupling_props.qubit_qubit_coupling_strength = v
    return coupling_props


def get_chip_properties(chip: ChipDocument) -> ChipProperties:
    """Get the properties of a chip as a dictionary."""
    chip_props = ChipProperties()

    # Initialize qubits
    for i in range(64):  # 64 qubits (00-63)
        qid_str = f"Q{i:02d}"
        chip_props.qubits[qid_str] = QubitProperties()

    # Process qubits
    for qid, qubit in chip.qubits.items():
        qid_str = f"Q{int(qid):02d}"
        chip_props.qubits[qid_str] = _process_qubit_data(qubit.data)

    # Process couplings
    for coupling_id, coupling in chip.couplings.items():
        source, target = coupling_id.split("-")
        source_str = f"Q{int(source):02d}"
        target_str = f"Q{int(target):02d}"
        coupling_key = f"{source_str}-{target_str}"
        chip_props.couplings[coupling_key] = _process_coupling_data(coupling.data)

    return chip_props


def read_base_properties(filename: str = "props.yaml") -> CommentedMap:
    """Read the base properties from props.yaml."""
    from pathlib import Path

    with Path(filename).open("r") as f:
        data = yaml_rt.load(f)
        return cast(CommentedMap, data)


def format_number(n: float | str) -> float | str:
    """Format scientific notation values."""
    if isinstance(n, float):
        if abs(n) >= 1e3:  # Changed from 1e4 to 1e3
            # Convert to e+3 notation
            exp = math.floor(math.log10(abs(n)))
            exp3 = exp - (exp % 3)  # Round down to nearest multiple of 3
            mantissa = n / (10**exp3)
            return float(f"{mantissa:.1f}e+3")
        return n
    return n


def merge_properties(base_props: CommentedMap, chip_props: ChipProperties) -> CommentedMap:
    """Merge chip properties with base properties, updating only differing values."""
    # Track which values have been updated with their old values
    updated_values: dict[str, dict[str, tuple[Any, Any]]] = {}

    # Helper function to update a property if it differs
    def update_if_different(section: str, key: str, value: float | str | bool | None) -> None:
        if value is not None and key in base_props["64Qv1"][section]:
            old_value = base_props["64Qv1"][section][key]
            if old_value != value:
                if section not in updated_values:
                    updated_values[section] = {}
                updated_values[section][key] = (old_value, value)
                base_props["64Qv1"][section][key] = format_number(value)

    # Update qubit properties
    for qid, qubit in chip_props.qubits.items():
        qubit_dict = {k: v for k, v in qubit.model_dump().items() if v is not None}
        for field, value in qubit_dict.items():
            update_if_different(field, qid, value)

    # Update coupling properties
    for coupling_id, coupling in chip_props.couplings.items():
        coupling_dict = {k: v for k, v in coupling.model_dump().items() if v is not None}
        for field, value in coupling_dict.items():
            update_if_different(field, coupling_id, value)

    # Add inline "# updated" comments for updated values
    for section, updates in updated_values.items():
        for key, (old_value, value) in updates.items():
            if value is not None:
                base_props["64Qv1"][section].yaml_add_eol_comment(
                    f"updated {old_value} -> {format_number(value)}", key, column=40
                )

    return base_props


def write_yaml(data: CommentedMap | ChipProperties, filename: str = "chip_properties.yaml") -> None:
    """Write chip properties to a YAML file in the required format."""
    if isinstance(data, ChipProperties):
        # Convert Pydantic models to dict and format numbers
        def process_model(model: BaseModel) -> dict[str, Any]:
            return {k: format_number(v) for k, v in model.model_dump().items() if v is not None}

        # Initialize output structure
        output_dict = CommentedMap()
        output_dict["64Qv1"] = CommentedMap()
        sections = [
            "resonator_frequency",
            "qubit_frequency",
            "anharmonicity",
            "external_loss_rate",
            "internal_loss_rate",
            "t1",
            "t2_echo",
            "t2_star",
            "static_zz_interaction",
            "qubit_qubit_coupling_strength",
            "average_readout_fidelity",
            "average_gate_fidelity",
            "x90_gate_fidelity",
            "x180_gate_fidelity",
            "zx90_gate_fidelity",
        ]
        for section in sections:
            output_dict["64Qv1"][section] = CommentedMap()

        # Process qubits
        for qid, qubit in data.qubits.items():
            qubit_dict = process_model(qubit)
            for field, value in qubit_dict.items():
                output_dict["64Qv1"][field][qid] = value

        # Process couplings
        for coupling_id, coupling in data.couplings.items():
            coupling_dict = process_model(coupling)
            for field, value in coupling_dict.items():
                output_dict["64Qv1"][field][coupling_id] = value

        data = output_dict

    # Write to file
    from pathlib import Path

    with Path(filename).open("w") as f:
        yaml_rt.dump(data, f)


if __name__ == "__main__":
    # Initialize database connection
    initialize()

    # Get current chip
    chip = ChipDocument.get_current_chip(username="orangekame3")

    # Convert properties
    chip_props = get_chip_properties(chip)

    # Read base properties
    base_props = read_base_properties()

    # Merge properties
    merged_props = merge_properties(base_props, chip_props)

    # Write to YAML file
    write_yaml(merged_props)
    print("Chip properties have been written to chip_properties.yaml")
