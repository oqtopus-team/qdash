import math
from typing import Any, Protocol, TypeAlias, cast

import pendulum
from prefect import flow
from prefect.logging import get_run_logger
from pydantic import BaseModel, Field
from qdash.config import get_settings
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.initialize import initialize
from qdash.workflow.subflow.chip_info.task import generate_chip_info_report
from qdash.workflow.utils.slack import SlackContents, Status
from qdash.workflow.utiltask.create_directory import (
    create_directory_task,
)

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
    bell_state_fidelity: float | None = None


class ChipProperties(BaseModel):
    """Properties for the entire chip."""

    qubits: dict[str, QubitProperties] = Field(default_factory=dict)
    couplings: dict[str, CouplingProperties] = Field(default_factory=dict)


def _process_qubit_data(qubit_data: dict, within_24hrs: bool = False) -> QubitProperties:
    """Process a single qubit's data dict into QubitProperties."""
    qubit_props = QubitProperties()
    if not qubit_data:
        return qubit_props

    now = pendulum.now(tz="Asia/Tokyo")
    cutoff = now.subtract(hours=24)

    for key, value in qubit_data.items():
        calibrated_at = value.get("calibrated_at")
        is_recent = True
        if within_24hrs and calibrated_at:
            try:
                calibrated_at_dt = pendulum.parse(calibrated_at, tz="Asia/Tokyo")
                is_recent = calibrated_at_dt >= cutoff
            except Exception:
                is_recent = False  # 日付フォーマットが不正なら無効とみなす

        v = value.get("value") if is_recent else None

        if key == "bare_frequency":
            qubit_props.qubit_frequency = v
        elif key == "t1":
            qubit_props.t1 = v * 1e3 if v is not None else None  # us → ns
        elif key == "t2_echo":
            qubit_props.t2_echo = v * 1e3 if v is not None else None
        elif key == "t2_star":
            qubit_props.t2_star = v * 1e3 if v is not None else None
        elif key == "average_readout_fidelity":
            qubit_props.average_readout_fidelity = v
        elif key == "x90_gate_fidelity":
            qubit_props.x90_gate_fidelity = v
        elif key == "x180_gate_fidelity":
            qubit_props.x180_gate_fidelity = v

    return qubit_props


def _process_coupling_data(coupling_data: dict, within_24hrs: bool = False) -> CouplingProperties:
    """Process a single coupling's data dict into CouplingProperties."""
    coupling_props = CouplingProperties()
    if not coupling_data:
        return coupling_props

    now = pendulum.now(tz="Asia/Tokyo")
    cutoff = now.subtract(hours=24)

    for key, value in coupling_data.items():
        calibrated_at = value.get("calibrated_at")
        is_recent = True
        if within_24hrs and calibrated_at:
            try:
                calibrated_at_dt = pendulum.parse(calibrated_at, tz="Asia/Tokyo")
                is_recent = calibrated_at_dt >= cutoff
            except Exception:
                is_recent = False

        v = value.get("value") if is_recent else None

        if key == "zx90_gate_fidelity":
            coupling_props.zx90_gate_fidelity = v
        elif key == "static_zz_interaction":
            coupling_props.static_zz_interaction = v
        elif key == "qubit_qubit_coupling_strength":
            coupling_props.qubit_qubit_coupling_strength = v
        elif key == "bell_state_fidelity":
            coupling_props.bell_state_fidelity = v

    return coupling_props


def get_chip_properties(chip: ChipDocument, within_24hrs: bool = False) -> ChipProperties:
    """Get the properties of a chip as a dictionary."""
    chip_props = ChipProperties()

    # Initialize qubits
    for i in range(64):  # 64 qubits (00-63)
        qid_str = f"Q{i:02d}"
        chip_props.qubits[qid_str] = QubitProperties()

    # Process qubits
    for qid, qubit in chip.qubits.items():
        qid_str = f"Q{int(qid):02d}"
        chip_props.qubits[qid_str] = _process_qubit_data(qubit.data, within_24hrs=within_24hrs)

    # Process couplings
    for coupling_id, coupling in chip.couplings.items():
        source, target = coupling_id.split("-")
        source_str = f"Q{int(source):02d}"
        target_str = f"Q{int(target):02d}"
        coupling_key = f"{source_str}-{target_str}"
        chip_props.couplings[coupling_key] = _process_coupling_data(
            coupling.data, within_24hrs=within_24hrs
        )

    return chip_props


