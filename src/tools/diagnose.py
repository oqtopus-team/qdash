import math
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

import plotly.graph_objects as go
from PIL import Image
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


def _write_figure(
    fig: go.Figure,
    file_format: Literal["png", "svg", "jpeg", "webp"] = "png",
    width: int = 600,
    height: int = 300,
    scale: int = 3,
    name: str = "",
    savepath: str = "",
) -> None:
    """Save the figure.

    Args:
    ----
        savepath (str): The path to save the figure.
        fig (go.Figure): The figure to save.
        file_format (str, optional): The format of the file. Defaults to "png".
        width (int, optional): The width of the figure. Defaults to 600.
        height (int, optional): The height of the figure. Defaults to 300.
        scale (int, optional): The scale of the figure. Defaults to 3.
        name (str, optional): The name of the figure. Defaults to "".

    """
    fig.write_image(
        savepath,
        format=file_format,
        width=width,
        height=height,
        scale=scale,
    )


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


if __name__ == "__main__":
    props = read_base_properties(filename="/workspace/config/qubex/64Q/config/props.yaml")["64Q"]
    info_type = (
        "qubit_frequency",
        "qubit_anharmonicity",
        "t1",
        "t2_echo",
        "average_readout_fidelity",
        "x90_gate_fidelity",
        "zx90_gate_fidelity",
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
        fig.write_image(file="resonator_frequency.png")

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
        fig.write_image(file="qubit_frequency.png")

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
        fig.write_image(file="external_loss_rate.png")

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
        fig.write_image(file="internal_loss_rate.png")

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
        fig.write_image(file="t1.png")

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
        fig.write_image(file="t2_star.png")

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
        fig.write_image(file="t2_echo.png")
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
        fig.write_image(file="average_readout_fidelity.png")

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
        fig.write_image(file="average_gate_fidelity.png")

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
        fig.write_image(file="x90_gate_fidelity.png")

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
        fig.write_image(file="x180_gate_fidelity.png")

    generate_rich_pdf_report(
        [
            "resonator_frequency.png",
            "qubit_frequency.png",
            "qubit_anharmonicity.png",
            "external_loss_rate.png",
            "internal_loss_rate.png",
            "t1.png",
            "t2_star.png",
            "t2_echo.png",
            "average_readout_fidelity.png",
            "average_gate_fidelity.png",
            "x90_gate_fidelity.png",
            "x180_gate_fidelity.png",
        ]
    )
