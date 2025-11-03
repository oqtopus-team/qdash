import math
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

import plotly.graph_objects as go
from PIL import Image
from prefect import task
from qubex.backend import LatticeGraph
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from ruamel import yaml
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarfloat import ScalarFloat

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


NODE_SIZE = 24
TEXT_SIZE = 10


class CustomLatticeGraph(LatticeGraph):
    def create_lattice_figure(
        self,
        *,
        title: str = "Lattice Data",
        values: list | None = None,
        texts: list[str] | None = None,
        hovertexts: list[str] | None = None,
        colorscale: str = "Viridis",
    ) -> go.Figure:
        value_matrix = self.create_data_matrix(values) if values else None
        text_matrix = self.create_data_matrix(texts) if texts else None
        hovertext_matrix = self.create_data_matrix(hovertexts) if hovertexts else None

        fig = go.Figure(
            go.Heatmap(
                z=value_matrix,
                text=text_matrix,
                colorscale=colorscale,
                hoverinfo="text",
                hovertext=hovertext_matrix or text_matrix,
                texttemplate="%{text}",
                showscale=False,
                textfont=dict(
                    family="monospace",
                    size=TEXT_SIZE,
                    weight="bold",
                ),
            )
        )

        width = 3 * NODE_SIZE * self.n_qubit_cols
        height = 3 * NODE_SIZE * self.n_qubit_rows

        fig.update_layout(
            title=title,
            showlegend=False,
            margin=dict(b=30, l=30, r=30, t=60),
            xaxis=dict(
                ticks="",
                linewidth=1,
                showgrid=False,
                zeroline=False,
                showticklabels=False,
            ),
            yaxis=dict(
                ticks="",
                autorange="reversed",
                linewidth=1,
                showgrid=False,
                zeroline=False,
                showticklabels=False,
            ),
            width=width,
            height=height,
        )

        return fig

    def create_graph_figure(
        self,
        *,
        directed: bool = True,
        title: str = "Graph Data",
        node_values: dict | None = None,
        node_texts: dict | None = None,
        node_hovertexts: dict | None = None,
        node_color: str | None = None,
        node_linecolor: str | None = None,
        node_textcolor: str | None = None,
        edge_values: dict | None = None,
        edge_texts: dict | None = None,
        edge_hovertexts: dict | None = None,
        edge_color: str | None = None,
        edge_textcolor: str | None = None,
        node_overlay: bool = False,
        edge_overlay: bool = False,
        node_overlay_values: dict | None = None,
        node_overlay_texts: dict | None = None,
        node_overlay_hovertexts: dict | None = None,
        node_overlay_color: str | None = None,
        node_overlay_linecolor: str | None = None,
        node_overlay_textcolor: str | None = None,
        edge_overlay_values: dict | None = None,
        edge_overlay_texts: dict | None = None,
        edge_overlay_hovertexts: dict | None = None,
        edge_overlay_color: str | None = None,
        edge_overlay_textcolor: str | None = None,
        colorscale: str = "Viridis",
    ):
        width = 3 * NODE_SIZE * self.n_qubit_cols
        height = 3 * NODE_SIZE * self.n_qubit_rows

        layout = go.Layout(
            title=title,
            width=width,
            height=height,
            margin=dict(b=30, l=30, r=30, t=60),
            xaxis=dict(
                ticks="",
                # showline=False,
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                constrain="domain",
            ),
            yaxis=dict(
                ticks="",
                autorange="reversed",
                # showline=False,
                showgrid=False,
                zeroline=False,
                showticklabels=False,
            ),
            plot_bgcolor="white",
            showlegend=False,
            hovermode="closest",
            hoverlabel=dict(
                bgcolor="white",
                bordercolor="black",
                font=dict(
                    family="monospace",
                    size=TEXT_SIZE,
                    color="black",
                ),
            ),
        )

        data = []

        mux_node_trace = self._create_mux_node_trace()
        data.append(mux_node_trace)

        qubit_edge_trace = self._create_qubit_edge_traces(
            directed=directed,
            values=edge_values,
            texts=edge_texts,
            hovertexts=edge_hovertexts,
            color=edge_color,
            textcolor=edge_textcolor,
            colorscale=colorscale,
        )
        data += qubit_edge_trace

        if edge_overlay:
            qubit_edge_overlay_trace = self._create_qubit_edge_traces(
                directed=directed,
                values=edge_overlay_values,
                texts=edge_overlay_texts,
                hovertexts=edge_overlay_hovertexts,
                color=edge_overlay_color,
                textcolor=edge_overlay_textcolor,
                colorscale=colorscale,
            )
            data += qubit_edge_overlay_trace

        qubit_node_trace = self._create_qubit_node_traces(
            values=node_values,
            texts=node_texts,
            hovertexts=node_hovertexts,
            color=node_color,
            linecolor=node_linecolor,
            textcolor=node_textcolor,
        )
        data += qubit_node_trace

        if node_overlay:
            qubit_node_overlay_trace = self._create_qubit_node_traces(
                values=node_overlay_values,
                texts=node_overlay_texts,
                hovertexts=node_overlay_hovertexts,
                color=node_overlay_color,
                linecolor=node_overlay_linecolor,
                textcolor=node_overlay_textcolor,
            )
            data += qubit_node_overlay_trace

        fig = go.Figure(
            data=data,
            layout=layout,
        )
        return fig


