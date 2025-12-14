"""Metrics PDF report generator using Plotly.

This module generates PDF reports for chip metrics data using Plotly and ReportLab,
following the same design pattern as the existing chip report.
"""

from __future__ import annotations

import io
import logging
import math
from datetime import datetime
from typing import Any, Literal

import numpy as np
import plotly.graph_objects as go
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from qdash.api.lib.metrics_config import load_metrics_config
from qdash.api.lib.topology_config import TopologyDefinition, load_topology
from qdash.api.schemas.metrics import ChipMetricsResponse

logger = logging.getLogger(__name__)

# Figure sizing constants - larger for better visibility
NODE_SIZE = 48  # Doubled for larger figures
TEXT_SIZE = 18  # Large text for readability in cells


class MetricsPDFGenerator:
    """Generate PDF reports for chip metrics using Plotly."""

    def __init__(
        self,
        metrics_response: ChipMetricsResponse,
        within_hours: int | None = None,
        selection_mode: Literal["latest", "best"] = "latest",
        topology_id: str | None = None,
    ):
        """Initialize the PDF generator.

        Args:
            metrics_response: The chip metrics data to include in the report
            within_hours: Time range filter applied to the data
            selection_mode: Selection mode used ("latest" or "best")
            topology_id: Optional topology ID for MUX-based layout
        """
        self.metrics_response = metrics_response
        self.within_hours = within_hours
        self.selection_mode = selection_mode
        self.config = load_metrics_config()
        self.width, self.height = A4

        # Load topology if provided
        self.topology: TopologyDefinition | None = None
        if topology_id:
            try:
                self.topology = load_topology(topology_id)
            except Exception as e:
                logger.warning(f"Failed to load topology {topology_id}: {e}")

        # Calculate grid dimensions
        self.n_qubits = metrics_response.qubit_count
        self.grid_size = self.topology.grid_size if self.topology else int(math.sqrt(self.n_qubits))
        self.mux_size = self.topology.mux.size if self.topology and self.topology.mux.enabled else 2

    def generate_pdf(self) -> io.BytesIO:
        """Generate the complete PDF report.

        Returns:
            BytesIO buffer containing the PDF data
        """
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)

        # Cover page
        self._draw_cover_page(c)
        c.showPage()

        page_num = 1

        # Qubit metrics pages
        qubit_metrics = self.metrics_response.qubit_metrics
        for metric_key, metric_meta in self.config.qubit_metrics.items():
            schema_key = self._map_config_to_schema_key(metric_key, "qubit")
            metric_data = getattr(qubit_metrics, schema_key, None)
            if metric_data:
                self._draw_metric_page(
                    c,
                    metric_key=metric_key,
                    metric_title=metric_meta.title,
                    metric_unit=metric_meta.unit,
                    metric_scale=metric_meta.scale,
                    metric_data=metric_data,
                    metric_type="qubit",
                    page_num=page_num,
                )
                c.showPage()
                page_num += 1

        # Coupling metrics pages
        coupling_metrics = self.metrics_response.coupling_metrics
        for metric_key, metric_meta in self.config.coupling_metrics.items():
            metric_data = getattr(coupling_metrics, metric_key, None)
            if metric_data:
                self._draw_metric_page(
                    c,
                    metric_key=metric_key,
                    metric_title=metric_meta.title,
                    metric_unit=metric_meta.unit,
                    metric_scale=metric_meta.scale,
                    metric_data=metric_data,
                    metric_type="coupling",
                    page_num=page_num,
                )
                c.showPage()
                page_num += 1

        c.save()
        buffer.seek(0)
        return buffer

    def _map_config_to_schema_key(self, config_key: str, metric_type: str) -> str:
        """Map configuration key to schema attribute key."""
        qubit_mapping = {
            "bare_frequency": "qubit_frequency",
        }

        if metric_type == "qubit" and config_key in qubit_mapping:
            return qubit_mapping[config_key]
        return config_key

    def _draw_cover_page(self, c: canvas.Canvas) -> None:
        """Draw the cover page of the report."""
        # Background header bar
        c.setFillColor(colors.Color(0.2, 0.3, 0.5))
        c.rect(0, self.height - 180, self.width, 180, fill=1, stroke=0)

        # Title
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 32)
        c.drawCentredString(self.width / 2, self.height - 80, "QDash Metrics Report")

        # Subtitle
        c.setFont("Helvetica", 14)
        c.drawCentredString(self.width / 2, self.height - 110, "Calibration Metrics Summary")

        # Generation info
        c.setFont("Helvetica", 11)
        c.drawCentredString(
            self.width / 2,
            self.height - 150,
            f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        )

        # Info box
        box_top = self.height - 240
        box_left = 60
        box_width = self.width - 120
        box_height = 200

        # Box shadow effect
        c.setFillColor(colors.Color(0.9, 0.9, 0.9))
        c.roundRect(box_left + 3, box_top - box_height - 3, box_width, box_height, 10, fill=1, stroke=0)

        # Box background
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.Color(0.8, 0.8, 0.8))
        c.setLineWidth(1)
        c.roundRect(box_left, box_top - box_height, box_width, box_height, 10, fill=1, stroke=1)

        # Box title
        c.setFillColor(colors.Color(0.2, 0.3, 0.5))
        c.setFont("Helvetica-Bold", 14)
        c.drawString(box_left + 20, box_top - 30, "Report Parameters")

        # Divider line
        c.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
        c.line(box_left + 20, box_top - 45, box_left + box_width - 20, box_top - 45)

        # Info content
        topology_name = self.topology.name if self.topology else "Default Grid"
        time_range = f"Last {self.within_hours} hours" if self.within_hours else "All time"

        info_items = [
            ("Chip ID", self.metrics_response.chip_id),
            ("Username", self.metrics_response.username),
            ("Qubit Count", str(self.metrics_response.qubit_count)),
            ("Grid Size", f"{self.grid_size} x {self.grid_size}"),
            ("Topology", topology_name),
            ("Time Range", time_range),
            ("Selection Mode", self.selection_mode.capitalize()),
        ]

        # Draw info in two columns
        y_pos = box_top - 70
        col1_x = box_left + 30
        col2_x = box_left + box_width / 2 + 10

        for i, (label, value) in enumerate(info_items):
            x_pos = col1_x if i % 2 == 0 else col2_x
            if i % 2 == 0 and i > 0:
                y_pos -= 28

            # Label
            c.setFillColor(colors.Color(0.5, 0.5, 0.5))
            c.setFont("Helvetica", 10)
            c.drawString(x_pos, y_pos, label)

            # Value
            c.setFillColor(colors.Color(0.1, 0.1, 0.1))
            c.setFont("Helvetica-Bold", 12)
            c.drawString(x_pos, y_pos - 14, value)

        # Footer
        c.setFillColor(colors.Color(0.6, 0.6, 0.6))
        c.setFont("Helvetica", 10)
        c.drawCentredString(self.width / 2, 50, "Generated by QDash - Quantum Device Calibration Dashboard")

    def _draw_metric_page(
        self,
        c: canvas.Canvas,
        metric_key: str,
        metric_title: str,
        metric_unit: str,
        metric_scale: float,
        metric_data: dict[str, Any],
        metric_type: Literal["qubit", "coupling"],
        page_num: int,
    ) -> None:
        """Draw a single metric page with Plotly figure."""
        # Header bar
        header_height = 50
        c.setFillColor(colors.Color(0.2, 0.3, 0.5))
        c.rect(0, self.height - header_height, self.width, header_height, fill=1, stroke=0)

        # Section title in header
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, self.height - 33, metric_title)

        # Unit badge
        c.setFillColor(colors.Color(0.3, 0.4, 0.6))
        unit_text = f"Unit: {metric_unit}"
        unit_width = c.stringWidth(unit_text, "Helvetica", 10) + 16
        c.roundRect(self.width - unit_width - 50, self.height - 40, unit_width, 22, 5, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 10)
        c.drawString(self.width - unit_width - 42, self.height - 33, unit_text)

        # Calculate statistics
        stats = self._calculate_statistics(metric_data, metric_scale, metric_type)

        # Generate Plotly figure
        if metric_type == "qubit":
            fig = self._create_qubit_heatmap(
                metric_data=metric_data,
                metric_scale=metric_scale,
                metric_title=metric_title,
                metric_unit=metric_unit,
            )
        else:
            fig = self._create_coupling_graph(
                metric_data=metric_data,
                metric_scale=metric_scale,
                metric_title=metric_title,
                metric_unit=metric_unit,
            )

        if fig:
            # Convert Plotly figure to image
            img_buffer = io.BytesIO()
            fig.write_image(img_buffer, format="png", scale=2)
            img_buffer.seek(0)

            # Get image dimensions
            img = Image.open(img_buffer)
            aspect = img.height / img.width
            img_width = self.width - 80
            img_height = img_width * aspect

            # Ensure image fits on page with room for header and stats
            max_img_height = self.height - 180  # Leave room for header and stats
            if img_height > max_img_height:
                img_height = max_img_height
                img_width = img_height / aspect

            # Center the image horizontally
            img_x = (self.width - img_width) / 2

            # Draw image
            img_buffer.seek(0)
            c.drawImage(
                ImageReader(img_buffer),
                img_x,
                self.height - img_height - header_height - 20,
                width=img_width,
                height=img_height,
            )

        # Draw statistics box at bottom
        self._draw_statistics_box(c, stats, metric_unit, y_pos=50)

        # Footer with page number and chip info
        c.setFillColor(colors.Color(0.6, 0.6, 0.6))
        c.setFont("Helvetica", 9)
        c.drawString(50, 25, f"Chip: {self.metrics_response.chip_id}")
        c.drawCentredString(self.width / 2, 25, datetime.now().strftime("%Y-%m-%d"))
        c.drawRightString(self.width - 50, 25, f"Page {page_num}")

    def _calculate_statistics(
        self,
        metric_data: dict[str, Any],
        metric_scale: float,
        metric_type: Literal["qubit", "coupling"],
    ) -> dict[str, Any]:
        """Calculate statistics for the metric values."""
        values = []
        for key, metric_value in metric_data.items():
            if metric_value and metric_value.value is not None:
                scaled_value = metric_value.value * metric_scale
                values.append(scaled_value)

        # Calculate correct total count based on metric type
        if metric_type == "qubit":
            total_count = self.n_qubits
        else:
            # For coupling metrics, count expected couplings from topology or use data keys
            if self.topology and self.topology.couplings:
                total_count = len(self.topology.couplings)
            else:
                # Fallback: count unique coupling pairs in the data
                total_count = len(metric_data)

        data_count = len(values)

        if not values:
            return {
                "coverage": 0.0,
                "coverage_count": 0,
                "total_count": total_count,
                "average": None,
                "median": None,
                "minimum": None,
                "maximum": None,
            }

        return {
            "coverage": (data_count / total_count * 100) if total_count > 0 else 0.0,
            "coverage_count": data_count,
            "total_count": total_count,
            "average": float(np.mean(values)),
            "median": float(np.median(values)),
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
        }

    def _draw_statistics_box(
        self, c: canvas.Canvas, stats: dict[str, Any], unit: str, y_pos: float
    ) -> None:
        """Draw statistics as a styled horizontal bar at the bottom of the page."""
        bar_height = 35
        box_left = 40
        box_width = self.width - 80

        # Draw background with rounded corners
        c.setFillColor(colors.Color(0.96, 0.97, 0.98))
        c.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
        c.setLineWidth(0.5)
        c.roundRect(box_left, y_pos, box_width, bar_height, 5, fill=1, stroke=1)

        # Statistics items with icons/labels
        stat_items = [
            ("Coverage", f"{stats['coverage']:.1f}%", f"({stats['coverage_count']}/{stats['total_count']})"),
            ("Median", self._format_stat_value(stats['median']), ""),
            ("Average", self._format_stat_value(stats['average']), ""),
            ("Min", self._format_stat_value(stats['minimum']), ""),
            ("Max", self._format_stat_value(stats['maximum']), ""),
        ]

        # Calculate spacing
        item_width = box_width / len(stat_items)
        x_pos = box_left + item_width / 2

        for label, value, extra in stat_items:
            # Draw vertical separator (except for first item)
            if x_pos > box_left + item_width / 2 + 5:
                c.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
                c.line(x_pos - item_width / 2, y_pos + 5, x_pos - item_width / 2, y_pos + bar_height - 5)

            # Label
            c.setFillColor(colors.Color(0.5, 0.5, 0.5))
            c.setFont("Helvetica", 8)
            label_width = c.stringWidth(label, "Helvetica", 8)
            c.drawString(x_pos - label_width / 2, y_pos + 22, label)

            # Value
            c.setFillColor(colors.Color(0.2, 0.3, 0.5))
            c.setFont("Helvetica-Bold", 10)
            value_text = f"{value} {extra}".strip()
            value_width = c.stringWidth(value_text, "Helvetica-Bold", 10)
            c.drawString(x_pos - value_width / 2, y_pos + 8, value_text)

            x_pos += item_width

    def _format_stat_value(self, value: float | None) -> str:
        """Format a statistic value for display."""
        if value is None:
            return "N/A"
        if abs(value) >= 100:
            return f"{value:.2f}"
        elif abs(value) >= 10:
            return f"{value:.3f}"
        elif abs(value) >= 1:
            return f"{value:.4f}"
        else:
            return f"{value:.5f}"

    def _get_qubit_position(self, qid: int) -> tuple[int, int]:
        """Get the grid position (row, col) for a qubit ID using MUX-based layout."""
        if self.topology and self.topology.qubits:
            pos = self.topology.qubits.get(qid)
            if pos:
                return pos.row, pos.col

        # MUX-based calculation
        mux_size = self.mux_size
        qubits_per_mux = mux_size * mux_size
        muxes_per_row = self.grid_size // mux_size

        mux_index = qid // qubits_per_mux
        mux_row = mux_index // muxes_per_row
        mux_col = mux_index % muxes_per_row

        local_index = qid % qubits_per_mux
        local_row = local_index // mux_size
        local_col = local_index % mux_size

        return mux_row * mux_size + local_row, mux_col * mux_size + local_col

    def _create_data_matrix(
        self, values: list[Any], default: Any = math.nan
    ) -> list[list[Any]]:
        """Create a 2D matrix from a list of values using MUX-based positioning."""
        matrix = [[default] * self.grid_size for _ in range(self.grid_size)]

        for qid, value in enumerate(values):
            if qid >= self.n_qubits:
                break
            row, col = self._get_qubit_position(qid)
            if 0 <= row < self.grid_size and 0 <= col < self.grid_size:
                matrix[row][col] = value

        return matrix

    def _create_qubit_heatmap(
        self,
        metric_data: dict[str, Any],
        metric_scale: float,
        metric_title: str,
        metric_unit: str,
    ) -> go.Figure:
        """Create a Plotly heatmap for qubit metrics."""
        # Build values and texts lists
        values = []
        texts = []

        for qid in range(self.n_qubits):
            qid_str = str(qid)
            metric_value = metric_data.get(qid_str)

            if metric_value and metric_value.value is not None:
                scaled_value = metric_value.value * metric_scale
                values.append(scaled_value)

                # Format text based on metric type
                if "fidelity" in metric_title.lower() or "%" in metric_unit:
                    text = f"Q{qid:03d}<br>{scaled_value:.2f}%"
                elif metric_unit in ["GHz", "MHz"]:
                    text = f"Q{qid:03d}<br>{scaled_value:.3f}<br>{metric_unit}"
                elif metric_unit in ["μs", "ns"]:
                    text = f"Q{qid:03d}<br>{scaled_value:.2f}<br>{metric_unit}"
                else:
                    text = f"Q{qid:03d}<br>{scaled_value:.3f}<br>{metric_unit}"
                texts.append(text)
            else:
                values.append(math.nan)
                texts.append("N/A")

        # Create matrices
        value_matrix = self._create_data_matrix(values)
        text_matrix = self._create_data_matrix(texts, default="N/A")

        # Create heatmap figure
        fig = go.Figure(
            go.Heatmap(
                z=value_matrix,
                text=text_matrix,
                colorscale="Viridis",
                hoverinfo="text",
                hovertext=text_matrix,
                texttemplate="%{text}",
                showscale=False,
                textfont=dict(
                    family="monospace",
                    size=TEXT_SIZE,
                    weight="bold",
                ),
            )
        )

        # Calculate figure size
        width = 3 * NODE_SIZE * self.grid_size
        height = 3 * NODE_SIZE * self.grid_size

        fig.update_layout(
            title=None,  # Title is in PDF header
            showlegend=False,
            margin=dict(b=20, l=20, r=20, t=20),
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

    def _create_coupling_graph(
        self,
        metric_data: dict[str, Any],
        metric_scale: float,
        metric_title: str,
        metric_unit: str,
    ) -> go.Figure:
        """Create a Plotly graph figure for coupling metrics."""
        # Calculate figure size
        width = 3 * NODE_SIZE * self.grid_size
        height = 3 * NODE_SIZE * self.grid_size

        layout = go.Layout(
            title=None,  # Title is in PDF header
            width=width,
            height=height,
            margin=dict(b=20, l=20, r=20, t=20),
            xaxis=dict(
                ticks="",
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                constrain="domain",
            ),
            yaxis=dict(
                ticks="",
                autorange="reversed",
                showgrid=False,
                zeroline=False,
                showticklabels=False,
            ),
            plot_bgcolor="white",
            showlegend=False,
            hovermode="closest",
        )

        data = []

        # Add MUX boundary rectangles
        mux_trace = self._create_mux_node_trace()
        data.append(mux_trace)

        # Add edge traces for couplings
        edge_traces = self._create_coupling_edge_traces(
            metric_data=metric_data,
            metric_scale=metric_scale,
        )
        data.extend(edge_traces)

        # Add node traces for qubits
        node_traces = self._create_qubit_node_traces()
        data.extend(node_traces)

        fig = go.Figure(data=data, layout=layout)
        return fig

    def _create_mux_node_trace(self) -> go.Scatter:
        """Create trace for MUX boundary rectangles."""
        shapes_x = []
        shapes_y = []

        mux_size = self.mux_size
        muxes_per_row = self.grid_size // mux_size

        for mux_row in range(muxes_per_row):
            for mux_col in range(muxes_per_row):
                # Rectangle corners
                x0 = mux_col * mux_size - 0.5
                y0 = mux_row * mux_size - 0.5
                x1 = (mux_col + 1) * mux_size - 0.5
                y1 = (mux_row + 1) * mux_size - 0.5

                # Draw rectangle as line path
                shapes_x.extend([x0, x1, x1, x0, x0, None])
                shapes_y.extend([y0, y0, y1, y1, y0, None])

        return go.Scatter(
            x=shapes_x,
            y=shapes_y,
            mode="lines",
            line=dict(color="lightgray", width=2),
            hoverinfo="skip",
        )

    def _create_qubit_node_traces(self) -> list[go.Scatter]:
        """Create traces for qubit nodes."""
        x_coords = []
        y_coords = []
        texts = []

        for qid in range(self.n_qubits):
            row, col = self._get_qubit_position(qid)
            x_coords.append(col)
            y_coords.append(row)
            texts.append(str(qid))

        node_trace = go.Scatter(
            x=x_coords,
            y=y_coords,
            mode="markers+text",
            marker=dict(
                size=NODE_SIZE * 1.2,
                color="lightblue",
                line=dict(color="darkblue", width=2),
            ),
            text=texts,
            textposition="middle center",
            textfont=dict(size=12, color="black", weight="bold"),
            hoverinfo="text",
            hovertext=[f"Q{qid}" for qid in range(self.n_qubits)],
        )

        return [node_trace]

    def _create_coupling_edge_traces(
        self,
        metric_data: dict[str, Any],
        metric_scale: float,
    ) -> list[go.Scatter]:
        """Create traces for coupling edges with values."""
        traces = []

        # Collect coupling values and combine bidirectional
        coupling_values: dict[tuple[int, int], float] = {}
        for key, metric_value in metric_data.items():
            if metric_value and metric_value.value is not None:
                try:
                    parts = key.split("-")
                    qid1, qid2 = int(parts[0]), int(parts[1])
                    # Use smaller qid first for consistent key
                    pair_key = (min(qid1, qid2), max(qid1, qid2))
                    scaled_value = metric_value.value * metric_scale

                    if pair_key in coupling_values:
                        # Average with existing value
                        coupling_values[pair_key] = (coupling_values[pair_key] + scaled_value) / 2
                    else:
                        coupling_values[pair_key] = scaled_value
                except (ValueError, IndexError):
                    continue

        if not coupling_values:
            return traces

        # Normalize values for coloring
        min_val = min(coupling_values.values())
        max_val = max(coupling_values.values())
        val_range = max_val - min_val if max_val != min_val else 1

        # Create edge lines and text annotations
        for (qid1, qid2), value in coupling_values.items():
            row1, col1 = self._get_qubit_position(qid1)
            row2, col2 = self._get_qubit_position(qid2)

            # Normalize value for color
            normalized = (value - min_val) / val_range

            # Get color from viridis-like scale
            color = self._get_viridis_color(normalized)

            # Line trace
            line_trace = go.Scatter(
                x=[col1, col2],
                y=[row1, row2],
                mode="lines",
                line=dict(color=color, width=3),
                hoverinfo="skip",
            )
            traces.append(line_trace)

            # Text at midpoint
            mid_x = (col1 + col2) / 2
            mid_y = (row1 + row2) / 2

            text_trace = go.Scatter(
                x=[mid_x],
                y=[mid_y],
                mode="text",
                text=[f"{value:.1f}"],
                textfont=dict(size=11, color="black", weight="bold"),
                hoverinfo="text",
                hovertext=[f"{qid1}-{qid2}: {value:.2f}%"],
            )
            traces.append(text_trace)

        return traces

    def _get_viridis_color(self, normalized: float) -> str:
        """Get a color from viridis-like colorscale."""
        # Simplified viridis colors (dark purple -> blue -> green -> yellow)
        colors = [
            (68, 1, 84),     # Dark purple
            (59, 82, 139),   # Blue
            (33, 145, 140),  # Teal
            (94, 201, 98),   # Green
            (253, 231, 37),  # Yellow
        ]

        # Interpolate
        idx = normalized * (len(colors) - 1)
        lower_idx = int(idx)
        upper_idx = min(lower_idx + 1, len(colors) - 1)
        frac = idx - lower_idx

        r = int(colors[lower_idx][0] * (1 - frac) + colors[upper_idx][0] * frac)
        g = int(colors[lower_idx][1] * (1 - frac) + colors[upper_idx][1] * frac)
        b = int(colors[lower_idx][2] * (1 - frac) + colors[upper_idx][2] * frac)

        return f"rgb({r},{g},{b})"
