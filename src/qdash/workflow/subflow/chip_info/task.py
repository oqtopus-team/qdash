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


def read_base_properties(filename: str = "props.yaml") -> CommentedMap:
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
    c.drawCentredString(
        width / 2, height - 140, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
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
        c.drawImage(
            ImageReader(path), 50, height - img_height - 80, width=img_width, height=img_height
        )

        # ページ番号
        c.setFont("Helvetica", 10)
        c.drawRightString(width - 50, 30, f"Page {i+1}")

        c.showPage()

    c.save()
    print(f"Saved rich report: {pdf_path}")


@task
def generate_chip_info_report(
    chip_info_dir: str = "",
) -> None:
    """Generate a report for chip information."""
    props_path = f"{chip_info_dir}/props.yaml"
    props = read_base_properties(
        filename=props_path,
    )["64Q"]
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
    graph = CustomLatticeGraph(64)
    if "resonator_frequency" in info_type:
        values = props["resonator_frequency"]
        fig = graph.create_lattice_figure(
            title="Resonator frequency (GHz)",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value:.3f}<br>GHz" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value * 1e3:.3f} MHz" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        fig.write_image(file=f"{chip_info_dir}/resonator_frequency.png")

    if "qubit_frequency" in info_type:
        values = props["qubit_frequency"]
        fig = graph.create_lattice_figure(
            title="Qubit frequency (GHz)",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value:.3f}<br>GHz" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value * 1e3:.3f} MHz" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        fig.write_image(file=f"{chip_info_dir}/qubit_frequency.png")

    if "qubit_anharmonicity" in info_type:
        values = props["anharmonicity"]
        fig = graph.create_lattice_figure(
            title="Qubit anharmonicity (MHz)",
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
        fig.write_image(file=f"{chip_info_dir}/qubit_anharmonicity.png")

    if "external_loss_rate" in info_type:
        values = props["external_loss_rate"]
        fig = graph.create_lattice_figure(
            title="External loss rate (MHz)",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value * 1e3:.2f}<br>MHz" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value * 1e3:.3f} MHz" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        fig.write_image(file=f"{chip_info_dir}/external_loss_rate.png")

    if "internal_loss_rate" in info_type:
        values = props["internal_loss_rate"]
        fig = graph.create_lattice_figure(
            title="Internal loss rate (MHz)",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value * 1e3:.2f}<br>MHz" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value * 1e3:.3f} MHz" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        fig.write_image(file=f"{chip_info_dir}/internal_loss_rate.png")

    if "t1" in info_type:
        values = props["t1"]
        fig = graph.create_lattice_figure(
            title="T1 (μs)",
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
        fig.write_image(file=f"{chip_info_dir}/t1.png")

    if "t2_star" in info_type:
        values = props["t2_star"]
        fig = graph.create_lattice_figure(
            title="T2* (μs)",
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
        fig.write_image(file=f"{chip_info_dir}/t2_star.png")

    if "t2_echo" in info_type:
        values = props["t2_echo"]
        fig = graph.create_lattice_figure(
            title="T2 echo (μs)",
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
        fig.write_image(file=f"{chip_info_dir}/t2_echo.png")

    if "average_readout_fidelity" in info_type:
        values = props["average_readout_fidelity"]
        fig = graph.create_lattice_figure(
            title="Average readout fidelity (%)",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value:.2%}" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value:.2%}" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        fig.write_image(file=f"{chip_info_dir}/average_readout_fidelity.png")

    if "average_gate_fidelity" in info_type:
        values = props["average_gate_fidelity"]
        fig = graph.create_lattice_figure(
            title="Average gate fidelity (%)",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value:.2%}" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value:.2%}" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        fig.write_image(file=f"{chip_info_dir}/average_gate_fidelity.png")

    if "x90_gate_fidelity" in info_type:
        values = props["x90_gate_fidelity"]
        fig = graph.create_lattice_figure(
            title="X90 gate fidelity (%)",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value:.2%}" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value:.2%}" if not math.isnan(value) else f"{qubit}: N/A"
                for qubit, value in values.items()
            ],
        )
        fig.write_image(file=f"{chip_info_dir}/x90_gate_fidelity.png")

    if "x180_gate_fidelity" in info_type:
        values = props["x180_gate_fidelity"]
        fig = graph.create_lattice_figure(
            title="X180 gate fidelity (%)",
            values=list(values.values()),
            texts=[
                f"{qubit}<br>{value:.2%}" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
            hovertexts=[
                f"{qubit}: {value:.2%}" if not math.isnan(value) else "N/A"
                for qubit, value in values.items()
            ],
        )
        fig.write_image(file=f"{chip_info_dir}/x180_gate_fidelity.png")

    def create_undirected_data(
        data: dict[str, float],
        method: Literal["avg", "max", "min"],
    ) -> dict[str, float]:
        result = {}
        for key, value in data.items():
            if value is None or math.isnan(value):
                continue
            pair = key.split("-")
            inv_key = f"{pair[1]}-{pair[0]}"
            if (
                inv_key in result
                and result[inv_key] is not None
                and not math.isnan(result[inv_key])
            ):
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

    if "zx90_gate_fidelity" in info_type:
        values = props["zx90_gate_fidelity"]
        values = create_undirected_data(
            data=values,
            method="max",
        )
        fig = graph.create_graph_figure(
            directed=False,
            title="ZX90 gate fidelity (%)",
            edge_values={key: value for key, value in values.items()},
            edge_texts={
                key: f"{value * 1e2:.1f}" if not math.isnan(value) else None
                for key, value in values.items()
            },
            edge_hovertexts={
                key: f"{key}: {value:.2%}" if not math.isnan(value) else "N/A"
                for key, value in values.items()
            },
        )
        fig.write_image(file=f"{chip_info_dir}/zx90_gate_fidelity.png")
    if "bell_state_fidelity" in info_type:
        values = props["bell_state_fidelity"]
        values = create_undirected_data(
            data=values,
            method="max",
        )
        fig = graph.create_graph_figure(
            directed=False,
            title="Bell state fidelity (%)",
            edge_values={key: value for key, value in values.items()},
            edge_texts={
                key: f"{value * 1e2:.1f}" if not math.isnan(value) else None
                for key, value in values.items()
            },
            edge_hovertexts={
                key: f"{key}: {value:.2%}" if not math.isnan(value) else "N/A"
                for key, value in values.items()
            },
        )
        fig.write_image(file=f"{chip_info_dir}/bell_state_fidelity.png")

    generate_rich_pdf_report(
        [
            f"{chip_info_dir}/qubit_frequency.png",
            f"{chip_info_dir}/qubit_anharmonicity.png",
            f"{chip_info_dir}/t1.png",
            f"{chip_info_dir}/t2_echo.png",
            f"{chip_info_dir}/average_readout_fidelity.png",
            f"{chip_info_dir}/x90_gate_fidelity.png",
            f"{chip_info_dir}/zx90_gate_fidelity.png",
            f"{chip_info_dir}/bell_state_fidelity.png",
        ],
        pdf_path=f"{chip_info_dir}/chip_info_report.pdf",
    )