def replace_none_with_nan(obj: dict | list | ScalarFloat | None | float | int | str):
    if isinstance(obj, dict):
        return {k: replace_none_with_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_none_with_nan(v) for v in obj]
    elif isinstance(obj, ScalarFloat):
        return float(obj)
    elif obj is None:
        return math.nan
    else:
        return obj


def read_base_properties(filename: str = "") -> CommentedMap:
    """Read the base properties from props.yaml and replace None with NaN, ScalarFloat with float."""
    with Path(filename).open("r") as f:
        data = yaml_rt.load(f)
        data = replace_none_with_nan(data)
        return cast(CommentedMap, data)


def generate_pdf_report(image_paths: list[str], pdf_path: str = "report.pdf"):
    """画像をPDFに貼り付けてレポートを作成。"""
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    for path in image_paths:
        if not Path(path).exists():
            continue
        img = Image.open(path)
        aspect = img.height / img.width
        img_width = width - 100
        img_height = img_width * aspect
        c.drawImage(
            ImageReader(path),
            50,
            height - img_height - 50,
            width=img_width,
            height=img_height,
        )
        c.showPage()

    c.save()
    print(f"Saved PDF report: {pdf_path}")


def generate_rich_pdf_report(image_paths: list[str], pdf_path: str = "rich_report.pdf"):
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    # 表紙
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(width / 2, height - 100, "QDash Calibration Report")

    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height - 140, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawCentredString(width / 2, height - 160, "Generated by: QDash System")

    c.showPage()

    # 本文
    for i, path in enumerate(image_paths):
        if not Path(path).exists():
            continue

        img = Image.open(path)
        aspect = img.height / img.width
        img_width = width - 100
        img_height = img_width * aspect

        # セクションタイトル
        section_title = Path(path).stem.replace("_", " ").title()
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, section_title)

        # 画像
        c.drawImage(ImageReader(path), 50, height - img_height - 80, width=img_width, height=img_height)

        # ページ番号
        c.setFont("Helvetica", 10)
        c.drawRightString(width - 50, 30, f"Page {i+1}")

        c.showPage()

    c.save()
    print(f"Saved rich report: {pdf_path}")


def create_undirected_data(
    data: dict[str, float],
    method: Literal["avg", "max", "min"],
) -> dict[str, float]:
    """Create undirected data by combining bidirectional values.

    Args:
    ----
        data: Dictionary of directed data with format {"qubit1-qubit2": value}
        method: Method to combine values ("avg", "max", or "min")

    Returns:
    -------
        Dictionary of undirected data

    """
    result: dict[str, float] = {}
    for key, value in data.items():
        if value is None or math.isnan(value):
            continue
        pair = key.split("-")
        inv_key = f"{pair[1]}-{pair[0]}"
        if inv_key in result and result[inv_key] is not None and not math.isnan(result[inv_key]):
            if method == "avg":
                result[inv_key] = (result[inv_key] + value) / 2
            elif method == "max":
                result[inv_key] = max(result[inv_key], value)
            elif method == "min":
                result[inv_key] = min(result[inv_key], value)
            else:
                raise ValueError(f"Unknown method: {method}")
        else:
            result[key] = float(value)
    return result


def pad_qubit_data(data: dict[str, float], chip_id: str = "64Qv1") -> dict[str, float]:
    """Pad missing qubit data with NaN values.

    Args:
    ----
        data: Dictionary of qubit data with format {"Q00": value, "Q01": value, ...}
        chip_id: Chip ID to determine the number of qubits

    Returns:
    -------
        Dictionary with all qubits from Q00 to Q{n_qubits-1}, with NaN for missing values

    """
    result: dict[str, float] = {}
    import re

    from qdash.workflow.engine.session.factory import create_session

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
    match = re.search(r"\d+", chip_id)
    if not match:
        raise ValueError(f"Could not extract number of qubits from chip_id: {chip_id}")
    n_qubits = int(match.group())
    exp = session.get_session()
    for i in range(n_qubits):
        qubit = exp.get_qubit_label(i)  # Use zero-padded format Q00, Q01, etc.
        result[qubit] = data.get(qubit, math.nan)
    return result