def get_best_chip_properties(chip: ChipDocument, within_24hrs: bool = False) -> ChipProperties:
    """Get the best properties of a chip as a dictionary."""
    chip_props = ChipProperties()

    # Initialize qubits
    for i in range(64):  # 64 qubits (00-63)
        qid_str = f"Q{i:02d}"
        chip_props.qubits[qid_str] = QubitProperties()

    # Process qubits
    for qid, qubit in chip.qubits.items():
        qid_str = f"Q{int(qid):02d}"
        chip_props.qubits[qid_str] = _process_qubit_data(qubit.best_data, within_24hrs=within_24hrs)

    # Process couplings
    for coupling_id, coupling in chip.couplings.items():
        source, target = coupling_id.split("-")
        source_str = f"Q{int(source):02d}"
        target_str = f"Q{int(target):02d}"
        coupling_key = f"{source_str}-{target_str}"
        chip_props.couplings[coupling_key] = _process_coupling_data(
            coupling.best_data, within_24hrs=within_24hrs
        )

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
        if value is None:
            return

        # セクションが存在しない場合は作成
        if section not in base_props["64Q"]:
            base_props["64Q"][section] = CommentedMap()
            updated_values[section] = {}

        section_map = base_props["64Q"][section]

        old_value = section_map.get(key)
        if old_value != value:
            if section not in updated_values:
                updated_values[section] = {}
            updated_values[section][key] = (old_value, value)
            section_map[key] = format_number(value)

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
                base_props["64Q"][section].yaml_add_eol_comment(
                    f"updated {old_value} -> {format_number(value)}", key, column=40
                )

    return base_props


def create_comment_map_from_chip_properties(chip_props: ChipProperties) -> CommentedMap:
    """Create a new CommentedMap structure from ChipProperties without merging."""
    props_map = CommentedMap()
    props_map["64Q"] = CommentedMap()

    # Qubit properties
    for qid, qubit in chip_props.qubits.items():
        qubit_dict = {k: v for k, v in qubit.model_dump().items() if v is not None}
        for field, value in qubit_dict.items():
            if field not in props_map["64Q"]:
                props_map["64Q"][field] = CommentedMap()
            props_map["64Q"][field][qid] = format_number(value)

    # Coupling properties
    for coupling_id, coupling in chip_props.couplings.items():
        coupling_dict = {k: v for k, v in coupling.model_dump().items() if v is not None}
        for field, value in coupling_dict.items():
            if field not in props_map["64Q"]:
                props_map["64Q"][field] = CommentedMap()
            props_map["64Q"][field][coupling_id] = format_number(value)

    return props_map


def write_yaml(data: CommentedMap | ChipProperties, filename: str = "chip_properties.yaml") -> None:
    """Write chip properties to a YAML file in the required format."""
    if isinstance(data, ChipProperties):
        # Convert Pydantic models to dict and format numbers
        def process_model(model: BaseModel) -> dict[str, Any]:
            return {k: format_number(v) for k, v in model.model_dump().items() if v is not None}

        # Initialize output structure
        output_dict = CommentedMap()
        output_dict["64Q"] = CommentedMap()
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
            "bell_state_fidelity",
        ]
        for section in sections:
            output_dict["64Q"][section] = CommentedMap()

        # Process qubits
        for qid, qubit in data.qubits.items():
            qubit_dict = process_model(qubit)
            for field, value in qubit_dict.items():
                output_dict["64Q"][field][qid] = value

        # Process couplings
        for coupling_id, coupling in data.couplings.items():
            coupling_dict = process_model(coupling)
            for field, value in coupling_dict.items():
                output_dict["64Q"][field][coupling_id] = value

        data = output_dict

    # Write to file
    from pathlib import Path

    with Path(filename).open("w") as f:
        yaml_rt.dump(data, f)


