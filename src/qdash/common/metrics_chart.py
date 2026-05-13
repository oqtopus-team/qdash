"""Standalone chart-generation helpers for chip metrics.

Functions in this module are used by both the PDF report generator
(``metrics_pdf.MetricsPDFGenerator``) and the Copilot heatmap tool.
They have **no dependency** on ReportLab or any PDF-specific logic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import plotly.graph_objects as go

if TYPE_CHECKING:
    from qdash.common.topology_config import TopologyDefinition

# Default sizing constants (PDF-oriented)
NODE_SIZE_DEFAULT = 48
TEXT_SIZE_DEFAULT = 18

# Compact sizing constants (chat UI)
NODE_SIZE_COMPACT = 28
TEXT_SIZE_COMPACT = 10


@dataclass
class ChipGeometry:
    """Grid geometry describing qubit positions on a chip."""

    n_qubits: int
    grid_size: int
    mux_size: int = 2
    qubit_positions: dict[int, tuple[int, int]] = field(default_factory=dict)


def chip_geometry_from_topology(topology: TopologyDefinition) -> ChipGeometry:
    """Build ``ChipGeometry`` from a loaded topology definition."""
    positions = {qid: (pos.row, pos.col) for qid, pos in topology.qubits.items()}
    return ChipGeometry(
        n_qubits=topology.num_qubits,
        grid_size=topology.grid_size,
        mux_size=topology.mux.size if topology.mux.enabled else 2,
        qubit_positions=positions,
    )


def build_chip_geometry(n_qubits: int, grid_size: int, mux_size: int = 2) -> ChipGeometry:
    """Build ``ChipGeometry`` without an explicit topology."""
    return ChipGeometry(n_qubits=n_qubits, grid_size=grid_size, mux_size=mux_size)


def get_qubit_position(geometry: ChipGeometry, qid: int) -> tuple[int, int]:
    """Return ``(row, col)`` for *qid* using explicit positions or MUX calculation."""
    if qid in geometry.qubit_positions:
        return geometry.qubit_positions[qid]

    mux_size = geometry.mux_size
    qubits_per_mux = mux_size * mux_size
    muxes_per_row = geometry.grid_size // mux_size

    mux_index = qid // qubits_per_mux
    mux_row = mux_index // muxes_per_row
    mux_col = mux_index % muxes_per_row

    local_index = qid % qubits_per_mux
    local_row = local_index // mux_size
    local_col = local_index % mux_size

    return mux_row * mux_size + local_row, mux_col * mux_size + local_col


def create_data_matrix(
    geometry: ChipGeometry,
    values: list[Any],
    default: Any = math.nan,
) -> list[list[Any]]:
    """Map a per-qubit value list onto a 2-D grid matrix."""
    matrix = [[default] * geometry.grid_size for _ in range(geometry.grid_size)]
    for qid, value in enumerate(values):
        if qid >= geometry.n_qubits:
            break
        row, col = get_qubit_position(geometry, qid)
        if 0 <= row < geometry.grid_size and 0 <= col < geometry.grid_size:
            matrix[row][col] = value
    return matrix


def _format_qubit_text(
    qid: int,
    scaled_value: float,
    metric_title: str,
    metric_unit: str,
) -> str:
    """Format qubit label text for heatmap cells."""
    label = f"Q{qid:03d}"
    if "fidelity" in metric_title.lower() or "%" in metric_unit:
        return f"{label}<br>{scaled_value:.2f}%"
    if metric_unit in ["GHz", "MHz"]:
        return f"{label}<br>{scaled_value:.3f}<br>{metric_unit}"
    if metric_unit in ["\u00b5s", "ns"]:
        return f"{label}<br>{scaled_value:.2f}<br>{metric_unit}"
    return f"{label}<br>{scaled_value:.3f}<br>{metric_unit}"


def create_qubit_heatmap(
    metric_data: dict[str, Any],
    geometry: ChipGeometry,
    metric_scale: float,
    metric_title: str,
    metric_unit: str,
    *,
    node_size: int = NODE_SIZE_DEFAULT,
    text_size: int = TEXT_SIZE_DEFAULT,
    compact: bool = False,
) -> go.Figure:
    """Create a Plotly heatmap for qubit metrics.

    Parameters
    ----------
    metric_data:
        Mapping ``qid_str -> MetricValue`` (must have ``.value`` attribute).
    geometry:
        Chip grid geometry.
    metric_scale:
        Multiplicative scaling factor for raw values.
    metric_title:
        Display title of the metric (used for text formatting heuristics).
    metric_unit:
        Display unit string.
    node_size / text_size:
        Sizing overrides (ignored when *compact* is ``True``).
    compact:
        If ``True``, use smaller sizing suitable for a chat UI, show a title
        and a colour-bar.
    """
    if compact:
        node_size = NODE_SIZE_COMPACT
        text_size = TEXT_SIZE_COMPACT

    values: list[float] = []
    texts: list[str] = []

    for qid in range(geometry.n_qubits):
        qid_str = str(qid)
        metric_value = metric_data.get(qid_str)

        if metric_value and metric_value.value is not None:
            scaled_value = metric_value.value * metric_scale
            values.append(scaled_value)
            texts.append(_format_qubit_text(qid, scaled_value, metric_title, metric_unit))
        else:
            values.append(math.nan)
            texts.append("N/A")

    value_matrix = create_data_matrix(geometry, values)
    text_matrix = create_data_matrix(geometry, texts, default="N/A")

    fig = go.Figure(
        go.Heatmap(
            z=value_matrix,
            text=text_matrix,
            colorscale="Viridis",
            hoverinfo="text",
            hovertext=text_matrix,
            texttemplate="%{text}",
            showscale=compact,
            textfont={
                "family": "monospace",
                "size": text_size,
                "weight": "bold",
            },
        )
    )

    width = 3 * node_size * geometry.grid_size
    height = 3 * node_size * geometry.grid_size

    layout_kwargs: dict[str, Any] = {
        "showlegend": False,
        "xaxis": {
            "ticks": "",
            "linewidth": 1,
            "showgrid": False,
            "zeroline": False,
            "showticklabels": False,
        },
        "yaxis": {
            "ticks": "",
            "autorange": "reversed",
            "linewidth": 1,
            "showgrid": False,
            "zeroline": False,
            "showticklabels": False,
        },
        "width": width,
        "height": height,
    }

    if compact:
        layout_kwargs["title"] = {"text": metric_title, "font": {"size": 14}}
        layout_kwargs["margin"] = {"b": 30, "l": 20, "r": 60, "t": 40}
    else:
        layout_kwargs["title"] = None
        layout_kwargs["margin"] = {"b": 20, "l": 20, "r": 20, "t": 20}

    fig.update_layout(**layout_kwargs)
    return fig