def generate_figures(props: dict, chip_info_dir: str, suffix: str = "", chip_id: str = "64Qv1") -> list[str]:
    """Generate figures for chip information.

    Args:
    ----
        props: Properties dictionary containing chip data
        chip_info_dir: Directory to save figures
        suffix: Suffix to append to filenames (e.g. "_24h", "_12h")

    Returns:
    -------
        List of generated figure paths

    """
    info_type = (
        "qubit_frequency",
        "qubit_anharmonicity",
        "t1",
        "t2_echo",
        "average_readout_fidelity",
        "x90_gate_fidelity",
        "zx90_gate_fidelity",
        "bell_state_fidelity",
    )

    generated_files = []
    import re

    match = re.search(r"\d+", chip_id)
    if not match:
        raise ValueError(f"Could not extract number of qubits from chip_id: {chip_id}")
    n_qubits = int(match.group())
    graph = CustomLatticeGraph(n_qubits=n_qubits)

    if "resonator_frequency" in info_type and "resonator_frequency" in props:
        values = pad_qubit_data(props["resonator_frequency"], chip_id=chip_id)
        fig = graph.create_lattice_figure(
            title=f"Resonator frequency (GHz){(' (' + suffix.lstrip('_') + ')') if suffix else ''}",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value:.3f}<br>GHz" if not math.isnan(value) else "N/A" for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value * 1e3:.3f} MHz" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        path = f"{chip_info_dir}/resonator_frequency{suffix}.png"
        fig.write_image(file=path)
        generated_files.append(path)

    if "qubit_frequency" in info_type and "qubit_frequency" in props:
        values = pad_qubit_data(props["qubit_frequency"], chip_id=chip_id)
        fig = graph.create_lattice_figure(
            title=f"Qubit frequency (GHz){(' (' + suffix.lstrip('_') + ')') if suffix else ''}",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value:.3f}<br>GHz" if not math.isnan(value) else "N/A" for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value * 1e3:.3f} MHz" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        path = f"{chip_info_dir}/qubit_frequency{suffix}.png"
        fig.write_image(file=path)
        generated_files.append(path)

    if "qubit_anharmonicity" in info_type and "anharmonicity" in props:
        values = pad_qubit_data(props["anharmonicity"], chip_id=chip_id)
        fig = graph.create_lattice_figure(
            title=f"Qubit anharmonicity (MHz){(' (' + suffix.lstrip('_') + ')') if suffix else ''}",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value * 1e3:.1f}<br>MHz" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value * 1e3:.3f} MHz" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        path = f"{chip_info_dir}/qubit_anharmonicity{suffix}.png"
        fig.write_image(file=path)
        generated_files.append(path)

    if "t1" in info_type and "t1" in props:
        values = pad_qubit_data(props["t1"], chip_id=chip_id)
        fig = graph.create_lattice_figure(
            title=f"T1 (μs){(' (' + suffix.lstrip('_') + ')') if suffix else ''}",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value * 1e-3:.2f}<br>μs" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value * 1e-3:.3f} μs" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        path = f"{chip_info_dir}/t1{suffix}.png"
        fig.write_image(file=path)
        generated_files.append(path)

    if "t2_echo" in info_type and "t2_echo" in props:
        values = pad_qubit_data(props["t2_echo"], chip_id=chip_id)
        fig = graph.create_lattice_figure(
            title=f"T2 echo (μs){(' (' + suffix.lstrip('_') + ')') if suffix else ''}",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value * 1e-3:.2f}<br>μs" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value * 1e-3:.3f} μs" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        path = f"{chip_info_dir}/t2_echo{suffix}.png"
        fig.write_image(file=path)
        generated_files.append(path)

    if "average_readout_fidelity" in info_type and "average_readout_fidelity" in props:
        values = pad_qubit_data(props["average_readout_fidelity"], chip_id=chip_id)
        fig = graph.create_lattice_figure(
            title=f"Average readout fidelity (%){(' (' + suffix.lstrip('_') + ')') if suffix else ''}",
            values=list(values.values()),
            texts=[f"{qubit}<br>{value:.2%}" if not math.isnan(value) else "N/A" for qubit, value in values.items()],
            hovertexts=[
                f"{qubit}: {value:.2%}" if not math.isnan(value) else f"{qubit}: N/A" for qubit, value in values.items()
            ],
        )
        path = f"{chip_info_dir}/average_readout_fidelity{suffix}.png"
        fig.write_image(file=path)
        generated_files.append(path)

    if "x90_gate_fidelity" in info_type and "x90_gate_fidelity" in props:
        values = pad_qubit_data(props["x90_gate_fidelity"], chip_id=chip_id)
        fig = graph.create_lattice_figure(
            title=f"X90 gate fidelity (%){(' (' + suffix.lstrip('_') + ')') if suffix else ''}",
            values=list(values.values()),
            texts=[f"{qubit}<br>{value:.2%}" if not math.isnan(value) else "N/A" for qubit, value in values.items()],
            hovertexts=[
                f"{qubit}: {value:.2%}" if not math.isnan(value) else f"{qubit}: N/A" for qubit, value in values.items()
            ],
        )
        path = f"{chip_info_dir}/x90_gate_fidelity{suffix}.png"
        fig.write_image(file=path)
        generated_files.append(path)

    if "zx90_gate_fidelity" in info_type and "zx90_gate_fidelity" in props:
        values = props["zx90_gate_fidelity"]
        values = create_undirected_data(
            data=values,
            method="max",
        )
        fig = graph.create_graph_figure(
            directed=False,
            title=f"ZX90 gate fidelity (%){(' (' + suffix.lstrip('_') + ')') if suffix else ''}",
            edge_values={key: value for key, value in values.items()},
            edge_texts={key: f"{value * 1e2:.1f}" if not math.isnan(value) else None for key, value in values.items()},
            edge_hovertexts={
                key: f"{key}: {value:.2%}" if not math.isnan(value) else "N/A" for key, value in values.items()
            },
        )
        path = f"{chip_info_dir}/zx90_gate_fidelity{suffix}.png"
        fig.write_image(file=path)
        generated_files.append(path)

    if "bell_state_fidelity" in info_type and "bell_state_fidelity" in props:
        values = props["bell_state_fidelity"]
        values = create_undirected_data(
            data=values,
            method="max",
        )
        fig = graph.create_graph_figure(
            directed=False,
            title=f"Bell state fidelity (%){(' (' + suffix.lstrip('_') + ')') if suffix else ''}",
            edge_values={key: value for key, value in values.items()},
            edge_texts={key: f"{value * 1e2:.1f}" if not math.isnan(value) else None for key, value in values.items()},
            edge_hovertexts={
                key: f"{key}: {value:.2%}" if not math.isnan(value) else "N/A" for key, value in values.items()
            },
        )
        path = f"{chip_info_dir}/bell_state_fidelity{suffix}.png"
        fig.write_image(file=path)
        generated_files.append(path)

    return generated_files