@flow(name="update-chip-properties", log_prints=True)
def update_props(username: str = "admin") -> None:
    """Update chip properties."""
    # Initialize database connection
    initialize()
    logger = get_run_logger()
    # Get current chip
    chip = ChipDocument.get_current_chip(username=username)

    # ==== 1. これまでの実績を加味したプロパティ ====
    chip_props_all = get_chip_properties(chip, within_24hrs=False)
    base_props = read_base_properties(filename="/app/config/props.yaml")
    merged_props_all = merge_properties(base_props, chip_props_all)

    # ==== 2. 24時間以内の最新プロパティ　====
    chip_props_24hrs = get_chip_properties(chip, within_24hrs=True)
    chip_props_24hrs_all = create_comment_map_from_chip_properties(chip_props_24hrs)
    # base_props とのマージは行わない

    # ==== 3. ベストプロパティと昨日のデータの比較 ====
    chip_props_best = get_best_chip_properties(chip, within_24hrs=True)
    chip_props_best_all = create_comment_map_from_chip_properties(chip_props_best)

    # Get yesterday's data
    yesterday_history = ChipHistoryDocument.get_yesterday_history(chip.chip_id, username)
    value_sci_notation_threshold = 1e3

    def format_value(value: float | None) -> str:
        """Format value for display."""
        if value is None:
            return "N/A"
        return f"{value:.2e}" if abs(value) >= value_sci_notation_threshold else f"{value:.3f}"

    def calculate_improvement(new_val: float | None, old_val: float | None) -> str:
        """Calculate improvement percentage."""
        if new_val is None or old_val is None or old_val == 0:
            return ""
        change = ((new_val - old_val) / abs(old_val)) * 100
        return f" ({change:+.1f}%)"

    def create_best_updates_text() -> str:
        """Generate a text showing best data updates from today."""
        lines = ["*🏆 Today's Best Data Updates*\n"]

        # Check qubit properties
        for qid, best_qubit in chip_props_best.qubits.items():
            best_dict = best_qubit.model_dump()

            updates = []
            for field, best_value in best_dict.items():
                if best_value is None:
                    continue

                # Get the value from yesterday for comparison
                yesterday_value = None
                if yesterday_history and qid in yesterday_history.qubits:
                    yesterday_data = yesterday_history.qubits[qid].data
                    if field == "t1":
                        yesterday_value = yesterday_data.get("t1", {}).get("value")
                        if yesterday_value:
                            yesterday_value *= 1e3  # Convert to ns
                    elif field == "t2_echo":
                        yesterday_value = yesterday_data.get("t2_echo", {}).get("value")
                        if yesterday_value:
                            yesterday_value *= 1e3  # Convert to ns
                    elif field == "t2_star":
                        yesterday_value = yesterday_data.get("t2_star", {}).get("value")
                        if yesterday_value:
                            yesterday_value *= 1e3  # Convert to ns
                    elif field in [
                        "x90_gate_fidelity",
                        "x180_gate_fidelity",
                        "average_readout_fidelity",
                    ]:
                        yesterday_value = yesterday_data.get(field, {}).get("value")

                # Only show if this is a new best value
                if yesterday_value is None:
                    updates.append(f"・{field}: New best! {format_value(best_value)}")
                elif best_value > yesterday_value:  # Assuming higher values are better
                    improvement = calculate_improvement(best_value, yesterday_value)
                    updates.append(
                        f"・{field}: New best! {format_value(yesterday_value)} → {format_value(best_value)}{improvement}"
                    )

            if updates:
                lines.append(f"\n*{qid}*")
                lines.extend(updates)

        # Check coupling properties
        for coupling_id, best_coupling in chip_props_best.couplings.items():
            best_dict = best_coupling.model_dump()

            updates = []
            for field, best_value in best_dict.items():
                if best_value is None:
                    continue

                # Get the value from yesterday for comparison
                yesterday_value = None
                if yesterday_history and coupling_id in yesterday_history.couplings:
                    yesterday_data = yesterday_history.couplings[coupling_id].data
                    yesterday_value = yesterday_data.get(field, {}).get("value")

                # Only show if this is a new best value
                if yesterday_value is None:
                    updates.append(f"・{field}: New best! {format_value(best_value)}")
                elif best_value > yesterday_value:  # Assuming higher values are better
                    improvement = calculate_improvement(best_value, yesterday_value)
                    updates.append(
                        f"・{field}: New best! {format_value(yesterday_value)} → {format_value(best_value)}{improvement}"
                    )

            if updates:
                lines.append(f"\n*{coupling_id}*")
                lines.extend(updates)

        return "\n".join(lines) if len(lines) > 1 else "*No best data updates today*\n"

    # Example usage to avoid unused function warning
    # logger.info(create_report_text(chip_props_best_all))

    # ==== 保存処理 ====
    settings = get_settings()
    date_str = pendulum.now(tz="Asia/Tokyo").date().strftime("%Y%m%d")
    chip_info_dir = f"/app/calib_data/{username}/{date_str}/chip_info"
    create_directory_task.submit(chip_info_dir).result()

    # 書き出し
    props_save_path = f"{chip_info_dir}/props.yaml"
    write_yaml(merged_props_all, filename=props_save_path)  # 全データ込み
    chip_props_24hrs_save_path = f"{chip_info_dir}/props_24hrs.yaml"
    logger.info(f"props.yaml saved to {props_save_path}")
    logger.info(f"props_24hrs.yaml saved to {chip_props_24hrs_save_path}")
    write_yaml(chip_props_24hrs_all, filename=chip_props_24hrs_save_path)
    # Send best updates report
    updates_text = create_best_updates_text()

    slack = SlackContents(
        status=Status.SUCCESS,
        title="🏆 Best Data Updates",
        msg=updates_text,
        ts="",
        path="",
        header="Today's best data updates",
        channel=settings.slack_channel_id,
        token=settings.slack_bot_token,
    )
    ts = slack.send_slack()
    slack = SlackContents(
        status=Status.SUCCESS,
        title="props.yaml",
        msg="props.yaml updated successfully.",
        ts=ts,
        path=props_save_path,
        header=f"file: {props_save_path}",
        channel=settings.slack_channel_id,
        token=settings.slack_bot_token,
    )
    slack.send_slack()
    generate_chip_info_report(chip_info_dir=chip_info_dir)
    slack = SlackContents(
        status=Status.SUCCESS,
        title="chip_info_report.pdf",
        msg="chip_info_report.pdf updated successfully.",
        ts=ts,
        path=f"{chip_info_dir}/chip_info_report.pdf",
        header=f"file: {chip_info_dir}/chip_info_report.pdf",
        channel=settings.slack_channel_id,
        token=settings.slack_bot_token,
    )
    slack.send_slack()
    logger.info("Chip properties updated successfully.")