@task
def generate_chip_info_report(
    chip_info_dir: str = "",
    chip_id: str = "64Qv1",
) -> None:
    """Generate a report for chip information."""
    # Read regular properties
    props_path = f"{chip_info_dir}/props.yaml"
    from prefect import get_run_logger

    logger = get_run_logger()
    props = read_base_properties(filename=props_path)[chip_id]

    # Generate regular figures
    regular_files = generate_figures(props, chip_info_dir, chip_id=chip_id)

    # Read and generate recent properties if available (based on cutoff_hours)
    cutoff_hours = 24  # Default fallback
    for hours in [6, 12, 24, 48, 72]:  # Check for various cutoff files
        props_path_recent = f"{chip_info_dir}/props_{hours}h.yaml"
        if Path(props_path_recent).exists():
            cutoff_hours = hours
            break

    props_path_recent = f"{chip_info_dir}/props_{cutoff_hours}h.yaml"
    if Path(props_path_recent).exists():
        props_all = read_base_properties(filename=props_path_recent)
        props_recent = props_all.get(chip_id)
        if props_recent is not None:
            logger.info(f"Generating {cutoff_hours}hr figures for {chip_id}...")
            logger.info(f"Properties: {props_recent}")
            recent_files = generate_figures(props_recent, chip_info_dir, f"_{cutoff_hours}h", chip_id=chip_id)
            generate_rich_pdf_report(
                regular_files + recent_files,
                pdf_path=f"{chip_info_dir}/chip_info_report.pdf",
            )
        else:
            logger.warning(f"No properties found for chip_id={chip_id}")
            generate_rich_pdf_report(
                regular_files,
                pdf_path=f"{chip_info_dir}/chip_info_report.pdf",
            )
